import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api", tags=["data"])


def _get_dataset(db: Session, dataset_id: int) -> models.Dataset:
    ds = db.get(models.Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds


# ---------- Datasets ----------
@router.get("/datasets", response_model=list[schemas.DatasetOut])
def list_datasets(series_type: models.SeriesType | None = None, db: Session = Depends(get_db)):
    q = select(models.Dataset).order_by(models.Dataset.name)
    if series_type:
        q = q.where(models.Dataset.series_type == series_type)
    return db.scalars(q).all()


@router.post("/datasets", response_model=schemas.DatasetOut, status_code=201)
def create_dataset(body: schemas.DatasetIn, db: Session = Depends(get_db)):
    ds = models.Dataset(**body.model_dump())
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


# ---------- Time series ----------
@router.get("/datasets/{dataset_id}/timeseries", response_model=list[schemas.TSPoint])
def get_timeseries(
    dataset_id: int,
    station_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    _get_dataset(db, dataset_id)
    m = models.TimeSeriesValue
    q = select(m.t, m.value).where(m.dataset_id == dataset_id, m.station_id == station_id)
    if start:
        q = q.where(m.t >= start)
    if end:
        q = q.where(m.t <= end)
    return [schemas.TSPoint(t=t, value=v) for t, v in db.execute(q.order_by(m.t))]


@router.post("/datasets/{dataset_id}/timeseries")
def upload_timeseries(dataset_id: int, body: schemas.TSUpload, db: Session = Depends(get_db)):
    """DATA UPDATE: upsert observations for one station."""
    ds = _get_dataset(db, dataset_id)
    if ds.series_type != models.SeriesType.time:
        raise HTTPException(400, "Dataset is not a time series dataset")
    station = db.scalar(select(models.Station).where(models.Station.code == body.station_code))
    if not station:
        raise HTTPException(404, f"Station {body.station_code} not found")

    rows = [{"dataset_id": dataset_id, "station_id": station.id, "t": p.t, "value": p.value} for p in body.points]
    if rows:
        stmt = insert(models.TimeSeriesValue).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["dataset_id", "station_id", "t"], set_={"value": stmt.excluded.value}
        )
        db.execute(stmt)
        db.commit()
    return {"upserted": len(rows)}


# ---------- Features (spatial + temporal) ----------
@router.get("/datasets/{dataset_id}/features")
def get_features(dataset_id: int, t: datetime | None = None, max_lod: int = 4, db: Session = Depends(get_db)):
    """GeoJSON FeatureCollection of features valid at time `t`."""
    _get_dataset(db, dataset_id)
    f = models.Feature
    q = select(
        f.id, f.name, f.lod, f.height, f.properties, func.ST_AsGeoJSON(f.geom).label("geojson")
    ).where(f.dataset_id == dataset_id, f.lod <= max_lod)
    if t:
        q = q.where(
            or_(f.valid_from.is_(None), f.valid_from <= t),
            or_(f.valid_to.is_(None), f.valid_to > t),
        )
    features = [
        {
            "type": "Feature",
            "id": r.id,
            "geometry": json.loads(r.geojson),
            "properties": {**(r.properties or {}), "name": r.name, "lod": r.lod, "height": r.height},
        }
        for r in db.execute(q)
    ]
    return {"type": "FeatureCollection", "features": features}


# ---------- Rasters ----------
@router.get("/datasets/{dataset_id}/rasters", response_model=list[schemas.RasterOut])
def get_rasters(dataset_id: int, db: Session = Depends(get_db)):
    _get_dataset(db, dataset_id)
    q = select(models.RasterFrame).where(models.RasterFrame.dataset_id == dataset_id).order_by(models.RasterFrame.t)
    return db.scalars(q).all()
