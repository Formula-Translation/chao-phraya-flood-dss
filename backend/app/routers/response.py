"""Stage 2 (incident) and stage 3 (compensation) endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api", tags=["incident & compensation"])
I, C = models.Incident, models.CompensationClaim


def _incidents(db: Session, where=None) -> list[schemas.IncidentOut]:
    claims = select(C.incident_id, func.count().label("n")).group_by(C.incident_id).subquery()
    cols = [c for c in I.__table__.columns if c.name != "geom"]
    q = (
        select(*cols, func.ST_X(I.geom).label("lon"), func.ST_Y(I.geom).label("lat"),
               func.coalesce(claims.c.n, 0).label("claims"))
        .outerjoin(claims, claims.c.incident_id == I.id)
        .order_by(I.status != "active", I.severity.desc(), I.started_at.desc())
    )
    if where is not None:
        q = q.where(where)
    return [schemas.IncidentOut(**r) for r in db.execute(q).mappings()]


@router.get("/incidents", response_model=list[schemas.IncidentOut])
def list_incidents(db: Session = Depends(get_db)):
    return _incidents(db)


@router.post("/incidents", response_model=schemas.IncidentOut, status_code=201)
def create_incident(body: schemas.IncidentIn, db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"lon", "lat"})
    inc = I(**data)
    if body.lon is not None and body.lat is not None:
        inc.geom = from_shape(Point(body.lon, body.lat), 4326)
    elif body.station_id:
        st = db.get(models.Station, body.station_id)
        if st is not None:
            inc.geom = st.geom
            inc.province = inc.province or st.province
            inc.amphoe = inc.amphoe or st.amphoe
    db.add(inc)
    db.commit()
    return _incidents(db, I.id == inc.id)[0]


@router.patch("/incidents/{incident_id}", response_model=schemas.IncidentOut)
def update_incident(incident_id: int, body: schemas.IncidentPatch, db: Session = Depends(get_db)):
    inc = db.get(I, incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(inc, k, v)
    if body.status == "closed" and inc.ended_at is None:
        inc.ended_at = datetime.now(timezone.utc)
    db.commit()
    return _incidents(db, I.id == incident_id)[0]


@router.get("/claims", response_model=list[schemas.ClaimOut])
def list_claims(incident_id: int | None = None, db: Session = Depends(get_db)):
    q = select(C).order_by(C.submitted_at.desc())
    if incident_id:
        q = q.where(C.incident_id == incident_id)
    return db.scalars(q).all()


@router.post("/claims", response_model=schemas.ClaimOut, status_code=201)
def create_claim(body: schemas.ClaimIn, db: Session = Depends(get_db)):
    inc = db.get(I, body.incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    claim = C(**body.model_dump(), province=inc.province, amphoe=inc.amphoe)
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


@router.patch("/claims/{claim_id}", response_model=schemas.ClaimOut)
def update_claim(claim_id: int, body: schemas.ClaimPatch, db: Session = Depends(get_db)):
    claim = db.get(C, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(claim, k, v)
    db.commit()
    db.refresh(claim)
    return claim


@router.get("/compensation/summary")
def compensation_summary(db: Session = Depends(get_db)):
    rows = db.execute(
        select(C.status, func.count(), func.coalesce(func.sum(C.estimated_thb), 0),
               func.coalesce(func.sum(C.approved_thb), 0)).group_by(C.status)
    ).all()
    by_status = {s: {"count": n, "estimated_thb": float(e), "approved_thb": float(a)} for s, n, e, a in rows}
    return {
        "by_status": by_status,
        "claims": sum(v["count"] for v in by_status.values()),
        "estimated_thb": sum(v["estimated_thb"] for v in by_status.values()),
        "approved_thb": sum(v["approved_thb"] for k, v in by_status.items() if k in ("approved", "paid")),
        "paid_thb": by_status.get("paid", {}).get("approved_thb", 0.0),
    }
