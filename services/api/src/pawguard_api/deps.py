"""FastAPI dependencies: authentication, organisation membership, capability checks.

Flow for an organisation-scoped request:
1. ``principal``: verify bearer token (signature, iss, aud, exp, role).
2. ``org_context``: the ``X-PawGuard-Org`` header *selects* an organisation; the membership row (active, valid
   now) is the proof. Capabilities and professional scopes are loaded from the database, never the token.
3. Handlers open ``ctx.tx()`` — a transaction with RLS context — for all reads/writes.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pawguard_api.auth import Principal, TokenVerifier
from pawguard_api.capabilities import PROFESSIONAL_SCOPE_FOR, Cap
from pawguard_api.db import user_tx
from pawguard_api.db_errors import map_db_error
from pawguard_api.errors import Forbidden, Unauthenticated
from pawguard_api.models import Membership, Organisation, ProfessionalApproval
from pawguard_api.settings import get_settings


@lru_cache
def get_verifier() -> TokenVerifier:
    return TokenVerifier(get_settings())


def principal(request: Request, verifier: Annotated[TokenVerifier, Depends(get_verifier)],
              authorization: Annotated[str | None, Header()] = None) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("Sign in to continue.", code="unauthenticated")
    p = verifier.verify(authorization[7:].strip())
    request.state.user_id = str(p.user_id)
    return p


CurrentPrincipal = Annotated[Principal, Depends(principal)]


@dataclass
class OrgContext:
    principal: Principal
    org_id: UUID
    membership_id: UUID
    role: str
    capabilities: frozenset[str]
    professional_scopes: frozenset[str]
    request_id: str | None
    timezone: str = "UTC"
    org_name: str = ""
    _session_checked: bool = field(default=False, repr=False)

    @property
    def user_id(self) -> UUID:
        return self.principal.user_id

    @contextmanager
    def tx(self) -> Iterator[Session]:
        """One transaction with this caller's RLS context. Database rule violations (including those raised at
        commit) surface as structured API errors."""
        try:
            with user_tx(self.principal.user_id, self.org_id) as db:
                yield db
        except DBAPIError as exc:
            raise map_db_error(exc) from exc

    def can(self, cap: Cap) -> bool:
        if cap.value not in self.capabilities:
            return False
        scope = PROFESSIONAL_SCOPE_FOR.get(cap)
        return scope is None or scope in self.professional_scopes

    def require(self, cap: Cap) -> None:
        if cap.value not in self.capabilities:
            raise Forbidden("You don't have permission to do this.", code="missing_capability",
                            details={"capability": cap.value})
        scope = PROFESSIONAL_SCOPE_FOR.get(cap)
        if scope and scope not in self.professional_scopes:
            raise Forbidden("This action needs an approved professional authority.",
                            code="missing_professional_approval", details={"scope": scope})

    def require_live_session(self, db: Session) -> None:
        """For sensitive commands: the Auth session must still exist server-side (not signed out/revoked)."""
        if self._session_checked:
            return
        sid = self.principal.session_id
        if sid is None:
            raise Unauthenticated("Please sign in again.", code="session_required")
        alive = db.execute(text("select app.session_is_active(:s, :u)"),
                           {"s": sid, "u": self.principal.user_id}).scalar()
        if alive is not True:
            raise Unauthenticated("Your session has ended. Please sign in again.", code="session_revoked")
        self._session_checked = True


def load_org_context(p: Principal, org_id: UUID, request_id: str | None) -> OrgContext:
    with user_tx(p.user_id, org_id) as db:
        m = db.execute(
            select(Membership).where(Membership.user_id == p.user_id, Membership.org_id == org_id,
                                     Membership.status == "active",
                                     Membership.valid_from <= text("now()"),
                                     (Membership.valid_until.is_(None)) | (Membership.valid_until > text("now()")))
        ).scalar_one_or_none()
        org = db.get(Organisation, org_id) if m is not None else None
        if m is None or org is None or org.activation_state != "active":
            raise Forbidden("You are not an active member of this organisation.", code="not_a_member")
        scopes = db.execute(
            select(ProfessionalApproval.scope).where(
                ProfessionalApproval.user_id == p.user_id, ProfessionalApproval.org_id == org_id,
                ProfessionalApproval.review_state == "approved",
                ProfessionalApproval.valid_from <= text("now()"),
                (ProfessionalApproval.valid_until.is_(None)) | (ProfessionalApproval.valid_until > text("now()")))
        ).scalars().all()
    return OrgContext(principal=p, org_id=org_id, membership_id=m.id, role=m.role,
                      capabilities=frozenset(m.capabilities), professional_scopes=frozenset(scopes),
                      request_id=request_id, timezone=org.timezone, org_name=org.name)


def org_context(request: Request, p: CurrentPrincipal,
                x_pawguard_org: Annotated[UUID | None, Header()] = None) -> OrgContext:
    if x_pawguard_org is None:
        raise Forbidden("Choose an organisation first.", code="organisation_required")
    ctx = load_org_context(p, x_pawguard_org, getattr(request.state, "request_id", None))
    request.state.org_id = str(ctx.org_id)
    return ctx


CurrentOrg = Annotated[OrgContext, Depends(org_context)]


def requires(*caps: Cap) -> Callable[[OrgContext], OrgContext]:
    """Dependency factory: ``ctx: Annotated[OrgContext, Depends(requires(Cap.X))]``."""

    def _dep(ctx: CurrentOrg) -> OrgContext:
        for cap in caps:
            ctx.require(cap)
        return ctx

    return _dep
