from pathlib import Path
import json, math
import pandas as pd
from datetime import datetime, timezone
from .config import DATA
from typing import Literal
from fastapi import FastAPI,Query,HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .daily import load_daily, advice, learning_counts, RESERVE, START, END, learning_policy
from .telemetry import latest

class AdviceRequest(BaseModel):
    battery_pct: float | None = Field(default=None,ge=0,le=100)
    device_id: str | None = None
    historical_device_id: str | None = None
    location: str | None = None
    weather_source: Literal['demo','live'] = 'demo'
    scenario: Literal['mixed','sunny','cloudy'] = 'mixed'
    prediction_hour: int = Field(default=8,ge=6,le=13)
    model_source: Literal['synthetic_demo','team_mock','measured'] = 'synthetic_demo'
from .config import load_settings
from .models import load
from .service import forecast

def historical_battery(device_id, path=None):
    path = path or DATA / 'ttn_historical.json'
    try:
        rows = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError('No readable historical file; download TTN storage data into data/ttn_historical.json first.') from exc
    if not isinstance(rows, list): raise ValueError('Expected a list of historical readings')
    valid = []
    for row in rows:
        try:
            if row['device_id'] != device_id or isinstance(row['battery_pct'], bool): continue
            battery = float(row['battery_pct'])
            ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            if not math.isfinite(battery) or not 0 <= battery <= 100 or ts.tzinfo is None or ts > datetime.now(timezone.utc): continue
            valid.append((ts, {'device_id': device_id, 'battery_pct': battery, 'timestamp': row['timestamp'], 'source': 'TTN historical storage (local saved file)', 'historical': True}))
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError): continue
    if not valid: raise ValueError('No valid historical battery reading for this device')
    return max(valid, key=lambda item: item[0])[1]

def create_app(cfg=None, model_source='synthetic_demo', bundle=None):
    cfg=cfg or load_settings();bundle=bundle or load(cfg,model_source)
    app=FastAPI(title='PPS Smart Energy Assistant',version='3.2.0',description='Prototype scenario forecasting; not a battery controller.')
    @app.get('/',response_class=HTMLResponse,include_in_schema=False)
    def home(): return Path(__file__).with_name('daily_dashboard.html').read_text(encoding='utf-8')
    @app.get('/energy',response_class=HTMLResponse,include_in_schema=False)
    def energy_page(): return Path(__file__).with_name('daily_dashboard.html').read_text(encoding='utf-8')
    @app.get('/research',response_class=HTMLResponse,include_in_schema=False)
    def research_page(): return Path(__file__).with_name('dashboard.html').read_text(encoding='utf-8')
    @app.get('/api/health')
    def health(): return {'status':'ok','model_source':bundle['source'],'location':cfg.location}
    @app.get('/api/metrics')
    def metrics(): return bundle['report']
    @app.get('/api/config')
    def configuration(): return {'location':cfg.location,'battery_capacity_wh':cfg.battery_capacity_wh,'panel_rated_w':cfg.panel_rated_w,'timezone':cfg.timezone,'reserve_pct':cfg.reserve_pct,'profile':'legacy_research','warning':'Original research assumptions; use /advice for the team suitcase.'}
    @app.get('/api/forecast')
    def predict(battery_pct:float=Query(65,ge=0,le=100),active_minutes:float=Query(45,ge=0,le=60),hours:int=Query(36,ge=1,le=48),weather_source:Literal['demo','live']='demo',scenario:Literal['mixed','sunny','cloudy']='mixed'):
        try: return forecast(cfg,bundle,battery_pct,active_minutes,hours,weather_source,scenario)
        except ValueError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    @app.get('/daily',response_class=HTMLResponse,include_in_schema=False)
    def daily_page(): return Path(__file__).with_name('daily_dashboard.html').read_text(encoding='utf-8')
    @app.get('/api/daily/config')
    def daily_config():
        return {'location':cfg.location,'timezone':cfg.timezone,**learning_policy()}
    @app.get('/api/daily/models')
    def available_models():
        result = {}
        for source in ('synthetic_demo','team_mock','measured'):
            try:
                load_daily(source)
                result[source] = {'available': True}
            except (ValueError, OSError, ImportError) as exc:
                result[source] = {'available': False, 'reason': str(exc)}
        return result
    @app.get('/api/daily/metrics')
    def daily_metrics(source:Literal['synthetic_demo','team_mock','measured']='synthetic_demo'):
        try: return load_daily(source)['report']
        except ValueError as exc: raise HTTPException(503,str(exc)) from exc
    @app.get('/api/daily/reliability')
    def daily_reliability(prediction_hour:int=Query(8,ge=6,le=13),source:Literal['synthetic_demo','team_mock','measured']='synthetic_demo'):
        try:
            report=load_daily(source)['report']; q=report['reliability_by_hour'].get(str(prediction_hour))
            if q is None: raise ValueError('No held-out test observations for this hour')
            return {'source':source,'model':report['selected'],'prediction_hour':prediction_hour,'field_validated':False,'scope':report['scope'],'learning_policy':report['learning_policy'],**q}
        except ValueError as exc: raise HTTPException(503,str(exc)) from exc
    @app.post('/advice')
    def daily_advice(req:AdviceRequest):
        try:
            if req.location is not None and req.location.casefold() not in (cfg.location.casefold(), 'pretoria' if 'pretoria' in cfg.location.casefold() else cfg.location.casefold()): raise ValueError('Model is configured for '+cfg.location+'; train for another location before using it.')
            battery=req.battery_pct; provenance='manual scenario input'; measurement=None; replay_time=None; hour=req.prediction_hour
            if req.historical_device_id:
                if battery is not None or req.device_id: raise ValueError('Choose exactly one battery source')
                if req.weather_source != 'demo': raise ValueError('Stored readings require a generated weather scenario; not current advice')
                measurement=historical_battery(req.historical_device_id); battery=measurement['battery_pct']; provenance='HISTORICAL TTN reading — demonstration only; measurement '+measurement['timestamp']
                replay_time=pd.Timestamp(measurement['timestamp']); local=replay_time.tz_convert(cfg.timezone); rounded=local.ceil('h'); hour=rounded.hour
                if not 6<=hour<=13 or rounded.date()!=local.date(): raise ValueError('Stored reading is outside the supported morning forecast window. Battery-based capacity is still available; use a manual scenario for a hypothetical morning.')
            elif battery is None:
                if not req.device_id: raise ValueError('Provide battery_pct or device_id')
                if req.weather_source!='live': raise ValueError('Use live weather with a current TTN measurement; demo requires manual input')
                measurement=latest(req.device_id); battery=measurement['battery_pct']; provenance='TTN decoded battery measurement'
                if measurement['device_state'] and measurement['device_state'].lower() in ('learning','in_use','active'):
                    raise ValueError('Device currently in use; charging-only forecast is not applicable')
            elif req.device_id: raise ValueError('Provide battery_pct or device_id, not both')
            result=advice(cfg,load_daily(req.model_source),battery,req.weather_source,req.scenario,hour,now=replay_time,battery_source=provenance)
            result['measurement']=measurement
            if req.historical_device_id: result['measurement_time_local']=local.isoformat()
            if req.historical_device_id:
                result['reason']='Stored battery and generated weather scenario, using the original measurement time rounded up; demonstration only. '+result['reason']
            return result
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    @app.get('/api/battery/historical')
    def battery_historical(device_id:str):
        try: return historical_battery(device_id)
        except ValueError as exc: raise HTTPException(404,str(exc)) from exc
    @app.get('/api/battery/latest')
    def battery_latest(device_id:str):
        try: return latest(device_id)
        except ValueError as exc: raise HTTPException(404,str(exc)) from exc
    @app.get('/api/lessons/actual')
    def actual_lessons(battery_pct:float=Query(...,ge=0,le=100)):
        return {'battery_pct':battery_pct,'reserve_pct':RESERVE,**learning_counts(battery_pct),'reason':'Recheck using actual battery before the first session; maximum 8 sessions / 32 lessons. Constant lesson drain assumption, not battery protection.'}
    return app
