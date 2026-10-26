"""Sample incidents, claims and photos for demos and testing. Not real people or events.

Built to exercise every outlier check:
- normal claims in three provinces, with Ang Thong farmers typically claiming less per rai
  than Chai Nat or Nakhon Sawan (so a claim at the national maximum stands out there)
- claims above the official maximum, above the 30-rai household limit, and a duplicate
- photos with GPS and dates near each incident, plus one reused, one taken far away,
  one dated before the flood, and one with its camera data stripped
"""
import io
import random
from datetime import datetime, timedelta, timezone

from geoalchemy2.shape import from_shape
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services import photos as photo_svc
from app.services import rates as rate_svc

BKK = timezone(timedelta(hours=7))
NOTE = "Sample data"

FIRST = ["สมชาย", "สมศรี", "ประเสริฐ", "มาลี", "บุญมี", "สุดา", "วิชัย", "อรุณี", "ทองคำ", "จันทร์เพ็ญ",
         "สมบัติ", "ละเอียด", "ประยูร", "บุญเรือน", "สุวิทย์", "นงลักษณ์", "เสถียร", "ราตรี", "ไพโรจน์", "สายสุนีย์"]
LAST = ["ใจดี", "ศรีสุข", "ทองดี", "มีสุข", "แก้วมณี", "บุญมา", "สุขเจริญ", "พรหมมา", "นาคสวัสดิ์", "ชื่นชม",
        "ปานทอง", "อินทร์แก้ว", "จันทร์หอม", "เพชรรัตน์", "สมบูรณ์"]

INCIDENTS = [
    # title, kind, severity, status, province, amphoe, lon, lat, days ago, households, rai, description, local price factor
    ("Bank overflow at Chai Nat town", "overflow", 3, "active", "ชัยนาท", "เมืองชัยนาท", 100.1270, 15.1850, 3, 420, 3100,
     "River above the right bank near the Chai Nat dam; sandbag line along the market road.", (0.88, 1.0)),
    ("Paddy inundation, Phayuha Khiri", "inundation", 2, "active", "นครสวรรค์", "พยุหะคีรี", 100.1360, 15.4560, 5, 150, 5200,
     "Low-lying rice fields flooded after the third rain event this week.", (0.85, 1.0)),
    ("Embankment seep, Mueang Nakhon Sawan", "breach", 1, "receding", "นครสวรรค์", "เมืองนครสวรรค์", 100.1300, 15.7000, 10, 35, 180,
     "Seepage under the flood wall at Pak Nam Pho; pumps running.", (0.85, 1.0)),
    ("Riverside flooding, Pa Mok", "inundation", 2, "active", "อ่างทอง", "ป่าโมก", 100.4440, 14.4930, 7, 210, 2600,
     "Chao Phraya overtopped low banks; orchards and paddies along the river under water.", (0.62, 0.74)),
]

# damage type, weight, typical quantity range
MIX = [("rice", 50, (3, 25)), ("field_crop", 14, (2, 14)), ("fruit_tree", 10, (1, 8)), ("fish_pond", 8, (0.5, 4)),
       ("house", 10, (1, 1)), ("cattle", 4, (1, 3)), ("pig", 4, (2, 8))]
STATUSES = ["submitted"] * 5 + ["surveyed"] * 4 + ["approved"] * 3 + ["paid"] * 3 + ["rejected"]


def _photo_bytes(label: str, rng: random.Random, lat=None, lon=None, taken=None, exif=True) -> bytes:
    w, h = 960, 720
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    horizon = int(h * rng.uniform(0.38, 0.5))
    for y in range(h):  # sky, then muddy water
        if y < horizon:
            t = y / horizon
            d.line([(0, y), (w, y)], fill=(int(150 + 60 * t), int(175 + 45 * t), int(200 + 30 * t)))
        else:
            t = (y - horizon) / (h - horizon)
            d.line([(0, y), (w, y)], fill=(int(140 - 40 * t), int(118 - 35 * t), int(80 - 25 * t)))
    for _ in range(rng.randint(2, 4)):  # half-submerged buildings and trees
        x = rng.randint(40, w - 200)
        bw, bh = rng.randint(90, 180), rng.randint(60, 140)
        d.rectangle([x, horizon - bh, x + bw, horizon + 25], fill=(rng.randint(150, 200), rng.randint(140, 180), 140))
        d.polygon([(x - 10, horizon - bh), (x + bw // 2, horizon - bh - 50), (x + bw + 10, horizon - bh)], fill=(130, 60, 45))
    for y in range(horizon + 20, h, 26):
        d.arc([rng.randint(-60, 0), y, w + 60, y + 30], 200, 340, fill=(170, 150, 110), width=2)
    font = ImageFont.load_default(size=34)
    d.rectangle([0, h - 70, w, h], fill=(23, 50, 58))
    d.text((24, h - 56), f"SAMPLE PHOTO  ·  {label}", fill=(238, 244, 242), font=font)

    meta = Image.Exif()
    if exif:
        meta[0x010F], meta[0x0110] = "Sample", "Field camera"
        if taken:
            meta.get_ifd(photo_svc.EXIF_IFD)[photo_svc.TAG_DATETIME_ORIGINAL] = taken.astimezone(BKK).strftime("%Y:%m:%d %H:%M:%S")
        if lat is not None:
            def dms(v):
                v = abs(v)
                deg = int(v)
                mins = int((v - deg) * 60)
                return (float(deg), float(mins), round((v - deg - mins / 60) * 3600, 2))
            gps = meta.get_ifd(photo_svc.GPS_IFD)
            gps[1], gps[2] = "N" if lat >= 0 else "S", dms(lat)
            gps[3], gps[4] = "E" if lon >= 0 else "W", dms(lon)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, exif=meta)
    return buf.getvalue()


def _add_photo(db: Session, claim: models.CompensationClaim, data: bytes, name: str) -> None:
    fields = photo_svc.save(data, name, "image/jpeg")
    db.add(models.ClaimPhoto(claim_id=claim.id, **fields))


def reset(db: Session) -> None:
    for p in db.scalars(select(models.ClaimPhoto)).all():
        photo_svc.delete_files(p.stored_name, p.original_ext)
    for inc in db.scalars(select(models.Incident)).all():
        db.delete(inc)  # cascades to claims and photos
    db.commit()


def seed(db: Session) -> dict:
    rng = random.Random(2569)
    rate_svc.ensure_defaults(db)
    find_rate = rate_svc.rate_lookup(db)
    now = datetime.now(BKK).replace(minute=0, second=0, microsecond=0)
    used_names: set[str] = set()

    def name() -> str:
        while True:
            n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used_names:
                used_names.add(n)
                return n

    claims_by_inc: dict[int, list] = {}
    incidents = []
    for (title, kind, sev, status, prov, amp, lon, lat, days, hh, rai, desc, factor) in INCIDENTS:
        inc = models.Incident(title=title, kind=kind, severity=sev, status=status, province=prov, amphoe=amp,
                              households_affected=hh, area_rai=rai, description=desc,
                              geom=from_shape(Point(lon, lat), 4326), started_at=now - timedelta(days=days))
        db.add(inc)
        db.flush()
        incidents.append((inc, lon, lat, factor))
        claims_by_inc[inc.id] = []

        types = [m[0] for m in MIX]
        weights = [m[1] for m in MIX]
        for i in range(rng.randint(16, 22)):
            dtype = rng.choices(types, weights)[0]
            lo, hi = dict((m[0], m[2]) for m in MIX)[dtype]
            rate, _ = find_rate(dtype, prov)
            f = rng.uniform(*factor)
            if rate.rate_thb is None:  # house: share of the cap
                area, units = None, 1
                est = round(rate.max_thb * rng.uniform(0.15, 0.85) * (f / 0.95), -2)
            elif rate.unit == "rai":
                area, units = round(rng.uniform(lo, hi) * (1 if rng.random() > 0.2 else 0.5), 1), None
                est = round(area * rate.rate_thb * f, -1)
            else:
                area, units = None, rng.randint(int(lo), int(hi))
                est = round(units * rate.rate_thb * rng.uniform(0.55, 0.95), -2)
            c = models.CompensationClaim(
                incident_id=inc.id, claimant=name(), village=f"หมู่ {rng.randint(1, 12)}", province=prov, amphoe=amp,
                damage_type=dtype, area_rai=area, units=units, estimated_thb=est, status=rng.choice(STATUSES), notes=NOTE,
                submitted_at=inc.started_at + timedelta(hours=rng.randint(6, 96)),
            )
            if c.status in ("approved", "paid"):
                c.approved_thb = round(est * rng.uniform(0.85, 1.0), -2)
            db.add(c)
            claims_by_inc[inc.id].append(c)
    db.flush()

    (chainat, cn_lon, cn_lat, _), (phayuha, ph_lon, ph_lat, _), (nsw, ns_lon, ns_lat, _), (pamok, pm_lon, pm_lat, _) = incidents

    def planted(inc, dtype, est, area=None, units=None, claimant=None, status="submitted", why=""):
        c = models.CompensationClaim(
            incident_id=inc.id, claimant=claimant or name(), village=f"หมู่ {rng.randint(1, 12)}",
            province=inc.province, amphoe=inc.amphoe, damage_type=dtype, area_rai=area, units=units,
            estimated_thb=est, status=status, notes=f"{NOTE}: {why}",
            submitted_at=inc.started_at + timedelta(hours=rng.randint(6, 72)),
        )
        db.add(c)
        claims_by_inc[inc.id].append(c)
        return c

    over_rate = planted(chainat, "rice", 110_000, area=12, why="amount far above the official rate")
    over_cap = planted(phayuha, "rice", 107_500, area=48, why="area above the 30-rai household limit")
    dup_a = planted(phayuha, "rice", 26_800, area=12.5, claimant="สมหมาย รักนา", why="duplicate claimant")
    dup_b = planted(phayuha, "rice", 25_900, area=12, claimant="นาย สมหมาย รักนา", why="duplicate claimant")
    house = planted(nsw, "house", 150_000, units=1, why="above the house repair cap")
    field = planted(pamok, "field_crop", 46_000, area=8, why="above the official rate")
    regional = planted(pamok, "rice", 22_000, area=10, why="at the national rate but high for Ang Thong")
    reused_from = planted(chainat, "fruit_tree", 30_500, area=5, why="photo later reused")
    reused_to = planted(pamok, "fruit_tree", 19_000, area=4, why="photo copied from another claim")
    far = planted(pamok, "rice", 14_500, area=9, why="photo taken far from the flood")
    before = planted(phayuha, "field_crop", 24_000, area=8, why="photo dated before the flood")
    stripped = planted(nsw, "rice", 15_200, area=8, why="photo without camera data")
    db.flush()

    # ---------- photos ----------
    special = {over_rate.id, over_cap.id, house.id, field.id, reused_from.id, reused_to.id, far.id, before.id, stripped.id}
    for inc, lon, lat, _ in incidents:
        for c in claims_by_inc[inc.id]:
            if c.id in special or rng.random() < 0.3:
                continue
            for k in range(rng.choice([1, 1, 2])):
                plat, plon = lat + rng.uniform(-0.025, 0.025), lon + rng.uniform(-0.025, 0.025)
                taken = inc.started_at + timedelta(hours=rng.randint(4, 120))
                _add_photo(db, c, _photo_bytes(f"claim {c.id}", rng, plat, plon, taken), f"IMG_{c.id:04d}_{k + 1}.jpg")

    def near(inc, lon, lat, label):
        return _photo_bytes(label, rng, lat + rng.uniform(-0.01, 0.01), lon + rng.uniform(-0.01, 0.01),
                            inc.started_at + timedelta(hours=rng.randint(6, 48)))

    _add_photo(db, over_rate, near(chainat, cn_lon, cn_lat, f"claim {over_rate.id}"), f"IMG_{over_rate.id:04d}_1.jpg")
    _add_photo(db, over_cap, near(phayuha, ph_lon, ph_lat, f"claim {over_cap.id}"), f"IMG_{over_cap.id:04d}_1.jpg")
    _add_photo(db, field, near(pamok, pm_lon, pm_lat, f"claim {field.id}"), f"IMG_{field.id:04d}_1.jpg")
    shared = near(chainat, cn_lon, cn_lat, f"claim {reused_from.id}")
    _add_photo(db, reused_from, shared, f"IMG_{reused_from.id:04d}_1.jpg")
    _add_photo(db, reused_to, shared, "flood_damage.jpg")
    _add_photo(db, far, _photo_bytes(f"claim {far.id}", rng, 14.80, 100.65, pamok.started_at + timedelta(hours=20)),
               f"IMG_{far.id:04d}_1.jpg")  # Lop Buri, ~45 km away
    _add_photo(db, before, _photo_bytes(f"claim {before.id}", rng, ph_lat + 0.01, ph_lon - 0.01,
                                        phayuha.started_at - timedelta(days=41)), f"IMG_{before.id:04d}_1.jpg")
    _add_photo(db, stripped, _photo_bytes(f"claim {stripped.id}", rng, exif=False), "Screenshot 2569-10-20.png.jpg")
    db.commit()

    n_claims = sum(len(v) for v in claims_by_inc.values())
    n_photos = db.query(models.ClaimPhoto).count()
    return {"status": "seeded", "incidents": len(incidents), "claims": n_claims, "photos": n_photos}
