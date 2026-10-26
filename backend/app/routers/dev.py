"""Development helpers — seed demo data. Remove or protect in production."""
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api/dev", tags=["dev"])

# Demo area: Chao Phraya near Nakhon Sawan
STATIONS = [
    ("C.2", "Nakhon Sawan", 100.1187, 15.6950),
    ("C.13", "Chai Nat Dam", 100.1830, 15.1600),
]


@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    if db.scalar(select(models.Dataset).limit(1)):
        return {"status": "already seeded"}

    wl = models.Dataset(name="Water level (observed)", series_type="time", unit="m MSL", source="demo")
    bld = models.Dataset(name="Buildings", series_type="feature", description="LOD 1–4 demo buildings")
    flood = models.Dataset(name="Flood depth", series_type="raster", unit="m")
    db.add_all([wl, bld, flood])

    stations = [models.Station(code=c, name=n, geom=from_shape(Point(x, y), 4326)) for c, n, x, y in STATIONS]
    db.add_all(stations)
    db.flush()

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for i, st in enumerate(stations):
        for h in range(24 * 7, -1, -1):
            t = now - timedelta(hours=h)
            v = 20 + i * 2 + 1.5 * math.sin(h / 12) + (24 * 7 - h) * 0.004
            db.add(models.TimeSeriesValue(dataset_id=wl.id, station_id=st.id, t=t, value=round(v, 3)))

    # grid of demo buildings with LOD 1..4
    x0, y0 = 100.120, 15.700
    for i in range(8):
        for j in range(8):
            x, y = x0 + i * 0.0006, y0 + j * 0.0006
            db.add(models.Feature(
                dataset_id=bld.id, name=f"B-{i}-{j}",
                geom=from_shape(box(x, y, x + 0.0004, y + 0.0004), 4326),
                lod=(i + j) % 4 + 1, height=3 + ((i * j) % 6) * 3,
            ))

    for d in range(3):
        db.add(models.RasterFrame(dataset_id=flood.id, t=now - timedelta(days=d),
                                  uri=f"s3://cfm-demo/flood_depth_{d}.tif"))
    db.commit()
    return {"status": "seeded", "datasets": [wl.id, bld.id, flood.id]}


@router.post("/seed-response")
def seed_response(reset: bool = False, db: Session = Depends(get_db)):
    """Sample incidents, compensation claims and photos for the Incident and Compensation tabs.

    reset=true deletes ALL incidents, claims and photos first (development only).
    """
    from app.services import sample_data

    if reset:
        sample_data.reset(db)
    elif db.scalar(select(models.Incident).limit(1)):
        return {"status": "already seeded", "hint": "POST /api/dev/seed-response?reset=true to replace with fresh samples"}
    return sample_data.seed(db)
