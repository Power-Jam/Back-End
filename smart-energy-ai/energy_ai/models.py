"""Chronological holdout comparison, no random split or test-set tuning."""
from __future__ import annotations
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from .config import ARTIFACTS, Settings
from dataclasses import asdict

SOLAR_FEATURES=['shortwave_radiation','temperature_2m','cloud_cover']
LOAD_FEATURES=['usage_minutes','hour_sin','hour_cos','weekend']

def features(df, cfg):
    df=df.copy()
    local=(pd.to_datetime(df.timestamp,utc=True)-pd.Timedelta(minutes=30)).dt.tz_convert(cfg.timezone)
    df['hour_sin']=np.sin(2*np.pi*local.dt.hour/24)
    df['hour_cos']=np.cos(2*np.pi*local.dt.hour/24)
    df['weekend']=(local.dt.dayofweek>=5).astype(int)
    return df

def clean(df):
    df=df.copy()
    required=['timestamp','solar_w','load_w','usage_minutes','battery_pct',*SOLAR_FEATURES]
    missing=set(required)-set(df.columns)
    if missing: raise ValueError(f'Missing columns: {sorted(missing)}')
    df['timestamp']=pd.to_datetime(df.timestamp,utc=True,errors='coerce')
    for col in required[1:]: df[col]=pd.to_numeric(df[col],errors='coerce')
    df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=required).sort_values('timestamp')
    if df.timestamp.duplicated().any(): raise ValueError('Duplicate timestamps: resolve before training')
    if (df.timestamp != df.timestamp.dt.floor('h')).any(): raise ValueError('Training records must be hourly interval-end UTC timestamps')
    valid=(df.solar_w>=0)&(df.load_w>=0)&df.usage_minutes.between(0,60)&df.battery_pct.between(0,100)&df.cloud_cover.between(0,100)&(df.shortwave_radiation>=0)
    df=df.loc[valid].reset_index(drop=True)
    if len(df)<240: raise ValueError('Need at least 240 valid paired hourly records (more recommended)')
    return df

def baselines(df,cfg):
    solar=np.clip(cfg.panel_rated_w*df.shortwave_radiation/1000*cfg.panel_derate,0,cfg.panel_rated_w)
    load=cfg.idle_w+(cfg.active_w-cfg.idle_w)*df.usage_minutes/60
    return {'solar_w':solar,'load_w':load}

def fit(df, cfg: Settings, source='synthetic_demo'):
    original_count=len(df)
    df=features(clean(df),cfg)
    n=len(df); a=int(n*.6); b=int(n*.8)
    train,val,test=df.iloc[:a],df.iloc[a:b],df.iloc[b:]
    report={'source':source,'input_rows':original_count,'valid_rows':n,'train_rows':len(train),'validation_rows':len(val),'test_rows':len(test),'train_end':str(train.timestamp.iloc[-1]),'test_start':str(test.timestamp.iloc[0]),'metrics':{}}
    models={}
    for target,cols in [('solar_w',SOLAR_FEATURES),('load_w',LOAD_FEATURES)]:
        candidates={'linear_regression':LinearRegression(), 'random_forest':RandomForestRegressor(n_estimators=80,max_depth=10,min_samples_leaf=4,random_state=42,n_jobs=1)}
        def predict(model, part):
            p=np.maximum(0,model.predict(part[cols]))
            if target=='solar_w': p=np.where(part.shortwave_radiation<=0,0,np.minimum(p,cfg.panel_rated_w))
            return p
        scores={}
        for name,model in candidates.items():
            model.fit(train[cols],train[target]); scores[name]=float(mean_absolute_error(val[target],predict(model,val)))
        scores['physical_baseline']=float(mean_absolute_error(val[target],baselines(val,cfg)[target]))
        chosen=min(scores,key=scores.get)
        # Refit on train+validation only. Test is never used to choose a model.
        final_train=df.iloc[:b]
        for model in candidates.values(): model.fit(final_train[cols],final_train[target])
        test_predictions={name:predict(model,test) for name,model in candidates.items()}
        test_predictions['physical_baseline']=baselines(test,cfg)[target]
        report['metrics'][target]={'selected':chosen,'validation_mae_w':scores,'test':{name:{'mae_w':float(mean_absolute_error(test[target],p)),'rmse_w':float(np.sqrt(mean_squared_error(test[target],p)))} for name,p in test_predictions.items()}}
        models[target]={'name':chosen,'model':candidates.get(chosen),'features':cols}
    report['scope']='Hourly solar/load prediction; historical weather and measured usage are known covariates, not archived day-ahead forecasts. Operational forecast errors can be larger.'
    bundle={'source':source,'settings':asdict(cfg),'models':models,'report':report}
    return bundle

def predict_power(bundle, df, cfg):
    df=features(df,cfg); base=baselines(df,cfg); out={}
    for target, m in bundle['models'].items():
        p=base[target] if m['model'] is None else m['model'].predict(df[m['features']])
        p=np.maximum(0,p)
        if target=='solar_w': p=np.where(df.shortwave_radiation<=0,0,np.minimum(p,cfg.panel_rated_w))
        out[target]=p
    return out

def save(bundle):
    ARTIFACTS.mkdir(exist_ok=True)
    path=ARTIFACTS/(bundle['source']+'.joblib')
    joblib.dump(bundle,path)
    (ARTIFACTS/(bundle['source']+'_metrics.json')).write_text(json.dumps(bundle['report'],indent=2),encoding='utf-8')
    return path

def load(cfg, source='synthetic_demo'):
    path=ARTIFACTS/(source+'.joblib')
    if not path.exists(): raise ValueError('No trained model. Run python -m energy_ai train-demo or train-real first.')
    bundle=joblib.load(path) # only local artifacts generated by this project; never load untrusted joblib
    if bundle['settings']!=asdict(cfg): raise ValueError('Configuration changed since training; retrain the model.')
    return bundle
