"""Daily charging-window regression. Demo data is synthetic, not field evidence."""
from __future__ import annotations
import math
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error
from .config import DATA, ARTIFACTS
from .integration import energy_analysis
from .demo import demo_weather
from .weather import read_forecast, save_forecast
import requests

START = 14
END = 17
HOURS = tuple(range(6,14))
FEATURES = ['morning_level','hours_until_session','window_radiation_sum','window_cloud_mean','window_temp_mean','day_of_year']
TARGET = 'start_level'
FULL_CHARGE_H = 11.0
WINDOW_MIN = (END - START) * 60  # scheduled window, not measured runtime
LESSON_MIN = 5
SESSION_MIN = 20
MAX_SESSIONS = 8  # latest teacher feedback
LESSONS_PER_SESSION = SESSION_MIN // LESSON_MIN
MAX_LESSONS = MAX_SESSIONS * LESSONS_PER_SESSION
MAX_LEARNING_MIN = MAX_LESSONS * LESSON_MIN
assert MAX_LEARNING_MIN <= WINDOW_MIN
SESSION_DRAIN = 10.0
DRAIN = SESSION_DRAIN * LESSON_MIN / SESSION_MIN
RESERVE = 10.0  # conservative END reserve; notebook only blocks starting below 10%
BATTERY_WH = 180.0
PANEL_W = 25.0
DERATE = .8
PROFILE = 'team_180wh_25w_8sessions_v2'
COVERAGE_TARGET = .90
MAX_OVER = .05
MARGINS = [0,2,5,8,10,15,20,30,40,100]


def lesson_count(level, reserve, margin=0):
    return np.clip(np.floor((np.asarray(level,dtype=float)-reserve-margin)/DRAIN + 1e-10),0,MAX_LESSONS).astype(int)


def learning_policy():
    """Single source of truth for the daily learning limit and team assumptions."""
    return {'max_sessions': MAX_SESSIONS, 'max_lessons': MAX_LESSONS,
            'max_learning_minutes': MAX_LEARNING_MIN, 'learning_window_minutes': WINDOW_MIN,
            'unallocated_window_minutes': WINDOW_MIN - MAX_LEARNING_MIN,
            'session_duration_minutes': SESSION_MIN, 'lesson_duration_minutes': LESSON_MIN,
            'lessons_per_session': LESSONS_PER_SESSION, 'session_drain_pp': SESSION_DRAIN,
            'drain_per_lesson_pp': DRAIN, 'reserve_pct': RESERVE,
            'learning_start': f'{START:02d}:00', 'learning_end': f'{END:02d}:00'}


def learning_counts(level, margin=0):
    lessons = int(lesson_count(level, RESERVE, margin))
    return {**learning_policy(), 'recommended_lessons': lessons,
            'recommended_sessions': lessons // LESSONS_PER_SESSION,
            'additional_lessons': lessons % LESSONS_PER_SESSION,
            'available_learning_minutes': lessons * LESSON_MIN}


def window_features(weather, battery, start, end):
    # Open-Meteo shortwave radiation is the preceding hour's mean. Include end labels.
    ends = pd.date_range(start+pd.Timedelta(hours=1),end,freq='h').tz_convert('UTC')
    w = pd.DataFrame({'timestamp':ends}).merge(weather,on='timestamp',how='left',validate='one_to_one')
    cols=['shortwave_radiation','cloud_cover','temperature_2m']
    if w.empty or not np.isfinite(w[cols].to_numpy()).all():
        raise ValueError('Incomplete charging-window weather; refresh forecast or choose demo.')
    return dict(morning_level=float(battery),hours_until_session=len(w),window_radiation_sum=float(w.shortwave_radiation.sum()),window_cloud_mean=float(w.cloud_cover.mean()),window_temp_mean=float(w.temperature_2m.mean()),day_of_year=start.dayofyear),w


def synthetic_days(cfg, days=365, seed=82):
    rng=np.random.default_rng(seed); rows=[]
    for date in pd.date_range('2025-01-01',periods=days,freq='D',tz=cfg.timezone):
        start=date+pd.Timedelta(hours=6); end=date+pd.Timedelta(hours=START)
        ends=pd.date_range(start+pd.Timedelta(hours=1),end,freq='h').tz_convert('UTC')
        w=demo_weather(ends,cfg,seed=int(rng.integers(1,2**30)))
        # Team physics baseline, with simulated day efficiency and taper.
        # The 11-hour charge is a reference only; irradiance changes charging time.
        level=float(rng.uniform(5,90)); levels={6:level}
        efficiency=rng.uniform(.85,1.15)
        for i,r in enumerate(w.itertuples(),7):
            rate=100 * min(PANEL_W, PANEL_W * r.shortwave_radiation / 1000 * DERATE) / BATTERY_WH
            taper=max(.35,min(1.,(100-level)/15))
            gain=max(0.,rate*efficiency*taper*(1-.003*(r.temperature_2m-25))+rng.normal(0,.35))
            level=min(100.,level+gain); levels[i]=level
        for p in HOURS:
            x,_=window_features(w,levels[p],date+pd.Timedelta(hours=p),end)
            rows.append({'date':str(date.date()),'prediction_hour':p,**x,TARGET:levels[START]})
    return pd.DataFrame(rows)


def clean_daily(df):
    required=['date','prediction_hour',*FEATURES,TARGET]
    if not set(required)<=set(df): raise ValueError(f'Missing columns: {set(required)-set(df)}')
    d=df[required].copy(); d['date']=pd.to_datetime(d.date,errors='raise').dt.normalize()
    for c in required[1:]: d[c]=pd.to_numeric(d[c],errors='raise')
    if d.date.isna().any() or not np.isfinite(d[required[1:]].to_numpy()).all(): raise ValueError('Missing or non-finite data')
    if d.duplicated(['date','prediction_hour']).any(): raise ValueError('Duplicate day/prediction hour')
    if not (d.prediction_hour.isin(HOURS).all() and (d.hours_until_session==START-d.prediction_hour).all() and (d.day_of_year==d.date.dt.dayofyear).all()): raise ValueError('Invalid prediction hour, duration or season')
    if not (d.morning_level.between(0,100).all() and d[TARGET].between(0,100).all() and d.window_cloud_mean.between(0,100).all() and d.window_temp_mean.between(-60,65).all() and d.window_radiation_sum.between(0,1400*d.hours_until_session).all()): raise ValueError('Invalid battery/weather range')
    if (d.groupby('date')[TARGET].nunique()>1).any(): raise ValueError('One actual 14:00 target required per day')
    if (d[TARGET]+1e-6<d.morning_level).any(): raise ValueError('Charging-only dataset contains decreasing battery; inspect device state or measurement noise')
    if d.date.nunique()<20: raise ValueError('Need at least 20 distinct verified charging days; use demo or hourly approach meanwhile')
    if not d.groupby('date').prediction_hour.apply(lambda s: 8 in s.values).all(): raise ValueError('Each day must include an 08:00 record for comparable morning evaluation')
    return d.sort_values(['date','prediction_hour']).reset_index(drop=True)


def fit_candidate(d, name, params=None):
    if name=='average_gain': return float(((d[TARGET]-d.morning_level)/d.hours_until_session).mean())
    model=LinearRegression() if name.startswith('linear') else RandomForestRegressor(n_estimators=80,random_state=42,n_jobs=1,**(params or {}))
    y=d[TARGET]-d.morning_level if name.endswith('_gain') else d[TARGET]
    return model.fit(d[FEATURES],y)


def predict_candidate(model,name,d):
    if name=='average_gain': p=d.morning_level+model*d.hours_until_session
    else:
        p=model.predict(d[FEATURES]); p=p+d.morning_level if name.endswith('_gain') else p
    # charging-only window, never forecast a decline or >100%
    return np.clip(np.maximum(np.asarray(p),d.morning_level.to_numpy()),0,100)


def quality(d,p,reserve,margin):
    actual=lesson_count(d[TARGET],reserve); advised=lesson_count(p,reserve,margin); diff=advised-actual
    session_diff=advised//LESSONS_PER_SESSION-actual//LESSONS_PER_SESSION
    return {'mae_pp':float(mean_absolute_error(d[TARGET],p)), 'exact_rate':float(np.mean(diff==0)), 'too_many_rate':float(np.mean(diff>0)), 'too_few_rate':float(np.mean(diff<0)), 'mean_lessons_lost_per_prediction':float(np.mean(np.maximum(-diff,0))), 'session_exact_rate':float(np.mean(session_diff==0)), 'session_too_many_rate':float(np.mean(session_diff>0)), 'session_too_few_rate':float(np.mean(session_diff<0)), 'n':len(d), 'within_5pp_rate':float(np.mean(np.abs(np.asarray(p)-d[TARGET].to_numpy())<=5))}


def fit_daily(df,cfg,source='synthetic_demo'):
    d=clean_daily(df); days=np.sort(d.date.unique()); n=len(days)
    a,b=int(n*.6),int(n*.8); c=a+(b-a)//2; tr=d[d.date.isin(days[:a])]; va=d[d.date.isin(days[a:c])]; cal=d[d.date.isin(days[c:b])]; te=d[d.date.isin(days[b:])]
    names=['average_gain','linear_direct','linear_gain','forest_direct','forest_gain']
    grid=[{'max_depth':depth,'min_samples_leaf':leaf} for depth in [4,8,None] for leaf in [3,8]]
    cv=[]; settings={}; train_days=days[:a]
    # Split distinct days, not individual rows; all morning predictions stay together.
    for name in names:
        for params in (grid if name.startswith('forest') else [None]):
            errors=[]
            for i,j in TimeSeriesSplit(n_splits=3).split(train_days):
                t=tr[tr.date.isin(train_days[i])]; v=tr[tr.date.isin(train_days[j])]
                p=predict_candidate(fit_candidate(t,name,params),name,v)
                errors.append(float(mean_absolute_error(v[TARGET],p)))
            cv.append({'model':name,'params':params,'cv_mae_pp':float(np.mean(errors))})
        settings[name]=min((r for r in cv if r['model']==name),key=lambda r:r['cv_mae_pp'])['params']
    val_predictions={name:predict_candidate(fit_candidate(tr,name,settings[name]),name,va) for name in names}
    # Select on primary 08:00 advice, with explicit over-advice limit. No test involvement.
    morning=va.prediction_hour.eq(8).to_numpy(); v8=va[morning]
    candidates=[{'model':name,'margin_pp':m,**quality(v8,p[morning],RESERVE,m)} for name,p in val_predictions.items() for m in MARGINS]
    feasible=[r for r in candidates if r['too_many_rate']<=MAX_OVER]
    best=min(feasible,key=lambda r:(r['mean_lessons_lost_per_prediction'],r['mae_pp'],r['margin_pp']))
    selected=best['model']; margin=best['margin_pp']; trva=pd.concat([tr,va]); models={name:fit_candidate(trva,name,settings[name]) for name in names}
    test_predictions={name:predict_candidate(models[name],name,te) for name in names}
    t8=te.prediction_hour.eq(8).to_numpy(); nonfull=te[TARGET].lt(99.9).to_numpy()
    report={'source':source,'location':cfg.location,'timezone':cfg.timezone,'scope':('Generated battery and weather training data; hardware validation pending.' if source=='synthetic_demo' else 'Team prototype battery dataset and weather proxy; hardware validation pending.') if source in ('synthetic_demo','team_mock') else 'User-supplied charging windows; provenance and forecast realism require verification.', 'weather_training':'Generated hourly weather scenarios' if source=='synthetic_demo' else 'Team prototype CSV; weather provenance supplied by team' if source=='team_mock' else 'Historical weather or archived forecasts as supplied; record provenance separately.', 'split':{'train_days':a,'validation_days':c-a,'calibration_days':b-c,'test_days':n-b,'train_rows':len(tr),'validation_rows':len(va),'calibration_rows':len(cal),'test_rows':len(te),'train_end':str(days[a-1])[:10],'selection_end':str(days[c-1])[:10],'calibration_start':str(days[c])[:10],'calibration_end':str(days[b-1])[:10],'test_start':str(days[b])[:10]},'cv':cv,'settings':settings,'selected':selected,'margin_pp':margin,'reserve_pct':RESERVE,'over_advice_target':MAX_OVER,'validation_08':{name:quality(v8,p[morning],RESERVE,margin) for name,p in val_predictions.items()},'validation_margin_search':candidates,'test_08':{name:quality(te[t8],p[t8],RESERVE,margin) for name,p in test_predictions.items()},'test_all':{name:{**quality(te,p,RESERVE,margin),'mae_nonfull_pp':float(mean_absolute_error(te.loc[nonfull,TARGET],p[nonfull])) if nonfull.any() else None} for name,p in test_predictions.items()},'test_by_hour':{str(h):quality(te[te.prediction_hour==h],test_predictions[selected][te.prediction_hour.eq(h).to_numpy()],RESERVE,margin) for h in sorted(te.prediction_hour.unique())},'lesson_drain_pp':DRAIN,'lesson_duration_min':LESSON_MIN,'full_charge_hours_reference':FULL_CHARGE_H,'test_errors':[{'date':str(r.date.date()),'hour':int(r.prediction_hour),'cloud_pct':float(r.window_cloud_mean),'morning_level':float(r.morning_level),'actual':float(r.start_level),'predicted':float(p),'error_pp':float(p-r.start_level)} for r,p in zip(te.itertuples(),test_predictions[selected])]}
    report['exploration_training_08']=[{'date':str(r.date.date()),'radiation_wh_m2':float(r.window_radiation_sum),'gain_pp':float(r.start_level-r.morning_level),'morning_level':float(r.morning_level),'target_pct':float(r.start_level)} for r in tr[tr.prediction_hour.eq(8)].itertuples()]
    # Independent chronological calibration. No test residual is used to set the interval.
    # One residual per day for each prediction hour. A finite-sample 90% rank is
    # unavailable with fewer than nine observations. Time dependence/domain shift
    # means the nominal conformal target is not a guaranteed future probability.
    report['profile']=PROFILE
    report['learning_policy']=learning_policy()
    report['hardware_profile']={'battery_wh':BATTERY_WH,'panel_w':PANEL_W,'start_hour':START,'end_hour':END,'session_minutes':SESSION_MIN,'session_drain_pp':SESSION_DRAIN,'lesson_minutes':LESSON_MIN,'reserve_pct':RESERVE,'max_sessions':MAX_SESSIONS,'max_lessons':MAX_LESSONS}
    report['reliability_by_hour']={}
    for h in HOURS:
        ch=cal[cal.prediction_hour.eq(h)]; th=te[te.prediction_hour.eq(h)]
        if th.empty: continue
        cp=predict_candidate(models[selected],selected,ch) if len(ch) else np.array([])
        residuals=np.sort(np.abs(cp-ch[TARGET].to_numpy()))
        rank=math.ceil((len(residuals)+1)*COVERAGE_TARGET)
        radius=float(residuals[rank-1]) if 0<rank<=len(residuals) else None
        tp=test_predictions[selected][te.prediction_hour.eq(h).to_numpy()]
        hits=int(np.sum(np.abs(tp-th[TARGET].to_numpy())<=radius+1e-10)) if radius is not None else None
        report['reliability_by_hour'][str(h)]={'target_coverage':COVERAGE_TARGET,'radius_pp':radius,'calibration_days':len(ch),'test_days':len(th),'test_interval_hits':hits,'test_interval_coverage':hits/len(th) if hits is not None else None,**quality(th,tp,RESERVE,margin)}
    return {'model':models[selected],'report':report}


def save_daily(bundle):
    ARTIFACTS.mkdir(exist_ok=True); source=bundle['report']['source']; path=ARTIFACTS/f'daily_{source}.joblib'
    joblib.dump(bundle,path); path.with_suffix('.json').write_text(json.dumps(bundle['report'],indent=2),encoding='utf-8'); return path


def load_daily(source='synthetic_demo'):
    path=ARTIFACTS/f'daily_{source}.joblib'
    if not path.exists():
        commands={'synthetic_demo':'train-daily-demo','team_mock':'train-daily-team --csv data/device_sessions_hourly_mock_long.csv','measured':'train-daily-real --csv data/daily_real_training.csv'}
        raise ValueError('Model not trained. Run python -m energy_ai '+commands[source])
    bundle=joblib.load(path)
    if bundle['report'].get('profile')!=PROFILE: raise ValueError('Old daily model profile. Retrain the daily model for this version.')
    return bundle


def advice(cfg,bundle,battery,weather_source='demo',scenario='mixed',prediction_hour=8,now=None,battery_source='manual scenario input'):
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now).tz_convert('UTC')
    local=now.tz_convert(cfg.timezone); date=local.normalize(); end=date+pd.Timedelta(hours=START)
    if not 0<=battery<=100: raise ValueError('Battery must be 0–100%')
    if weather_source=='live':
        # Conservative: discard partial current hour. The input is a current measurement.
        start=local.ceil('h')
        if start.hour not in HOURS or start.date()!=date.date(): raise ValueError('Live morning advice requires a current battery reading between 06:00 and 13:00 local time. Use demo for a hypothetical morning.')
        try:
            weather,meta=read_forecast(cfg)
        except ValueError:
            try: save_forecast(cfg); weather,meta=read_forecast(cfg)
            except (requests.RequestException,ValueError) as exc: raise ValueError('Live weather unavailable; no forecast generated. Refresh the cache or use a generated weather scenario.') from exc
        weather_label='Open-Meteo forecast cache'; fetched=meta['fetched_at']
    else:
        if prediction_hour not in HOURS: raise ValueError('Demo prediction hour must be 06:00–13:00')
        start=date+pd.Timedelta(hours=prediction_hour); ends=pd.date_range(start+pd.Timedelta(hours=1),end,freq='h').tz_convert('UTC')
        weather=demo_weather(ends,cfg,scenario=scenario); weather_label='Generated weather scenario'; fetched=None
    x,w=window_features(weather,battery,start,end); report=bundle['report']
    if report.get('profile')!=PROFILE or report['reserve_pct']!=RESERVE or report['location']!=cfg.location or report['timezone']!=cfg.timezone: raise ValueError('Model configuration changed; retrain daily model before using advice.')
    raw_level=float(predict_candidate(bundle['model'],report['selected'],pd.DataFrame([x]))[0]); margin=report['margin_pp']
    # Keep the evaluated ML prediction unchanged. Use a separate conservative
    # engineering planning ceiling from the same hourly weather and team profile.
    potential_wh=float(np.clip(PANEL_W * w.shortwave_radiation.to_numpy()/1000 * DERATE,0,PANEL_W).sum())
    ceiling=min(100., battery+100*potential_wh/BATTERY_WH)
    level=min(raw_level,ceiling)
    # Round downward to ensure the displayed planning level and count agree.
    level=math.floor(level*100+1e-9)/100
    counts=learning_counts(level,margin); n=counts['recommended_lessons']
    reliability=report['reliability_by_hour'].get(str(start.hour),{}).copy()
    radius=reliability.get('radius_pp')
    reliability.update({'lower_battery_pct':max(0,math.floor((raw_level-radius)*100)/100) if radius is not None else None,'upper_battery_pct':min(100,math.ceil((raw_level+radius)*100)/100) if radius is not None else None,'evaluation_source':report['source'],'field_validated':False,'prediction_hour':start.hour,'interpretation':'Raw ML held-out performance, before the engineering planning ceiling. The guarded recommendations have not been independently evaluated. Historical coverage is not a probability for this forecast.'})
    peak=w.loc[w.shortwave_radiation.idxmax()]; peak_end=peak.timestamp.tz_convert(cfg.timezone)
    peak_window=None if peak.shortwave_radiation<=0 else {'start':(peak_end-pd.Timedelta(hours=1)).isoformat(),'end':peak_end.isoformat(),'radiation_w_m2':round(float(peak.shortwave_radiation),1)}
    reason=f'Forecast charging window has {x["window_radiation_sum"]:.0f} Wh/m² radiation and {x["window_cloud_mean"]:.0f}% average cloud cover. Raw ML prediction at 14:00 is {raw_level:.1f}%; conservative planning battery is {level:.1f}% (weather-based engineering ceiling {ceiling:.1f}%). With a {RESERVE:g}% reserve and {margin:g} pp model margin, the estimate allows {n} five-minute lessons ({counts["recommended_sessions"]} full twenty-minute sessions and {counts["additional_lessons"]} extra lessons), within the teacher’s limit of {MAX_SESSIONS} sessions / {MAX_LESSONS} lessons. Charge when sunlight is available before 14:00; do not use while charging. Recheck actual battery before learning.'
    return {'location':cfg.location,'model_source':report['source'],'model':report['selected'],'battery_source':battery_source,'weather_source':weather_label,'weather_fetched_at':fetched,'prediction_time_local':start.isoformat(),'learning_start_local':end.isoformat(),'learning_end_local':(date+pd.Timedelta(hours=END)).isoformat(),'current_battery_pct':battery,'predicted_start_level':round(raw_level,2),'planning_start_level':level,'engineering_ceiling_pct':round(ceiling,2),'engineering_limit_applied':raw_level>ceiling+1e-9,'battery_based_capacity_at_input':learning_counts(battery),'margin_pp':margin,'reserve_pct':RESERVE,'drain_per_lesson_pp':DRAIN,'lesson_duration_minutes':LESSON_MIN,**counts,'prediction_reliability':reliability,'hardware_profile':report['hardware_profile'],'estimated_remaining_pct':round(level-n*DRAIN,2),'estimated_remaining_with_margin_pct':round(max(0,level-margin-n*DRAIN),2),'status':'READY' if n>=1 else 'CHARGE_OR_POSTPONE','reason':reason,'features':x,'energy_analysis':energy_analysis(cfg,w,battery,level,counts,report['hardware_profile'],DERATE,raw_level=raw_level),'strongest_sunlight_window':peak_window,'hourly_sunlight':[{'start_local':(r.timestamp.tz_convert(cfg.timezone)-pd.Timedelta(hours=1)).isoformat(),'end_local':r.timestamp.tz_convert(cfg.timezone).isoformat(),'radiation_w_m2':round(float(r.shortwave_radiation),1)} for r in w.itertuples()],'limitations':'Advisory estimate, not battery protection. Team profile: 180 Wh, 25 W, 10 pp per 20-minute session, 10% end reserve. All require hardware validation; the reported 11 h charge and 3 h runtime are references only. Model margin is not a safety guarantee. Mock training is not real battery validation. Live predictions discard partial-hour charging.'}


def prepare_real_windows(cfg, logs, weather, device_id, verified_days, max_gap_minutes=30):
    """Use explicitly verified charging-only days. Never infer sun exposure from SoC alone.

    Logs must represent the configured location and device. Weather timestamps are UTC
    interval-end labels. Samples must be within 10 min before each boundary.
    """
    logs=logs[logs.device_id==device_id].copy()
    logs['timestamp']=pd.to_datetime(logs.timestamp,utc=True,errors='raise'); logs=logs.sort_values('timestamp')
    logs['battery_pct']=pd.to_numeric(logs.battery_pct,errors='raise')
    if logs.empty or not logs.battery_pct.between(0,100).all() or logs.timestamp.duplicated().any(): raise ValueError('Invalid or empty device logs')
    weather=weather.copy();weather['timestamp']=pd.to_datetime(weather.timestamp,utc=True,errors='raise')
    rows=[]; skipped=[]
    for day in sorted(set(verified_days)):
        date=pd.Timestamp(day).normalize().tz_localize(cfg.timezone); end=date+pd.Timedelta(hours=START)
        first=date+pd.Timedelta(hours=6)
        window=logs[logs.timestamp.between(first-pd.Timedelta(minutes=10),end)]
        if window.empty or window.timestamp.diff().dropna().gt(pd.Timedelta(minutes=max_gap_minutes)).any():
            skipped.append((str(date.date()),'Missing logs or long gaps'));continue
        if 'device_state' in window and window.device_state.fillna('').str.lower().isin(['learning','in_use','active']).any():
            skipped.append((str(date.date()),'Usage recorded during charging window'));continue
        def battery_at(t):
            match=window[window.timestamp.between(t-pd.Timedelta(minutes=10),t)]
            return None if match.empty else float(match.iloc[-1].battery_pct)
        target=battery_at(end)
        if target is None or battery_at(date+pd.Timedelta(hours=8)) is None:
            skipped.append((str(date.date()),'Missing 08:00 or 14:00 measurement'));continue
        day_rows=[]
        for h in HOURS:
            start=date+pd.Timedelta(hours=h); level=battery_at(start)
            if level is None or level>target: continue
            try: x,_=window_features(weather,level,start,end)
            except ValueError: continue
            day_rows.append({'date':str(date.date()),'prediction_hour':h,**x,TARGET:target})
        if not any(r['prediction_hour']==8 for r in day_rows):
            skipped.append((str(date.date()),'Incomplete weather or decreasing SoC at 08:00'));continue
        rows.extend(day_rows)
    return pd.DataFrame(rows,columns=['date','prediction_hour',*FEATURES,TARGET]),skipped


def team_mock_windows(df):
    """Import the team's hourly CSV convention: hour h battery is end of hour h.
    Keep only complete weekday charging windows with no usage before 14:00.
    Data remains mock; this does not verify hardware or archived forecasts.
    """
    required=['timestamp_local','day_type','hour','battery_pct','use_min','solar_radiation_wm2','cloud_cover_pct','temperature_c']
    if not set(required)<=set(df): raise ValueError(f'Missing team CSV columns: {set(required)-set(df)}')
    d=df[required].copy(); d['ts']=pd.to_datetime(d.timestamp_local.astype(str).str[:19],errors='raise')
    d['date']=d.ts.dt.normalize()
    for k in required[2:]: d[k]=pd.to_numeric(d[k],errors='raise')
    if d.ts.isna().any() or d.duplicated('ts').any() or not np.isfinite(d[required[2:]].to_numpy()).all() or not (d.hour==d.ts.dt.hour).all(): raise ValueError('Invalid or duplicate hourly records')
    if not (d.battery_pct.between(0,100).all() and d.use_min.between(0,60).all() and d.solar_radiation_wm2.between(0,1400).all() and d.cloud_cover_pct.between(0,100).all() and d.temperature_c.between(-60,65).all()): raise ValueError('Invalid team CSV measurements')
    rows=[]
    types=['school_weekday','exam_weekday','school_holiday_weekday','public_holiday']
    for date,g in d.groupby('date'):
        if date.dayofweek>=5 or not g.day_type.isin(types).all(): continue
        g=g.set_index('hour').sort_index()
        if not set(range(5,14))<=set(g.index) or g.loc[6:13,'use_min'].gt(0).any(): continue
        target=float(g.loc[13,'battery_pct'])
        if g.loc[5:12,'battery_pct'].gt(target+1e-6).any(): continue
        for h in HOURS:
            w=g.loc[h:13]
            rows.append({'date':str(date.date()),'prediction_hour':h,'morning_level':float(g.loc[h-1,'battery_pct']),'hours_until_session':START-h,'window_radiation_sum':float(w.solar_radiation_wm2.sum()),'window_cloud_mean':float(w.cloud_cover_pct.mean()),'window_temp_mean':float(w.temperature_c.mean()),'day_of_year':date.dayofyear,TARGET:target})
    if not rows: raise ValueError('No complete charging-only weekday windows in team CSV')
    return clean_daily(pd.DataFrame(rows))
