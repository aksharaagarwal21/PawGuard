"""Partner CSV imports: immutable raw file → dry-run validation report → approved transactional apply.

Cleaning rules (brief §6): trim whitespace and normalise Unicode (NFC) without altering local-script names; map
controlled vocabularies through the versioned dictionary below (unmapped values are *flagged* and recorded as
'unknown', never guessed from frequency); reject impossible values (bad/future dates, out-of-range coordinates,
malformed lots); never auto-merge — similar existing records are reported as candidate links. Imported vaccination
records are always "submitted for review".
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import AnimalCreate, ObservationIn, VaccinationCreate
from pawguard_api.deps import OrgContext
from pawguard_api.domain import animals as animal_domain
from pawguard_api.domain import vaccinations as vacc_domain
from pawguard_api.domain.common import expect_version, record_audit, require_reason
from pawguard_api.errors import Conflict, NotFound, Unprocessable
from pawguard_api.models import Animal, Area, VaccineLot, VaccineProduct

DICTIONARY_VERSION = "vocab-1"
MAPPING_VERSIONS = {"animals_csv": "animals-v1", "vaccinations_csv": "vaccinations-v1"}
MAX_ROWS = 5000

VOCAB: dict[str, dict[str, str]] = {
    "species": {"dog": "dog", "dogs": "dog", "canine": "dog", "cat": "cat", "feline": "cat", "other": "other"},
    "sex": {"f": "female", "female": "female", "bitch": "female", "m": "male", "male": "male"},
    "sterilisation_status": {"yes": "sterilised", "y": "sterilised", "sterilised": "sterilised",
                             "sterilized": "sterilised", "neutered": "sterilised", "spayed": "sterilised",
                             "no": "not_sterilised", "n": "not_sterilised", "intact": "not_sterilised",
                             "not sterilised": "not_sterilised", "not sterilized": "not_sterilised"},
    "age_band": {"puppy": "puppy", "pup": "puppy", "young": "young", "juvenile": "young", "adult": "adult",
                 "senior": "senior", "old": "senior"},
    "ownership_category": {"owned": "owned", "pet": "owned", "community": "community", "street": "community",
                           "stray": "community", "unowned": "unowned", "shelter": "shelter"},
    "date_precision": {"day": "day", "exact": "day", "month": "month", "year": "year", "unknown": "unknown"},
}
UNKNOWN_TOKENS = {"", "?", "na", "n/a", "unknown", "not known", "-", "none", "nil"}
REQUIRED = {"animals_csv": ["source_row_id"], "vaccinations_csv": ["source_row_id", "animal_reference"]}
LOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./ -]{0,39}$")


def _clean(v: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", v or "")).strip()


def _vocab(field: str, raw: str, issues: list[dict]) -> str:
    v = raw.lower()
    if v in UNKNOWN_TOKENS:
        return "unknown"
    mapped = VOCAB[field].get(v)
    if mapped is None:
        issues.append({"field": field, "code": "unmapped_value", "severity": "warning",
                       "message": f"'{raw}' is not in vocabulary {DICTIONARY_VERSION}; recorded as unknown."})
        return "unknown"
    return mapped


def _date(raw: str, fmt: str, field: str, issues: list[dict]) -> date | None:
    if raw.lower() in UNKNOWN_TOKENS:
        return None
    try:
        d = datetime.strptime(raw, fmt).date()
    except ValueError:
        issues.append({"field": field, "code": "invalid_date", "severity": "error",
                       "message": f"Not a date in the declared format {fmt}."})
        return None
    if d > date.today() + timedelta(days=1):
        issues.append({"field": field, "code": "date_in_future", "severity": "error",
                       "message": "Date is in the future."})
        return None
    if d.year < 1990:
        issues.append({"field": field, "code": "implausible_date", "severity": "warning",
                       "message": "Date before 1990 — please check."})
    return d


def _float(raw: str, lo: float, hi: float, field: str, issues: list[dict]) -> float | None:
    if raw.lower() in UNKNOWN_TOKENS:
        return None
    try:
        v = float(raw)
    except ValueError:
        issues.append({"field": field, "code": "not_a_number", "severity": "error", "message": "Not a number."})
        return None
    if not lo <= v <= hi:
        issues.append({"field": field, "code": "out_of_range", "severity": "error",
                       "message": f"Must be between {lo} and {hi}."})
        return None
    return v


def parse(content: bytes) -> list[dict[str, str]]:
    try:
        text_ = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Unprocessable("The file must be UTF-8 encoded CSV.", code="invalid_encoding") from exc
    reader = csv.DictReader(io.StringIO(text_))
    if not reader.fieldnames:
        raise Unprocessable("The file has no header row.", code="no_header")
    rows = [{(k or "").strip().lower(): _clean(v) for k, v in r.items()} for r in reader]
    if len(rows) > MAX_ROWS:
        raise Unprocessable(f"At most {MAX_ROWS} rows per import.", code="too_many_rows")
    return rows


def dry_run(db: Session, ctx: OrgContext, import_type: str, rows: list[dict[str, str]], date_format: str,
            job_id: UUID | None) -> dict[str, Any]:
    areas = {a.code.lower(): a for a in db.execute(select(Area)).scalars()}
    products = {p.name.lower(): p for p in db.execute(select(VaccineProduct)).scalars()}
    seen_ids: set[str] = set()
    out_rows = []
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        issues: list[dict] = []
        for col in REQUIRED[import_type]:
            if not row.get(col):
                issues.append({"field": col, "code": "required", "severity": "error", "message": "Required."})
        sid = row.get("source_row_id", "")
        if sid in seen_ids:
            issues.append({"field": "source_row_id", "code": "duplicate_in_file", "severity": "error",
                           "message": "Same source_row_id appears earlier in this file."})
        seen_ids.add(sid)
        prior = db.execute(text("select 1 from app.animals where source_reference like :p union all "
                                "select 1 from app.animal_vaccination_events where source_reference like :p limit 1"),
                           {"p": f"import:%:{import_type}:{sid}"}).first() if sid else None
        if prior:
            issues.append({"field": "source_row_id", "code": "already_imported", "severity": "skip",
                           "message": "This source row was imported before; it will be skipped."})
        clean: dict[str, Any] = {"source_row_id": sid}
        if import_type == "animals_csv":
            for f in ("species", "sex", "sterilisation_status", "age_band", "ownership_category"):
                clean[f] = _vocab(f, row.get(f, ""), issues) if f in row else ("dog" if f == "species" else "unknown")
            for f in ("nickname", "coat_description", "identifying_marks"):
                clean[f] = row.get(f) or None
            code = (row.get("area_code") or "").lower()
            if code and code not in areas:
                issues.append({"field": "area_code", "code": "unknown_area", "severity": "warning",
                               "message": "Unknown area code; area left empty."})
            clean["area_id"] = str(areas[code].id) if code in areas else None
            clean["last_seen_on"] = _date(row.get("last_seen_date", ""), date_format, "last_seen_date", issues)
            lat = _float(row.get("latitude", ""), -90, 90, "latitude", issues)
            lon = _float(row.get("longitude", ""), -180, 180, "longitude", issues)
            if (lat is None) != (lon is None):
                issues.append({"field": "latitude", "code": "incomplete_coordinates", "severity": "warning",
                               "message": "Only one coordinate given; location ignored."})
                lat = lon = None
            clean["lat"], clean["lon"] = lat, lon
            if clean["nickname"] and clean["area_id"]:
                cand = db.execute(text("select reference_code from app.animals where lower(nickname) = lower(:n) "
                                       "and home_area_id = :a and profile_state not in ('merged_alias','archived') "
                                       "limit 3"), {"n": clean["nickname"], "a": clean["area_id"]}).scalars().all()
                if cand:
                    issues.append({"field": "nickname", "code": "possible_existing_record", "severity": "warning",
                                   "message": "Similar existing record(s): " + ", ".join(cand)
                                   + ". A new provisional record will be created; review for a merge."})
        else:
            ref = (row.get("animal_reference") or "").upper()
            animal = (db.execute(select(Animal).where(Animal.reference_code == ref)).scalar_one_or_none()
                      if ref else None)
            if ref and animal is None:
                issues.append({"field": "animal_reference", "code": "unknown_animal", "severity": "error",
                               "message": "No animal with this reference in your organisation."})
            elif animal is not None and animal.profile_state in ("merged_alias", "archived"):
                issues.append({"field": "animal_reference", "code": "animal_not_usable", "severity": "error",
                               "message": f"Record is {animal.profile_state}."})
            clean["animal_id"] = str(animal.id) if animal else None
            prec = _vocab("date_precision", row.get("date_precision", "day") or "day", issues)
            d = _date(row.get("administered_on", ""), date_format, "administered_on", issues)
            if d is None and prec != "unknown" and not any(i["field"] == "administered_on" for i in issues):
                prec = "unknown"
            if prec == "month" and d:
                d = d.replace(day=1)
            if prec == "year" and d:
                d = d.replace(month=1, day=1)
            clean["date_precision"], clean["administered_on"] = (prec, d) if d else ("unknown", None)
            pname = row.get("product_name", "")
            product = products.get(pname.lower()) if pname else None
            if pname and product is None:
                issues.append({"field": "product_name", "code": "product_not_listed", "severity": "warning",
                               "message": "Product not in the organisation's list; kept as written."})
            clean["product_id"] = str(product.id) if product else None
            clean["product_text"] = pname if pname and not product else None
            lot = row.get("lot_number", "")
            if lot and lot.lower() not in UNKNOWN_TOKENS and not LOT_RE.match(lot):
                issues.append({"field": "lot_number", "code": "malformed_lot", "severity": "error",
                               "message": "Lot numbers may contain letters, digits, spaces, '-', '/' and '.'."})
            lot_row = None
            if product and lot:
                lot_row = db.execute(select(VaccineLot).where(VaccineLot.product_id == product.id,
                                                              VaccineLot.lot_number == lot)).scalar_one_or_none()
            clean["lot_id"] = str(lot_row.id) if lot_row else None
            clean["lot_text"] = lot if lot and not lot_row and lot.lower() not in UNKNOWN_TOKENS else None
            clean["administered_by_name"] = row.get("administered_by_name") or None
            clean["administered_by_registration"] = row.get("registration") or None
        errors = [i for i in issues if i["severity"] == "error"]
        status = ("skip" if any(i["severity"] == "skip" for i in issues) else
                  "rejected" if errors else "warning" if issues else "valid")
        out_rows.append({"row": n, "source_row_id": sid, "status": status, "issues": issues, "clean": clean})
    summary = {s: sum(1 for r in out_rows if r["status"] == s) for s in ("valid", "warning", "rejected", "skip")}
    return {"mapping_version": MAPPING_VERSIONS[import_type], "dictionary_version": DICTIONARY_VERSION,
            "date_format": date_format, "summary": summary, "rows": out_rows}


def create_job(db: Session, ctx: OrgContext, import_type: str, source_label: str, filename: str | None,
               content: bytes, date_format: str) -> UUID:
    ctx.require(Cap.DATA_IMPORT)
    sha = hashlib.sha256(content).hexdigest()
    existing = db.execute(text("select id from app.import_jobs where raw_sha256 = :s and import_type = :t"),
                          {"s": sha, "t": import_type}).scalar()
    if existing:
        raise Conflict("This exact file was already uploaded.", code="duplicate_file",
                       details={"import_id": str(existing)})
    report = dry_run(db, ctx, import_type, parse(content), date_format, None)
    s = report["summary"]
    job_id = db.execute(text("""
        insert into app.import_jobs (org_id, import_type, source_label, raw_filename, raw_sha256, raw_bytes,
          mapping_version, row_count, valid_count, rejected_count, warning_count, report, created_by)
        values (:o, :t, :l, :f, :sha, :raw, :mv, :rc, :vc, :rj, :wc, cast(:rep as jsonb), :u) returning id"""),
        {"o": ctx.org_id, "t": import_type, "l": source_label, "f": filename, "sha": sha, "raw": content,
         "mv": report["mapping_version"], "rc": sum(s.values()), "vc": s["valid"], "rj": s["rejected"],
         "wc": s["warning"], "rep": json.dumps(report, default=str), "u": ctx.user_id}).scalar_one()
    record_audit(db, ctx, "import.validated", "import_job", job_id, {"type": import_type, **s})
    return job_id


def apply(db: Session, ctx: OrgContext, job_id: UUID, row_version: int, include_warnings: bool) -> dict[str, int]:
    """Create records for valid (and optionally warning) rows in one transaction. Rejected/skipped rows are left."""
    ctx.require(Cap.DATA_IMPORT)
    job = db.execute(text("select * from app.import_jobs where id = :id for update"), {"id": job_id}).one_or_none()
    if job is None:
        raise NotFound("Import not found.", code="import_not_found")
    expect_version(job.row_version, row_version, "import")
    if job.state != "validated":
        raise Conflict("This import was already applied or discarded.", code="invalid_state")
    if job.import_type == "vaccinations_csv":
        ctx.require(Cap.VACCINATION_SUBMIT)
    else:
        ctx.require(Cap.ANIMAL_WRITE)
    created: dict[str, list[str]] = {"animals": [], "observations": [], "vaccination_events": []}
    statuses = {"valid", "warning"} if include_warnings else {"valid"}
    for r in job.report["rows"]:
        if r["status"] not in statuses:
            continue
        c = r["clean"]
        src = f"import:{job_id}:{job.import_type}:{c['source_row_id']}"
        if job.import_type == "animals_csv":
            obs = None
            if c.get("last_seen_on") or c.get("lat") is not None:
                obs = ObservationIn(observed_on=c.get("last_seen_on"),
                                    time_precision="day" if c.get("last_seen_on") else "unknown",
                                    location={"lat": c["lat"], "lon": c["lon"], "method": "unknown"}
                                    if c.get("lat") is not None else None, area_id=c.get("area_id"))
            aid = animal_domain.create_animal(db, ctx, AnimalCreate(
                species=c["species"], sex=c["sex"], sterilisation_status=c["sterilisation_status"],
                age_band=c["age_band"], ownership_category=c["ownership_category"], nickname=c["nickname"],
                coat_description=c["coat_description"], identifying_marks=c["identifying_marks"],
                home_area_id=c.get("area_id"), first_observation=obs), source_type="import", source_reference=src)
            created["animals"].append(str(aid))
        else:
            eid = vacc_domain.submit(db, ctx, VaccinationCreate(
                animal_id=c["animal_id"], date_precision=c["date_precision"], administered_on=c["administered_on"],
                product_id=c.get("product_id"), product_text=c.get("product_text"), lot_id=c.get("lot_id"),
                lot_text=c.get("lot_text"), administered_by_name=c.get("administered_by_name"),
                administered_by_registration=c.get("administered_by_registration"), source_type="partner_record",
                source_reference=src[:200]))
            created["vaccination_events"].append(str(eid))
    db.execute(text("""update app.import_jobs set state = 'applied', applied_by = :u, applied_at = now(),
                       created_record_ids = cast(:c as jsonb) where id = :id"""),
               {"u": ctx.user_id, "c": json.dumps(created), "id": job_id})
    counts = {k: len(v) for k, v in created.items()}
    record_audit(db, ctx, "import.applied", "import_job", job_id, counts)
    return counts


def rollback(db: Session, ctx: OrgContext, job_id: UUID, reason: str) -> int:
    """Animal imports only: archive the created records if none has been touched since the import. Records are
    archived, not deleted, so provenance survives. Vaccination imports are corrected through review instead."""
    ctx.require(Cap.DATA_IMPORT)
    ctx.require(Cap.ANIMAL_MERGE)
    reason = require_reason(reason)
    job = db.execute(text("select * from app.import_jobs where id = :id for update"), {"id": job_id}).one_or_none()
    if job is None:
        raise NotFound("Import not found.", code="import_not_found")
    if job.state != "applied" or job.import_type != "animals_csv":
        raise Conflict("Only applied animal imports can be rolled back.", code="invalid_state")
    ids = job.created_record_ids.get("animals", [])
    touched = db.execute(text("""select count(*) from app.animals a where a.id = any(cast(:ids as uuid[])) and (
        a.row_version > 1 or exists (select 1 from app.animal_vaccination_events e where e.animal_id = a.id)
        or (select count(*) from app.animal_observations o where o.animal_id = a.id) > 1
        or exists (select 1 from app.field_tasks t where t.animal_id = a.id))"""), {"ids": ids}).scalar_one()
    if touched:
        raise Conflict(f"{touched} imported record(s) have been used since the import; roll back is not safe. "
                       "Archive or merge them individually.", code="records_in_use")
    db.execute(text("update app.animals set profile_state = 'archived', archived_reason = :r "
                    "where id = any(cast(:ids as uuid[]))"), {"r": f"Import rolled back: {reason}"[:500], "ids": ids})
    db.execute(text("""update app.import_jobs set state = 'rolled_back', rolled_back_by = :u, rolled_back_at = now(),
                       rollback_reason = :r where id = :id"""), {"u": ctx.user_id, "r": reason, "id": job_id})
    record_audit(db, ctx, "import.rolled_back", "import_job", job_id, {"archived": len(ids)}, reason=reason)
    return len(ids)

