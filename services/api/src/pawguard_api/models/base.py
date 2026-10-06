"""Declarative base. The schema is owned by Alembic migrations; models mirror it for typed access."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="app")
    type_annotation_map = {UUID: PGUUID(as_uuid=True)}


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Versioned:
    """Mutable rows carry ``row_version``; the ``touch_row`` trigger increments it on every update."""

    row_version: Mapped[int] = mapped_column(server_default=text("1"))


def uuid_pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, server_default=text("extensions.gen_random_uuid()"))
