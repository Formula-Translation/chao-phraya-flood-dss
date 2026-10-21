"""Prediction tool — placeholder.

Takes the observed series up to `base_time` ("TODAY") and produces three
scenario branches (low / expected / high). Swap `run_model` for the real
engine (MIKE+ run, ML model, rating curve, etc.) — the API contract stays the same.
"""
from datetime import datetime, timedelta

# spread multiplier around the expected trend: low below, high above
SCENARIOS = {
    "Scenario 1 – low": -1.0,
    "Scenario 2 – expected": 0.0,
    "Scenario 3 – high": 1.0,
}


def run_model(
    history: list[tuple[datetime, float]], base_time: datetime, horizon_hours: int
) -> dict[str, list[tuple[datetime, float]]]:
    if not history:
        raise ValueError("No observed data before base_time")

    last_t, last_v = history[-1]
    # trend (m per hour) over the last 24 hours, whatever the sampling interval
    window = [(t, v) for t, v in history if t >= last_t - timedelta(hours=24)]
    hours = max((window[-1][0] - window[0][0]).total_seconds() / 3600, 1)
    slope = (window[-1][1] - window[0][1]) / hours

    # uncertainty band widens with lead time
    spread = max(abs(slope) * 0.8, 0.01)

    out: dict[str, list[tuple[datetime, float]]] = {}
    for name, factor in SCENARIOS.items():
        series = []
        for h in range(1, horizon_hours + 1):
            t = base_time + timedelta(hours=h)
            series.append((t, round(last_v + slope * h + factor * spread * h, 3)))
        out[name] = series
    return out
