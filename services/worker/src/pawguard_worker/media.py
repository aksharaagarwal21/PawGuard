"""Media validation from bytes (never from the declared Content-Type or file name).

Images: decoded with Pillow under a pixel budget (decompression-bomb guard), format must match the declared
type, EXIF orientation applied, then re-encoded as metadata-free JPEG derivatives (display ≤1600 px, thumb ≤320 px).
The quarantined original is deleted once derivatives exist, so stored location/EXIF metadata does not linger.
PDFs: header and size checked and the bytes copied to the derived area unparsed (no PDF rendering in the worker).
"""

import contextlib
import hashlib
import io
import warnings
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text

from pawguard_api.integrations.storage import derived_key, get_storage
from pawguard_worker.jobs import JobContext, TerminalJobError

PIPELINE_VERSION = "media-validate-1"
MAX_PIXELS = 40_000_000  # ~ 8000 × 5000
MIN_SIDE = 64
FORMAT_FOR_MIME = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
VARIANTS = {"display": 1600, "thumb": 320}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def _jpeg(img: Image.Image, max_side: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    copy.save(buf, format="JPEG", quality=85, optimize=True)  # no exif/icc passed → metadata stripped
    return buf.getvalue()


def decode_image(data: bytes, declared_mime: str) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            probe = Image.open(io.BytesIO(data))
            fmt = probe.format
            probe.verify()
            img = Image.open(io.BytesIO(data))
            img.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise TerminalJobError("too_many_pixels") from exc
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise TerminalJobError("decode_failed") from exc
    if fmt != FORMAT_FOR_MIME.get(declared_mime):
        raise TerminalJobError("type_mismatch")
    img = ImageOps.exif_transpose(img)
    if min(img.size) < MIN_SIDE:
        raise TerminalJobError("too_small")
    return img.convert("RGB")


def validate(ctx: JobContext) -> dict[str, Any]:
    with ctx.tx() as c:
        m = c.execute(text("select * from app.media_assets where id = :id"), {"id": ctx.target_id}).one_or_none()
        if m is None:
            raise TerminalJobError("media_missing")
        if m.state not in ("uploaded", "validating"):
            if m.state == "approved":
                _queue_analysis(ctx)  # idempotent: covers a retry after approval succeeded
            return {"skipped": m.state}
        c.execute(text("update app.media_assets set state = 'validating' where id = :id"), {"id": m.id})
    storage = get_storage()
    try:
        data = storage.download(m.object_key, max_bytes=m.declared_bytes)
    except FileNotFoundError as exc:
        raise TerminalJobError("object_missing") from exc
    except ValueError as exc:
        raise TerminalJobError("size_mismatch") from exc
    sha = hashlib.sha256(data).hexdigest()
    derivatives: dict[str, str] = {}
    width = height = None
    if m.declared_mime == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise TerminalJobError("type_mismatch")
        key = derived_key(m.org_id, m.id, "original.pdf")
        storage.upload(key, data, "application/pdf")
        derivatives["original"] = key
        detected = "application/pdf"
    else:
        img = decode_image(data, m.declared_mime)
        width, height = img.size
        for variant, side in VARIANTS.items():
            key = derived_key(m.org_id, m.id, f"{variant}.jpg")
            storage.upload(key, _jpeg(img, side), "image/jpeg")
            derivatives[variant] = key
        derivatives["original"] = derivatives["display"]
        detected = m.declared_mime
    with ctx.tx() as c:
        dup = c.execute(text("select id from app.media_assets where org_id = :o and sha256 = :s and id <> :id "
                             "and state = 'approved' limit 1"), {"o": m.org_id, "s": sha, "id": m.id}).scalar()
        c.execute(text("""update app.media_assets set state = 'approved', detected_mime = :mime, sha256 = :sha,
                          width = :w, height = :h, derivatives = cast(:d as jsonb), validated_at = now()
                          where id = :id"""),
                  {"mime": detected, "sha": sha, "w": width, "h": height, "id": m.id,
                   "d": __import__("json").dumps(derivatives)})
        if dup:
            c.execute(text("""insert into app.data_quality_issues (org_id, resource_type, resource_id, rule, severity,
                              explanation) values (:o, 'media', :id, 'exact_duplicate_file', 'info',
                              'Identical bytes to another file in this organisation.')"""), {"o": m.org_id, "id": m.id})
    if m.declared_mime != "application/pdf":
        storage.remove([m.object_key])  # drop the original with its EXIF/GPS metadata
    _queue_analysis(ctx)
    return {"pipeline": PIPELINE_VERSION, "derivatives": sorted(derivatives), "duplicate": bool(dup)}


def _queue_analysis(ctx: JobContext) -> None:
    from pawguard_worker.analysis import queue_analysis
    from pawguard_worker.identity import queue_enrolment_for_media

    queue_analysis(ctx)
    queue_enrolment_for_media(ctx)


def reject(ctx: JobContext, code: str) -> None:
    with ctx.tx() as c:
        key = c.execute(text("""update app.media_assets set state = 'rejected', rejection_code = :code
                                where id = :id and state in ('uploaded','validating') returning object_key"""),
                        {"code": code, "id": ctx.target_id}).scalar()
    if key:
        with contextlib.suppress(Exception):  # an orphan-cleanup job removes anything left behind
            get_storage().remove([key])
