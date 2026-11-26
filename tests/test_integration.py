import pytest
from fastapi.testclient import TestClient
from energy_ai.config import load_settings
from energy_ai.daily import fit_daily, synthetic_days, advice
from energy_ai.demo import training_data
from energy_ai.models import fit
from energy_ai.api import create_app

@pytest.fixture(scope='module')
def cfg(): return load_settings()
@pytest.fixture(scope='module')
def daily(cfg): return fit_daily(synthetic_days(cfg,days=60),cfg)
@pytest.fixture(scope='module')
def old(cfg): return fit(training_data(cfg,days=20),cfg)

@pytest.mark.parametrize('battery,scenario',[(0,'cloudy'),(41,'sunny'),(100,'mixed')])
def test_same_window(cfg,daily,battery,scenario):
    d=advice(cfg,daily,battery,'demo',scenario,8,now='2026-11-25T06:00Z'); a=d['energy_analysis']
    assert a['profile']['battery_wh']==180 and a['profile']['panel_w']==25
    assert a['ml_start_level']==d['predicted_start_level']
    assert len(a['charging_intervals'])==len(d['hourly_sunlight'])==6
    assert a['charging_intervals'][-1]['end_local']==d['learning_start_local']
    assert all(r['load_w']==0 and r['mode']=='charging' for r in a['charging_intervals'])
    assert [round(r['radiation_w_m2'],1) for r in a['charging_intervals']]==[r['radiation_w_m2'] for r in d['hourly_sunlight']]
    assert len(a['learning_intervals'])==d['recommended_lessons']<=32
    assert all(r['solar_w']==0 and r['session']<=8 and r['end_local']<=d['learning_end_local'] for r in a['learning_intervals'])
    assert all(0<=r['battery_pct']<=100 for r in a['charging_intervals']+a['learning_intervals'])
    assert a['stored_energy_gain_wh']<=a['potential_solar_energy_wh']+.02
    if a['learning_intervals']: assert a['learning_intervals'][-1]['battery_pct']==pytest.approx(d['estimated_remaining_pct'],abs=.01)
    if battery==100: assert a['best_charging_window'] is None

def test_integrated_api(cfg,daily,old,monkeypatch):
    monkeypatch.setattr('energy_ai.api.load_daily',lambda source:daily)
    with TestClient(create_app(cfg,bundle=old)) as c:
        assert 'Integrated hourly energy analysis' in c.get('/').text
        assert 'Integrated hourly energy analysis' in c.get('/daily').text
        assert 'Legacy research dashboard' in c.get('/research').text
        assert c.get('/api/config').json()['profile']=='legacy_research'
        assert c.get('/api/forecast?hours=6').status_code==200
        r=c.post('/advice',json={'battery_pct':41,'scenario':'sunny'});assert r.status_code==200
        assert 'energy_analysis' in r.json() and 'prediction_reliability' in r.json()
