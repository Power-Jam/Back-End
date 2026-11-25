"""TTN MQTT collector; credentials supplied only via environment variables."""
import json, os, sqlite3, math
from datetime import datetime, timezone
from .config import DATA
DB=DATA/'battery_telemetry.sqlite3'
def connect_db(path=DB):
    con=sqlite3.connect(path,timeout=10)
    con.execute('CREATE TABLE IF NOT EXISTS observations (device_id TEXT NOT NULL, timestamp TEXT NOT NULL, battery_pct REAL NOT NULL, device_state TEXT, PRIMARY KEY(device_id,timestamp))')
    return con

def ingest(message,path=DB,battery_field='battery_pct',expected_device=None):
    device=message['end_device_ids']['device_id']; decoded=message['uplink_message']['decoded_payload']
    if not isinstance(device,str) or not device or (expected_device and device!=expected_device): raise ValueError('Unexpected device ID')
    raw=decoded[battery_field]
    if isinstance(raw,bool): raise ValueError('Battery must be a number')
    battery=float(raw)
    if not math.isfinite(battery) or not 0<=battery<=100: raise ValueError('Battery percentage outside 0–100')
    ts=datetime.fromisoformat(message['received_at'].replace('Z','+00:00'))
    if ts.tzinfo is None: raise ValueError('Missing timestamp timezone')
    ts=ts.astimezone(timezone.utc).isoformat(); state=decoded.get('device_state'); state=str(state) if state is not None else None
    with connect_db(path) as con: con.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?)',(device,ts,battery,state))
    return {'device_id':device,'timestamp':ts,'battery_pct':battery,'device_state':state}

def latest(device,path=DB,max_age_minutes=15):
    with connect_db(path) as con: row=con.execute('SELECT * FROM observations WHERE device_id=? ORDER BY timestamp DESC LIMIT 1',(device,)).fetchone()
    if not row: raise ValueError('No TTN battery measurement for this device')
    result=dict(zip(['device_id','timestamp','battery_pct','device_state'],row))
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(result['timestamp'])).total_seconds()/60
    if not 0<=age<=max_age_minutes: raise ValueError('Battery measurement stale or future-dated; wait for a new uplink')
    return result

def export_csv(path=DB):
    import pandas as pd
    with connect_db(path) as con: df=pd.read_sql_query('SELECT * FROM observations ORDER BY device_id,timestamp',con)
    target=DATA/'battery_telemetry.csv';df.to_csv(target,index=False);return target

def listen():
    import paho.mqtt.client as mqtt
    names=['TTN_HOST','TTN_USERNAME','TTN_API_KEY','TTN_DEVICE_ID']
    missing=[n for n in names if not os.getenv(n)]
    if missing: raise ValueError('Missing environment variables: '+', '.join(missing))
    host,user,key,device=[os.environ[n] for n in names]; field=os.getenv('TTN_BATTERY_FIELD','battery_pct')
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2);client.username_pw_set(user,key);client.tls_set()
    topic=f'v3/{user}/devices/{device}/up'
    def on_connect(c,u,flags,reason,props):
        if reason==0: c.subscribe(topic,qos=0); print('Connected; listening for',device,flush=True)
        else: print('TTN connection rejected:',reason,flush=True)
    def on_message(c,u,msg):
        try: print('Saved:',ingest(json.loads(msg.payload),battery_field=field,expected_device=device),flush=True)
        except (ValueError,KeyError,TypeError,OverflowError) as exc: print('Rejected uplink:',type(exc).__name__,str(exc),flush=True)
    client.on_connect=on_connect;client.on_message=on_message;client.connect(host,8883,60);client.loop_forever()
