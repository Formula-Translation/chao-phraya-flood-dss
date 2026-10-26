"""Store claim photos and read their EXIF (time taken, GPS position, camera).

Each upload is kept three ways under settings.upload_dir:
    <uuid>.<ext>         the original file, untouched (evidence)
    <uuid>.jpg           a browser-friendly copy, max 1600 px (HEIC → JPEG)
    thumbs/<uuid>.jpg    a 360 px thumbnail
"""
import hashlib
import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

try:  # iPhone photos
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - optional
    pass

BKK = timezone(timedelta(hours=7))  # EXIF times carry no zone; field photos are taken in Thailand

EXIF_IFD, GPS_IFD = 0x8769, 0x8825
TAG_DATETIME_ORIGINAL, TAG_DATETIME_DIGITIZED, TAG_DATETIME = 0x9003, 0x9004, 0x0132
TAG_MAKE, TAG_MODEL = 0x010F, 0x0110


class PhotoError(ValueError):
    pass


def root() -> Path:
    p = Path(settings.upload_dir)
    (p / "thumbs").mkdir(parents=True, exist_ok=True)
    return p


def paths(stored_name: str, original_ext: str) -> dict[str, Path]:
    r = root()
    return {
        "original": r / f"{stored_name}{original_ext}",
        "display": r / f"{stored_name}.jpg",
        "thumb": r / "thumbs" / f"{stored_name}.jpg",
    }


def _ratio(v) -> float:
    try:
        return float(v)
    except TypeError:
        num, den = v
        return float(num) / float(den) if den else 0.0


def _dms(values, ref) -> float | None:
    try:
        d, m, s = (_ratio(x) for x in values)
    except Exception:
        return None
    deg = d + m / 60 + s / 3600
    if isinstance(ref, bytes):
        ref = ref.decode(errors="ignore")
    return -deg if str(ref).upper().startswith(("S", "W")) else deg


def read_exif(img: Image.Image) -> dict:
    out: dict = {"taken_at": None, "lat": None, "lon": None, "camera": None}
    try:
        exif = img.getexif()
    except Exception:
        return out
    sub = exif.get_ifd(EXIF_IFD)
    raw = sub.get(TAG_DATETIME_ORIGINAL) or sub.get(TAG_DATETIME_DIGITIZED) or exif.get(TAG_DATETIME)
    if raw:
        try:
            out["taken_at"] = datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S").replace(tzinfo=BKK)
        except ValueError:
            pass
    gps = exif.get_ifd(GPS_IFD)
    if gps and 2 in gps and 4 in gps:
        lat, lon = _dms(gps[2], gps.get(1, "N")), _dms(gps[4], gps.get(3, "E"))
        if lat is not None and lon is not None and (lat or lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            out["lat"], out["lon"] = round(lat, 6), round(lon, 6)
    make, model = exif.get(TAG_MAKE), exif.get(TAG_MODEL)
    cam = " ".join(str(x).strip("\x00 ").strip() for x in (make, model) if x)
    out["camera"] = cam or None
    return out


def save(data: bytes, filename: str, content_type: str | None) -> dict:
    """Validate and store an uploaded image. Returns the fields for a ClaimPhoto row."""
    if len(data) > settings.max_photo_mb * 1024 * 1024:
        raise PhotoError(f"{filename} is larger than {settings.max_photo_mb} MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise PhotoError(f"{filename} isn't an image this system can read (use JPEG, PNG or HEIC)")

    meta = read_exif(img)
    width, height = img.size
    ext = Path(filename).suffix.lower()[:10] or "." + (img.format or "img").lower()
    stored = uuid.uuid4().hex
    p = paths(stored, ext)
    p["original"].write_bytes(data)

    shown = ImageOps.exif_transpose(img)
    if shown.mode not in ("RGB", "L"):
        shown = shown.convert("RGB")
    disp = shown.copy()
    disp.thumbnail((1600, 1600))
    disp.save(p["display"], "JPEG", quality=85)
    thumb = shown.copy()
    thumb.thumbnail((360, 360))
    thumb.save(p["thumb"], "JPEG", quality=80)

    return {
        "filename": filename[:300], "stored_name": stored, "original_ext": ext,
        "content_type": content_type, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "width": width, "height": height, **meta,
    }


def delete_files(stored_name: str, original_ext: str) -> None:
    for f in paths(stored_name, original_ext).values():
        f.unlink(missing_ok=True)
