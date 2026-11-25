import pandas as pd
import pytest
from fastapi.testclient import TestClient
from energy_ai.config import load_settings
from energy_ai.demo import training_data,demo_weather
from energy_ai.models import fit,clean
from energy_ai.battery import advance,decision
from energy_ai.service import forecast
from energy_ai.api import create_app
from energy_ai.weather import parse_hourly,FIELDS,fetch

@pytest.fixture(scope='module')
def cfg(): return load_settings()
@pytest.fixture(scope='module')
def bundle(cfg): return fit(training_data(cfg,days=20),cfg)

def test_balance(cfg):
    e,_,_=advance(250,100,50,1,cfg);assert e==pytest.approx(295)
    e,_,_=advance(250,0,95,1,cfg);assert e==pytest.approx(150)
    assert advance(490,100,0,1,cfg)[0]==500
    assert advance(10,0,100,1,cfg)[0]==0
    assert decision(10,20,35)[0]=='STOP_OR_SAVE'

def test_weather_parse():
    payload={'hourly':{'time':['2025-01-01T00:00'],**{k:[0] for k in FIELDS}}}
    df=parse_hourly(payload);assert str(df.timestamp.dtype)=='datetime64[ns, UTC]'

def test_weather_http_mock(cfg,monkeypatch):
    def get(url,params,timeout):
        assert 'forecast' in url and params['latitude']==cfg.latitude and params['timezone']=='UTC'
        class R:
            def raise_for_status(self): pass
            def json(self):return {'hourly':{'time':['2025-01-01T00:00'],**{k:[0] for k in FIELDS}}}
        return R()
    monkeypatch.setattr('energy_ai.weather.requests.get',get)
    assert len(fetch(cfg))==1

def test_model_split(bundle):
    r=bundle['report'];assert pd.Timestamp(r['train_end'])<pd.Timestamp(r['test_start'])
    assert r['source']=='synthetic_demo'
    assert set(r['metrics'])=={'solar_w','load_w'}
    for m in r['metrics'].values(): assert m['selected'] in m['test']

def test_invalid_duplicates(cfg):
    df=training_data(cfg,10);df=pd.concat([df,df.iloc[:1]])
    with pytest.raises(ValueError,match='Duplicate'):clean(df)

def test_forecast(cfg,bundle):
    d=forecast(cfg,bundle,65,45,48,'demo','cloudy',now='2026-11-18T12:30Z')
    assert len(d['forecast'])==48 and d['tomorrow_points']==24
    assert all(0<=r['battery_pct']<=100 for r in d['forecast'])
    assert d['model_source']=='synthetic_demo' and 'SIMULATED' in d['weather_source']
    assert d['initial_battery_source'].startswith('manual')
    assert d['forecast'][0]['timestamp']=='2026-11-18T13:00:00+00:00'

def test_low_battery(cfg,bundle):
    d=forecast(cfg,bundle,10,60,6,now='2026-11-18T12:00Z');assert d['hours_to_reserve']==0 and d['status']=='STOP_OR_SAVE'

def test_api(cfg,bundle):
    with TestClient(create_app(cfg,bundle=bundle)) as client:
        assert client.get('/').status_code==200
        assert client.get('/api/health').json()['status']=='ok'
        assert client.get('/api/metrics').status_code==200
        assert client.get('/api/forecast?battery_pct=101').status_code==422
        r=client.get('/api/forecast?hours=6');assert r.status_code==200 and len(r.json()['forecast'])==6

def test_live_weather_cache(cfg,bundle,monkeypatch):
    times=pd.date_range('2026-11-18T13:00Z',periods=8,freq='h')
    monkeypatch.setattr('energy_ai.service.read_forecast',lambda c:(demo_weather(times,c),{'fetched_at':'2026-11-18T12:00Z'}))
    d=forecast(cfg,bundle,65,45,6,'live',now='2026-11-18T12:30Z')
    assert d['weather_source']=='Open-Meteo forecast cache'
    with pytest.raises(ValueError,match='missing'):forecast(cfg,bundle,65,45,12,'live',now='2026-11-18T12:30Z')


def test_solar_daily_summary(cfg,bundle):
    d=forecast(cfg,bundle,50,15,48,'demo','sunny',now='2026-11-18T06:30Z')
    days=d['solar_daily']; rows=d['forecast']
    assert rows[0]['duration_hours']==0.5
    assert sum(day['coverage_hours'] for day in days)==47.5
    assert sum(day['solar_energy_wh'] for day in days)==pytest.approx(sum(r['solar_energy_wh'] for r in rows),abs=0.25)
    for day in days:
        same=[r for r in rows if r['interval_start_local'][:10]==day['local_date']]
        assert day['coverage_end_local']==same[-1]['local_time']
        best=day['best_charging_window']
        if best:
            assert best['battery_gain_wh']==pytest.approx(max(r['battery_gain_wh'] for r in same),abs=0.001)
            assert best['net_power_w']>0
            assert best['start_local'][:10]==day['local_date']
    assert days[0]['best_charging_window'] is not None


def test_solar_no_surplus(cfg,bundle):
    d=forecast(cfg,bundle,10,45,4,'demo','cloudy',now='2026-11-18T18:00Z')
    assert d['status']=='STOP_OR_SAVE'
    assert d['solar_daily'][0]['best_charging_window'] is None
    assert d['solar_daily'][0]['charging_opportunity']=='no_solar_surplus'
    assert d['solar_daily'][0]['solar_energy_wh']==0


def test_solar_window_ranking_and_urgency():
    from energy_ai.solar_planning import daily_solar_summary
    def row(hour,solar,load,gain):
        return {'start_local':f'2026-11-18T{hour:02}:00:00+02:00','end_local':f'2026-11-18T{hour+1:02}:00:00+02:00','duration_hours':1,'solar_w':solar,'load_w':load,'net_power_w':solar-load,'battery_gain_wh':gain,'radiation_w_m2':solar*10}
    rows=[row(10,80,70,9),row(11,65,20,40.5),row(12,90,10,0)]
    d=daily_solar_summary(rows,'2026-11-18T10:30:00+02:00')[0]
    assert d['best_charging_window']['start_local']==rows[1]['start_local']
    assert d['warning_before_or_at_best_window']
    assert d['solar_energy_wh']==235
    assert daily_solar_summary([rows[2]])[0]['charging_opportunity']=='no_available_battery_gain'


def test_solar_api(cfg,bundle):
    with TestClient(create_app(cfg,bundle=bundle)) as client:
        r=client.get('/api/forecast?hours=24&scenario=sunny')
        assert r.status_code==200 and r.json()['solar_daily']
        html=client.get('/energy').text
        assert 'sunChart' in html and 'powerChart' in html and 'renderSolar(d)' in html
