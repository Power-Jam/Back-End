from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
ARTIFACTS = ROOT / 'artifacts'

@dataclass(frozen=True)
class Settings:
    location: str
    latitude: float
    longitude: float
    timezone: str
    battery_capacity_wh: float
    panel_rated_w: float
    panel_derate: float
    idle_w: float
    active_w: float
    charge_efficiency: float
    discharge_efficiency: float
    reserve_pct: float
    warning_pct: float
    lesson_start_hour: int
    lesson_end_hour: int

    def __post_init__(self):
        ZoneInfo(self.timezone)
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError('Invalid coordinates')
        if not (self.battery_capacity_wh > 0 and self.panel_rated_w > 0 and 0 <= self.idle_w <= self.active_w):
            raise ValueError('Invalid battery/panel/load ratings')
        if not all(0 < x <= 1 for x in (self.panel_derate, self.charge_efficiency, self.discharge_efficiency)):
            raise ValueError('Efficiencies must be in (0, 1]')
        if not 0 < self.reserve_pct < self.warning_pct < 100:
            raise ValueError('Invalid reserve or warning threshold')
        if not 0 <= self.lesson_start_hour < self.lesson_end_hour <= 24:
            raise ValueError('Invalid lesson schedule')

def load_settings(path=ROOT / 'config.json') -> Settings:
    return Settings(**json.loads(Path(path).read_text(encoding='utf-8')))
