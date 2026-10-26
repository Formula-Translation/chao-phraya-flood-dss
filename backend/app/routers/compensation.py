"""Compensation review: outlier assessments, official rates and photo evidence."""
import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.services import outliers
from app.services import photos as photo_svc

router = APIRouter(prefix="/api", tags=["compensation review"])
R, P = models.CompensationRate, models.ClaimPhoto


# ---------- assessments ----------
@router.get("/compensation/assessments", response_model=list[schemas.AssessmentSummary])
def list_assessments(db: Session = Depends(get_db)):
    """Outlier level and score for every claim (for the claims table)."""
    return [schemas.AssessmentSummary(**a.model_dump(include=set(schemas.AssessmentSummary.model_fields)))
            for a in outliers.assess(db).values()]


@router.get("/claims/{claim_id}/assessment", response_model=schemas.Assessment)
def claim_assessment(claim_id: int, db: Session = Depends(get_db)):
    result = outliers.assess(db).get(claim_id)
    if result is None:
        raise HTTPException(404, "Claim not found")
    return result


# ---------- rates ----------
@router.get("/compensation/rates", response_model=list[schemas.RateOut])
def list_rates(db: Session = Depends(get_db)):
    return db.scalars(select(R).order_by(R.category, R.damage_type, R.province.nulls_first())).all()


@router.post("/compensation/rates", response_model=schemas.RateOut, status_code=201)
def create_override(body: schemas.RateIn, db: Session = Depends(get_db)):
    """Add a province-specific rate that overrides the national one."""
    if not body.province:
        raise HTTPException(400, "A province is required; edit the national rate instead")
    base = db.scalar(select(R).where(R.damage_type == body.damage_type, R.province.is_(None)))
    if base is None:
        raise HTTPException(404, f"No national rate for {body.damage_type}")
    if db.scalar(select(R).where(R.damage_type == body.damage_type, R.province == body.province)):
        raise HTTPException(409, f"{body.province} already has a {base.label.lower()} rate")
    row = R(
        damage_type=base.damage_type, province=body.province, label=base.label, category=base.category,
        unit=base.unit, rate_thb=body.rate_thb if body.rate_thb is not None else base.rate_thb,
        max_units=body.max_units if body.max_units is not None else base.max_units,
        max_thb=body.max_thb if body.max_thb is not None else base.max_thb,
        source=body.source or f"Provincial override for {body.province}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/compensation/rates/{rate_id}", response_model=schemas.RateOut)
def update_rate(rate_id: int, body: schemas.RatePatch, db: Session = Depends(get_db)):
    row = db.get(R, rate_id)
    if not row:
        raise HTTPException(404, "Rate not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/compensation/rates/{rate_id}", status_code=204)
def delete_override(rate_id: int, db: Session = Depends(get_db)):
    row = db.get(R, rate_id)
    if not row:
        raise HTTPException(404, "Rate not found")
    if row.province is None:
        raise HTTPException(400, "National rates can be edited but not deleted")
    db.delete(row)
    db.commit()


# ---------- photos ----------
def _photo_out(p: models.ClaimPhoto, inc_pos: tuple | None) -> schemas.PhotoOut:
    out = schemas.PhotoOut.model_validate(p)
    out.url = f"/api/photos/{p.id}/file"
    out.thumb_url = f"/api/photos/{p.id}/file?size=thumb"
    if inc_pos and inc_pos[0] is not None and p.lat is not None:
        out.distance_km = round(outliers.haversine_km(p.lat, p.lon, inc_pos[1], inc_pos[0]), 2)
    return out


def _incident_pos(db: Session, claim: models.CompensationClaim):
    return db.execute(
        select(func.ST_X(models.Incident.geom), func.ST_Y(models.Incident.geom)).where(models.Incident.id == claim.incident_id)
    ).first()


@router.get("/claims/{claim_id}/photos", response_model=list[schemas.PhotoOut])
def list_photos(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(models.CompensationClaim, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    pos = _incident_pos(db, claim)
    rows = db.scalars(select(P).where(P.claim_id == claim_id).order_by(P.taken_at.nulls_last(), P.id)).all()
    return [_photo_out(p, pos) for p in rows]


@router.post("/claims/{claim_id}/photos", response_model=list[schemas.PhotoOut], status_code=201)
async def upload_photos(claim_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Attach one or more photos. EXIF time and GPS are read on the server, not trusted from the client."""
    claim = db.get(models.CompensationClaim, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    saved = []
    for f in files:
        data = await f.read()
        try:
            fields = await asyncio.to_thread(photo_svc.save, data, f.filename or "photo", f.content_type)
        except photo_svc.PhotoError as e:
            for p in saved:  # keep the upload all-or-nothing
                photo_svc.delete_files(p.stored_name, p.original_ext)
            raise HTTPException(400, str(e))
        saved.append(P(claim_id=claim_id, **fields))
    db.add_all(saved)
    db.commit()
    pos = _incident_pos(db, claim)
    return [_photo_out(p, pos) for p in saved]


@router.get("/photos/{photo_id}/file")
def photo_file(photo_id: int, size: str = "display", db: Session = Depends(get_db)):
    """size = thumb (360 px) | display (1600 px JPEG) | original (the uploaded file)."""
    p = db.get(P, photo_id)
    if not p:
        raise HTTPException(404, "Photo not found")
    files = photo_svc.paths(p.stored_name, p.original_ext)
    key = size if size in files else "display"
    path = files[key]
    if not path.exists():
        raise HTTPException(404, "Photo file missing on the server")
    if key == "original":
        return FileResponse(path, media_type=p.content_type, filename=p.filename)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.get(P, photo_id)
    if not p:
        raise HTTPException(404, "Photo not found")
    photo_svc.delete_files(p.stored_name, p.original_ext)
    db.delete(p)
    db.commit()

