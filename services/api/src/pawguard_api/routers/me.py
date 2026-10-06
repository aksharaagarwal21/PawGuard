from fastapi import APIRouter
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from pawguard_api.db import user_tx
from pawguard_api.deps import CurrentOrg, CurrentPrincipal
from pawguard_api.errors import Conflict
from pawguard_api.models import Membership, Organisation, ProfessionalApproval, UserProfile
from pawguard_api.schemas import ActiveOrgOut, EnvironmentOut, MembershipOut, MeOut, MeUpdate
from pawguard_api.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["me"])


def _load_me(p: CurrentPrincipal) -> MeOut:
    s = get_settings()
    with user_tx(p.user_id) as db:
        db.execute(insert(UserProfile).values(user_id=p.user_id).on_conflict_do_nothing())
        profile = db.get(UserProfile, p.user_id)
        assert profile is not None
        rows = db.execute(
            select(Membership, Organisation)
            .join(Organisation, Organisation.id == Membership.org_id)
            .where(Membership.user_id == p.user_id, Membership.status == "active",
                   Membership.valid_from <= text("now()"),
                   Membership.valid_until.is_(None) | (Membership.valid_until > text("now()")))
            .order_by(Organisation.name)
        ).all()
        scopes = db.execute(
            select(ProfessionalApproval.org_id, ProfessionalApproval.scope).where(
                ProfessionalApproval.user_id == p.user_id, ProfessionalApproval.review_state == "approved",
                ProfessionalApproval.valid_from <= text("now()"),
                ProfessionalApproval.valid_until.is_(None) | (ProfessionalApproval.valid_until > text("now()")))
        ).all()
    by_org: dict[object, list[str]] = {}
    for org_id, scope in scopes:
        by_org.setdefault(org_id, []).append(scope)
    return MeOut(
        user_id=p.user_id, email=p.email, preferred_name=profile.preferred_name, locale=profile.locale,
        profile_row_version=profile.row_version,
        memberships=[MembershipOut(membership_id=m.id, org_id=o.id, org_name=o.name, org_is_demo=o.is_demo,
                                   org_type=o.org_type, timezone=o.timezone, role=m.role,
                                   capabilities=sorted(m.capabilities),
                                   professional_scopes=sorted(by_org.get(o.id, [])))
                     for m, o in rows if o.activation_state == "active"],
        environment=EnvironmentOut(env=s.env, demo_mode=s.demo_mode),
    )


@router.get("/me", response_model=MeOut, summary="Current user, memberships and capabilities")
def get_me(p: CurrentPrincipal) -> MeOut:
    """Permission: any signed-in user. Capabilities come from the database, never from the token."""
    return _load_me(p)


@router.patch("/me", response_model=MeOut, summary="Update own display name or language")
def patch_me(body: MeUpdate, p: CurrentPrincipal) -> MeOut:
    """Permission: any signed-in user, own profile only. Requires the current ``row_version``."""
    values = body.model_dump(exclude_unset=True, exclude={"row_version"})
    if values:
        with user_tx(p.user_id) as db:
            res = db.execute(update(UserProfile)
                             .where(UserProfile.user_id == p.user_id, UserProfile.row_version == body.row_version)
                             .values(**values))
            if res.rowcount != 1:
                raise Conflict("Your profile changed elsewhere. Reload and try again.", code="stale_row_version")
    return _load_me(p)


@router.get("/me/organisation", response_model=ActiveOrgOut, summary="The organisation requests are made for")
def get_active_org(ctx: CurrentOrg) -> ActiveOrgOut:
    """Permission: an active member. Lets clients (e.g. the offline field kit) bind queued work to the organisation
    and account the server will apply it to."""
    return ActiveOrgOut(user_id=ctx.user_id, org_id=ctx.org_id, org_name=ctx.org_name,
                        membership_id=ctx.membership_id, role=ctx.role, capabilities=sorted(ctx.capabilities))
