# ADR-003: Object storage with signed URLs and lifecycle deletion; Postgres for metadata

**Status:** Proposed · **Date:** 2026-09-27

## Context
Videos, landmark CSVs, PNGs and PDFs live on Render's ephemeral disk (F15). They are deleted only by accident (redeploy) or never (failed runs, F06). The PDF regeneration path loses mode and charts. The data is biometric and health-adjacent.

## Decision
- **Cloudflare R2** (S3-compatible, zero egress fees, free tier). Use any S3 client via `boto3`; swapping to S3 later is only a config change.
- The browser uploads the video **directly** to R2 with a presigned PUT (size + content-type constrained). The API never streams video bytes.
- Bucket prefixes `raw/`, `derived/`, `reports/`. A **lifecycle rule deletes `raw/` after 7 days**, and the worker also deletes the raw object immediately after a successful analysis unless the clinic opted in to keep it.
- PDFs are generated on demand from DB data (deterministic) or cached under `reports/` with a 30-day TTL. Downloads use short-lived (5 min) presigned GETs issued only after an authz check.
- Postgres stores metrics, per-stride arrays (JSONB), quality flags, `pipeline_version`, config and mode, i.e. everything needed to rebuild a report.

## Consequences
- Verifiable deletion (object versioning off + lifecycle + a deletion audit log row).
- No local disk state, so web and worker instances are disposable.
- There is a new external credential to manage (R2 keys in Render env).
