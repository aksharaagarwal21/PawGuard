"""Private media: upload intents → direct upload to a single signed object key → completion check → worker
validation from bytes. Records may reference media only once it is uploaded (and it is shown only once
approved). Download links are short-lived and issued after an authorisation check."""

from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import (
    DetectionOut,
    MediaAnalysisOut,
    MediaOut,
    QualityOut,
    SignedUrlOut,
    UploadIntentCreate,
    UploadIntentOut,
)
from pawguard_api.deps import OrgContext
from pawguard_api.domain.common import enqueue_job, record_audit
from pawguard_api.errors import Conflict, NotFound, Unprocessable
from pawguard_api.integrations.storage import (
    DOWNLOAD_TTL_SECONDS,
    SIGNED_UPLOAD_TTL_SECONDS,
    get_storage,
    quarantine_key,
)
from pawguard_api.models import MediaAsset

PDF_ALLOWED_PURPOSES = {"vaccination_evidence", "document"}


def create_upload_intent(db: Session, ctx: OrgContext, data: UploadIntentCreate) -> UploadIntentOut:
    ctx.require(Cap.MEDIA_UPLOAD)
    if data.content_type == "application/pdf" and data.purpose not in PDF_ALLOWED_PURPOSES:
        raise Unprocessable("Animal photos must be JPEG, PNG or WebP images.", code="unsupported_type")
    storage = get_storage()
    media_id = uuid4()
    key = quarantine_key(ctx.org_id, media_id)
    db.add(MediaAsset(id=media_id, org_id=ctx.org_id, created_by=ctx.user_id, bucket=storage.bucket, object_key=key,
                      purpose=data.purpose, declared_mime=data.content_type, declared_bytes=data.byte_size,
                      source_rights=data.source_rights, consent_scope=data.consent_scope,
                      uploader_user_id=ctx.user_id, is_demo=False))
    db.flush()
    url = storage.signed_upload_url(key)
    record_audit(db, ctx, "media.upload_intent_created", "media", media_id,
                 {"purpose": data.purpose, "type": data.content_type})
    return UploadIntentOut(media_id=media_id, upload_url=url, headers={"Content-Type": data.content_type},
                           expires_in_seconds=SIGNED_UPLOAD_TTL_SECONDS)


def _load(db: Session, media_id: UUID, for_update: bool = False) -> MediaAsset:
    stmt = select(MediaAsset).where(MediaAsset.id == media_id)
    media = db.execute(stmt.with_for_update() if for_update else stmt).scalar_one_or_none()
    if media is None:
        raise NotFound("File not found.", code="media_not_found")
    return media


def complete_upload(db: Session, ctx: OrgContext, media_id: UUID) -> MediaOut:
    ctx.require(Cap.MEDIA_UPLOAD)
    media = _load(db, media_id, for_update=True)
    if media.uploader_user_id != ctx.user_id:
        raise NotFound("File not found.", code="media_not_found")
    if media.state != "pending_upload":
        return media_out(db, media)  # idempotent: completion already recorded
    info = get_storage().info(media.object_key)
    if info is None:
        raise Conflict("The file has not finished uploading.", code="upload_incomplete")
    if info.size != media.declared_bytes or (info.content_type or "") != media.declared_mime:
        media.state = "rejected"
        media.rejection_code = "declared_metadata_mismatch"
        get_storage().remove([media.object_key])
        record_audit(db, ctx, "media.rejected", "media", media.id, {"code": media.rejection_code})
        db.flush()
        return media_out(db, media)
    media.state = "uploaded"
    media.byte_size = info.size
    media.uploaded_at = text("now()")
    enqueue_job(db, ctx, "media.validate", "media", media.id)
    record_audit(db, ctx, "media.uploaded", "media", media.id, {"bytes": info.size})
    db.flush()
    return media_out(db, media)


def cancel_upload(db: Session, ctx: OrgContext, media_id: UUID) -> None:
    media = _load(db, media_id, for_update=True)
    if media.uploader_user_id != ctx.user_id:
        raise NotFound("File not found.", code="media_not_found")
    in_use = db.execute(text("""select exists(select 1 from app.observation_media where media_id = :m)
                                or exists(select 1 from app.vaccination_evidence where media_id = :m)"""),
                        {"m": media_id}).scalar()
    if in_use:
        raise Conflict("This file is already attached to a record and is kept as evidence.", code="media_in_use")
    if media.state in ("pending_upload", "uploaded", "rejected"):
        media.state = "deleted"
        get_storage().remove([media.object_key])
        record_audit(db, ctx, "media.cancelled", "media", media.id)


def media_out(db: Session, media: MediaAsset) -> MediaOut:
    job_state = db.execute(text("select state from app.background_jobs where target_id = :m "
                                "order by queued_at desc limit 1"), {"m": media.id}).scalar()
    return MediaOut(id=media.id, purpose=media.purpose, state=media.state, rejection_code=media.rejection_code,
                    detected_mime=media.detected_mime, width=media.width, height=media.height,
                    byte_size=media.byte_size, created_at=media.created_at, validated_at=media.validated_at,
                    job_state=job_state)


def _require_read(ctx: OrgContext, media: MediaAsset) -> None:
    """Registry readers see any file in their organisation; uploaders (e.g. pet owners) see their own uploads."""
    if not (media.uploader_user_id == ctx.user_id and ctx.can(Cap.MEDIA_UPLOAD)):
        ctx.require(Cap.ANIMAL_READ)


def get_media(db: Session, ctx: OrgContext, media_id: UUID) -> MediaOut:
    media = _load(db, media_id)
    _require_read(ctx, media)
    return media_out(db, media)


def signed_url(db: Session, ctx: OrgContext, media_id: UUID, variant: str) -> SignedUrlOut:
    """Only approved files, only derivatives (metadata-stripped) — never the quarantined original."""
    media = _load(db, media_id)
    _require_read(ctx, media)
    if media.state != "approved":
        raise Conflict("This file is not available yet.", code="media_not_approved", details={"state": media.state})
    key = (media.derivatives or {}).get(variant)
    if not key:
        raise NotFound("That version of the file does not exist.", code="variant_not_found")
    url = get_storage().signed_download_urls([key]).get(key)
    if not url:
        raise NotFound("File not found.", code="media_not_found")
    record_audit(db, ctx, "media.accessed", "media", media.id, {"variant": variant})
    return SignedUrlOut(url=url, expires_in_seconds=DOWNLOAD_TTL_SECONDS)



def analysis(db: Session, ctx: OrgContext, media_id: UUID) -> MediaAnalysisOut:
    """Quality + detection results for an animal photo, with an explicit state for every outcome."""
    ctx.require(Cap.ANIMAL_READ)
    media = _load(db, media_id)
    if media.purpose != "animal_photo":
        return MediaAnalysisOut(state="not_applicable")
    if media.state in ("pending_upload", "uploaded", "validating"):
        return MediaAnalysisOut(state="pending")
    if media.state != "approved":
        return MediaAnalysisOut(state="not_applicable", failure_code=media.rejection_code)
    job = db.execute(text("select state, last_error_code from app.background_jobs where target_id = :m "
                          "and job_type = 'media.analyse' order by queued_at desc limit 1"),
                     {"m": media_id}).one_or_none()
    if job is None or job.state in ("queued", "processing"):
        return MediaAnalysisOut(state="pending")
    quality_rows = db.execute(text("""select region_key, warnings, decision, sharpness, brightness
                                      from app.image_quality_results where media_id = :m order by region_key"""),
                              {"m": media_id}).all()
    quality = [QualityOut(region=q.region_key, warnings=list(q.warnings), decision=q.decision,
                          sharpness=q.sharpness, brightness=q.brightness) for q in quality_rows]
    if job.state == "failed":
        return MediaAnalysisOut(state="failed", failure_code=job.last_error_code, quality=quality)
    det = db.execute(text("""select d.*, mv.name, mv.version_label from app.detection_results d
                             join app.model_versions mv on mv.id = d.model_version_id
                             where d.media_id = :m order by d.created_at desc limit 1"""),
                     {"m": media_id}).one_or_none()
    if det is None:
        return MediaAnalysisOut(state="unavailable", quality=quality, image_width=media.width,
                                image_height=media.height)
    dogs = [DetectionOut(label="dog", x=d["x"], y=d["y"], w=d["w"], h=d["h"])
            for d in det.detections if d.get("label") == "dog"]
    return MediaAnalysisOut(state="completed" if dogs else "no_animal", dogs=dogs, person_count=det.person_count,
                            image_width=det.image_width, image_height=det.image_height, quality=quality,
                            model_name=det.name, model_version=det.version_label,
                            pipeline_version=det.pipeline_version)
