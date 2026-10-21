from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api/reports", tags=["report & access"])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    by_type = dict(
        db.execute(select(models.Dataset.series_type, func.count()).group_by(models.Dataset.series_type)).all()
    )
    latest_obs = db.scalar(select(func.max(models.TimeSeriesValue.t)))
    return {
        "datasets": {k.value: v for k, v in by_type.items()},
        "stations": db.scalar(select(func.count()).select_from(models.Station)),
        "scenarios": db.scalar(select(func.count()).select_from(models.Scenario)),
        "latest_observation": latest_obs,
    }
