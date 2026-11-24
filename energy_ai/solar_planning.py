"""Summarise forecast intervals, not a new ML model or charging controller."""
from collections import defaultdict
import pandas as pd


def daily_solar_summary(intervals, charge_by_local=None):
    """Use unrounded interval values; intervals are in local time.

    The best opportunity is the remaining interval with the largest expected
    increase in stored energy under the existing usage plan. No external
    charging or schedule optimisation is assumed. Ties favour earlier times.
    """
    days = defaultdict(list)
    for row in intervals:
        days[pd.Timestamp(row['start_local']).date().isoformat()].append(row)
    summaries = []
    for date, rows in days.items():
        best = max(rows, key=lambda r: r['battery_gain_wh'])
        has_gain = best['battery_gain_wh'] > 1e-6
        window = None
        if has_gain:
            window = {k: best[k] for k in ('start_local', 'end_local')}
            window.update({k: round(best[k], 3) for k in (
                'solar_w', 'load_w', 'net_power_w', 'battery_gain_wh')})
        reason = ('positive_battery_gain' if has_gain else
                  'no_solar_surplus' if all(r['net_power_w'] <= 0 for r in rows)
                  else 'no_available_battery_gain')
        summaries.append({
            'local_date': date,
            'coverage_start_local': rows[0]['start_local'],
            'coverage_end_local': rows[-1]['end_local'],
            'coverage_hours': round(sum(r['duration_hours'] for r in rows), 3),
            'solar_energy_wh': round(sum(r['solar_w'] * r['duration_hours'] for r in rows), 2),
            'sunlight_energy_wh_m2': round(sum(r['radiation_w_m2'] * r['duration_hours'] for r in rows), 2),
            'peak_radiation_w_m2': round(max(r['radiation_w_m2'] for r in rows), 2),
            'peak_solar_w': round(max(r['solar_w'] for r in rows), 2),
            'best_charging_window': window,
            'charging_opportunity': reason,
            'warning_before_or_at_best_window': bool(window and charge_by_local and
                pd.Timestamp(charge_by_local) <= pd.Timestamp(window['start_local'])),
        })
    return summaries
