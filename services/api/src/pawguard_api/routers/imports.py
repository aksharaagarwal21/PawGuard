"""Partner data imports (dry run → review → apply)."""

import base64
import binascii
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import text

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import Out, StrictModel
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import imports
from pawguard_api.errors import NotFound, Unprocessable

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])
DATE_FORMATS = {"YYYY-MM-DD": "%Y-%m-%d", "DD/MM/YYYY": "%d/%m/%Y", "DD-MM-YYYY": "%d-%m-%Y"}


class ImportCreate(StrictModel):
    import_type: Literal["animals_csv", "vaccinations_csv"]
    source_label: str = Field(min_length=3, max_length=200, description="Where the file came from (partner, export)")
    filename: str | None = Field(default=None, max_length=200)
    date_format: Literal["YYYY-MM-DD", "DD/MM/YYYY", "DD-MM-YYYY"] = "YYYY-MM-DD"
    content_base64: str = Field(max_length=2_900_000)


class ImportSummary(Out):
    id: UUID
    import_type: str
    source_label: str
    raw_filename: str | None
    state: str
    row_count: int
    valid_count: int
    warning_count: int
    rejected_count: int
    created_at: datetime
    applied_at: datetime | None
    row_version: int


class ImportDetail(ImportSummary):
    report: dict[str, Any]
    created_record_ids: dict[str, Any]


class ImportApply(StrictModel):
    row_version: int
    include_warning_rows: bool = False


class ImportRollback(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


def _load(db, import_id: UUID, detail: bool):  # type: ignore[no-untyped-def]
    row = db.execute(text("select * from app.import_jobs where id = :id"), {"id": import_id}).one_or_none()
    if row is None:
        raise NotFound("Import not found.", code="import_not_found")
    base = {k: getattr(row, k) for k in ImportSummary.model_fields}
    if detail:
        return ImportDetail(**base, report=row.report, created_record_ids=row.created_record_ids)
    return ImportSummary(**base)


@router.post("", status_code=201, response_model=ImportDetail, summary="Upload a CSV and run a dry run")
def create(body: ImportCreate, ctx: CurrentOrg) -> JSONResponse:
    """Permission: ``data.import``. Stores the raw file immutably (≤ 2 MB, UTF-8 CSV) and returns a validation
    report. Nothing is created until the import is applied."""
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Unprocessable("File content is not valid base64.", code="invalid_content") from exc
    if len(content) > 2 * 1024 * 1024:
        raise Unprocessable("Files are limited to 2 MB.", code="file_too_large")
    with ctx.tx() as db:
        job_id = imports.create_job(db, ctx, body.import_type, body.source_label, body.filename, content,
                                    DATE_FORMATS[body.date_format])
        payload = _load(db, job_id, True).model_dump(mode="json")
    return JSONResponse(payload, status_code=201)


@router.get("", response_model=list[ImportSummary], summary="Import history")
def list_imports(ctx: CurrentOrg) -> list[ImportSummary]:
    """Permission: ``data.import``."""
    ctx.require(Cap.DATA_IMPORT)
    with ctx.tx() as db:
        ids = db.execute(text("select id from app.import_jobs order by created_at desc limit 100")).scalars().all()
        return [_load(db, i, False) for i in ids]


@router.get("/{import_id}", response_model=ImportDetail, summary="Import report")
def get(import_id: UUID, ctx: CurrentOrg) -> ImportDetail:
    """Permission: ``data.import``. The report contains partner data and is restricted accordingly."""
    ctx.require(Cap.DATA_IMPORT)
    with ctx.tx() as db:
        return _load(db, import_id, True)


@router.post("/{import_id}/apply", response_model=ImportDetail, summary="Apply a validated import")
def apply(import_id: UUID, body: ImportApply, ctx: CurrentOrg) -> ImportDetail:
    """Permission: ``data.import`` + ``animal.write`` (animals) or ``vaccination.submit`` (vaccinations). One
    transaction; rejected and previously imported rows are never applied; vaccination rows arrive as submitted."""
    with ctx.tx() as db:
        imports.apply(db, ctx, import_id, body.row_version, body.include_warning_rows)
        db.flush()
        return _load(db, import_id, True)


@router.post("/{import_id}/rollback", response_model=ImportDetail, summary="Roll back an animal import")
def rollback(import_id: UUID, body: ImportRollback, ctx: CurrentOrg) -> ImportDetail:
    """Permission: ``data.import`` + ``animal.merge``. Archives the created records if none has been used since."""
    with ctx.tx() as db:
        imports.rollback(db, ctx, import_id, body.reason)
        db.flush()
        return _load(db, import_id, True)
