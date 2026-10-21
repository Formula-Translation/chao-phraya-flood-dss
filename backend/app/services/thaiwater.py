"""ThaiWater (HII / สสน.) public API client and importer.

waterlevel_load  -> latest reading + full metadata for every telemetry station
waterlevel_graph -> 10-minute history for one station
"""
import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models

log = logging.getLogger("thaiwater")
BASE = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public"
BKK = timezone(timedelta(hours=7))
DATASET_NAME = "Water level (ThaiWater)"


def _get(path: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "cfm-dss/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _ts(v):
    if not v:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=BKK)
        except ValueError:
            continue
    return None


def _txt(v, lang="th"):
    if isinstance(v, dict):
        return v.get(lang) or v.get("th") or v.get("en")
    return v


def dataset(db: Session) -> models.Dataset:
    ds = db.scalar(select(models.Dataset).where(models.Dataset.name == DATASET_NAME))
    if not ds:
        ds = models.Dataset(name=DATASET_NAME, series_type=models.SeriesType.time, unit="m MSL",
                            source="thaiwater", description="Telemetry water level from api-v3.thaiwater.net")
        db.add(ds)
        db.flush()
    return ds


def sync_stations(db: Session) -> dict:
    records = _get("waterlevel_load")["waterlevel_data"]["data"]
    ds = dataset(db)
    all_st = db.scalars(select(models.Station)).all()
    by_ext = {s.external_id: s for s in all_st if s.external_id}
    by_code = {s.code: s for s in all_st}

    readings = []
    for r in records:
        st = r.get("station") or {}
        sid = st.get("id")
        lat, lon = _num(st.get("tele_station_lat")), _num(st.get("tele_station_long"))
        if not sid or lat is None or lon is None:
            continue
        code = (st.get("tele_station_oldcode") or "").strip() or f"TW{sid}"
        obj = by_ext.get(sid)
        if obj is None:
            cand = by_code.get(code)
            if cand is not None and cand.external_id is None:
                obj = cand  # adopt a demo station with the same code
            elif cand is not None:
                code = f"{code}-{sid}"
        if obj is None:
            obj = models.Station(code=code, name=code)
            db.add(obj)
            by_code[code] = obj
        by_ext[sid] = obj

        geo, basin, agency = r.get("geocode") or {}, r.get("basin") or {}, r.get("agency") or {}
        name = st.get("tele_station_name")
        obj.external_id = sid
        obj.name = _txt(name) or code
        obj.name_en = name.get("en") if isinstance(name, dict) else None
        obj.geom = from_shape(Point(lon, lat), 4326)
        obj.river = r.get("river_name") or None
        obj.tambon = _txt(geo.get("tumbon_name"))
        obj.amphoe = _txt(geo.get("amphoe_name"))
        obj.province = _txt(geo.get("province_name"))
        obj.basin = _txt(basin.get("basin_name"))
        obj.agency = _txt(agency.get("agency_shortname")) or _txt(agency.get("agency_name"))
        obj.left_bank = _num(st.get("left_bank"))
        obj.right_bank = _num(st.get("right_bank"))
        obj.min_bank = _num(st.get("min_bank"))
        obj.ground_level = _num(st.get("ground_level"))
        obj.warning_level = _num(st.get("warning_level_m"))
        obj.critical_level = _num(st.get("critical_level_msl"))
        obj.is_key_station = bool(st.get("is_key_station"))
        obj.situation_level = int(r["situation_level"]) if str(r.get("situation_level") or "").isdigit() else None
        obj.storage_percent = _num(r.get("storage_percent"))
        obj.latest_value = _num(r.get("waterlevel_msl"))
        obj.latest_time = _ts(r.get("waterlevel_datetime"))
        if obj.latest_value is not None and obj.latest_time is not None:
            readings.append(obj)

    db.flush()
    rows = [{"dataset_id": ds.id, "station_id": s.id, "t": s.latest_time, "value": s.latest_value} for s in readings]
    if rows:
        db.execute(insert(models.TimeSeriesValue).values(rows).on_conflict_do_nothing())
    db.commit()
    return {"stations": len(by_ext), "readings": len(rows)}


def sync_history(db: Session, station: models.Station, days: int = 7) -> int:
    if not station.external_id:
        return 0
    end = datetime.now(BKK).date()
    start = end - timedelta(days=days)
    data = _get(
        f"waterlevel_graph?station_type=tele_waterlevel&station_id={station.external_id}"
        f"&start_date={start}&end_date={end}"
    )["data"]
    ds = dataset(db)
    rows = []
    for p in data.get("graph_data") or []:
        t, v = _ts(p.get("datetime")), _num(p.get("value"))
        if t is not None and v is not None:
            rows.append({"dataset_id": ds.id, "station_id": station.id, "t": t, "value": v})
    for key, attr in (("min_bank", "min_bank"), ("ground_level", "ground_level"),
                      ("warning_level", "warning_level"), ("critical_level", "critical_level")):
        if _num(data.get(key)) is not None and getattr(station, attr) is None:
            setattr(station, attr, _num(data.get(key)))
    for i in range(0, len(rows), 1000):
        db.execute(insert(models.TimeSeriesValue).values(rows[i:i + 1000]).on_conflict_do_nothing())
    db.commit()
    return len(rows)
