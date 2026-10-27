# GaitScan Rebuild — Progress

Plan: [REBUILD_PLAN_V3.md](REBUILD_PLAN_V3.md). Full history of Phases 0–2 is in git and `phase-reports/`.

- Done and deployed: Phase 0 + Phase 1 merged to main (#1, #2); backend on Render `gaitscan-api`, frontend on Vercel
- Merged since: #11 per-IP rate limits keyed on CLIENT_IP_HEADER (Render: True-Client-IP), #12 pillow 13.0.0 / certifi 2026.10.19
- Phase 2 merged and deployed 2026-10-24: backend #10 (e6432fe, Render), frontend #10 (88cc8e7, Vercel)
- Current phase: **3.2 — Reliability engine** (checklist in the plan)
- Phase 2 LJMU gates (Topham et al. 2023, CC BY 4.0): path-convergence side-view check + view_unconfirmed; duplicate pose = one person; legs_not_tracked (>= 4 s steady, < 6 steps); irregular_steps (label-free step CV > 0.15)
- Cadence/step time label-free (heel-separation peaks); per-leg knee hidden with a note when labelled step CV > 0.2; stride time withheld (Phase 3)
  - 27 AI-annotated + cross-checked clips: MAE 12.0 -> 1.6 steps/min (max 4.9); held-out 54 clips / 34 participants vs RTMPose: MAE 1.7 (max 5.4)
- Next task: Phase 3.2 degradation curves (running in Docker: data/ljmu/deg), then the reliability model
- Blockers / human actions:
  - hip_sagittal_excursion hidden from API/PDF/UI (CONDITIONAL); still computed for the Phase 3 check
  - No protocol-conforming real clip yet (walk01 is rejected: no complete step)
  - Dependabot PRs #7–#9 open, untriaged
- Phase 3 (PR #14, frontend #11, 2026-10-26): per-pass results, test-type registry, accuracy block; knee/step length/speed "not yet validated"; floor calibration UI
  - make evaluate on LJMU: cadence MAE 1.55 steps/min, p95 4.67 (97 clips); test 21 clips MAE 1.10, p95 2.36; app shows ±4.7 steps/min, ±0.024 s
  - Stride time stays withheld (labels follow position: 37/110 legs read one step as a stride); per-leg values need strides two steps long
  - Blocked: walking-speed reference (no 8 m start/end in clips), norms (no age/sex), sit-to-stand (OpenCap, Phase 8), irregular_steps + heel visibility (phone clips)
- Phase 3.5 (frontend #12, stacked on #11): Tailwind v4 + owned shadcn/ui, tokens (light/dark, one teal accent), app shell, all screens migrated, App.jsx split
- Phase 3.2 (2026-10-27): degradation curves on LJMU (54 participants, 896 runs): the gate's acceptance falls steeply as quality drops; some accepted degraded clips reach 9 steps/min error (published range 4.7)
  - Learned per-clip error model (GBM + conformal, leave-participant-out): coverage OK but no discrimination (Spearman 0.11); not shipped
- Phase 4 (backend #16, frontend #13; stacked): background analysis + polling, typed client from a drift-checked contract, router, dashboard, notes/tags, comparison vs LJMU repeatability (MDC95 4.4 steps/min), knee curves, live framing check, onboarding, demo, PWA manifest, Playwright e2e, Locust
  - Blocked: in-browser recording (frame timing on real phones); cut: goals, visual explanations; normative knee band and ghost replay need decisions/data
- Phase 5 (backend #17, frontend #14; stacked): consent, privacy center, password reset + verification (mailer: console/none), share links, F40 name, F10 invite expiry + join limit
  - Audit re-run (probes out_*_phase5): API probe 15 PASS / 1 FAIL (F12 enumeration: accepted until an email provider enables verified sign-up); F13 /status max 0.03 s during an analysis
  - F01-F44: closed except accepted F12 (enumeration), F21 (Render cold start), F40 part (clinicians can't upload for a patient), F05 part (token in localStorage, not an httpOnly cookie), F06 part (no scheduled retention purge: data kept until the user deletes it)
