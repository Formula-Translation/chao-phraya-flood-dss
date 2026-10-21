from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.services.prediction import run_model

router = APIRouter(prefix="/api", tags=["prediction & scenarios"])


@router.post("/prediction/run", response_model=list[schemas.ScenarioOut])
def run_prediction(body: schemas.PredictionRequest, db: Session = Depends(get_db)):
    m = models.TimeSeriesValue
    q = select(m.t, m.value).where(
        m.dataset_id == body.dataset_id, m.station_id == body.station_id, m.value.is_not(None)
    )
    if body.base_time:
        q = q.where(m.t <= body.base_time)
    history = list(db.execute(q.order_by(m.t)).tuples())
    if not history:
        raise HTTPException(400, "No observed data for this dataset/station")

    base_time = body.base_time or history[-1][0]
    results = run_model(history, base_time, body.horizon_hours)

    scenarios = []
    for name, series in results.items():
        sc = models.Scenario(
            name=name, model=body.model, base_time=base_time,
            input_dataset_id=body.dataset_id,
            params={"station_id": body.station_id, "horizon_hours": body.horizon_hours},
        )
        db.add(sc)
        db.flush()
        db.add_all(
            models.ScenarioResult(scenario_id=sc.id, station_id=body.station_id, t=t, value=v)
            for t, v in series
        )
        scenarios.append(sc)
    db.commit()
    return scenarios


@router.get("/scenarios", response_model=list[schemas.ScenarioOut])
def list_scenarios(limit: int = 30, db: Session = Depends(get_db)):
    q = select(models.Scenario).order_by(models.Scenario.created_at.desc(), models.Scenario.id).limit(limit)
    return db.scalars(q).all()


@router.get("/scenarios/{scenario_id}/results", response_model=list[schemas.ScenarioResultOut])
def scenario_results(scenario_id: int, db: Session = Depends(get_db)):
    r = models.ScenarioResult
    rows = db.execute(select(r.t, r.value).where(r.scenario_id == scenario_id).order_by(r.t))
    return [schemas.ScenarioResultOut(t=t, value=v) for t, v in rows]
