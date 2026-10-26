"""Compensation outlier checks.

Every claim is checked three ways and gets a list of flags, a 0–100 score and a level
(ok / review / high):

1. Official rates   Is the amount above what the rate allows for the claimed area or
                    units, or is the area above the household limit?
2. Regional peers   Is the amount per rai (or per head, m², …) unusual compared with the
                    same damage type in the same province? Uses the median and MAD
                    (modified z-score, Iglewicz & Hoaglin), which a few extreme claims
                    can't drag around the way a mean and standard deviation can.
                    Falls back to all provinces when a region has too few claims.
3. Evidence         Duplicate claimants, missing photos, photos reused on another claim,
                    taken far from the flood, or dated before it started.

The peer median and interquartile range also give the "expected" amount for the claim.
"""
import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.services import rates as rate_svc

MIN_PEERS = 5  # claims needed in a province before it is used as the comparison group
Z_REVIEW, Z_HIGH = 2.5, 3.5
PHOTO_KM_REVIEW, PHOTO_KM_HIGH = 10, 30
NO_PHOTO_REVIEW_THB = 10_000
POINTS = {"high": 40, "review": 15, "info": 0}
LEVEL_ORDER = {"high": 2, "review": 1, "info": 0}


@dataclass
class Flag:
    code: str
    level: str
    title: str
    detail: str
    photo_id: int | None = None


@dataclass
class Peers:
    name: str
    values: list[float] = field(default_factory=list)
    areas: list[float] = field(default_factory=list)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _quartiles(xs: list[float]) -> tuple[float, float, float]:
    if len(xs) < 4:
        m = statistics.median(xs)
        return min(xs), m, max(xs)
    q1, q2, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    return q1, q2, q3


def modified_z(x: float, xs: list[float]) -> float:
    med = statistics.median(xs)
    mad = statistics.median(abs(v - med) for v in xs)
    if mad == 0:  # most claims identical: fall back to mean absolute deviation
        mad = statistics.fmean(abs(v - med) for v in xs) * 1.2533
    if mad == 0:
        return 0.0 if x == med else math.copysign(10.0, x - med)
    return 0.6745 * (x - med) / mad


_TITLES = re.compile(r"^(นาย|นางสาว|นาง|น\.ส\.|mr\.?|mrs\.?|ms\.?|miss)\s*", re.I)


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", "", _TITLES.sub("", name.strip().lower()))


def _money(x: float | None) -> str:
    return "–" if x is None else f"฿{x:,.0f}"


def _qty(x: float | None) -> str:
    return "–" if x is None else (f"{x:,.0f}" if float(x).is_integer() else f"{x:,.1f}")


def assess(db: Session) -> dict[int, schemas.Assessment]:
    """Assess every claim (peers need the whole set anyway)."""
    find_rate = rate_svc.rate_lookup(db)
    claims = db.scalars(select(models.CompensationClaim)).all()

    inc_rows = db.execute(
        select(models.Incident.id, models.Incident.started_at, models.Incident.title,
               func.ST_X(models.Incident.geom), func.ST_Y(models.Incident.geom))
    ).all()
    incidents = {i: {"started": s, "title": t, "lon": x, "lat": y} for i, s, t, x, y in inc_rows}

    photos_by_claim: dict[int, list[models.ClaimPhoto]] = defaultdict(list)
    claims_by_hash: dict[str, set[int]] = defaultdict(set)
    for p in db.scalars(select(models.ClaimPhoto)).all():
        photos_by_claim[p.claim_id].append(p)
        claims_by_hash[p.sha256].add(p.claim_id)
    claim_by_id = {c.id: c for c in claims}

    # ---------- prepare per-claim quantities and peer groups ----------
    prep = {}
    groups: dict[tuple, Peers] = {}
    for c in claims:
        rate, region = find_rate(c.damage_type, c.province)
        qty = rate_svc.quantity(c, rate)
        lump = rate is not None and rate.rate_thb is None
        per_unit = c.estimated_thb if lump else (c.estimated_thb / qty if qty else None)
        prep[c.id] = (rate, region, qty, lump, per_unit)
        if c.status == "rejected" or per_unit is None:
            continue
        for key, name in (((c.province, c.damage_type), c.province or "unknown province"),
                          ((None, c.damage_type), "all provinces")):
            g = groups.setdefault(key, Peers(name))
            g.values.append(per_unit)
            if qty and not lump:
                g.areas.append(qty)

    name_counts: dict[tuple, list[int]] = defaultdict(list)
    for c in claims:
        name_counts[(c.incident_id, _norm_name(c.claimant))].append(c.id)

    out: dict[int, schemas.Assessment] = {}
    for c in claims:
        rate, region, qty, lump, per_unit = prep[c.id]
        flags: list[Flag] = []
        label = rate.label.lower() if rate else c.damage_type
        unit = rate_svc.PER_UNIT_LABEL.get(rate.unit, rate.unit) if rate else "unit"
        eligible, max_thb = rate_svc.official_max(rate, qty)

        # ---------- 1. official rates ----------
        if rate is None:
            flags.append(Flag("no_rate", "info", "No official rate for this damage type",
                              f"“{c.damage_type}” has no rate in the rate table, so only peer checks apply."))
        elif not lump and not qty:
            what = "area" if rate.unit == "rai" else "quantity"
            flags.append(Flag("no_quantity", "review", f"No {what} entered",
                              f"{rate.label} is paid per {unit}, but no {what} was entered, so the amount can't be checked."))
        if rate and max_thb is not None and c.estimated_thb > max_thb * 1.001:
            ratio = c.estimated_thb / max_thb if max_thb else math.inf
            basis = (f"the cap for {label} is {_money(max_thb)}" if lump else
                     f"the most payable for {_qty(eligible)} {unit} of {label} is {_money(max_thb)} "
                     f"({rate.rate_thb:,.0f} ฿/{unit}, {region} rate)")
            flags.append(Flag("over_official", "high" if ratio >= 1.5 else "review", "Above the official maximum",
                              f"Claims {_money(c.estimated_thb)} ({ratio:.1f}× the limit), but {basis}."))
        if rate and rate.max_units and not lump and qty and qty > rate.max_units:
            flags.append(Flag("over_unit_cap", "review", "Above the household limit",
                              f"{_qty(qty)} {unit} claimed; only {_qty(rate.max_units)} {unit} per household are eligible."))
        if c.approved_thb is not None and max_thb is not None and c.approved_thb > max_thb * 1.001:
            flags.append(Flag("approved_over_official", "high", "Approved above the official maximum",
                              f"Approved {_money(c.approved_thb)} against a maximum of {_money(max_thb)}."))

        # ---------- 2. regional peers ----------
        g = groups.get((c.province, c.damage_type))
        if not g or len(g.values) < MIN_PEERS:
            g = groups.get((None, c.damage_type))
        peer_n = len(g.values) if g else 0
        peer_med = statistics.median(g.values) if peer_n else None
        exp_low = exp_mid = exp_high = None
        if g and peer_n >= MIN_PEERS and per_unit is not None:
            z = modified_z(per_unit, g.values)
            per = "" if lump else f"/{unit}"
            what = f"{_money(per_unit)}{per} vs a median of {_money(peer_med)}{per}"
            where = f"across {peer_n} {label} claims in {g.name}"
            if z > Z_HIGH:
                flags.append(Flag("peer_high", "high", "Far above similar claims", f"{what} {where}."))
            elif z > Z_REVIEW:
                flags.append(Flag("peer_above", "review", "Higher than similar claims", f"{what} {where}."))
            elif z < -Z_HIGH:
                flags.append(Flag("peer_low", "info", "Much lower than similar claims",
                                  f"{what} {where}. Check for a typing error."))
            if not lump and qty and len(g.areas) >= MIN_PEERS and modified_z(qty, g.areas) > Z_HIGH:
                flags.append(Flag("area_high", "review", f"Much larger {('area' if unit == 'rai' else 'quantity')} than neighbours",
                                  f"{_qty(qty)} {unit} vs a median of {_qty(statistics.median(g.areas))} {unit} "
                                  f"for {label} claims in {g.name}."))
            q1, q2, q3 = _quartiles(g.values)
            mult = 1 if lump else (eligible or qty or 0)
            cap = max_thb if max_thb is not None else math.inf
            exp_low, exp_mid, exp_high = (min(v * mult, cap) for v in (q1, q2, q3))

        # ---------- 3. evidence ----------
        same_name = name_counts[(c.incident_id, _norm_name(c.claimant))]
        if len(same_name) > 1:
            others = [claim_by_id[i] for i in same_name if i != c.id]
            same_type = [o for o in others if o.damage_type == c.damage_type]
            if same_type:
                flags.append(Flag("duplicate_claim", "high", "Possible duplicate claim",
                                  f"{c.claimant} has another {label} claim in this incident "
                                  f"(#{', #'.join(str(o.id) for o in same_type)})."))
            else:
                flags.append(Flag("multiple_claims", "info", "Several claims from this household",
                                  f"{c.claimant} also claimed for "
                                  f"{', '.join(o.damage_type.replace('_', ' ') for o in others)} in this incident."))

        inc = incidents.get(c.incident_id, {})
        pics = photos_by_claim.get(c.id, [])
        if not pics:
            lvl = "review" if c.estimated_thb >= NO_PHOTO_REVIEW_THB else "info"
            flags.append(Flag("no_photos", lvl, "No photo evidence",
                              f"No damage photos attached{' to a claim this size' if lvl == 'review' else ''}."))
        for p in pics:
            reused = claims_by_hash[p.sha256] - {c.id}
            if reused:
                o = claim_by_id[min(reused)]
                flags.append(Flag("photo_reused", "high", "Photo reused from another claim",
                                  f"{p.filename} is identical to a photo on claim #{o.id} ({o.claimant}).", p.id))
            if p.lat is not None and inc.get("lat") is not None:
                d = haversine_km(p.lat, p.lon, inc["lat"], inc["lon"])
                if d > PHOTO_KM_REVIEW:
                    flags.append(Flag("photo_far", "high" if d > PHOTO_KM_HIGH else "review", "Photo taken far from the flood",
                                      f"{p.filename} was taken {d:,.0f} km from the incident location.", p.id))
            if p.taken_at and inc.get("started"):
                started = inc["started"]
                if p.taken_at < started - timedelta(days=1):
                    days = (started - p.taken_at).days
                    flags.append(Flag("photo_before", "high", "Photo taken before the flood",
                                      f"{p.filename} is dated {p.taken_at:%d %b %Y}, {days} days before the incident "
                                      f"started ({started:%d %b %Y}).", p.id))
                elif p.taken_at > started + timedelta(days=90):
                    flags.append(Flag("photo_late", "info", "Photo taken long after the flood",
                                      f"{p.filename} is dated {p.taken_at:%d %b %Y}.", p.id))
            if p.lat is None and p.taken_at is None:
                flags.append(Flag("photo_no_exif", "info", "No location or time in photo",
                                  f"{p.filename} has no camera data. Screenshots and photos forwarded through chat apps "
                                  f"lose it; ask for the original file.", p.id))
            elif p.lat is None:
                flags.append(Flag("photo_no_gps", "info", "No location in photo",
                                  f"{p.filename} has no GPS position, so where it was taken can't be checked.", p.id))

        # ---------- score ----------
        flags.sort(key=lambda f: -LEVEL_ORDER[f.level])
        score = min(100, sum(POINTS[f.level] for f in flags))
        top = flags[0].level if flags else "info"
        level = "high" if top == "high" or score >= 40 else "review" if top == "review" else "ok"
        issues = [f for f in flags if f.level != "info"]

        out[c.id] = schemas.Assessment(
            claim_id=c.id, level=level, score=score, flags=len(issues),
            top_flag=issues[0].title if issues else None,
            flag_list=[schemas.FlagOut(**f.__dict__) for f in flags],
            rate=schemas.RateOut.model_validate(rate) if rate else None, rate_region=region,
            quantity=qty, eligible_quantity=eligible, official_max_thb=max_thb,
            peer_group=g.name if g else None, peer_count=peer_n, peer_median=peer_med,
            expected_low_thb=exp_low, expected_mid_thb=exp_mid, expected_high_thb=exp_high,
        )
    return out
