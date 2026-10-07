"""Signed vaccination certificates: public trust and revocation lists, owner certificates, staff issue/correct."""

from uuid import UUID

from fastapi import APIRouter, Request, Response

from pawguard_api.credential_contracts import (
    CredentialPhotoOut,
    DemoSamplesOut,
    EvidenceCheckOut,
    IssuedOut,
    PetCertificatesOut,
    SignedListOut,
    VaccinationCorrect,
)
from pawguard_api.deps import CurrentOrg, CurrentPrincipal
from pawguard_api.domain import credentials, evidence_check, petcare, vaccinations
from pawguard_api.errors import ApiError
from pawguard_api.integrations.cose import SigningUnavailable

router = APIRouter(tags=["certificates (signed)"])


def _signed(doc_fn: object, response: Response) -> SignedListOut:
    try:
        doc = doc_fn()  # type: ignore[operator]
    except SigningUnavailable as exc:
        raise ApiError("Certificate verification lists are not set up on this server.", code="signing_unavailable",
                       status_code=503) from exc
    response.headers["cache-control"] = "public, max-age=60"
    return SignedListOut(**doc)


@router.get("/api/v1/public/trust-list", response_model=SignedListOut, summary="Signed list of trusted clinic keys")
def trust_list(response: Response) -> SignedListOut:
    """Permission: public. COSE_Sign1 signed by the platform root key (its public key is built into the app).
    Retired keys stay listed so older certificates still verify; revoked keys are marked revoked."""
    return _signed(credentials.trust_list, response)


@router.get("/api/v1/public/revocations", response_model=SignedListOut, summary="Signed list of cancelled certificates")
def revocations(response: Response) -> SignedListOut:
    """Permission: public. Certificate ids that a clinic cancelled or replaced; signed by the platform root key."""
    return _signed(credentials.revocation_list, response)


@router.get("/api/v1/public/credentials/{credential_id}/photo", response_model=CredentialPhotoOut,
            summary="Pet photo for comparison (online check)")
def credential_photo(credential_id: UUID, response: Response) -> CredentialPhotoOut:
    """Permission: public; the credential id comes from a scanned certificate. Only for active certificates; returns
    the pet's photo if it has one, never anything about the owner or a location."""
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex"
    return CredentialPhotoOut(photo_url=credentials.credential_photo(credential_id))


@router.get("/api/v1/public/demo-certificates", response_model=DemoSamplesOut,
            summary="Demo sample certificates (demo mode only)")
def demo_certificates() -> DemoSamplesOut:
    """Permission: public, demo mode only. A genuine, an altered (one date changed, not re-signed) and a cancelled
    certificate from the fictional demo clinics."""
    return DemoSamplesOut(**credentials.demo_samples())


@router.get("/api/v1/my/pets/{pet_id}/certificates", response_model=PetCertificatesOut,
            summary="My pet's signed vaccination certificates")
def my_certificates(pet_id: UUID, p: CurrentPrincipal, request: Request) -> PetCertificatesOut:
    """Permission: the caller owns this pet. Verified vaccinations with their signed QR; owner-entered records are
    only counted (never signed)."""
    ctx = petcare.owned_context(p, pet_id, getattr(request.state, "request_id", None))
    with ctx.tx() as db:
        return PetCertificatesOut(**credentials.pet_certificates(db, pet_id))


@router.post("/api/v1/vaccination-events/{event_id}/certificate", status_code=201, response_model=IssuedOut,
             summary="Issue (or re-issue) the signed certificate for a verified record")
def issue_certificate(event_id: UUID, ctx: CurrentOrg) -> IssuedOut:
    """Permission: veterinary reviewer of the record's organisation. Refused (409 not_verified) for records that no
    vet has verified, including owner-entered ones. An existing certificate is replaced (revoked) first."""
    from pawguard_api.capabilities import Cap

    ctx.require(Cap.VACCINATION_REVIEW)
    actor = credentials.Actor(ctx.org_id, ctx.user_id, ctx.request_id)
    with ctx.tx() as db:
        try:
            new_id = credentials.issue_replacing(db, actor, event_id)
        except SigningUnavailable as exc:
            raise ApiError("Signing is not set up on this server.", code="signing_unavailable",
                           status_code=503) from exc
    return IssuedOut(credential_id=new_id)


@router.post("/api/v1/vaccination-events/{event_id}/correction", status_code=201, response_model=IssuedOut,
             summary="Correct a verified record (vet); replaces its signed certificate")
def correct(event_id: UUID, body: VaccinationCorrect, ctx: CurrentOrg) -> IssuedOut:
    """Permission: approved veterinary reviewer. A new verified record supersedes the old one; the old certificate is
    revoked (pointing at the new one) and a new certificate is issued, in one transaction."""
    with ctx.tx() as db:
        new_event = vaccinations.correct_verified(db, ctx, event_id, body)
        cid = db.execute(credentials.ACTIVE_FOR_EVENT, {"e": new_event}).scalar()
    if cid is None:
        raise ApiError("Corrected, but signing is not set up on this server.", code="signing_unavailable",
                       status_code=503)
    return IssuedOut(credential_id=cid)


@router.get("/api/v1/vaccination-events/{event_id}/evidence-check", response_model=EvidenceCheckOut,
            summary="AI-assisted check of a record's certificates")
def check_evidence(event_id: UUID, ctx: CurrentOrg) -> EvidenceCheckOut:
    """Permission: clinic staff. For each attached certificate: verifies a signed PawGuard QR if present, reads the
    certificate (OCR / Gemini vision for sample clinics) and compares date, vaccine and batch with the record, and flags
    a file already used for another record. Assists the vet — never verifies or rejects on its own."""
    with ctx.tx() as db:
        return EvidenceCheckOut(**evidence_check.check_event(db, ctx, event_id))
