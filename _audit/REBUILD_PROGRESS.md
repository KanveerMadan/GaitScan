# GaitScan Rebuild — Progress

Source of truth for which phase is next. Plan: [REBUILD_PLAN.md](REBUILD_PLAN.md). Reports: [phase-reports/](phase-reports/).

| Phase | Status |
|---|---|
| 0 — Stop the bleeding | done |
| 1 — Foundations | done (local; deploy + CI-on-PR are human actions) |
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
- Status: **done locally** (2026-10-03) · report: [phase-reports/PHASE_1.md](phase-reports/PHASE_1.md)
- Scope amended 2026-09-27 (owner request): + F10 login rate limiting, + F12 email enumeration (mitigation; full closure needs Phase 4 invite/email flow), + F15 mode persisted for PDF regeneration, + password minimum length 10 on registration and password change only (legacy short passwords still log in). See REBUILD_PLAN D6 Phase 1 task 11.
- Branches (**not pushed**; both GitHub repos are public, see PHASE_1 human action 1): backend `rebuild/phase-1-foundations`, frontend `rebuild/phase-1-foundations`, both stacked on the unmerged `rebuild/phase-0-stop-the-bleeding` (re-checked 2026-10-03: not in `origin/main`).
- Blocked on human: CI green on a PR (needs push), Render deploying the Docker image, Render X-Forwarded-For verification (TRUSTED_PROXY_HOPS=2).
- Findings closed: F10 (pending the Render verification), F11 (npm 48→0; pip 40→2 protobuf, CI-ignored until Phase 2), F15 (mode), F16, F17, F38, F41. Partial: F12 (enumeration residual until Phase 4), F39 (Vite/env/lint done; router + split + typed client per ADR-008 later).
- Evidence: backend 119 passed (SQLite + Postgres 16), audit spec unchanged (7 failed / 11 passed, Phase 2); frontend 18 passed; security probe v3 11/16 → 14/16 PASS; walk01 output byte-identical to Phase 0; Docker image verified against Postgres seeded with a legacy create_all schema.
- Backend commits:
  - earlier session: `b7e9408` plan amendment · `f17025c` golden test · `649a337` gaitcore/app split · `1f7402b` remove src/ · `f2c646c` pyproject + uv.lock + PyJWT · `ecf9fe9` validated settings · `d9f6f1c` Alembic baseline · `00f81d4`/`2b1b863` F15 · `d55e252`/`236777b` auth hardening · `3908373`/`3b5249f` observability · `a5f3aad`/`89f08e8` invite codes · `210d303` ruff format · `f385e5c` lint · `b063d73` wip
  - `9b2a713` test: failing test for clinician session list when the patient row is missing
  - `4eb8129` fix(clinician): 404 instead of 500 when a linked patient row is missing
  - `d16de70` refactor(db): SQLAlchemy 2.0 DeclarativeBase with typed Mapped columns
  - `024e5c8` build(types): mypy strict on gaitcore, default checking on app
  - `d792c67` fix(logging): route remaining print() calls through logging; lint bans print
  - `99a88f8` build: pre-commit hooks for ruff, ruff format, mypy and detect-secrets
  - `7eedc3e` fix(pre-commit): honour ruff excludes when hooks pass explicit filenames
  - `36eb5bb` test: failing tests for proxy-aware, spoof-resistant client IP (F10)
  - `e294b21` fix(ratelimit): derive client IP from trusted proxy hops, not the socket peer
  - `77ccbe2` test: failing tests for /healthz
  - `b282fb8` feat(api): /healthz checks database connectivity for the Render health check
  - `e0ee698` test: failing test for the Postgres driver SQLAlchemy 2.1 selects
  - `7edd884` fix(deps): use psycopg 3, the driver SQLAlchemy 2.1 picks for postgresql://
  - `ee1208b` test: upgrade a real create_all database with rows in every table
  - `89afcf8` fix(db): baseline reconciles legacy create_all drift when adopting tables
  - `4d45898` test: failing test for bound parameters (password hashes) in DB error text
  - `a2fd9aa` fix(logging): hide SQL bound parameters from exceptions and logs
  - `26ec903` test: legacy fixture advances Postgres sequences; upgraded DB must accept new rows
  - `abd6785` build(docker): slim non-root image that migrates, then serves one uvicorn worker
  - `b90ffdf` build(render): Blueprint for the Docker web service with /healthz
  - `5f3d886` ci: lint, typecheck, test on SQLite+Postgres, pip-audit, docker build; Dependabot
  - `7ddc49b` docs: accurate README with capture protocol, CONTRIBUTING, architecture, env vars
  - `c43d05c` docs(audit): security probe v3 for the app/ layout; Phase 1 evidence
  - (next) docs(audit): Phase 1 report and progress
- Frontend commits:
  - `96ebe3c` build: migrate Create React App to Vite + Vitest, TypeScript with allowJs
  - `7e388b4` fix(lint): satisfy eslint recommended + react-hooks rules
  - `9ebe484` style: apply prettier
  - `1e73cdb` test: failing specs for 10-char hint, 429 and 422 messages, change-password form
  - `9cf43c8` feat(auth): change-password form, 10-char hint, readable 429/422 errors
  - `c922f19` ci: lint, typecheck, test, build and npm audit; pre-commit hooks; Dependabot
  - `427daa6` docs: README for the Vite setup, not-a-medical-device notice, accurate features
  - `4fc629e` fix(build): require VITE_API_BASE_URL only for vite build, not preview
- Next: Phase 2 — Measurement core v2 (can start before the deploy; it doesn't depend on it). First task there: upgrade mediapipe and remove the two protobuf ignores from backend CI.

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
