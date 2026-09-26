# ADR-007: Consent, retention and deletion as first-class features; no LLM on health data by default

**Status:** Proposed · **Date:** 2026-09-27

## Context
There is no consent, no retention policy and no deletion. Biometric skeletons are persisted forever, videos are left on disk after failures, and findings are sent to Groq without disclosure (F06). The target market is Indian clinics and academies (DPDP Act 2023; minors at sports academies).

## Decision
- **Consent record** per patient: purpose text version, capture method (clinician-attested, patient-signed tablet), guardian consent flag for minors, timestamp, and withdrawal timestamp. The analysis API refuses patients without active consent.
- **Retention:** raw video deleted after analysis (default) or ≤ 7 days (R2 lifecycle). Derived landmarks are kept only as downsampled per-stride summaries. Reports and metrics are kept for the clinic's configured period (default 3 years), then purged by a scheduled job.
- **Deletion:** `DELETE /patients/{id}` cascades DB rows and R2 objects and writes an audit entry with object keys. `GET /patients/{id}/export` returns JSON + PDFs (access right).
- **LLM:** removed from the analysis path. If reintroduced, it runs on de-identified metrics only, is opt-in per org, and is disclosed in the notice.
- **Docs:** a privacy notice, a DPA template for clinics, a grievance contact and a sub-processor list (Render, Cloudflare, Sentry).
- **Logs:** a structured logger with a redaction filter (passwords, tokens, names, emails) and no request bodies.

## Consequences
- This is a sales prerequisite for clinics and doubles as strong portfolio material.
- It adds one scheduled job (Render cron) and some UI.
