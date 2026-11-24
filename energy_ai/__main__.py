import argparse
import json
from pathlib import Path
import pandas as pd
from .config import load_settings,DATA
from .demo import training_data
from .models import fit,save
from .weather import fetch,save_forecast

def main():
    p=argparse.ArgumentParser(description='PPS smart energy forecasting prototype')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('train-demo')
    sub.add_parser('fetch-weather')
    h=sub.add_parser('fetch-history'); h.add_argument('--start',default='2024-01-01');h.add_argument('--end',default='2025-12-31')
    t=sub.add_parser('train-real');t.add_argument('--sensors',required=True);t.add_argument('--weather',required=True)
    s=sub.add_parser('serve');s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8000);s.add_argument('--model',choices=['synthetic_demo','measured'],default='synthetic_demo')
    args=p.parse_args();cfg=load_settings()
    if args.cmd=='train-demo':
        df=training_data(cfg);df.to_csv(DATA/'demo_training.csv',index=False)
        bundle=fit(df,cfg); print('Saved:',save(bundle));print(json.dumps(bundle['report'],indent=2))
    elif args.cmd=='fetch-weather': print('Saved:',save_forecast(cfg))
    elif args.cmd=='fetch-history':
        df=fetch(cfg,start=args.start,end=args.end);path=DATA/'pretoria_historical_weather.csv';df.to_csv(path,index=False);print(f'Saved {len(df)} rows to {path}')
    elif args.cmd=='train-real':
        sensor=pd.read_csv(args.sensors);weather=pd.read_csv(args.weather)
        needed=['timestamp','battery_pct','solar_w','load_w','usage_minutes']
        sensor=sensor[needed].copy()
        for df in (sensor,weather): df['timestamp']=pd.to_datetime(df.timestamp,utc=True,errors='raise')
        df=sensor.merge(weather,on='timestamp',how='inner',validate='one_to_one')
        print(f'Matched {len(df)} of {len(sensor)} sensor rows')
        bundle=fit(df,cfg,source='measured');print('Saved:',save(bundle));print(json.dumps(bundle['report'],indent=2))
    elif args.cmd=='serve':
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(cfg,args.model),host=args.host,port=args.port)

if __name__=='__main__': main()
