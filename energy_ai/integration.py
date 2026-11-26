"""Connect daily ML advice to the original energy balance and solar planner."""
from dataclasses import replace
import pandas as pd
from .battery import advance
from .models import baselines
from .solar_planning import daily_solar_summary


def energy_analysis(cfg, weather, battery, predicted, counts, profile, derate, raw_level=None):
    # Battery-side drain and solar derate already include assumed losses.
    team = replace(cfg, battery_capacity_wh=profile['battery_wh'],
                   panel_rated_w=profile['panel_w'], panel_derate=derate,
                   idle_w=0., active_w=profile['battery_wh']*profile['session_drain_pp']/100/(profile['session_minutes']/60),
                   charge_efficiency=1., discharge_efficiency=1.,
                   reserve_pct=profile['reserve_pct'],
                   lesson_start_hour=profile['start_hour'], lesson_end_hour=profile['end_hour'])
    w=weather.copy(); w['usage_minutes']=0.
    solar=baselines(w,team)['solar_w'].to_numpy()
    energy=battery*team.battery_capacity_wh/100
    intervals=[]; rows=[]
    for r,p in zip(w.itertuples(),solar):
        end=r.timestamp.tz_convert(cfg.timezone); start=end-pd.Timedelta(hours=1)
        old=energy; energy,_,_=advance(energy,float(p),0.,1.,team)
        interval={'start_local':start.isoformat(),'end_local':end.isoformat(),
                  'duration_hours':1.,'solar_w':float(p),'load_w':0.,'net_power_w':float(p),
                  'radiation_w_m2':float(r.shortwave_radiation),'battery_gain_wh':max(0.,energy-old)}
        intervals.append(interval)
        rows.append({**interval,'mode':'charging','battery_pct':round(100*energy/team.battery_capacity_wh,2)})
    summary=daily_solar_summary(intervals)[0]
    physics_level=100*energy/team.battery_capacity_wh
    # Afternoon starts at the ML estimate, not the independent physics estimate.
    learning=[]; start=pd.Timestamp(rows[-1]['end_local']); e=predicted*team.battery_capacity_wh/100
    for i in range(counts['recommended_lessons']):
        end=start+pd.Timedelta(minutes=counts['lesson_duration_minutes'])
        e,_,_=advance(e,0.,team.active_w,counts['lesson_duration_minutes']/60,team)
        learning.append({'lesson':i+1,'session':i//counts['lessons_per_session']+1,'start_local':start.isoformat(),'end_local':end.isoformat(),'mode':'learning','solar_w':0.,'load_w':team.active_w,'battery_pct':round(100*e/team.battery_capacity_wh,2)})
        start=end
    return {'method':'Original energy balance and solar planner adapted to team profile; physical baseline, not a second ML prediction.',
            'profile':{'battery_wh':team.battery_capacity_wh,'panel_w':team.panel_rated_w,'panel_derate':derate,'learning_battery_side_w':team.active_w,'charging_load_w':0.},
            'physics_start_level':round(physics_level,2),'ml_start_level':round(predicted if raw_level is None else raw_level,2),'planning_start_level':round(predicted,2),
            'ml_minus_physics_pp':round((predicted if raw_level is None else raw_level)-physics_level,2),'potential_solar_energy_wh':summary['solar_energy_wh'],
            'stored_energy_gain_wh':round(energy-battery*team.battery_capacity_wh/100,2),
            'best_charging_window':summary['best_charging_window'],'charging_intervals':rows,'learning_intervals':learning,
            'limitations':'Independent physics reference, not an accuracy measurement. Assumes zero charging-mode load and fixed derating, no taper or standby drain; no charging during learning. Afternoon trajectory starts from the guarded planning estimate and is not a measured schedule.'}
