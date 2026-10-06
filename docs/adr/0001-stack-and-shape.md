# ADR 0001 — Modular monolith on the brief's default stack

Date: 2026-10-05 · Status: accepted

## Context
New repository (empty workspace). Single developer machine: Windows 11, i7-1255U (10 cores), 16 GB RAM, Docker Desktop (8 GB VM), no CUDA GPU. Network access to npm, PyPI, GitHub, Hugging Face, Zenodo.

## Decision
Use the brief's defaults: Next.js App Router + TypeScript strict; FastAPI + SQLAlchemy + Alembic; PostgreSQL with PostGIS and pgvector; Supabase Auth + private Storage (local stack via Supabase CLI 2.119.0); Celery + Redis with a transactional outbox; OpenCV + ONNX Runtime for inference; PyTorch only in `ml/`.

Substitutions, each for a verified reason:
- **TypeScript 6.0.3, not 7.0.2.** typescript-eslint 8.71 declares `typescript >=4.8.4 <6.1.0`.
- **ESLint 9.x, not 10.x.** eslint-config-next 16.3.8 pulls plugins whose peer ranges are not yet confirmed for ESLint 10.
- **Python 3.12** for all services and images (widest wheel coverage for torch/onnxruntime/ortools); local Python 3.13 is not used.
- **pnpm via corepack** pinned in `packageManager`.

## Consequences
Two language runtimes and a local Supabase stack (6 containers) are needed for development; `scripts/dev-up` starts them. No Kubernetes, graph DB, blockchain or multi-agent orchestration.
