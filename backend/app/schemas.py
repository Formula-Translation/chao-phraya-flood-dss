from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import SeriesType


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DatasetIn(BaseModel):
    name: str
    series_type: SeriesType
    unit: str | None = None
    source: str | None = None
    description: str | None = None
    meta: dict[str, Any] = {}


class DatasetOut(ORM, DatasetIn):
    id: int
    created_at: datetime
    updated_at: datetime


class StationOut(ORM):
    id: int
    code: str
    name: str
    lon: float | None = None
    lat: float | None = None
    external_id: int | None = None
    name_en: str | None = None
    river: str | None = None
    tambon: str | None = None
    amphoe: str | None = None
    province: str | None = None
    basin: str | None = None
    agency: str | None = None
    left_bank: float | None = None
    right_bank: float | None = None
    min_bank: float | None = None
    ground_level: float | None = None
    warning_level: float | None = None
    critical_level: float | None = None
    is_key_station: bool | None = None
    situation_level: int | None = None
    storage_percent: float | None = None
    latest_value: float | None = None
    latest_time: datetime | None = None


class TSPoint(BaseModel):
    t: datetime
    value: float | None


class TSUpload(BaseModel):
    station_code: str
    points: list[TSPoint]


class RasterOut(ORM):
    id: int
    t: datetime
    uri: str


class PredictionRequest(BaseModel):
    dataset_id: int
    station_id: int
    model: str = "persistence-trend"
    horizon_hours: int = 48
    base_time: datetime | None = None  # defaults to latest observation ("today")


class ScenarioOut(ORM):
    id: int
    name: str
    model: str
    base_time: datetime
    params: dict[str, Any]
    status: str


class ScenarioResultOut(BaseModel):
    t: datetime
    value: float


# ---------- incidents ----------
class IncidentIn(BaseModel):
    title: str
    kind: str = "inundation"
    severity: int = 1
    status: str = "active"
    station_id: int | None = None
    province: str | None = None
    amphoe: str | None = None
    description: str | None = None
    households_affected: int = 0
    area_rai: float = 0
    lon: float | None = None
    lat: float | None = None


class IncidentPatch(BaseModel):
    status: str | None = None
    severity: int | None = None
    households_affected: int | None = None
    area_rai: float | None = None
    description: str | None = None


class IncidentOut(BaseModel):
    id: int
    title: str
    kind: str
    severity: int
    status: str
    station_id: int | None
    province: str | None
    amphoe: str | None
    description: str | None
    households_affected: int
    area_rai: float
    lon: float | None
    lat: float | None
    started_at: datetime
    ended_at: datetime | None
    claims: int = 0


# ---------- compensation ----------
class ClaimIn(BaseModel):
    incident_id: int
    claimant: str
    village: str | None = None
    damage_type: str = "rice"
    area_rai: float | None = None
    units: float | None = None
    estimated_thb: float = 0
    notes: str | None = None


class ClaimPatch(BaseModel):
    status: str | None = None
    approved_thb: float | None = None
    notes: str | None = None


class ClaimOut(ORM):
    id: int
    incident_id: int
    claimant: str
    village: str | None
    province: str | None = None
    amphoe: str | None = None
    damage_type: str
    area_rai: float | None
    units: float | None = None
    estimated_thb: float
    approved_thb: float | None
    status: str
    notes: str | None
    submitted_at: datetime


class RateIn(BaseModel):
    damage_type: str
    province: str | None = None
    rate_thb: float | None = None
    max_units: float | None = None
    max_thb: float | None = None
    source: str | None = None


class RatePatch(BaseModel):
    rate_thb: float | None = None
    max_units: float | None = None
    max_thb: float | None = None
    source: str | None = None


class RateOut(ORM):
    id: int
    damage_type: str
    province: str | None
    label: str
    category: str
    unit: str
    rate_thb: float | None
    max_units: float | None
    max_thb: float | None
    source: str | None
    effective_from: datetime | None


class PhotoOut(ORM):
    id: int
    claim_id: int
    filename: str
    content_type: str | None
    size_bytes: int
    width: int | None
    height: int | None
    taken_at: datetime | None
    lat: float | None
    lon: float | None
    camera: str | None
    uploaded_at: datetime
    url: str = ""
    thumb_url: str = ""
    distance_km: float | None = None  # from the incident location


class FlagOut(BaseModel):
    code: str
    level: str  # info | review | high
    title: str
    detail: str
    photo_id: int | None = None


class AssessmentSummary(BaseModel):
    claim_id: int
    level: str  # ok | review | high
    score: int
    flags: int
    top_flag: str | None


class Assessment(AssessmentSummary):
    flag_list: list[FlagOut]
    rate: RateOut | None
    rate_region: str | None  # "national" or the province of an override
    quantity: float | None
    eligible_quantity: float | None
    official_max_thb: float | None
    peer_group: str | None
    peer_count: int
    peer_median: float | None  # per unit (or per claim for lump-sum types)
    expected_low_thb: float | None
    expected_mid_thb: float | None
    expected_high_thb: float | None
