import json
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
from energy_ai.api import create_app
from energy_ai.storage import parse_storage,fetch_storage

def test_model_availability(monkeypatch):
    def load(source):
        if source!='synthetic_demo': raise ValueError('Not trained')
        return {}
    monkeypatch.setattr('energy_ai.api.load_daily',load)
    with TestClient(create_app(bundle={'source':'synthetic_demo','report':{}})) as c:
        d=c.get('/api/daily/models').json()
        assert d['synthetic_demo']['available'] and not d['team_mock']['available'] and not d['measured']['available']
        assert 'Prototype model' in c.get('/').text

def test_storage_download_and_preserve(monkeypatch,tmp_path):
    stamp=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    message={'result':{'end_device_ids':{'device_id':'scb-5000'},'received_at':stamp,'uplink_message':{'decoded_payload':{'battery_percent':3}}}}
    text=json.dumps(message)+'\n'+json.dumps({'result':{}})+'\n'
    assert len(parse_storage(text,'scb-5000'))==1
    assert parse_storage(text,'other')==[]
    path=tmp_path/'history.json'; path.write_text(json.dumps([{'device_id':'scb-5000','timestamp':'2025-01-01T00:00:00Z','battery_pct':40}]))
    class Response:
        def raise_for_status(self): pass
    r=Response();r.text=text
    monkeypatch.setenv('TTN_API_KEY','test-only-not-real')
    monkeypatch.setattr('energy_ai.storage.requests.get',lambda *a,**kw:r)
    assert fetch_storage(path=path)[:2]==(1,2)
    assert fetch_storage(path=path)[:2]==(1,2)
    assert json.loads(path.read_text())[-1]['battery_pct']==3

def test_bundled_team_dataset():
    import pandas as pd
    from energy_ai.config import DATA
    from energy_ai.daily import team_mock_windows, clean_daily
    raw=pd.read_csv(DATA/'device_sessions_hourly_mock_long.csv')
    assert len(raw)==8760 and raw.date.nunique()==365
    assert not raw.isna().any().any() and not raw.duplicated().any()
    windows=clean_daily(team_mock_windows(raw))
    assert len(windows)==2080 and windows.date.nunique()==260
