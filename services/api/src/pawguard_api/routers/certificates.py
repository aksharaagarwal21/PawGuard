"""Certificate reading (OCR): a draft for the person to check; a vet still verifies the record."""

from uuid import UUID

from fastapi import APIRouter, Request

from pawguard_api.deps import CurrentOrg, CurrentPrincipal
from pawguard_api.domain import certificates
from pawguard_api.notify_contracts import CertificateDraftOut, OcrStatusOut

router = APIRouter(prefix="/api/v1", tags=["certificates"])


@router.get("/ocr/status", response_model=OcrStatusOut, summary="Is certificate reading available?")
def ocr_status(p: CurrentPrincipal) -> OcrStatusOut:
    """Permission: any signed-in user."""
    return OcrStatusOut(**certificates.status())


@router.post("/my/certificates/{media_id}/read", response_model=CertificateDraftOut,
             summary="Read my certificate photo into a draft")
def read_certificate(media_id: UUID, p: CurrentPrincipal, request: Request) -> CertificateDraftOut:
    """Permission: the person who uploaded the certificate. Reads the photo (not PDFs) with OCR and returns a draft —
    dates, matched vaccine, batch — to check before saving. The full text is not stored. 20 reads an hour."""
    return CertificateDraftOut(**certificates.read_own(p, media_id, getattr(request.state, "request_id", None)))


@router.get("/vaccination-events/{event_id}/certificate-drafts", response_model=list[CertificateDraftOut],
            summary="OCR drafts for a record's certificates")
def drafts(event_id: UUID, ctx: CurrentOrg) -> list[CertificateDraftOut]:
    """Permission: clinic staff. Shown beside the image in the review workbench; never verifies anything."""
    with ctx.tx() as db:
        return [CertificateDraftOut(**d) for d in certificates.drafts_for_event(db, ctx, event_id)]
