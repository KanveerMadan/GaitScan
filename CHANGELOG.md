# Changelog

The rebuild of GaitScan after the technical audit (`_audit/GAITSCAN_AUDIT.md`), phase by phase
(`_audit/REBUILD_PLAN_V3.md`). Backend PRs are in this repository; frontend PRs are in
`gaitscan-frontend`. "Fxx" refers to the audit findings ([docs/findings.md](docs/findings.md)).

## Owner decisions — 2026-11-12
- Knee angle removed from the API, PDF, export and app (Phase 8 cancelled: it can never be
  validated); migration 0013 deleted it from stored results.
- Optional sex and birth year (settings) and sex (profiles) for a published cadence reference by
  age and sex in the app (Mobbs et al. 2025, CC BY 4.0).
- Google sign-in never signs in to an account made with a password (account pre-hijacking), matches
  addresses without regard to capitals, and requires the token's expiry and account id.
- MIT licence. Data-blocked items closed: no more video will be collected.

## Real-world recording checks — backend #18
- The steadiness window is now the walker's own step time (0.5–1.0 s), not a fixed 0.5 s. Slow
  walkers were losing most of their steps.
- A second person in view, or the heels out of view, for a step or more now drops that stretch
  instead of rejecting the whole video. The rest must still pass every other check. When too
  little walking is left, the rejection says why.
- On three phone videos: two cadences closer to a visual count, and one turned-down video now
  measured. LJMU: 97/109 reference clips accepted (unchanged), cadence ±4.5 steps/min (was ±4.7).
- New quality fields: `steadiness_window_s`, `second_person_s`, `heels_hidden_s`.

## Phase 6 — Polish (frontend #15)
- Route-level code splitting: first load 808 → 333 kB.
- Landing page with the accuracy figures from the API.
- Phone layout (no sideways scrolling at 360 px), app icons, consistent copy.
- Playwright checks: phone width, and axe (WCAG 2.1 AA) in light and dark mode. Lighthouse
  (mobile): 97 / 100 / 100 / 100.

## Phase 5 — Accounts, sharing, privacy (backend #17, frontend #14)
- Consent before the first analysis (versioned, withdrawable, history kept).
- Privacy center: export everything, delete a session, delete the account.
- Password reset and email verification: single-use, expiring, hashed links. A password change ends
  other logins. Email delivery waits for a provider; until then these endpoints answer 503 with a
  reason.
- Read-only share links for one session: hashed tokens, 7-day default, revocable.
- Names on sessions and PDFs (F40); invite codes expire and joins are rate-limited (F10).

## Phase 4 — Usability (backend #16, frontend #13)
- Non-blocking analysis: `POST /analyses` → 202, then poll `GET /analyses/{id}` (F13).
- Typed API client generated from the OpenAPI contract, drift-checked in both CIs.
- Router, dashboard, session page with notes and tags, and session comparison against LJMU
  repeatability (minimal detectable change).
- Knee-angle curves, live framing check, first-test walkthrough, demo, installable PWA.
- Playwright e2e of the main flow; Locust load test.

## Phase 3.5 — Design foundation (frontend #12)
- Tailwind v4, owned shadcn/ui primitives, light/dark tokens with one teal accent, Geist.
- App shell; every screen migrated.

## Phase 3.2 — Reliability engine (backend #15)
- Degradation curves on LJMU (resolution, frame rate, compression, low light, roll, 45° yaw).
- A learned per-clip error model (gradient boosting + conformal intervals, leave-participant-out)
  was evaluated and not shipped: it didn't rank clips by error better than chance (Spearman 0.11; 0.13 after the real-world
  gates change).
  See [docs/reliability-engine.md](docs/reliability-engine.md).

## Phase 3 — Honest results (backend #14, frontend #11)
- `make evaluate`: the accuracy check on LJMU (Topham et al. 2023, CC BY 4.0). Error ranges are
  shown next to each metric (F22).
- Knee angle, step length and walking speed labelled "not yet validated" in the API, PDF and UI.
- Per-pass results, a test-type registry, floor calibration for step length and speed.

## Phase 2 — Measurement correctness (backend #10, frontend #10)
- Measurement core v2 (ADR-006):
  - pixel-space angles;
  - visibility masking without filling;
  - zero-phase filtering;
  - steady-pass detection;
  - label-free cadence from heel separation;
  - per-stride knee peaks (F24–F27, F29, F31, F33, F34, F42).
- Recording checks with specific reasons. The side-on check, `legs_not_tracked` and
  `irregular_steps` were chosen on LJMU.
- Risk score, symmetry indices, activity classifier, exercise suggestions and LLM text removed;
  old values archived (F23, F28, F30, F35, F37).
- MediaPipe Tasks 1.0.1 with a pinned model (F11, F32); one pose run per process (F14).

## Phase 1 — Foundations (backend #2, frontend #2)
- `pyproject.toml` + `uv.lock`, Dockerfile, `render.yaml`, Alembic (F16, F17).
- JSON logging with redaction, Sentry, pre-commit hooks (F41).
- Rate limits keyed on a spoof-resistant client IP, 10-character passwords (F10, F12).
- CRA → Vite (F39, F11).

## Phase 0 — Security hotfix (backend #1, frontend #1)
- Secret from the environment and fail closed (F01); auth and ownership on sessions and reports
  (F02); no client-chosen roles (F03).
- No plaintext passwords stored or logged (F04, F05); CORS allow-list and 12-hour tokens (F08).
- Generic errors and no public docs (F09); escaped PDF text (F20).
- Upload checks and video always deleted (F06, F07); measurement wording instead of diagnosis (F36).
