# ADR-002: Async analysis via a Postgres-backed job table + one worker process

**Status:** Superseded by REBUILD_PLAN_V3.md (2026-10-03): no job queue; a FastAPI background task + status polling in Phase 4 · **Date:** 2026-09-27

## Context
`/analyze` runs a CPU-bound pipeline inside `async def`, blocking the event loop: a 28.7 s health-check stall was measured (F13). Peak RSS is 339–516 MB (F14) on 512 MB instances. Volume is expected to be tens to low hundreds of analyses per day. The budget is a student's.

## Options
| Option | Extra infra | Notes |
|---|---|---|
| Celery + Redis | Redis ($) + broker config | Heavy for one task type |
| Arq / RQ + Redis | Redis ($) | Fine, but Redis is one more service to run and secure |
| **Postgres jobs table (`SELECT … FOR UPDATE SKIP LOCKED`)** | none, since Postgres already exists | ~80 lines; transactional with results |
| Managed (Modal, Cloud Tasks) | vendor | Good later for burst/GPU |

## Decision
An `analysis_jobs` table (`id, org_id, status[queued|running|succeeded|failed], attempts, error_code, input_key, result_id, pipeline_version, created_at, started_at, finished_at, locked_until`). The API inserts a row and returns `202 {job_id}`. A **Render Background Worker** (same Docker image, `python -m app.worker`) claims jobs with `SKIP LOCKED`, runs `gaitcore` in a subprocess with a timeout and memory cap, writes results, and retries up to 2× on transient errors. The frontend polls `GET /jobs/{id}` every 2–3 s.

## Consequences
- The API stays responsive and the worker's memory is isolated from the web process.
- Throughput is 1 job at a time per worker. Scale by adding workers; move to Arq/Redis when queue latency > ~1 min at peak (`# ponytail:` note in code).
- Polling instead of websockets/webhooks is simple and adequate for multi-second jobs.
- Adds one Render service (~US$7/month Starter).
