"""Retrieve TTN historical uplinks, retaining original timestamps and provenance."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import requests
from .config import DATA


def parse_storage(text, device, field='battery_percent'):
    readings = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith((':','event:', 'id:')):
            continue
        if line.startswith('data:'):
            line = line[5:].strip()
        wrapper = json.loads(line)
        message = wrapper.get('result', {})
        try:
            if message['end_device_ids']['device_id'] != device:
                continue
            raw = message['uplink_message']['decoded_payload'][field]
            value = float(raw)
            timestamp = message['received_at']
            stamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if isinstance(raw, bool) or not math.isfinite(value) or not 0 <= value <= 100 or stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
                continue
            readings.append({'device_id':device, 'battery_pct':value, 'timestamp':timestamp, 'source':'TTN historical storage'})
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            continue
    return readings


def fetch_storage(device='scb-5000', application='scb-5000', last='12h', path=None):
    key = os.getenv('TTN_API_KEY','').strip()
    if not key:
        raise ValueError('Set TTN_API_KEY privately in this terminal first.')
    path = Path(path or DATA/'ttn_historical.json')
    response = requests.get(f'https://eu1.cloud.thethings.network/api/v3/as/applications/{application}/packages/storage/uplink_message',headers={'Authorization':'Bearer '+key,'Accept':'text/event-stream'},params={'last':last},timeout=(10,60))
    response.raise_for_status()
    new = parse_storage(response.text, device, os.getenv('TTN_BATTERY_FIELD','battery_percent'))
    old = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else []
    if not isinstance(old,list):
        raise ValueError('Existing historical file is not a JSON list; refusing to overwrite.')
    merged = {(r['device_id'],r['timestamp']):r for r in old}
    merged.update({(r['device_id'],r['timestamp']):r for r in new})
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(sorted(merged.values(),key=lambda r:r['timestamp']),indent=2),encoding='utf-8'); tmp.replace(path)
    return len(new),len(merged),path
