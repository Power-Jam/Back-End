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
    sub.add_parser('train-all',help='Train original hourly, daily prototype and bundled team models')
    sub.add_parser('train-daily-demo')
    tm=sub.add_parser('train-daily-team');tm.add_argument('--csv',required=True)
    dr=sub.add_parser('train-daily-real');dr.add_argument('--csv',required=True)
    sub.add_parser('listen-ttn')
    sub.add_parser('export-ttn')
    history=sub.add_parser('fetch-ttn-history');history.add_argument('--device-id',default='scb-5000');history.add_argument('--application',default='scb-5000');history.add_argument('--last',default='12h')
    prep=sub.add_parser('prepare-daily-real');prep.add_argument('--logs',required=True);prep.add_argument('--weather',required=True);prep.add_argument('--device-id',required=True);prep.add_argument('--verified-days',required=True)
    sub.add_parser('fetch-weather')
    h=sub.add_parser('fetch-history'); h.add_argument('--start',default='2024-01-01');h.add_argument('--end',default='2025-12-31')
    t=sub.add_parser('train-real');t.add_argument('--sensors',required=True);t.add_argument('--weather',required=True)
    s=sub.add_parser('serve');s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8000);s.add_argument('--model',choices=['synthetic_demo','measured'],default='synthetic_demo')
    args=p.parse_args();cfg=load_settings()
    if args.cmd=='train-all':
        from .daily import synthetic_days,fit_daily,save_daily,team_mock_windows
        DATA.mkdir(exist_ok=True)
        df=training_data(cfg); df.to_csv(DATA/'demo_training.csv',index=False)
        print('Hourly model:',save(fit(df,cfg)),flush=True)
        df=synthetic_days(cfg); df.to_csv(DATA/'daily_demo_training.csv',index=False)
        print('Daily prototype model:',save_daily(fit_daily(df,cfg)),flush=True)
        team_path=DATA/'device_sessions_hourly_mock_long.csv'
        if not team_path.is_file(): raise FileNotFoundError(f'Bundled team dataset missing: {team_path}')
        team=team_mock_windows(pd.read_csv(team_path)); team.to_csv(DATA/'daily_team_training.csv',index=False)
        print('Team prototype model:',save_daily(fit_daily(team,cfg,'team_mock')),flush=True)
    elif args.cmd in ('train-daily-demo','train-daily-real','train-daily-team'):
        from .daily import synthetic_days,fit_daily,save_daily,team_mock_windows
        source='synthetic_demo' if args.cmd=='train-daily-demo' else 'team_mock' if args.cmd=='train-daily-team' else 'measured'
        df=synthetic_days(cfg) if source=='synthetic_demo' else team_mock_windows(pd.read_csv(args.csv)) if source=='team_mock' else pd.read_csv(args.csv)
        if source=='synthetic_demo': df.to_csv(DATA/'daily_demo_training.csv',index=False)
        bundle=fit_daily(df,cfg,source); print('Saved:',save_daily(bundle))
        report=bundle['report']; print(json.dumps({k:report[k] for k in ('source','split','selected','margin_pp','test_08','reliability_by_hour')},indent=2))
    elif args.cmd=='prepare-daily-real':
        from .daily import prepare_real_windows
        days=pd.read_csv(args.verified_days)['date'].astype(str).tolist()
        df,skipped=prepare_real_windows(cfg,pd.read_csv(args.logs),pd.read_csv(args.weather),args.device_id,days)
        path=DATA/'daily_real_training.csv';df.to_csv(path,index=False)
        print(f'Saved {len(df)} rows from {df.date.nunique()} days to {path}; skipped: {skipped}')
    elif args.cmd=='listen-ttn':
        from .telemetry import listen
        listen()
    elif args.cmd=='fetch-ttn-history':
        from .storage import fetch_storage
        new,total,path=fetch_storage(args.device_id,args.application,args.last)
        print(f'Retrieved {new} valid readings; {total} total stored at {path}')
    elif args.cmd=='export-ttn':
        from .telemetry import export_csv
        print('Saved:',export_csv())
    elif args.cmd=='train-demo':
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
