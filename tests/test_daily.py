import json
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from energy_ai.config import load_settings
from energy_ai.daily import synthetic_days, fit_daily, clean_daily, advice, lesson_count, prepare_real_windows, learning_counts, team_mock_windows
from energy_ai.demo import demo_weather, training_data
from energy_ai.models import fit
from energy_ai.api import create_app
from energy_ai.telemetry import ingest,latest

@pytest.fixture(scope='module')
def cfg(): return load_settings()
@pytest.fixture(scope='module')
def daily(cfg): return fit_daily(synthetic_days(cfg,days=100),cfg)

def test_lessons():
    assert int(lesson_count(100,0))==32
    assert int(lesson_count(86,20,8))==23
    assert int(lesson_count(20,20))==0
    assert int(lesson_count(22,20))==0
    assert int(lesson_count(100,20))==32

def test_daily_dataset(cfg):
    d=clean_daily(synthetic_days(cfg,20));assert len(d)==160
    assert d.groupby('date').start_level.nunique().eq(1).all()
    assert (d.start_level>=d.morning_level).all()
    with pytest.raises(ValueError,match='Duplicate'): clean_daily(pd.concat([d,d.iloc[:1]]))

def test_daily_model(daily):
    r=daily['report']; assert r['split']['train_days']==60 and r['split']['test_days']==20
    assert r['split']['train_end']<r['split']['test_start']; assert len(r['test_errors'])==160
    assert r['selected'] in r['test_08']
    assert any(x['model']=='forest_gain' for x in r['cv'])

def test_daily_advice(cfg,daily):
    d=advice(cfg,daily,41,'demo','sunny',8,now='2026-11-25T06:00Z')
    assert d['learning_start_local'].endswith('14:00:00+02:00')
    assert len(d['hourly_sunlight'])==6 and d['available_learning_minutes']==5*d['recommended_lessons']
    assert 41<=d['predicted_start_level']<=100
    assert d['recommended_lessons']==int(lesson_count(d['planning_start_level'],10,d['margin_pp']))
    assert d['model_source']=='synthetic_demo'

def test_live_window(cfg,daily,monkeypatch):
    times=pd.date_range('2026-11-25T07:00Z',periods=8,freq='h')
    monkeypatch.setattr('energy_ai.daily.read_forecast',lambda c:(demo_weather(times,c),{'fetched_at':'2026-11-25T06:00Z'}))
    d=advice(cfg,daily,41,'live',now='2026-11-25T06:15Z');assert d['prediction_time_local'].endswith('09:00:00+02:00');assert len(d['hourly_sunlight'])==5
    with pytest.raises(ValueError,match='Live morning'): advice(cfg,daily,41,'live',now='2026-11-25T14:00Z')

def message(value=41,age=0):
    return {'end_device_ids':{'device_id':'test'},'received_at':(datetime.now(timezone.utc)-timedelta(minutes=age)).isoformat(),'uplink_message':{'decoded_payload':{'battery_pct':value,'device_state':'charging'}}}

def test_ttn(tmp_path):
    db=tmp_path/'test.sqlite'; m=message();ingest(m,db);ingest(m,db)
    assert latest('test',db)['battery_pct']==41
    with pytest.raises(ValueError): ingest(message(101),db)
    with pytest.raises(ValueError,match='stale'): ingest(message(40,60),tmp_path/'stale.sqlite');latest('test',tmp_path/'stale.sqlite')
    with pytest.raises(ValueError,match='Unexpected'): ingest(m,db,expected_device='other')

def test_prepare_real(cfg):
    times=pd.date_range('2026-11-25T04:00Z','2026-11-25T12:00Z',freq='15min')
    logs=pd.DataFrame({'device_id':'test','timestamp':times,'battery_pct':np.linspace(20,80,len(times)),'device_state':'charging'})
    weather=demo_weather(pd.date_range('2026-11-25T05:00Z','2026-11-25T12:00Z',freq='h'),cfg)
    rows,skipped=prepare_real_windows(cfg,logs,weather,'test',['2026-11-25']);assert len(rows)==8 and not skipped and rows.start_level.eq(80).all()
    logs.loc[5,'device_state']='learning';rows,skipped=prepare_real_windows(cfg,logs,weather,'test',['2026-11-25']);assert rows.empty and skipped

def test_daily_api(cfg,daily,monkeypatch):
    monkeypatch.setattr('energy_ai.api.load_daily',lambda source:daily)
    old=fit(training_data(cfg,days=20),cfg)
    with TestClient(create_app(cfg,bundle=old)) as client:
        assert client.get('/daily').status_code==200
        assert client.get('/api/daily/metrics').json()['selected']==daily['report']['selected']
        assert client.get('/api/daily/reliability').json()['test_days']==20
        r=client.post('/advice',json={'battery_pct':41,'scenario':'sunny'});assert r.status_code==200 and 'recommended_lessons' in r.json()
        assert client.post('/advice',json={'battery_pct':101}).status_code==422
        assert client.post('/advice',json={}).status_code==422
        assert client.get('/api/lessons/actual?battery_pct=80').json()['recommended_lessons']==28


def test_session_grouping():
    assert learning_counts(100)['recommended_sessions']==8
    assert learning_counts(80,2)['recommended_lessons']==27
    assert learning_counts(80,2)['recommended_sessions']==6
    assert learning_counts(80,2)['additional_lessons']==3
    assert learning_counts(10)['recommended_lessons']==0


def test_reliability(cfg,daily):
    r=daily['report']; assert r['split']['selection_end']<r['split']['calibration_start']<=r['split']['calibration_end']<r['split']['test_start']
    q=r['reliability_by_hour']['8']; assert q['calibration_days']==10 and q['test_days']==20
    assert q['radius_pp']>=0 and 0<=q['test_interval_coverage']<=1
    d=advice(cfg,daily,41,'demo','sunny',8,now='2026-11-25T06:00Z'); q=d['prediction_reliability']
    assert 0<=q['lower_battery_pct']<=d['predicted_start_level']<=q['upper_battery_pct']<=100
    assert not q['field_validated']
    assert d['recommended_sessions']*4+d['additional_lessons']==d['recommended_lessons']


def test_team_import():
    rows=[]
    for date in pd.bdate_range('2026-01-01',periods=20):
        for h in range(5,14):
            rows.append(dict(timestamp_local=str(date+pd.Timedelta(hours=h)),day_type='school_weekday',hour=h,battery_pct=20+(h-5)*5,use_min=0,solar_radiation_wm2=300,cloud_cover_pct=30,temperature_c=20))
    d=team_mock_windows(pd.DataFrame(rows));assert len(d)==160 and d.start_level.eq(60).all()
    assert d[d.prediction_hour.eq(8)].morning_level.eq(30).all()


def test_teacher_limit_exhaustive():
    from energy_ai.daily import MAX_SESSIONS, MAX_LESSONS, MAX_LEARNING_MIN, learning_policy
    assert (MAX_SESSIONS,MAX_LESSONS,MAX_LEARNING_MIN)==(8,32,160)
    assert learning_policy()['unallocated_window_minutes']==20
    for level in np.linspace(0,100,1001):
        for margin in (0,2,5,8,15,100):
            d=learning_counts(level,margin)
            assert 0<=d['recommended_lessons']<=32
            assert 0<=d['recommended_sessions']<=8
            assert d['recommended_sessions']*4+d['additional_lessons']==d['recommended_lessons']
            assert d['available_learning_minutes']<=160
            assert d['max_lessons']==32 and d['max_sessions']==8
    assert learning_counts(100,0)['recommended_lessons']==32
    assert learning_counts(100,0)['additional_lessons']==0


def test_teacher_limit_api(cfg,daily,monkeypatch):
    monkeypatch.setattr('energy_ai.api.load_daily',lambda source:daily)
    old=fit(training_data(cfg,days=20),cfg)
    with TestClient(create_app(cfg,bundle=old)) as client:
        policy=client.get('/api/daily/config').json()
        assert policy['max_sessions']==8 and policy['max_lessons']==32
        actual=client.get('/api/lessons/actual?battery_pct=100').json()
        assert actual['recommended_sessions']==8 and actual['recommended_lessons']==32
        for scenario in ('sunny','cloudy','mixed'):
            response=client.post('/advice',json={'battery_pct':100,'scenario':scenario})
            assert response.status_code==200
            d=response.json()
            assert d['recommended_sessions']<=8 and d['recommended_lessons']<=32
            assert d['max_learning_minutes']==160
            assert d['prediction_reliability']['field_validated'] is False
        q=client.get('/api/daily/reliability').json()
        assert q['learning_policy']['max_lessons']==32
