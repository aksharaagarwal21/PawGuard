# ADR 0005 — Alembic is the single migration authority

Date: 2026-10-05 · Status: accepted

Supabase CLI migrations and seeding are disabled in `infra/supabase/config.toml`. Alembic revisions use explicit SQL (`op.execute`) for extensions, roles, policies, triggers, functions and specialised indexes; SQLAlchemy models mirror the schema but `alembic revision --autogenerate` output is always reviewed by hand. Supabase-owned schemas (`auth`, `storage`) are never altered by Alembic except to read `auth.sessions` through a narrow function.
