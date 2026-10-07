"""Signed vaccination credentials (ADR 0010/0011): clinic keys, issuing and revoking certificates, and the signed
trust and revocation lists that the offline verifier uses.

A credential is issued in the same transaction as the vet's verification (or the clinic's own record). It proves
that a clinic in the trust list issued the record and that it was not changed — not that the pet is healthy, and not
that the animal someone is looking at is the one on the certificate.
"""

import base64
import io
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import cbor2
import segno
from sqlalchemy import text

from pawguard_api.db import public_tx
from pawguard_api.domain import audit
from pawguard_api.errors import ApiError, Conflict, NotFound
from pawguard_api.integrations import cose
from pawguard_api.settings import get_settings

PAYLOAD_VERSION = 1


@dataclass(frozen=True)
class Actor:
    """Who is acting (a request context or an operator command)."""
    org_id: UUID
    user_id: UUID | None
    request_id: str | None = None


def _audit(db: Any, actor: Actor, action: str, target_type: str, target_id: Any, summary: dict[str, Any],
           reason: str | None = None) -> None:
    audit.record(db, action=action, org_id=actor.org_id, actor_user_id=actor.user_id,
                 actor_kind="user" if actor.user_id else "system", target_type=target_type, target_id=target_id,
                 request_id=actor.request_id, reason=reason, summary=summary)


# ---- clinic keys -------------------------------------------------------------------------------------------------

def ensure_key(db: Any, actor: Actor) -> str:
    """The organisation's active key id, creating the key if it has none (inside the caller's transaction)."""
    row = db.execute(text("select kid from app.signing_key_for_issue(:o)"), {"o": actor.org_id}).first()
    if row:
        return str(row.kid)
    raw, public = cose.new_key()
    kid = secrets.token_hex(8)
    sealed = cose.seal(raw, kid, get_settings())
    del raw
    created = db.execute(text("select app.add_signing_key(:o, :k, :p, :s, :u)"),
                         {"o": actor.org_id, "k": kid, "p": public, "s": sealed, "u": actor.user_id}).scalar()
    if not created:
        raise Conflict("This organisation cannot sign certificates (not active).", code="org_not_active")
    _audit(db, actor, "signing_key.created", "signing_key", None, {"kid": kid})
    return kid


def rotate_key(db: Any, actor: Actor) -> str:
    """Retire the active key (it keeps verifying what it signed) and create a new one. Operator command."""
    old = db.execute(text("""update app.clinic_signing_keys set status = 'retired', retired_at = now()
                             where org_id = :o and status = 'active' returning kid"""), {"o": actor.org_id}).scalar()
    kid = ensure_key(db, actor)
    _audit(db, actor, "signing_key.rotated", "signing_key", None, {"retired": old, "new": kid})
    return kid


def revoke_key(db: Any, actor: Actor, kid: str, reason: str) -> bool:
    """A compromised key: every certificate it signed now shows as issued by an untrusted clinic."""
    done = db.execute(text("""update app.clinic_signing_keys set status = 'revoked', revoked_at = now(),
                              revoke_reason = left(:r, 300)
                              where kid = :k and status <> 'revoked' returning org_id"""),
                      {"k": kid, "r": reason}).scalar()
    if done:
        _audit(db, Actor(done, actor.user_id, actor.request_id), "signing_key.revoked", "signing_key", None,
               {"kid": kid}, reason=reason)
    return bool(done)


# ---- issuing -----------------------------------------------------------------------------------------------------

_EVENT = """
select e.id, e.org_id, e.state, e.administered_on, e.next_review_on, e.next_review_source,
       coalesce(p.name, e.product_text) as product, coalesce(l.lot_number, e.lot_text) as lot,
       a.reference_code, a.nickname, a.species, a.sex, a.coat_description,
       o.name as org_name, coalesce(vp.preferred_name, e.administered_by_name) as vet_name
  from app.animal_vaccination_events e
  join app.animals a on a.id = e.animal_id
  join app.organisations o on o.id = e.org_id
  left join app.vaccine_products p on p.id = e.product_id
  left join app.vaccine_lots l on l.id = e.lot_id
  left join app.user_profiles vp on vp.user_id = e.verified_by
 where e.id = :e"""


def _clip(v: str | None, n: int) -> str | None:
    return v.strip()[:n] if v and v.strip() else None


def build_payload(row: Any, credential_id: UUID, issued_at: int) -> dict[int, Any]:
    """Minimal fields only (ADR 0010): no owner, address, location, photo or notes."""
    pet = {1: row.reference_code, 2: _clip(row.nickname, 40), 3: row.species, 4: row.sex,
           5: _clip(row.coat_description, 40)}
    vac = {1: _clip(row.product, 80), 2: _clip(row.lot, 40), 3: row.administered_on.isoformat(),
           4: row.next_review_on.isoformat() if row.next_review_on else None,
           5: ("vet" if row.next_review_source == "vet" else "template") if row.next_review_on else None}
    return {1: PAYLOAD_VERSION, 2: credential_id.bytes,
            3: {k: v for k, v in pet.items() if v is not None},
            4: {k: v for k, v in vac.items() if v is not None},
            5: {1: UUID(str(row.org_id)).bytes, 2: _clip(row.org_name, 80)},
            6: _clip(row.vet_name, 60) or "Clinic vet", 7: issued_at}


def issue(db: Any, actor: Actor, event_id: UUID, credential_id: UUID | None = None) -> UUID:
    """Sign a verified record (same transaction as the verification). Unverified records are refused."""
    row = db.execute(text(_EVENT), {"e": event_id}).first()
    if row is None or str(row.org_id) != str(actor.org_id):
        raise NotFound("Vaccination record not found.", code="vaccination_event_not_found")
    if row.state != "verified":
        raise Conflict("Only vaccinations verified by a vet get a signed certificate.", code="not_verified",
                       details={"state": row.state})
    if row.administered_on is None:
        raise Conflict("A signed certificate needs the date the vaccine was given.", code="missing_date")
    kid = ensure_key(db, actor)
    key_row = db.execute(text("select kid, sealed from app.signing_key_for_issue(:o)"), {"o": actor.org_id}).one()
    signer = cose.unseal(bytes(key_row.sealed), kid, get_settings())
    credential_id, issued_at = credential_id or uuid.uuid4(), int(time.time())
    qr = cose.to_qr_text(cose.sign1(build_payload(row, credential_id, issued_at), bytes.fromhex(kid), signer))
    del signer
    db.execute(text("select app.store_credential(:i, :e, :k, :q, to_timestamp(:t), :u)"),
               {"i": credential_id, "e": event_id, "k": kid, "q": qr, "t": issued_at, "u": actor.user_id})
    _audit(db, actor, "credential.issued", "vaccination_event", event_id,
           {"credential_id": str(credential_id), "kid": kid})
    return credential_id


def try_issue(db: Any, actor: Actor, event_id: UUID) -> UUID | None:
    """Issue when signing is configured; a missing master key must not block a vet's verification (backfill later)."""
    try:
        with db.begin_nested():
            return issue(db, actor, event_id)
    except cose.SigningUnavailable:
        return None


def revoke_for_event(db: Any, actor: Actor, event_id: UUID, reason: str, replaced_by: UUID | None = None
                     ) -> list[UUID]:
    ids = [r.id for r in db.execute(text("""select id from app.vaccination_credentials
                                            where event_id = :e and state = 'active'"""), {"e": event_id})]
    for cid in ids:
        db.execute(text("select app.revoke_credential(:i, :r, :n)"), {"i": cid, "r": reason, "n": replaced_by})
        _audit(db, actor, "credential.revoked", "vaccination_event", event_id,
               {"credential_id": str(cid), "replaced_by": str(replaced_by) if replaced_by else None}, reason=reason)
    return ids


ACTIVE_FOR_EVENT = text("select id from app.vaccination_credentials where event_id = :e and state = 'active'")


def issue_replacing(db: Any, actor: Actor, event_id: UUID) -> UUID:
    """Issue a fresh certificate for a verified record, revoking the current one (e.g. after a clinic key rotation)."""
    new_id = uuid.uuid4()  # revoke first (one active certificate per record), pointing at the new id
    revoke_for_event(db, actor, event_id, "Re-issued by the clinic", replaced_by=new_id)
    return issue(db, actor, event_id, new_id)


def reissue_after_correction(db: Any, actor: Actor, old_event: UUID, new_event: UUID) -> UUID | None:
    """A correction replaces the old certificate: revoke it (pointing at the new one) and sign the new record."""
    new_id = try_issue(db, actor, new_event)
    revoke_for_event(db, actor, old_event, "Replaced by a corrected record", replaced_by=new_id)
    return new_id


def backfill(db: Any, actor: Actor) -> int:
    """Sign every verified record of this organisation that has no active certificate."""
    rows = db.execute(text("""select e.id from app.animal_vaccination_events e
                              where e.org_id = :o and e.state = 'verified' and e.administered_on is not null
                                and not exists (select 1 from app.vaccination_credentials c
                                                where c.event_id = e.id and c.state = 'active')"""),
                      {"o": actor.org_id}).scalars().all()
    for event_id in rows:
        issue(db, actor, event_id)
    return len(rows)


# ---- signed lists (public) ---------------------------------------------------------------------------------------

_lists: dict[str, tuple[int, float, dict[str, Any]]] = {}
LIST_TTL = 300  # seconds; a new version is signed at once


def _signed_list(name: str, build: Any) -> dict[str, Any]:
    s = get_settings()
    with public_tx() as db:
        version = int(db.execute(text("select app.signing_list_version(:n)"), {"n": name}).scalar() or 0)
        cached = _lists.get(name)
        if cached and cached[0] == version and time.time() - cached[1] < LIST_TTL:
            return cached[2]
        payload = build(db, version)
    signed = cose.sign1(payload, cose.ROOT_KID, cose.root_key(s))
    doc = {"format": "PG-TL1" if name == "trust" else "PG-RL1", "version": version,
           "cose": base64.b64encode(signed).decode("ascii")}
    _lists[name] = (version, time.time(), doc)
    return doc


def trust_list() -> dict[str, Any]:
    def build(db: Any, version: int) -> dict[int, Any]:
        keys = []
        for k in db.execute(text("select * from app.trust_keys()")):
            entry = {1: bytes.fromhex(k.kid), 2: UUID(str(k.org_id)).bytes, 3: k.org_name, 4: bytes(k.public_key),
                     5: int(k.valid_from.timestamp()), 7: k.status, 8: bool(k.is_demo)}
            if k.valid_to is not None:
                entry[6] = int(k.valid_to.timestamp())
            keys.append(entry)
        return {1: version, 2: int(time.time()), 3: keys, 4: get_settings().verify_stale_after_days}
    return _signed_list("trust", build)


def revocation_list() -> dict[str, Any]:
    def build(db: Any, version: int) -> dict[int, Any]:
        ids = [UUID(str(r.id)).bytes for r in db.execute(text("select id from app.revoked_credentials()"))]
        return {1: version, 2: int(time.time()), 3: ids}
    return _signed_list("revocation", build)


def credential_photo(credential_id: UUID) -> str | None:
    with public_tx() as db:
        key = db.execute(text("select app.credential_photo_key(:i)"), {"i": credential_id}).scalar()
    if not key:
        return None
    from pawguard_api.integrations.storage import get_storage

    try:
        return get_storage().signed_download_urls([key]).get(key)
    except Exception:
        return None


# ---- owner and demo views ----------------------------------------------------------------------------------------

def qr_svg(qr_text: str) -> str:
    buf = io.BytesIO()
    # viewBox, no fixed size: the page scales it (a fixed 276 px SVG in a smaller box was cropped, unscannable).
    segno.make(qr_text, error="m").save(buf, kind="svg", scale=4, border=4, xmldecl=False, svgns=True, omitsize=True)
    return buf.getvalue().decode("utf-8")


def qr_png(qr_text: str, scale: int = 6) -> io.BytesIO:
    png = io.BytesIO()
    segno.make(qr_text, error="m").save(png, kind="png", scale=scale, border=2)
    png.seek(0)
    return png


def is_rabies(product: str | None) -> bool:
    return bool(product and "rabies" in product.lower())


def pet_certificates(db: Any, animal_id: UUID) -> dict[str, Any]:
    """Every verified vaccination of the pet with its active certificate; owner-entered records are only counted."""
    rows = db.execute(text("""
        select e.id as event_id, coalesce(p.name, e.product_text) as vaccine, e.administered_on, e.next_review_on,
               e.next_review_source, c.id as credential_id, c.qr_text, c.issued_at
          from app.animal_vaccination_events e
          left join app.vaccine_products p on p.id = e.product_id
          left join app.vaccination_credentials c on c.event_id = e.id and c.state = 'active'
         where e.animal_id = :a and e.state = 'verified'
         order by e.administered_on desc nulls last"""), {"a": animal_id}).all()
    unverified = int(db.execute(text("""select count(*) from app.animal_vaccination_events
                                        where animal_id = :a and state in ('submitted','needs_correction')"""),
                                {"a": animal_id}).scalar() or 0)
    items = [{"event_id": r.event_id, "vaccine": r.vaccine, "administered_on": r.administered_on,
              "next_due_on": r.next_review_on, "next_due_source": r.next_review_source,
              "is_rabies": is_rabies(r.vaccine), "credential_id": r.credential_id, "qr_text": r.qr_text,
              "qr_svg": qr_svg(r.qr_text) if r.qr_text else None, "issued_at": r.issued_at} for r in rows]
    rabies = next((i for i in items if i["is_rabies"] and i["qr_text"]), None)
    return {"featured_event_id": rabies["event_id"] if rabies else None, "items": items,
            "unverified_count": unverified}


def tampered_copy(qr_text: str) -> str:
    """Demo only: change the date given by one day WITHOUT re-signing — the verifier must show it as altered."""
    msg = cose.parse_sign1(cose.from_qr_text(qr_text))
    payload = dict(msg.payload)
    vac = dict(payload[4])
    vac[3] = (date.fromisoformat(vac[3]).replace(day=1) if not vac[3].endswith("-01")
              else date.fromisoformat(vac[3]).replace(day=2)).isoformat()
    payload[4] = vac
    forged = cbor2.dumps(cbor2.CBORTag(cose.COSE_SIGN1_TAG, [msg.protected, {}, cbor2.dumps(payload), msg.signature]))
    return cose.to_qr_text(forged)


def demo_samples() -> dict[str, Any]:
    """Genuine, altered and cancelled sample certificates from the demo organisations (demo mode only)."""
    if not get_settings().demo_mode:
        raise ApiError("Not available.", code="not_found", status_code=404)
    with public_tx() as db:
        row = db.execute(text("select * from app.demo_sample_certificates()")).one()
    genuine, revoked = row.genuine, row.cancelled
    out: dict[str, Any] = {}
    for name, qr in (("genuine", genuine), ("altered", tampered_copy(genuine) if genuine else None),
                     ("cancelled", revoked)):
        out[name] = {"qr_text": qr, "qr_svg": qr_svg(qr) if qr else None}
    return out

