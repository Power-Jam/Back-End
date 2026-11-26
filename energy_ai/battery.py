"""Energy balance over an hour (or fraction). All powers are average W."""
from .config import Settings

def advance(energy_wh, solar_w, load_w, hours, cfg: Settings):
    net = (solar_w-load_w)*hours
    delta = net*cfg.charge_efficiency if net>=0 else net/cfg.discharge_efficiency
    raw = energy_wh+delta
    return max(0., min(cfg.battery_capacity_wh,raw)), max(0.,-raw), max(0.,raw-cfg.battery_capacity_wh)

def decision(pct, reserve, warning):
    if pct <= reserve:
        return 'STOP_OR_SAVE', 'Save your work and stop using the device soon if charging is unavailable.'
    if pct <= warning:
        return 'CHARGE_SOON', 'Charge the battery when possible or reduce usage.'
    return 'CONTINUE', 'Enough estimated energy to continue learning.'
