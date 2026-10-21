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
def seed_response(db: Session = Depends(get_db)):
    """Sample incidents and compensation claims so the Incident and Compensation tabs have content."""
    if db.scalar(select(models.Incident).limit(1)):
        return {"status": "already seeded"}
    now = datetime.now(timezone.utc)
    incs = [
        models.Incident(title="Bank overflow at Chai Nat town", kind="overflow", severity=3, status="active",
                        province="ชัยนาท", amphoe="เมืองชัยนาท", households_affected=420, area_rai=3100,
                        description="River above right bank near the Chai Nat dam; sandbag line along the market road.",
                        geom=from_shape(Point(100.1270, 15.1850), 4326), started_at=now - timedelta(days=2)),
        models.Incident(title="Paddy inundation, Phayuha Khiri", kind="inundation", severity=2, status="active",
                        province="นครสวรรค์", amphoe="พยุหะคีรี", households_affected=150, area_rai=5200,
                        description="Low-lying rice fields flooded after the third rain event this week.",
                        geom=from_shape(Point(100.1360, 15.4560), 4326), started_at=now - timedelta(days=4)),
        models.Incident(title="Embankment seep, Mueang Nakhon Sawan", kind="breach", severity=1, status="receding",
                        province="นครสวรรค์", amphoe="เมืองนครสวรรค์", households_affected=35, area_rai=180,
                        description="Seepage under the flood wall at Pak Nam Pho; pumps running.",
                        geom=from_shape(Point(100.1300, 15.7000), 4326), started_at=now - timedelta(days=9)),
    ]
    db.add_all(incs)
    db.flush()
    statuses = ["submitted", "surveyed", "approved", "paid", "submitted", "surveyed", "approved", "rejected"]
    types = ["crops", "house", "crops", "livestock", "crops", "house", "fishery", "crops"]
    n = 0
    for inc in incs:
        for i in range(8 if inc.severity > 1 else 3):
            st = statuses[(i + inc.id) % len(statuses)]
            est = round(4000 + ((i * 7919 + inc.id * 104729) % 46000), -2)
            db.add(models.CompensationClaim(
                incident_id=inc.id, claimant=f"Household {inc.id:02d}-{i + 1:03d}", village=f"หมู่ {i % 9 + 1}",
                damage_type=types[i % len(types)], area_rai=round(2 + (i * 3.7) % 25, 1), estimated_thb=est,
                approved_thb=round(est * 0.85, -2) if st in ("approved", "paid") else None, status=st,
                submitted_at=inc.started_at + timedelta(hours=6 + i * 5),
            ))
            n += 1
    db.commit()
    return {"status": "seeded", "incidents": len(incs), "claims": n}
