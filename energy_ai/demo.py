"""Deterministic synthetic data for testing only; no actual PPS measurements."""
import numpy as np
import pandas as pd
from .config import Settings
from .weather import FIELDS

def demo_weather(times, cfg: Settings, scenario='mixed', seed=42):
    times = pd.DatetimeIndex(times)
    rng = np.random.default_rng(seed)
    local = (times - pd.Timedelta(minutes=30)).tz_convert(cfg.timezone)
    hour = local.hour.to_numpy() + local.minute.to_numpy()/60
    day = local.dayofyear.to_numpy()
    daylight = np.maximum(0, np.sin(np.pi*(hour-6)/12)) * ((hour>=6)&(hour<=18))
    if scenario == 'sunny':
        cloud = np.full(len(times), 12.)
    elif scenario == 'cloudy':
        cloud = np.full(len(times), 87.)
    else:
        cloud = np.clip(45 + 30*np.sin(day*0.81) + rng.normal(0,15,len(times)), 0,100)
    ghi = 950*daylight*(1-0.82*cloud/100)*(1+0.08*np.cos((day-15)*2*np.pi/365))
    temp = 18+8*daylight+3*np.sin(day*2*np.pi/365)+rng.normal(0,0.6,len(times))
    return pd.DataFrame(dict(timestamp=times, temperature_2m=temp, cloud_cover=cloud,
                             shortwave_radiation=ghi, direct_radiation=ghi*(1-cloud/100),
                             sunshine_duration=3600*daylight*(1-cloud/100)))

def training_data(cfg: Settings, days=90):
    rng = np.random.default_rng(73)
    times = pd.date_range('2025-01-01 01:00', periods=days*24, freq='h', tz='UTC')
    df = demo_weather(times,cfg)
    midpoint = (times-pd.Timedelta(minutes=30)).tz_convert(cfg.timezone)
    active = (midpoint.hour>=cfg.lesson_start_hour)&(midpoint.hour<cfg.lesson_end_hour)&(midpoint.dayofweek<6)
    df['usage_minutes'] = np.where(active, rng.uniform(15,60,len(df)),rng.uniform(0,5,len(df)))
    df['solar_w'] = np.clip(cfg.panel_rated_w*df.shortwave_radiation/1000*cfg.panel_derate*(1-0.003*(df.temperature_2m-25)) + rng.normal(0,2,len(df)),0,cfg.panel_rated_w)
    df.loc[df.shortwave_radiation==0,'solar_w']=0
    df['load_w'] = np.maximum(0,cfg.idle_w+(cfg.active_w-cfg.idle_w)*df.usage_minutes/60+rng.normal(0,2,len(df)))
    from .battery import advance
    energy = cfg.battery_capacity_wh*0.8
    soc=[]
    for row in df.itertuples():
        energy,_,_=advance(energy,row.solar_w,row.load_w,1,cfg)
        soc.append(100*energy/cfg.battery_capacity_wh)
    df['battery_pct']=soc
    df['source']='synthetic_demo'
    return df
