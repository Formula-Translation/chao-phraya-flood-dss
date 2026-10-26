"""Official assistance rates for flood damage.

Defaults follow the Ministry of Agriculture and Cooperatives criteria for emergency
disaster assistance to farmers, in effect for disasters from 21 Aug 2026 (2569), and the
Ministry of Finance 2025 (2568) advance-fund regulation used by DDPM for housing and
livelihood. They are loaded once into the `compensation_rates` table, where they can be
edited, and overridden per province, from the app or the API.

Always check against the official announcement before using figures for real payments.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models

BKK = timezone(timedelta(hours=7))
MOAC_2569 = "MOAC emergency disaster assistance criteria, effective 21 Aug 2026 (2569)"
MOAC_2564 = "MOAC criteria, livestock rates unchanged from 2021 (2564); upper value of the age range"
MOF_2568 = "Ministry of Finance advance-fund regulation 2025 (2568), via DDPM"

# damage_type: (label, category, unit, rate_thb, max_units, max_thb, source)
DEFAULT_RATES: dict[str, tuple] = {
    "rice": ("Rice", "crops", "rai", 2240, 30, None, MOAC_2569),
    "field_crop": ("Field crops and vegetables", "crops", "rai", 3180, 30, None, MOAC_2569),
    "fruit_tree": ("Fruit and perennial trees", "crops", "rai", 6800, 30, None, MOAC_2569),
    "fish_pond": ("Fish in earth ponds or paddies", "fishery", "rai", 4890, 5, None, MOAC_2569),
    "shrimp_pond": ("Prawn, shrimp or shellfish ponds", "fishery", "rai", 12350, 5, None, MOAC_2569),
    "fish_cage": ("Fish cages or cement tanks", "fishery", "sq_m", 390, 80, None, MOAC_2569),
    "cattle": ("Cattle", "livestock", "head", 35000, 5, None, MOAC_2564),
    "buffalo": ("Buffalo", "livestock", "head", 39000, 5, None, MOAC_2564),
    "pig": ("Pigs", "livestock", "head", 3000, 10, None, MOAC_2564),
    "house": ("House repair", "housing", "house", None, 1, 88600, MOF_2568),
    "tools": ("Occupational tools", "housing", "household", None, 1, 13500, MOF_2568),
}

# damage types used before the rate table existed
LEGACY_TYPES = {"crops": "rice", "fishery": "fish_pond", "livestock": "cattle", "property": "tools"}

PER_UNIT_LABEL = {"rai": "rai", "sq_m": "m²", "head": "head", "house": "house", "household": "household"}


def ensure_defaults(db: Session) -> None:
    """Insert any missing national rates and migrate legacy claim types."""
    have = set(db.scalars(select(models.CompensationRate.damage_type).where(models.CompensationRate.province.is_(None))))
    effective = datetime(2026, 8, 21, tzinfo=BKK)
    for key, (label, cat, unit, rate, max_units, max_thb, src) in DEFAULT_RATES.items():
        if key not in have:
            db.add(models.CompensationRate(
                damage_type=key, province=None, label=label, category=cat, unit=unit, rate_thb=rate,
                max_units=max_units, max_thb=max_thb, source=src, effective_from=effective,
            ))
    for old, new in LEGACY_TYPES.items():
        db.execute(text("UPDATE compensation_claims SET damage_type = :new WHERE damage_type = :old"),
                   {"new": new, "old": old})
    # claims recorded before region columns existed take the incident's region
    db.execute(text(
        "UPDATE compensation_claims c SET province = i.province, amphoe = COALESCE(c.amphoe, i.amphoe) "
        "FROM incidents i WHERE c.incident_id = i.id AND c.province IS NULL"
    ))
    db.commit()


def rate_lookup(db: Session):
    """Return f(damage_type, province) -> (rate row or None, region label)."""
    rows = db.scalars(select(models.CompensationRate)).all()
    national = {r.damage_type: r for r in rows if r.province is None}
    regional = {(r.damage_type, r.province): r for r in rows if r.province is not None}

    def find(damage_type: str, province: str | None):
        if province and (damage_type, province) in regional:
            return regional[(damage_type, province)], province
        r = national.get(damage_type)
        return (r, "national") if r else (None, None)

    return find


def quantity(claim: models.CompensationClaim, rate: models.CompensationRate | None) -> float | None:
    """Units the rate applies to: rai for per-rai types, otherwise the claim's `units`."""
    if rate is None:
        return claim.area_rai or claim.units
    if rate.unit == "rai":
        return claim.area_rai
    if rate.rate_thb is None:  # lump sum: one house / one household
        return claim.units or 1
    return claim.units


def official_max(rate: models.CompensationRate | None, qty: float | None) -> tuple[float | None, float | None]:
    """(eligible quantity, maximum payable amount) under the rate's caps."""
    if rate is None:
        return None, None
    if rate.rate_thb is None:
        return 1, rate.max_thb
    if qty is None:
        return None, None
    eligible = min(qty, rate.max_units) if rate.max_units else qty
    amount = eligible * rate.rate_thb
    if rate.max_thb:
        amount = min(amount, rate.max_thb)
    return eligible, amount
