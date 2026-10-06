from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response

from pawguard_api.contracts import MediaAnalysisOut, MediaOut, SignedUrlOut, UploadIntentCreate, UploadIntentOut
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import media

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.post("/upload-intents", status_code=201, response_model=UploadIntentOut, summary="Prepare a private upload")
def create_intent(body: UploadIntentCreate, ctx: CurrentOrg) -> UploadIntentOut:
    """Permission: ``media.upload``. Returns a signed URL for exactly one quarantined object key. Uploading does not
    make a file trusted: it is validated from its bytes before it can be shown or used as evidence."""
    with ctx.tx() as db:
        return media.create_upload_intent(db, ctx, body)


@router.post("/{media_id}/complete", response_model=MediaOut, summary="Confirm an upload finished")
def complete(media_id: UUID, ctx: CurrentOrg) -> MediaOut:
    """Permission: ``media.upload``, uploader only. Checks the stored object's size and declared type, then queues
    validation. Idempotent."""
    with ctx.tx() as db:
        return media.complete_upload(db, ctx, media_id)


@router.get("/{media_id}", response_model=MediaOut, summary="File status")
def get(media_id: UUID, ctx: CurrentOrg) -> MediaOut:
    """Permission: ``animal.read``. Poll this for validation progress."""
    with ctx.tx() as db:
        return media.get_media(db, ctx, media_id)


@router.get("/{media_id}/analysis", response_model=MediaAnalysisOut, summary="Photo quality and detected animals")
def get_analysis(media_id: UUID, ctx: CurrentOrg) -> MediaAnalysisOut:
    """Permission: ``animal.read``. Advisory only: boxes say where an animal *may* be in the photo so the person can
    choose the subject; they do not identify the animal. ``unavailable``/``failed`` never block manual entry."""
    with ctx.tx() as db:
        return media.analysis(db, ctx, media_id)


@router.get("/{media_id}/url", response_model=SignedUrlOut, summary="Short-lived link to a validated file")
def url(media_id: UUID, ctx: CurrentOrg,
        variant: Annotated[Literal["display", "thumb", "original"], Query()] = "display") -> SignedUrlOut:
    """Permission: ``animal.read``. Only approved files; links expire after 120 seconds and access is audited.
    ``original`` refers to the validated, metadata-stripped copy (PDF evidence is stored as uploaded)."""
    with ctx.tx() as db:
        return media.signed_url(db, ctx, media_id, variant)


@router.delete("/{media_id}", status_code=204, summary="Cancel an unused upload")
def cancel(media_id: UUID, ctx: CurrentOrg) -> Response:
    """Permission: uploader only. Files already attached to a record are kept as evidence."""
    with ctx.tx() as db:
        media.cancel_upload(db, ctx, media_id)
    return Response(status_code=204)
