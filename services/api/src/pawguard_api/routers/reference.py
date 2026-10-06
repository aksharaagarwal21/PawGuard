"""Reference data and organisation administration: areas, vaccine products/lots, members, professional
approvals and the audit log."""

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select, text

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import Out, StrictModel
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain.common import expect_version, record_audit, require_reason
from pawguard_api.errors import Conflict, Forbidden, NotFound
from pawguard_api.models import Membership, ProfessionalApproval, VaccineLot, VaccineProduct

router = APIRouter(prefix="/api/v1", tags=["reference"])


class AreaOut(Out):
    id: UUID
    code: str
    name: str
    kind: str
    parent_area_id: UUID | None
    has_boundary: bool
    boundary_source: str | None


@router.get("/areas", response_model=list[AreaOut], summary="Working areas")
def list_areas(ctx: CurrentOrg) -> list[AreaOut]:
    """Permission: any member. Areas currently in effect for the organisation."""
    with ctx.tx() as db:
        rows = db.execute(text("""select id, code, name, kind, parent_area_id, boundary is not null as has_boundary,
                                  boundary_source from app.areas
                                  where effective_to is null or effective_to > current_date order by name""")).all()
    return [AreaOut(**r._mapping) for r in rows]


class ProductOut(Out):
    id: UUID
    name: str
    manufacturer: str | None
    species: list[str]
    unit: str
    review_state: str
    active: bool


class LotOut(Out):
    id: UUID
    product_id: UUID
    lot_number: str
    expiry_date: date | None


class ProductCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=200)
    species: list[str] = Field(default_factory=lambda: ["dog"], max_length=5)
    unit: str = Field(default="dose", pattern="^(dose|vial|ml)$")


class LotCreate(StrictModel):
    product_id: UUID
    lot_number: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9./ -]{0,39}$")
    expiry_date: date | None = None
    supplier: str | None = Field(default=None, max_length=200)


@router.get("/vaccine-products", response_model=list[ProductOut], summary="Animal vaccine products")
def list_products(ctx: CurrentOrg) -> list[ProductOut]:
    """Permission: any member. ``review_state`` shows whether a qualified person has reviewed the entry."""
    with ctx.tx() as db:
        rows = db.execute(select(VaccineProduct).where(VaccineProduct.active).order_by(VaccineProduct.name)).scalars()
        return [ProductOut(id=p.id, name=p.name, manufacturer=p.manufacturer, species=p.species, unit=p.unit,
                           review_state=p.review_state, active=p.active) for p in rows]


@router.post("/vaccine-products", status_code=201, response_model=ProductOut, summary="Add a product")
def create_product(body: ProductCreate, ctx: CurrentOrg) -> ProductOut:
    """Permission: ``campaign.manage``. New products are ``unreviewed``."""
    ctx.require(Cap.CAMPAIGN_MANAGE)
    with ctx.tx() as db:
        p = VaccineProduct(org_id=ctx.org_id, created_by=ctx.user_id, **body.model_dump())
        db.add(p)
        db.flush()
        record_audit(db, ctx, "vaccine_product.created", "vaccine_product", p.id)
        return ProductOut(id=p.id, name=p.name, manufacturer=p.manufacturer, species=p.species, unit=p.unit,
                          review_state="unreviewed", active=True)


@router.get("/vaccine-lots", response_model=list[LotOut], summary="Known lots")
def list_lots(ctx: CurrentOrg, product_id: UUID | None = None) -> list[LotOut]:
    """Permission: any member."""
    with ctx.tx() as db:
        stmt = select(VaccineLot).order_by(VaccineLot.lot_number)
        if product_id:
            stmt = stmt.where(VaccineLot.product_id == product_id)
        return [LotOut(id=lot.id, product_id=lot.product_id, lot_number=lot.lot_number, expiry_date=lot.expiry_date)
                for lot in db.execute(stmt).scalars()]


@router.post("/vaccine-lots", status_code=201, response_model=LotOut, summary="Record a lot")
def create_lot(body: LotCreate, ctx: CurrentOrg) -> LotOut:
    """Permission: ``campaign.manage``."""
    ctx.require(Cap.CAMPAIGN_MANAGE)
    with ctx.tx() as db:
        lot = VaccineLot(org_id=ctx.org_id, created_by=ctx.user_id, **body.model_dump())
        db.add(lot)
        db.flush()
        record_audit(db, ctx, "vaccine_lot.created", "vaccine_lot", lot.id)
        return LotOut(id=lot.id, product_id=lot.product_id, lot_number=lot.lot_number, expiry_date=lot.expiry_date)


class MemberOut(Out):
    membership_id: UUID
    user_id: UUID
    name: str | None
    role: str
    status: str
    capabilities: list[str]
    professional_scopes: list[str]
    can_work_tasks: bool


@router.get("/members", response_model=list[MemberOut], summary="Organisation members")
def list_members(ctx: CurrentOrg) -> list[MemberOut]:
    """Permission: ``task.manage`` or ``member.manage`` (names and roles only — no contact details)."""
    if not (ctx.can(Cap.TASK_MANAGE) or ctx.can(Cap.MEMBER_MANAGE)):
        ctx.require(Cap.MEMBER_MANAGE)
    with ctx.tx() as db:
        rows = db.execute(text("""
            select m.id, m.user_id, up.preferred_name, m.role, m.status, m.capabilities,
                   coalesce((select array_agg(pa.scope) from app.professional_approvals pa
                             where pa.membership_id = m.id and pa.review_state = 'approved'
                               and (pa.valid_until is null or pa.valid_until > now())), '{}') as scopes
            from app.memberships m left join app.user_profiles up on up.user_id = m.user_id
            where m.status in ('active','suspended') order by up.preferred_name nulls last""")).all()
    return [MemberOut(membership_id=r.id, user_id=r.user_id, name=r.preferred_name, role=r.role, status=r.status,
                      capabilities=sorted(r.capabilities), professional_scopes=sorted(r.scopes),
                      can_work_tasks="task.work" in r.capabilities) for r in rows]


class MembershipRevoke(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)
    row_version: int


@router.post("/members/{membership_id}/revoke", status_code=204, summary="Revoke a membership")
def revoke_member(membership_id: UUID, body: MembershipRevoke, ctx: CurrentOrg) -> None:
    """Permission: ``member.manage`` + live session. Takes effect on the member's next request (membership is read
    on every request); queued offline work is re-checked when it syncs."""
    ctx.require(Cap.MEMBER_MANAGE)
    with ctx.tx() as db:
        ctx.require_live_session(db)
        m = db.execute(select(Membership).where(Membership.id == membership_id).with_for_update()).scalar()
        if m is None:
            raise NotFound("Member not found.", code="member_not_found")
        if m.user_id == ctx.user_id:
            raise Forbidden("You cannot revoke your own membership.", code="cannot_revoke_self")
        expect_version(m.row_version, body.row_version, "membership")
        if m.status == "revoked":
            raise Conflict("Already revoked.", code="invalid_state")
        m.status = "revoked"
        m.revoked_by = ctx.user_id
        m.revoked_at = text("now()")
        m.revocation_reason = body.reason
        db.execute(text("update app.professional_approvals set review_state = 'revoked', decided_at = now(), "
                        "decision_reason = 'membership revoked' "
                        "where membership_id = :m and review_state = 'approved'"),
                   {"m": membership_id})
        record_audit(db, ctx, "membership.revoked", "membership", membership_id, reason=body.reason)


class ApprovalCreate(StrictModel):
    membership_id: UUID
    scope: str = Field(pattern="^(veterinary_review|clinical_care|content_review_clinical|content_review_veterinary)$")
    evidence_reference: str = Field(min_length=1, max_length=500,
                                    description="What was checked (e.g. registration number and register consulted)")
    valid_until: datetime | None = None


class ApprovalOut(Out):
    id: UUID
    membership_id: UUID
    scope: str
    review_state: str
    valid_until: datetime | None


@router.post("/professional-approvals", status_code=201, response_model=ApprovalOut,
             summary="Record a verified professional authority")
def approve_professional(body: ApprovalCreate, ctx: CurrentOrg) -> ApprovalOut:
    """Permission: ``professional.approve`` + live session. The approver cannot approve themselves (enforced in the
    database too). PawGuard does not check external professional registers: the approver records what they
    verified in ``evidence_reference``."""
    ctx.require(Cap.PROFESSIONAL_APPROVE)
    with ctx.tx() as db:
        ctx.require_live_session(db)
        m = db.execute(select(Membership).where(Membership.id == body.membership_id,
                                                Membership.status == "active")).scalar()
        if m is None:
            raise NotFound("Member not found.", code="member_not_found")
        if m.user_id == ctx.user_id:
            raise Forbidden("Professional authority must be approved by someone else.", code="self_approval")
        pa = ProfessionalApproval(org_id=ctx.org_id, membership_id=m.id, user_id=m.user_id, scope=body.scope,
                                  evidence_reference=body.evidence_reference, reviewer_user_id=ctx.user_id,
                                  review_state="approved", decided_at=text("now()"), valid_until=body.valid_until,
                                  created_by=ctx.user_id)
        db.add(pa)
        db.flush()
        record_audit(db, ctx, "professional_approval.granted", "professional_approval", pa.id,
                     {"scope": body.scope, "membership_id": str(m.id)})
        return ApprovalOut(id=pa.id, membership_id=m.id, scope=pa.scope, review_state="approved",
                           valid_until=pa.valid_until)


class ApprovalRevoke(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/professional-approvals/{approval_id}/revoke", status_code=204, summary="Revoke professional authority")
def revoke_professional(approval_id: UUID, body: ApprovalRevoke, ctx: CurrentOrg) -> None:
    """Permission: ``professional.approve`` + live session."""
    ctx.require(Cap.PROFESSIONAL_APPROVE)
    with ctx.tx() as db:
        ctx.require_live_session(db)
        pa = db.get(ProfessionalApproval, approval_id)
        if pa is None:
            raise NotFound("Approval not found.", code="approval_not_found")
        reason = require_reason(body.reason)
        pa.review_state = "revoked"
        pa.decision_reason = reason
        pa.decided_at = text("now()")
        record_audit(db, ctx, "professional_approval.revoked", "professional_approval", pa.id, reason=reason)


class AuditOut(Out):
    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_name: str | None
    actor_kind: str
    action: str
    target_type: str | None
    target_id: UUID | None
    reason: str | None
    change_summary: dict[str, Any]


@router.get("/audit", response_model=list[AuditOut], summary="Audit trail")
def audit_log(ctx: CurrentOrg, target_id: UUID | None = None,
              limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[AuditOut]:
    """Permission: ``audit.read``. Change summaries are redacted (field names and state changes only)."""
    ctx.require(Cap.AUDIT_READ)
    with ctx.tx() as db:
        rows = db.execute(text("""select ae.*, up.preferred_name as actor_name from app.audit_events ae
                                  left join app.user_profiles up on up.user_id = ae.actor_user_id
                                  where (cast(:t as uuid) is null or ae.target_id = :t)
                                  order by ae.occurred_at desc limit :lim"""), {"t": target_id, "lim": limit}).all()
    return [AuditOut(id=r.id, occurred_at=r.occurred_at, actor_user_id=r.actor_user_id, actor_name=r.actor_name,
                     actor_kind=r.actor_kind, action=r.action, target_type=r.target_type, target_id=r.target_id,
                     reason=r.reason, change_summary=r.change_summary) for r in rows]
