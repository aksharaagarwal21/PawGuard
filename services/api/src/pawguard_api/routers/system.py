"""Maintainer-facing provider health. Shows what is configured/available — never secret values."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import Out
from pawguard_api.deps import OrgContext, requires
from pawguard_api.domain import identity
from pawguard_api.routers.health import check_components
from pawguard_api.settings import get_settings

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class ProviderCapability(Out):
    key: str
    status: str  # available | unavailable | preview_only | not_configured | research_only
    detail: str


class ProvidersOut(Out):
    components: dict[str, dict[str, object]]
    capabilities: list[ProviderCapability]


@router.get("/providers", response_model=ProvidersOut, summary="Provider and integration status")
def providers(ctx: Annotated[OrgContext, Depends(requires(Cap.SYSTEM_VIEW))]) -> ProvidersOut:
    """Permission: ``system.view`` in the selected organisation."""
    s = get_settings()
    with ctx.tx() as db:
        active = {r.task: r for r in db.execute(text(
            "select task, name, version_label from app.model_versions where state = 'active'")).all()}
        preview = db.execute(text("select name, version_label from app.model_versions "
                                  "where task = 'identity_embedding' and research_preview")).one_or_none()
        fb = identity.feedback(db, ctx) if ctx.can(Cap.IDENTITY_SEARCH) else None
    det = active.get("dog_detection")
    ident = active.get("identity_embedding")
    usage = (f" Decisions so far: {fb.decisions} ({fb.chose_top1} chose the first suggestion, "
             f"{fb.chose_other_suggestion} another suggestion, {fb.chose_unsuggested_animal} an animal that was not "
             f"suggested, {fb.new_animal} new, {fb.not_sure} not sure).") if fb and fb.decisions else ""
    if ident:
        ident_cap = ProviderCapability(key="identity_matching", status="available",
                                       detail=f"Active model: {ident.name} {ident.version_label}. Suggestions need "
                                              "human confirmation." + usage)
    elif preview:
        ident_cap = ProviderCapability(key="identity_matching", status="research_only",
                                       detail=f"Research model {preview.name} {preview.version_label} has not passed "
                                              "the release gate. Demo organisations can preview it; real "
                                              "organisations use manual search and registration." + usage)
    else:
        ident_cap = ProviderCapability(key="identity_matching", status="unavailable",
                                       detail="No identity model is active. Manual search and registration are the "
                                              "full workflow.")
    caps = [
        ident_cap,
        ProviderCapability(key="dog_detection", status="available" if det else "unavailable",
                           detail=f"Active model: {det.name} {det.version_label} (assistive; boxes only)." if det
                           else "No detector model is active; photos are stored without automatic boxes."),
        ProviderCapability(key="map_tiles", status="available" if s.map_tile_url else "not_configured",
                           detail="Basemap tiles configured." if s.map_tile_url
                           else "Maps show boundaries and markers without a basemap; lists always available."),
        ProviderCapability(key="notifications", status="preview_only",
                           detail="In-app notices and previews only. No SMS/email/WhatsApp provider configured."),
        ProviderCapability(key="assistant_generation", status="not_configured",
                           detail="No language-model provider configured (Phase 10)."),
    ]
    return ProvidersOut(components=check_components(), capabilities=caps)
