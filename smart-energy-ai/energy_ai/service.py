from __future__ import annotations
import numpy as np
import pandas as pd
from .battery import advance, decision
from .demo import demo_weather
from .weather import read_forecast
from .models import predict_power

def forecast(cfg,bundle,battery_pct=65,active_minutes=45,hours=36,weather_source='demo',scenario='mixed',now=None):
    if not 0<=battery_pct<=100 or not 0<=active_minutes<=60 or not 1<=hours<=48:
        raise ValueError('Battery 0–100%, usage 0–60 minutes/hour, horizon 1–48 hours')
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now).tz_convert('UTC')
    # Hourly radiation refers to the interval END; first interval may be partial.
    ends=pd.date_range(now.floor('h')+pd.Timedelta(hours=1), periods=hours, freq='h')
    if weather_source=='live':
        weather,meta=read_forecast(cfg)
        df=pd.DataFrame({'timestamp':ends}).merge(weather,on='timestamp',how='left',validate='one_to_one')
        weather_label='Open-Meteo forecast cache'; fetched=meta['fetched_at']
    elif weather_source=='demo':
        df=demo_weather(ends,cfg,scenario=scenario); weather_label='SIMULATED weather'; fetched=None
    else: raise ValueError('Unknown weather source')
    cols=['shortwave_radiation','temperature_2m','cloud_cover']
    if df[cols].isna().any().any() or not np.isfinite(df[cols].to_numpy()).all():
        raise ValueError('Weather data missing for requested horizon; refresh cache or shorten horizon.')
    local=(df.timestamp-pd.Timedelta(minutes=30)).dt.tz_convert(cfg.timezone)
    df['usage_minutes']=np.where((local.dt.hour>=cfg.lesson_start_hour)&(local.dt.hour<cfg.lesson_end_hour),active_minutes,0.)
    p=predict_power(bundle,df,cfg)
    e=cfg.battery_capacity_wh*battery_pct/100
    rows=[]; first_reserve=0.0 if battery_pct<=cfg.reserve_pct else None; first_empty=0.0 if battery_pct==0 else None; first_warning=0.0 if battery_pct<=cfg.warning_pct else None
    previous=now
    for i,row in enumerate(df.itertuples()):
        duration=(row.timestamp-previous).total_seconds()/3600
        start_e=e
        e,unserved,_=advance(e,float(p['solar_w'][i]),float(p['load_w'][i]),duration,cfg)
        reserve_wh=cfg.battery_capacity_wh*cfg.reserve_pct/100
        elapsed=(previous-now).total_seconds()/3600
        # Linear interpolation within the interval; use unclipped energy slope.
        net=(p['solar_w'][i]-p['load_w'][i])*duration
        delta=net*cfg.charge_efficiency if net>=0 else net/cfg.discharge_efficiency
        if delta<0:
            warning_wh=cfg.battery_capacity_wh*cfg.warning_pct/100
            if first_warning is None and start_e+delta<=warning_wh:
                first_warning=elapsed+duration*(start_e-warning_wh)/(-delta)
            if first_reserve is None and start_e+delta<=reserve_wh:
                first_reserve=elapsed+duration*(start_e-reserve_wh)/(-delta)
            if first_empty is None and start_e+delta<=0:
                first_empty=elapsed+duration*start_e/(-delta)
        pct=100*e/cfg.battery_capacity_wh
        code,msg=decision(pct,cfg.reserve_pct,cfg.warning_pct)
        rows.append({'timestamp':row.timestamp.isoformat(),'local_time':row.timestamp.tz_convert(cfg.timezone).isoformat(),'battery_pct':round(pct,2),'solar_w':round(float(p['solar_w'][i]),2),'load_w':round(float(p['load_w'][i]),2),'usage_minutes_per_hour':float(row.usage_minutes),'radiation_w_m2':round(float(row.shortwave_radiation),2),'cloud_pct':round(float(row.cloud_cover),1),'temperature_c':round(float(row.temperature_2m),1),'unserved_battery_equivalent_wh':round(unserved,2),'status':code})
        previous=row.timestamp
    status,msg=decision(battery_pct,cfg.reserve_pct,cfg.warning_pct)
    if status=='CONTINUE' and first_reserve is not None and first_reserve<=4:
        status='CHARGE_SOON';msg='Battery reserve may be reached within four hours. Plan to charge or reduce usage.'
    now_local=now.tz_convert(cfg.timezone)
    tomorrow=(now_local+pd.Timedelta(days=1)).date()
    next_day=[r for r in rows if pd.Timestamp(r['local_time']).date()==tomorrow]
    return {'location':cfg.location,'generated_at':now.isoformat(),'weather_source':weather_label,'weather_fetched_at':fetched,'model_source':bundle['source'],'initial_battery_pct':battery_pct,'initial_battery_source':'manual scenario input, not live sensor','reserve_pct':cfg.reserve_pct,'warning_pct':cfg.warning_pct,'usage_schedule':f'{cfg.lesson_start_hour:02}:00–{cfg.lesson_end_hour:02}:00 local time, {active_minutes} active minutes per hour, idle otherwise','charge_by_local':None if first_warning is None else (now+pd.Timedelta(hours=float(first_warning))).tz_convert(cfg.timezone).isoformat(),'reserve_at_local':None if first_reserve is None else (now+pd.Timedelta(hours=float(first_reserve))).tz_convert(cfg.timezone).isoformat(),'hours_to_reserve':None if first_reserve is None else round(first_reserve,2),'hours_to_empty':None if first_empty is None else round(first_empty,2),'status':status,'recommendation':msg,'tomorrow_local_date':str(tomorrow),'tomorrow_min_pct':min((r['battery_pct'] for r in next_day),default=None),'tomorrow_points':len(next_day),'forecast':rows,'limitations':'Scenario estimate only; assumes configured hardware, planned usage and no external charging. Synthetic training is not field validation. A null time means threshold not reached in this horizon.'}
