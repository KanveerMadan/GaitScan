# GaitScan Rebuild — Progress

Source of truth for which phase is next. Plan: [REBUILD_PLAN.md](REBUILD_PLAN.md). Reports: [phase-reports/](phase-reports/).

| Phase | Status |
|---|---|
| 0 — Stop the bleeding | done |
| 1 — Foundations | in progress |
| 2 — Measurement core v2 | todo |
| 3 — Async jobs + object storage | todo |
| 4 — Tenancy, auth, consent, deletion | todo |
| 5 — Validation harness | todo |
| 6 — Product & report | todo |

## Phase 0 — Stop the bleeding
- Status: **done** (2026-09-27) · report: [phase-reports/PHASE_0.md](phase-reports/PHASE_0.md)
- Branches (not pushed): backend `rebuild/phase-0-stop-the-bleeding` from `origin/main` 38c8db3; frontend `rebuild/phase-0-stop-the-bleeding` from `origin/main` be64af4
- Findings closed: F01, F02, F03, F04, F05, F08, F09, F19, F20, F36. Partial: F06 (raw video always deleted, no skeleton CSV, LLM off by default; consent/retention are Phase 4), F07 (case-insensitive ext + size cap; content sniffing/duration are Phase 3), F18 (stubs deleted, .gitignore fixed; history rewrite is a human action).
- Still open, by plan: F10 and F12 (Phase 4), F15 (Phase 3), F40 (Phase 6).
- Human actions pending before deploy: set `JWT_SECRET` + `CORS_ORIGINS` on Render, push branches, deploy frontend then backend, review clinician accounts (see report).
- Backend commits:
  - `f9fafdf` chore(git): ignore env files, media, local DBs and audit scratch
  - `2c115ad` test: add failing Phase 0 security, upload, report and language tests
  - `e47fd9b` chore: delete empty main.py and tests/test_angles.py stubs
  - `679164a` fix(auth): load JWT secret from env and fail closed in production
  - `58831bb` fix(auth): ignore client-supplied role on registration
  - `7cfc29d` fix(api): delete /debug/links
  - `6b28629` fix(plots): select the Agg backend explicitly
  - `2cd1474` fix(pdf): escape all interpolated text before ReportLab markup parsing
  - `78ff1e1` fix(api): restrict CORS to configured origins and hide docs outside dev
  - `315a654` fix(api): require auth and ownership on /sessions/{id} and /report/{id}
  - `a1e511f` fix(api): harden /analyze upload handling and error responses
  - `cb1a1ef` fix(copy): replace diagnostic wording with measurement wording
  - `2367d0f` fix(privacy): make LLM exercise explanations opt-in, off by default
  - `265aabe` fix(pdf): remove the risk-score headline and diagnostic wording
  - `69ebd67` fix(api): serve stored sessions with current wording and a disclaimer
  - `d5850fd` docs(config): document every environment variable in .env.example
  - `bee2a0f` docs(audit): add audit, rebuild plan, ADRs, probes and Phase 0 report
  - (next) docs(audit): redact test tokens from Phase 0 test output
- Frontend commits:
  - `3f87bee` chore(git): ignore env files, media and local databases
  - `1ae4331` test: replace CRA boilerplate test with failing Phase 0 specs
  - `f7956ee` fix(auth): stop storing passwords and logging tokens
  - `e69207c` fix(reports): download PDFs with an authenticated request
  - `c2d56a5` fix(copy): measurement framing, disclaimer and no risk score in the UI
- Next: Phase 1 — Foundations (can start without waiting for the human actions; nothing in it depends on the deploy).

## Phase 1 — Foundations
- Status: in progress
- Scope amended 2026-09-27 (owner request): + F10 login rate limiting, + F12 email enumeration (mitigation; full closure needs Phase 4 invite/email flow), + F15 mode persisted for PDF regeneration, + password minimum length 10 on registration and password change only (legacy short passwords still log in). See REBUILD_PLAN D6 Phase 1 task 11.
- Branches: backend `rebuild/phase-1-foundations`, frontend `rebuild/phase-1-foundations`, both **stacked on the unmerged phase-0 branches** (branching from `main` would drop Phase 0).

## Phase 2 — Measurement core v2
- Status: todo

## Phase 3 — Async jobs + object storage
- Status: todo

## Phase 4 — Tenancy, auth, consent, deletion
- Status: todo

## Phase 5 — Validation harness
- Status: todo

## Phase 6 — Product & report
- Status: todo
