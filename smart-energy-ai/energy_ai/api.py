from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Query,HTTPException
from fastapi.responses import HTMLResponse
from .config import load_settings
from .models import load
from .service import forecast

def create_app(cfg=None, model_source='synthetic_demo', bundle=None):
    cfg=cfg or load_settings();bundle=bundle or load(cfg,model_source)
    app=FastAPI(title='PPS Smart Energy Assistant',version='1.0.0',description='Prototype scenario forecasting; not a battery controller.')
    @app.get('/',response_class=HTMLResponse,include_in_schema=False)
    def home(): return Path(__file__).with_name('dashboard.html').read_text(encoding='utf-8')
    @app.get('/api/health')
    def health(): return {'status':'ok','model_source':bundle['source'],'location':cfg.location}
    @app.get('/api/metrics')
    def metrics(): return bundle['report']
    @app.get('/api/config')
    def configuration(): return {'location':cfg.location,'battery_capacity_wh':cfg.battery_capacity_wh,'panel_rated_w':cfg.panel_rated_w,'timezone':cfg.timezone,'reserve_pct':cfg.reserve_pct}
    @app.get('/api/forecast')
    def predict(battery_pct:float=Query(65,ge=0,le=100),active_minutes:float=Query(45,ge=0,le=60),hours:int=Query(36,ge=1,le=48),weather_source:Literal['demo','live']='demo',scenario:Literal['mixed','sunny','cloudy']='mixed'):
        try: return forecast(cfg,bundle,battery_pct,active_minutes,hours,weather_source,scenario)
        except ValueError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    return app
