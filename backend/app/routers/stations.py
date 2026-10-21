import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.services import thaiwater

router = APIRouter(prefix="/api", tags=["stations"])

_COLS = [c for c in models.Station.__table__.columns if c.name != "geom"]


def _rows(db: Session, where=None):
    q = select(*_COLS, func.ST_X(models.Station.geom).label("lon"), func.ST_Y(models.Station.geom).label("lat"))
    if where is not None:
        q = q.where(where)
    return [schemas.StationOut(**r) for r in db.execute(q.order_by(models.Station.code)).mappings()]


@router.get("/stations", response_model=list[schemas.StationOut])
def list_stations(db: Session = Depends(get_db)):
    return _rows(db)


@router.get("/stations/{station_id}", response_model=schemas.StationOut)
def get_station(station_id: int, db: Session = Depends(get_db)):
    rows = _rows(db, models.Station.id == station_id)
    if not rows:
        raise HTTPException(404, "Station not found")
    return rows[0]


@router.post("/sync/stations")
async def sync_stations(db: Session = Depends(get_db)):
    """Import / refresh every telemetry station from ThaiWater."""
    try:
        return await asyncio.to_thread(thaiwater.sync_stations, db)
    except Exception as e:  # network, API change…
        raise HTTPException(502, f"ThaiWater sync failed: {e}")


@router.post("/stations/{station_id}/sync-history")
async def sync_history(station_id: int, days: int = 7, db: Session = Depends(get_db)):
    st = db.get(models.Station, station_id)
    if not st:
        raise HTTPException(404, "Station not found")
    try:
        n = await asyncio.to_thread(thaiwater.sync_history, db, st, days)
    except Exception as e:
        raise HTTPException(502, f"ThaiWater history failed: {e}")
    return {"points": n, "dataset_id": thaiwater.dataset(db).id}
