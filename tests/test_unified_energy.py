from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from energy_ai.config import load_settings
from energy_ai.daily import advice, learning_counts, PROFILE, learning_policy, RESERVE
from energy_ai.api import create_app
import pandas as pd

@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr('energy_ai.daily.predict_candidate',lambda *args: [99.])
    return {'model':None,'report':{'profile':PROFILE,'source':'synthetic_demo','selected':'forest_direct','margin_pp':5,'reserve_pct':RESERVE,'location':load_settings().location,'timezone':load_settings().timezone,'reliability_by_hour':{},'hardware_profile':{'battery_wh':180,'panel_w':25,'start_hour':14,'end_hour':17,'session_minutes':20,'session_drain_pp':10,'lesson_minutes':5,'reserve_pct':10,'max_sessions':8,'max_lessons':32}}}

def test_guard_and_capacity(model):
    d=advice(load_settings(),model,3,'demo','cloudy',13,now='2025-11-25T10:48Z')
    assert d['predicted_start_level']==99
    assert d['planning_start_level']<=3+25/180*100
    assert d['recommended_lessons']==learning_counts(d['planning_start_level'],5)['recommended_lessons']==0
    assert d['battery_based_capacity_at_input']['recommended_lessons']==0
    assert d['engineering_limit_applied']
    assert d['energy_analysis']['planning_start_level']==d['planning_start_level']

def test_historical_replay_and_shared_dashboard(model,monkeypatch):
    monkeypatch.setattr('energy_ai.api.load_daily',lambda source:model)
    monkeypatch.setattr('energy_ai.api.historical_battery',lambda device:{'device_id':device,'battery_pct':3.,'timestamp':'2025-11-25T09:48:34Z','historical':True})
    with TestClient(create_app(bundle={'source':'synthetic_demo','report':{}})) as c:
        assert c.get('/').text==c.get('/energy').text
        assert 'Legacy research dashboard' in c.get('/research').text
        r=c.post('/advice',json={'historical_device_id':'scb-5000','prediction_hour':8})
        assert r.status_code==200,r.text
        d=r.json();assert d['prediction_time_local']=='2025-11-25T12:00:00+02:00'
        assert d['measurement_time_local'].startswith('2025-11-25T11:48')
        assert d['planning_start_level']<=3+2*25/180*100
        assert d['recommended_lessons']<=32
        assert c.get('/api/lessons/actual?battery_pct=30').json()['recommended_lessons']==8
