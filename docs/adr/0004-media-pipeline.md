# ADR 0004 — Media: pre-signed single-object uploads, quarantine, worker validation

Date: 2026-10-05 · Status: accepted

## Decision
Private bucket; API issues a signed upload URL for exactly one object key under `quarantine/`; the browser uploads bytes directly to Storage; completion is confirmed via the API; a worker validates bytes (decode, MIME sniff, size and pixel limits, EXIF orientation), computes SHA-256, writes normalised derivatives with metadata stripped under `derived/`, then marks the asset `approved` or `rejected` with a reason code. Domain records may only reference `approved` media. Downloads are short-lived signed URLs issued after authorisation. Only JPEG/PNG/WebP images and PDF evidence (stored, not parsed) are accepted initially.

## Consequences
The worker holds a server-side Storage key (Supabase has no per-prefix machine keys); it runs in its own container and never exposes it. Documented as residual risk in `THREAT_MODEL.md`.
