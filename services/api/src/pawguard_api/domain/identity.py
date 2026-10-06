"""Assisted identification: availability, search requests, candidate results and human decisions.

Nothing here links a photo to an animal. A search produces *possible matches*; the person then records a decision
(same animal / new animal / not sure) and, separately, creates the sighting or registration as usual. A model is
offered to every organisation only when it is ``active`` (which the database allows only after its release gate
passed). A staged ``research_preview`` model runs only in demo organisations and is always labelled as research.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import (
    BoxIn,
    CandidateAnimalOut,
    IdentityCandidateOut,
    IdentityFeedbackOut,
    IdentitySearchOut,
    IdentityStatusOut,
    PhotoRef,
)
from pawguard_api.deps import OrgContext
from pawguard_api.domain.common import enqueue_job, record_audit
from pawguard_api.errors import Conflict, NotFound, Unprocessable

WANTED = "task = 'identity_embedding' and (state = 'active' or research_preview or index_wanted)"


def _model_for(db: Session, ctx: OrgContext) -> tuple[Any | None, str, str | None]:
    """(model row, mode, reason). Demo organisations may use a research-preview model; nobody else may."""
    active = db.execute(text("select * from app.model_versions where task = 'identity_embedding' "
                             "and state = 'active'")).one_or_none()
    if active is not None:
        return active, "assisted", None
    preview = db.execute(text("select * from app.model_versions where task = 'identity_embedding' "
                              "and research_preview")).one_or_none()
    if preview is None:
        return None, "unavailable", "no_model"
    is_demo = db.execute(text("select is_demo from app.organisations where id = :o"), {"o": ctx.org_id}).scalar()
    return (preview, "research_preview", None) if is_demo else (None, "unavailable", "research_only")


def _gallery_stats(db: Session, model_id: UUID) -> tuple[int, int, int]:
    """(animals with embeddings, embedded photos, eligible photos) for this organisation and model. Counts come
    from a security-definer function: the API role cannot read the embeddings table itself."""
    row = db.execute(text("select * from app.identity_gallery_stats(:mv)"), {"mv": model_id}).one()
    return row.animals, row.photos, row.eligible


def status(db: Session, ctx: OrgContext) -> IdentityStatusOut:
    ctx.require(Cap.IDENTITY_SEARCH)
    model, mode, reason = _model_for(db, ctx)
    if model is None:
        return IdentityStatusOut(mode="unavailable", reason=reason)
    animals, photos, eligible = _gallery_stats(db, model.id)
    return IdentityStatusOut(mode=mode, model_label=f"{model.family} · {model.version_label}",
                             release_gate_passed=bool((model.release_gate or {}).get("passed")),
                             gallery_animals=animals, gallery_photos=photos,
                             index_coverage=round(photos / eligible, 3) if eligible else None)


def create_search(db: Session, ctx: OrgContext, media_id: UUID, box: BoxIn | None) -> UUID:
    ctx.require(Cap.IDENTITY_SEARCH)
    media = db.execute(text("select id, purpose, state, width, height from app.media_assets where id = :m"),
                       {"m": media_id}).one_or_none()
    if media is None:
        raise NotFound("Photo not found.", code="media_not_found")
    if media.purpose != "animal_photo" or media.state != "approved":
        raise Conflict("The photo is not ready yet. Wait until it has been checked.", code="media_not_ready")
    if box is not None and media.width and media.height and (box.x + box.w > media.width + 1
                                                             or box.y + box.h > media.height + 1):
        raise Unprocessable("The selected area lies outside the photo.", code="box_out_of_bounds")
    model, mode, reason = _model_for(db, ctx)
    sid = db.execute(text("""
        insert into app.identity_searches (org_id, media_id, subject_bbox, model_version_id, mode, state,
          failure_code, threshold, requested_by, completed_at)
        values (:o, :m, cast(:b as jsonb), :mv, :mode, :st, :fc, :tau, :u, case when :st = 'pending' then null
          else now() end)
        returning id"""),
        {"o": ctx.org_id, "m": media_id, "b": box.model_dump_json() if box else None,
         "mv": model.id if model else None, "mode": mode, "st": "pending" if model else "unavailable",
         "fc": reason, "tau": (model.thresholds or {}).get("similarity_tau") if model else None,
         "u": ctx.user_id}).scalar_one()
    if model is not None:
        enqueue_job(db, ctx, "identity.search", "identity_search", sid, max_attempts=2)
    record_audit(db, ctx, "identity.search_requested", "identity_search", sid, {"mode": mode})
    return sid


def _candidate_photos(db: Session, rows: list[dict]) -> dict[str, str]:
    ids = [p for c in rows for p in c.get("media_ids", [])[:2]]
    if not ids:
        return {}
    ders = db.execute(text("select id, derivatives from app.media_assets where id = any(cast(:ids as uuid[]))"),
                      {"ids": ids}).all()
    keys = {str(r.id): (r.derivatives or {}).get("display") for r in ders}
    from pawguard_api.integrations.storage import get_storage

    try:
        urls = get_storage().signed_download_urls([k for k in keys.values() if k])
    except Exception:
        urls = {}
    return {mid: urls.get(k) for mid, k in keys.items() if k}


def get_search(db: Session, ctx: OrgContext, search_id: UUID) -> IdentitySearchOut:
    ctx.require(Cap.IDENTITY_SEARCH)
    s = db.execute(text("""select s.*, mv.family, mv.version_label from app.identity_searches s
                           left join app.model_versions mv on mv.id = s.model_version_id where s.id = :id"""),
                   {"id": search_id}).one_or_none()
    if s is None:
        raise NotFound("Search not found.", code="search_not_found")
    cands: list[IdentityCandidateOut] = []
    raw = list(s.candidates or [])
    if raw:
        animals = {str(a.id): a for a in db.execute(text("""
            select a.id, a.reference_code, a.nickname, a.coat_description, a.identifying_marks, a.profile_state,
                   a.last_observed_at, ar.name as area_name
            from app.animals a left join app.areas ar on ar.id = a.home_area_id
            where a.id = any(cast(:ids as uuid[]))"""), {"ids": [c["animal_id"] for c in raw]})}
        urls = _candidate_photos(db, raw)
        for c in raw:
            a = animals.get(c["animal_id"])
            if a is None:  # not visible (e.g. archived since) — never leak that it existed
                continue
            cands.append(IdentityCandidateOut(
                rank=c["rank"],
                animal=CandidateAnimalOut(id=a.id, reference_code=a.reference_code, nickname=a.nickname,
                                          coat_description=a.coat_description,
                                          identifying_marks=a.identifying_marks, profile_state=a.profile_state,
                                          home_area_name=a.area_name, last_observed_at=a.last_observed_at),
                photos=[PhotoRef(media_id=m, url=urls.get(m)) for m in c.get("media_ids", [])[:2]]))
    dec = db.execute(text("select decision, animal_id from app.identity_decisions where search_id = :s "
                          "order by created_at desc limit 1"), {"s": search_id}).one_or_none()
    return IdentitySearchOut(
        id=s.id, mode=s.mode, state=s.state, failure_code=s.failure_code, candidates=cands,
        gallery_animals=s.gallery_animals,
        index_coverage=float(s.index_coverage) if s.index_coverage is not None else None,
        model_label=f"{s.family} · {s.version_label}" if s.family else None,
        decision=dec.decision if dec else None, decided_animal_id=dec.animal_id if dec else None,
        created_at=s.created_at)


def decide(db: Session, ctx: OrgContext, search_id: UUID, decision: str, animal_id: UUID | None,
           reason: str | None) -> None:
    """Record the person's decision. Append-only; the latest decision counts. Linking happens elsewhere."""
    ctx.require(Cap.IDENTITY_DECIDE)
    s = db.execute(text("select id, state, candidates from app.identity_searches where id = :id"),
                   {"id": search_id}).one_or_none()
    if s is None:
        raise NotFound("Search not found.", code="search_not_found")
    if s.state == "pending":
        raise Conflict("The search is still running.", code="search_pending")
    if (decision == "same_animal") != (animal_id is not None):
        raise Unprocessable("Choose the animal when you say it is the same animal.", code="animal_required")
    rank = None
    if animal_id is not None:
        visible = db.execute(text("select profile_state from app.animals where id = :a"), {"a": animal_id}).scalar()
        if visible is None or visible in ("merged_alias", "archived"):
            raise Unprocessable("That animal record cannot be chosen.", code="animal_not_usable")
        rank = next((c["rank"] for c in (s.candidates or []) if c["animal_id"] == str(animal_id)), None)
    db.execute(text("""insert into app.identity_decisions (org_id, search_id, decision, animal_id, candidate_rank,
                         was_suggested, reason, decided_by)
                       values (:o, :s, :d, :a, :r, :w, :reason, :u)"""),
               {"o": ctx.org_id, "s": search_id, "d": decision, "a": animal_id, "r": rank, "w": rank is not None,
                "reason": (reason or "").strip() or None, "u": ctx.user_id})
    record_audit(db, ctx, "identity.decided", "identity_search", search_id,
                 {"decision": decision, "candidate_rank": rank, "was_suggested": rank is not None})


def feedback(db: Session, ctx: OrgContext) -> IdentityFeedbackOut:
    ctx.require(Cap.IDENTITY_SEARCH)
    r = db.execute(text("""
        with latest as (select distinct on (search_id) * from app.identity_decisions
                        order by search_id, created_at desc)
        select (select count(*) from app.identity_searches where state <> 'unavailable') as searches,
               count(*) as decisions,
               count(*) filter (where decision = 'same_animal' and candidate_rank = 1) as top1,
               count(*) filter (where decision = 'same_animal' and candidate_rank > 1) as other_suggestion,
               count(*) filter (where decision = 'same_animal' and candidate_rank is null) as unsuggested,
               count(*) filter (where decision = 'new_animal') as new_animal,
               count(*) filter (where decision = 'not_sure') as not_sure
        from latest""")).one()
    return IdentityFeedbackOut(searches=r.searches, decisions=r.decisions, chose_top1=r.top1,
                               chose_other_suggestion=r.other_suggestion, chose_unsuggested_animal=r.unsuggested,
                               new_animal=r.new_animal, not_sure=r.not_sure)


def queue_enrolment(db: Session, ctx: OrgContext, observation_id: UUID) -> int:
    """After a sighting with a chosen subject is linked to an animal, add its photos to the gallery of every
    identity model being maintained. Photos still being validated are enrolled by the worker once approved."""
    if not db.execute(text(f"select exists (select 1 from app.model_versions where {WANTED})")).scalar():  # noqa: S608
        return 0
    rows = db.execute(text("""
        select om.id from app.observation_media om
          join app.animal_observations o on o.id = om.observation_id
          join app.media_assets m on m.id = om.media_id
         where om.observation_id = :o and o.animal_id is not null and jsonb_typeof(om.subject_bbox) = 'object'
           and m.state = 'approved'"""), {"o": observation_id}).scalars().all()
    for om_id in rows:
        enqueue_job(db, ctx, "identity.enrol", "observation_media", om_id, max_attempts=2)
    return len(rows)
