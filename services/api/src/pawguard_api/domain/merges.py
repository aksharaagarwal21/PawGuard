"""Duplicate animal profiles: propose → (different person) approve/execute → optional reverse.

Execution moves the source profile's relationships to the target and turns the source into a
``merged_alias``. Every moved row id is stored in a manifest so reversal restores exactly what moved.
Provenance is never deleted: vaccination events keep ``original_animal_id``; observations keep
``reported_animal_reference``; the audit trail records each step.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import MergeOut, MergePreview, MergePropose
from pawguard_api.deps import OrgContext
from pawguard_api.domain.animals import get_animal, load_animal
from pawguard_api.domain.common import emit, record_audit
from pawguard_api.errors import Conflict, Forbidden, NotFound
from pawguard_api.models import AnimalMerge

MOVABLE = {
    "observations": "app.animal_observations",
    "vaccination_events": "app.animal_vaccination_events",
    "tasks": "app.field_tasks",
    "caregivers": "app.animal_caregivers",
}


def _counts(db: Session, animal_id: UUID) -> dict[str, int]:
    return {name: db.execute(text(f"select count(*) from {table} where animal_id = :a"),  # noqa: S608
                             {"a": animal_id}).scalar_one() for name, table in MOVABLE.items()}


def _conflicts(db: Session, source_id: UUID, target_id: UUID) -> list[str]:
    s = load_animal(db, source_id)
    t = load_animal(db, target_id)
    out = []
    for field in ("species", "sex", "sterilisation_status"):
        a, b = getattr(s, field), getattr(t, field)
        if "unknown" not in (a, b) and a != b:
            out.append(f"{field}_differs")
    if s.home_area_id and t.home_area_id and s.home_area_id != t.home_area_id:
        out.append("home_area_differs")
    return out


def preview(db: Session, ctx: OrgContext, source_id: UUID, target_id: UUID) -> MergePreview:
    ctx.require(Cap.ANIMAL_READ)
    if source_id == target_id:
        raise Conflict("Choose two different records.", code="same_animal")
    for a in (source_id, target_id):
        load_animal(db, a, usable=True)
    return MergePreview(source=get_animal(db, ctx, source_id), target=get_animal(db, ctx, target_id),
                        moves=_counts(db, source_id), conflicts=_conflicts(db, source_id, target_id))


def propose(db: Session, ctx: OrgContext, data: MergePropose) -> UUID:
    if not (ctx.can(Cap.ANIMAL_WRITE) or ctx.can(Cap.ANIMAL_MERGE)):
        ctx.require(Cap.ANIMAL_WRITE)
    if data.source_animal_id == data.target_animal_id:
        raise Conflict("Choose two different records.", code="same_animal")
    for a in (data.source_animal_id, data.target_animal_id):
        load_animal(db, a, usable=True)
    open_existing = db.execute(text("""select id from app.animal_merge_operations where state = 'proposed'
        and source_animal_id = :s and target_animal_id = :t"""),
        {"s": data.source_animal_id, "t": data.target_animal_id}).scalar()
    if open_existing:
        return open_existing
    merge = AnimalMerge(org_id=ctx.org_id, created_by=ctx.user_id, source_animal_id=data.source_animal_id,
                        target_animal_id=data.target_animal_id, reason=data.reason, proposed_by=ctx.user_id)
    db.add(merge)
    db.flush()
    record_audit(db, ctx, "animal_merge.proposed", "animal_merge", merge.id,
                 {"source": str(data.source_animal_id), "target": str(data.target_animal_id)}, reason=data.reason)
    emit(db, ctx, "animal_merge.proposed", "animal_merge", merge.id)
    return merge.id


def _lock(db: Session, merge_id: UUID) -> AnimalMerge:
    m = db.execute(select(AnimalMerge).where(AnimalMerge.id == merge_id).with_for_update()).scalar()
    if m is None:
        raise NotFound("Merge not found.", code="merge_not_found")
    return m


def execute(db: Session, ctx: OrgContext, merge_id: UUID, reason: str) -> None:
    ctx.require(Cap.ANIMAL_MERGE)
    ctx.require_live_session(db)
    m = _lock(db, merge_id)
    if m.state != "proposed":
        raise Conflict("This merge is not awaiting a decision.", code="invalid_state", details={"state": m.state})
    if m.proposed_by == ctx.user_id:
        raise Forbidden("A different person must approve a merge they did not propose.", code="second_person_required")
    source = load_animal(db, m.source_animal_id, for_update=True, usable=True)
    load_animal(db, m.target_animal_id, for_update=True, usable=True)
    manifest: dict[str, Any] = {"previous_source_state": source.profile_state}
    for name, table in MOVABLE.items():
        ids = db.execute(text(f"update {table} set animal_id = :t where animal_id = :s returning id"),  # noqa: S608
                         {"t": m.target_animal_id, "s": m.source_animal_id}).scalars().all()
        manifest[name] = [str(i) for i in ids]
    source.profile_state = "merged_alias"
    source.merged_into_id = m.target_animal_id
    db.execute(text("""update app.animals t set last_observed_at = greatest(t.last_observed_at, s.last_observed_at)
                       from app.animals s where t.id = :t and s.id = :s"""),
               {"t": m.target_animal_id, "s": m.source_animal_id})
    m.state = "executed"
    m.decided_by = ctx.user_id
    m.executed_at = text("now()")
    m.manifest = manifest
    record_audit(db, ctx, "animal_merge.executed", "animal_merge", m.id,
                 {k: len(v) for k, v in manifest.items() if isinstance(v, list)}, reason=reason)
    emit(db, ctx, "animal_merge.executed", "animal_merge", m.id)


def reject(db: Session, ctx: OrgContext, merge_id: UUID, reason: str) -> None:
    ctx.require(Cap.ANIMAL_MERGE)
    m = _lock(db, merge_id)
    if m.state != "proposed":
        raise Conflict("This merge is not awaiting a decision.", code="invalid_state")
    m.state = "rejected"
    m.decided_by = ctx.user_id
    record_audit(db, ctx, "animal_merge.rejected", "animal_merge", m.id, reason=reason)


def reverse(db: Session, ctx: OrgContext, merge_id: UUID, reason: str) -> None:
    ctx.require(Cap.ANIMAL_MERGE)
    ctx.require_live_session(db)
    m = _lock(db, merge_id)
    if m.state != "executed":
        raise Conflict("Only an executed merge can be reversed.", code="invalid_state")
    source = load_animal(db, m.source_animal_id, for_update=True)
    if source.profile_state != "merged_alias" or source.merged_into_id != m.target_animal_id:
        raise Conflict("The records changed after this merge; reverse later merges first.", code="merge_chain")
    for name, table in MOVABLE.items():
        ids = m.manifest.get(name) or []
        if ids:
            db.execute(text(f"update {table} set animal_id = :s where id = any(cast(:ids as uuid[])) "  # noqa: S608
                            "and animal_id = :t"), {"s": m.source_animal_id, "t": m.target_animal_id, "ids": ids})
    source.merged_into_id = None
    source.profile_state = m.manifest.get("previous_source_state") or "provisional"
    m.state = "reversed"
    m.reversed_by = ctx.user_id
    m.reversed_at = text("now()")
    m.reversal_reason = reason
    record_audit(db, ctx, "animal_merge.reversed", "animal_merge", m.id, reason=reason)
    emit(db, ctx, "animal_merge.reversed", "animal_merge", m.id)


def merge_out(db: Session, merge_id: UUID) -> MergeOut:
    r = db.execute(text("""select m.*, s.reference_code as source_reference, t.reference_code as target_reference
                           from app.animal_merge_operations m join app.animals s on s.id = m.source_animal_id
                           join app.animals t on t.id = m.target_animal_id where m.id = :id"""),
                   {"id": merge_id}).one_or_none()
    if r is None:
        raise NotFound("Merge not found.", code="merge_not_found")
    moved = {k: len(v) for k, v in (r.manifest or {}).items() if isinstance(v, list)}
    return MergeOut(id=r.id, source_animal_id=r.source_animal_id, source_reference=r.source_reference,
                    target_animal_id=r.target_animal_id, target_reference=r.target_reference, state=r.state,
                    reason=r.reason, proposed_by=r.proposed_by, decided_by=r.decided_by, executed_at=r.executed_at,
                    moved=moved, reversed_at=r.reversed_at, reversal_reason=r.reversal_reason,
                    created_at=r.created_at, row_version=r.row_version)
