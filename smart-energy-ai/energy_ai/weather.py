"""Open-Meteo adapter. All timestamps are UTC, labelled at interval end."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from .config import DATA, Settings

FIELDS = ['temperature_2m', 'cloud_cover', 'shortwave_radiation', 'direct_radiation', 'sunshine_duration']
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'

def parse_hourly(payload: dict) -> pd.DataFrame:
    if payload.get('error'):
        raise ValueError(payload.get('reason', 'Weather service error'))
    df = pd.DataFrame(payload['hourly']).rename(columns={'time': 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df[['timestamp', *FIELDS]].sort_values('timestamp')
    if df.empty or df.timestamp.duplicated().any():
        raise ValueError('Weather response empty or has duplicate timestamps')
    return df.reset_index(drop=True)

def fetch(settings: Settings, *, start: str | None = None, end: str | None = None, days=7) -> pd.DataFrame:
    if bool(start) != bool(end):
        raise ValueError('Supply both start and end dates')
    params = {'latitude': settings.latitude, 'longitude': settings.longitude,
              'hourly': ','.join(FIELDS), 'timezone': 'UTC'}
    if start:
        params.update(start_date=start, end_date=end)
    else:
        params['forecast_days'] = days
    response = requests.get(ARCHIVE_URL if start else FORECAST_URL, params=params, timeout=(10, 60))
    response.raise_for_status()
    return parse_hourly(response.json())

def save_forecast(settings: Settings) -> Path:
    df = fetch(settings)
    path = DATA / 'cache' / 'pretoria_forecast.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path.with_suffix('.tmp'), index=False)
    path.with_suffix('.tmp').replace(path)
    meta = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'latitude': settings.latitude,
            'longitude': settings.longitude, 'source': 'Open-Meteo forecast API'}
    path.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return path

def read_forecast(settings: Settings, *, max_age_hours=12):
    path = DATA / 'cache' / 'pretoria_forecast.csv'
    if not path.exists() or not path.with_suffix('.json').exists():
        raise ValueError('No forecast cache. Run python -m energy_ai fetch-weather first.')
    meta = json.loads(path.with_suffix('.json').read_text())
    if (meta['latitude'], meta['longitude']) != (settings.latitude, settings.longitude):
        raise ValueError('Cached forecast coordinates differ from current configuration. Refresh weather.')
    age = (pd.Timestamp.now(tz='UTC') - pd.Timestamp(meta['fetched_at'])).total_seconds()/3600
    if not 0 <= age <= max_age_hours:
        raise ValueError('Weather cache is stale or invalid. Run python -m energy_ai fetch-weather again.')
    df = pd.read_csv(path, parse_dates=['timestamp'])
    df['timestamp'] = pd.to_datetime(df.timestamp, utc=True)
    return df, meta
