"""Series Dataset model.

A Dataset is one of four series types (see whiteboard):
  - time      -> TimeSeriesValue  (station + t + value)
  - feature   -> Feature          (geometry valid over [valid_from, valid_to], with LOD)
  - attribute -> AttributeValue   (feature + t + key + value)
  - raster    -> RasterFrame      (t + URI to a COG / NetCDF frame)

Prediction output is kept per Scenario so the UI can show history up to
"today" and scenario branches 1/2/3 after it.
"""
import enum
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SeriesType(str, enum.Enum):
    time = "time"
    feature = "feature"
    attribute = "attribute"
    raster = "raster"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    series_type: Mapped[SeriesType] = mapped_column(Enum(SeriesType, name="series_type"))
    unit: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    features: Mapped[list["Feature"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    geom = mapped_column(Geometry("POINT", srid=4326))

    # metadata from ThaiWater (HII) — see services/thaiwater.py
    external_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    name_en: Mapped[str | None] = mapped_column(String(200))
    river: Mapped[str | None] = mapped_column(String(200))
    tambon: Mapped[str | None] = mapped_column(String(200))
    amphoe: Mapped[str | None] = mapped_column(String(200))
    province: Mapped[str | None] = mapped_column(String(200))
    basin: Mapped[str | None] = mapped_column(String(200))
    agency: Mapped[str | None] = mapped_column(String(200))
    left_bank: Mapped[float | None] = mapped_column(Float)
    right_bank: Mapped[float | None] = mapped_column(Float)
    min_bank: Mapped[float | None] = mapped_column(Float)
    ground_level: Mapped[float | None] = mapped_column(Float)
    warning_level: Mapped[float | None] = mapped_column(Float)
    critical_level: Mapped[float | None] = mapped_column(Float)
    is_key_station: Mapped[bool | None] = mapped_column(Boolean)
    situation_level: Mapped[int | None] = mapped_column(Integer)
    storage_percent: Mapped[float | None] = mapped_column(Float)
    latest_value: Mapped[float | None] = mapped_column(Float)
    latest_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# columns added after the first release; created on startup if missing
STATION_EXTRA_COLUMNS = {
    "external_id": "INTEGER UNIQUE", "name_en": "VARCHAR(200)", "river": "VARCHAR(200)",
    "tambon": "VARCHAR(200)", "amphoe": "VARCHAR(200)", "province": "VARCHAR(200)",
    "basin": "VARCHAR(200)", "agency": "VARCHAR(200)", "left_bank": "DOUBLE PRECISION",
    "right_bank": "DOUBLE PRECISION", "min_bank": "DOUBLE PRECISION", "ground_level": "DOUBLE PRECISION",
    "warning_level": "DOUBLE PRECISION", "critical_level": "DOUBLE PRECISION", "is_key_station": "BOOLEAN",
    "situation_level": "INTEGER", "storage_percent": "DOUBLE PRECISION", "latest_value": "DOUBLE PRECISION",
    "latest_time": "TIMESTAMPTZ",
}


class TimeSeriesValue(Base):
    __tablename__ = "timeseries_values"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[str | None] = mapped_column(String(20))


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    geom = mapped_column(Geometry("GEOMETRY", srid=4326))
    lod: Mapped[int] = mapped_column(Integer, default=1)  # LOD 1–4 for buildings
    height: Mapped[float | None] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset] = relationship(back_populates="features")


class AttributeValue(Base):
    __tablename__ = "attribute_values"

    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), primary_key=True)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    text_value: Mapped[str | None] = mapped_column(Text)


class RasterFrame(Base):
    __tablename__ = "raster_frames"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uri: Mapped[str] = mapped_column(String(500))  # e.g. s3://.../depth_2026-10-21.tif
    bbox = mapped_column(Geometry("POLYGON", srid=4326))

    __table_args__ = (Index("ix_raster_dataset_t", "dataset_id", "t"),)


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(100))
    base_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # "TODAY"
    input_dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="done")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScenarioResult(Base):
    __tablename__ = "scenario_results"

    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float] = mapped_column(Float)


# ---------------- Incident & compensation (stages 2 and 3) ----------------
class Incident(Base):
    """A flood event being handled: bank overflow, embankment breach, inundation…"""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(50), default="inundation")  # inundation | overflow | breach | flash_flood
    severity: Mapped[int] = mapped_column(Integer, default=1)  # 1 watch, 2 serious, 3 severe
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | receding | closed
    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id", ondelete="SET NULL"))
    province: Mapped[str | None] = mapped_column(String(200))
    amphoe: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    households_affected: Mapped[int] = mapped_column(Integer, default=0)
    area_rai: Mapped[float] = mapped_column(Float, default=0)
    geom = mapped_column(Geometry("POINT", srid=4326))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompensationClaim(Base):
    """A household's claim for flood damage, linked to an incident."""
    __tablename__ = "compensation_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    claimant: Mapped[str] = mapped_column(String(200))
    village: Mapped[str | None] = mapped_column(String(200))
    province: Mapped[str | None] = mapped_column(String(200))  # region used for peer comparison
    amphoe: Mapped[str | None] = mapped_column(String(200))
    # key into compensation_rates, e.g. rice | field_crop | fruit_tree | fish_pond | cattle | house
    damage_type: Mapped[str] = mapped_column(String(50), default="rice")
    area_rai: Mapped[float | None] = mapped_column(Float)  # for per-rai damage types
    units: Mapped[float | None] = mapped_column(Float)  # heads, m² of cages, houses… for other types
    estimated_thb: Mapped[float] = mapped_column(Float, default=0)
    approved_thb: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted | surveyed | approved | paid | rejected
    geom = mapped_column(Geometry("POINT", srid=4326))
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompensationRate(Base):
    """Official assistance rate for one damage type.

    province = NULL is the national rate; a row with a province overrides it for that region.
    """
    __tablename__ = "compensation_rates"
    __table_args__ = (Index("ux_rate_type_province", "damage_type", "province", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    damage_type: Mapped[str] = mapped_column(String(50))
    province: Mapped[str | None] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))  # crops | fishery | livestock | housing
    unit: Mapped[str] = mapped_column(String(20))  # rai | sq_m | head | house | household
    rate_thb: Mapped[float | None] = mapped_column(Float)  # per unit; NULL for lump-sum types
    max_units: Mapped[float | None] = mapped_column(Float)  # household cap on units
    max_thb: Mapped[float | None] = mapped_column(Float)  # cap on the amount
    source: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ClaimPhoto(Base):
    """Photo evidence for a claim, with metadata read from the file's EXIF."""
    __tablename__ = "claim_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("compensation_claims.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(300))  # original name from the uploader
    stored_name: Mapped[str] = mapped_column(String(100))  # <uuid> — files: <uuid>.<ext>, <uuid>.jpg, thumbs/<uuid>.jpg
    original_ext: Mapped[str] = mapped_column(String(10))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    camera: Mapped[str | None] = mapped_column(String(200))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Columns added after a table first shipped. Created on startup if missing (until Alembic is set up).
EXTRA_COLUMNS = {
    "stations": STATION_EXTRA_COLUMNS,
    "compensation_claims": {
        "province": "VARCHAR(200)", "amphoe": "VARCHAR(200)", "units": "DOUBLE PRECISION",
    },
}
