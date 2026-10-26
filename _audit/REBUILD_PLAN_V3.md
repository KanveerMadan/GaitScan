# GaitScan — Rebuild Plan V3 (checklist)

Rules:
- Every new MEASUREMENT passes the Phase 3 accuracy check (LJMU, Topham et al. 2023, CC BY 4.0; synthetic where no public data exists); a failing measurement is not shipped. No OpenCap before Phase 8 (decided 2026-10-26).
- No feature introduces a health claim or an unvalidated number.
- Metrics: KEEP cadence, step time, sagittal knee angle (shown as "not yet validated" until Phase 8) · CONDITIONAL step length + speed (floor calibration only), hip sagittal excursion (must pass Phase 3), stride time (withheld 2026-10-24: brief L/R flips) · REMOVED risk score, frontal-plane, ankle, L/R angle symmetry, uncalibrated distance/speed, activity classification, modes, exercises, LLM.
- Priority: [M] Must, [S] Should, [C] Could. Cut [C] first, then [S]; never cut security, correctness or the design foundation.
- Docs only in Phase 7; during development only this file, REBUILD_PROGRESS.md, commit messages and brief code comments.

## Phase 0 — Stop the bleeding: done
## Phase 1 — Foundations: done
## Phase 2 — Measurement correctness: done (walk01 rejected: no complete step; needs a protocol-conforming clip)

## Phase 3 — Honest results + new measurements
- [x] [M] Confirm the pipeline supports multiple passes, a second test type, and a user-supplied treadmill speed; refactor if not (treadmill: rejected as view_unconfirmed until Phase 4 treadmill mode)
- [x] [M] Accuracy check on LJMU (cadence, step time; walking speed from the known 8 m path) via reproducible `make evaluate` → machine-readable JSON/CSV (speed blocked: the clips don't show the walk's start or end, so no distance reference)
- [x] [M] Peak knee flexion marked "not yet validated" in API, PDF and UI (no knee reference without OpenCap)
- [x] [M] Error ranges from that check shown in the app next to each metric
- [ ] [M] Published reference norms (cited in code comments) only where they exist (blocked: norms depend on age and sex, which the app doesn't collect, and no verified norms table was retrievable)
- [x] [M] Results page and PDF show units, error ranges, quality indicator
- [x] [M] Multiple passes per session: per-pass results, mean, between-pass variability (synthetic only: LJMU clips hold one pass)
- [x] [S] Floor calibration UI (two tapped markers, known distance) → step length, walking speed (values labelled not yet validated)
- [ ] [S] Five-times sit-to-stand (timing + repetition count), checked against OpenCap sit-to-stand data (blocked: no OpenCap until Phase 8)
- [ ] [C] 30-second chair stand on the same detector (blocked with sit-to-stand)
- [ ] [C] Step-timing breakdown (stance/swing %, step-time asymmetry), only if the accuracy check supports it (cut: needs per-foot events, which fail on LJMU)
- [ ] [M] Per-foot heel strikes robust to brief L/R flips (xfail tests in test_measurement.py), then re-show stride time (2026-10-26: a continuity fix passes the synthetic flips but not LJMU, where labels follow position and 37/110 legs read one step as a stride; not shipped, stride time stays withheld; per-leg values now need strides two steps long)
- [ ] [M] Re-validate irregular_steps (label-free step-time CV > 0.15, chosen on held-out LJMU) on phone clips, incl. uneven gait (blocked: needs real phone clips)
- [x] [S] gait.py:110 edge steps: steps at a steady-window edge are lost (e.g. LJMU P34_E1T1 rejected) (checked 2026-10-26: a padded search gained 1 clip but cadence MAE 1.66 -> 1.72, max 5.4 -> 6.4; not changed)
- [ ] [S] gait.py:103 heel visibility: heel separation doesn't require visible heels; check on phone clips (blocked: needs real phone clips)
- [x] [S] result.py:56 brief flips: labelled step CV <= 0.2 misses 5-10% brief flips (per-leg knee flexion) (stride check hides all 10% cases; at 5%, 2/8 synthetic seeds still show a knee 4-6 deg low)

## Phase 3.2 — Reliability engine
- [ ] [M] Degradation curves on LJMU (resolution, fps, compression, low light, camera yaw/roll): how each gait metric's error grows
- [ ] [M] Learned reliability model: per-clip expected error / reject (gradient boosting or small MLP, conformal intervals), leave-participant-out evaluation
- [ ] [M] Ship it in the app: learned ± error next to each metric, learned rejections with reasons
- [ ] [S] arXiv-style write-up (deferred to Phase 7)

## Phase 3.5 — Design foundation (before any Phase 4 UI): done (frontend #12)
- [x] [M] Design direction
- [x] [M] Design system: color, typography, spacing tokens, light/dark themes
- [x] [M] Tailwind + shadcn/ui (Radix)
- [x] [M] App shell: navigation and layout
- [x] [M] Migrate existing screens into the shell
- [x] [M] Use design-taste-frontend, frontend-design-toolkit, web-design-guidelines; no generic template look (design-taste-frontend and web-design-guidelines used; frontend-design-toolkit not yet)
- [ ] [M] All Phase 4–5 screens built with this system (ongoing rule)

## Phase 4 — Usability + app features
- [ ] [M] Non-blocking analysis: FastAPI background task + status endpoint + polling (no Redis/Celery)
- [ ] [M] In-browser recording with live framing guidance (MediaPipe Tasks for Web, same pinned model; analysis server-side)
- [ ] [M] Guided first-test onboarding (setup steps + demo + recording)
- [ ] [M] Personal dashboard: latest results, trends, last test date
- [ ] [M] Session comparison: side by side, overlaid knee curves, "real change" vs "within measurement error"
- [ ] [M] Session notes/tags
- [ ] [M] Split App.jsx per ADR-008 with a typed API client (split done in Phase 3.5; typed client remains)
- [ ] [M] One Playwright e2e test of the main flow, in CI
- [ ] [S] Demo mode (sample video, no signup; synthetic or explicitly consented clip)
- [ ] [S] Visual explanations: keyframes with skeleton + heel strikes, knee curve with gait cycles, offending frame on rejection (server-rendered images, no video stored)
- [ ] [S] Knee-angle curve with a published normative band
- [ ] [S] Ghost replay: today's walk overlaid on a past session as skeletons, aligned by gait cycle (DTW), differences highlighted
- [ ] [S] Installable PWA
- [ ] [S] Goals with progress tracking
- [ ] [S] k6 or Locust load test (capacity in the terminal summary)
- [ ] [C] "Analysis done" notification
- [ ] [C] Profile settings: height, units, language, dark mode
- [ ] [C] Timeline search/filters
- [ ] [C] Treadmill mode (user-entered speed)

## Phase 5 — Accounts, sharing, privacy
- [ ] [M] Transactional email (provider justified in the terminal summary; secrets via env)
- [ ] [M] Password reset with expiring single-use tokens
- [ ] [M] Email verification (closes F12)
- [ ] [M] Consent screen before first analysis
- [ ] [M] Privacy center: export data, delete sessions, delete account
- [ ] [M] Patient name on PDF (F40)
- [ ] [S] Professional inbox (shared reports, comments; access-control tests)
- [ ] [S] Expiring, revocable, read-only share links (random token, 7-day default, no personal data in URL), with tests
- [ ] [S] Re-test reminders (user schedule, easy unsubscribe)
- [ ] [C] Sign in with Google
- [ ] [C] Multiple adult profiles per account, blocking under-18 profiles
- [ ] [C] Hindi UI strings
- [ ] [M] Re-run every audit probe; F01–F44 each closed or explicitly accepted

## Phase 6 — Frontend redesign & polish
- [ ] [M] Production-quality redesign of every screen
- [ ] [M] Landing page
- [ ] [M] Mobile-first responsive layouts
- [ ] [M] Loading, empty, error states everywhere
- [ ] [M] WCAG AA
- [ ] [M] Lighthouse 90+ (code splitting, image optimization)
- [ ] [M] Use the design skills; no generic template look
- [ ] [S] Skeletons, transitions, micro-interactions
- [ ] [S] Consistent chart styling
- [ ] [S] Branding: logo, favicon, app icons
- [ ] [S] Consistent copy
- [ ] [C] Visual regression screenshots in CI

## Phase 7 — Documentation
- [ ] README and setup
- [ ] Architecture docs and ADR updates
- [ ] Model card / "Accuracy & Limitations" page (from `make evaluate`) + evaluate instructions
- [ ] Learn pages per metric with cited sources
- [ ] SECURITY.md with threat model
- [ ] Capture protocol guide
- [ ] Changelog of all phases
- [ ] Final findings table (F01–F44)
- [ ] Case-study write-up

## Phase 8 — OpenCap knee-angle validation (optional)
- [ ] Verify a side-on camera exists in the OpenCap data
- [ ] Validate peak knee flexion (and hip sagittal excursion) against its marker data
- [ ] Extend the reliability model to knee angles
- [ ] Update the model card
- [ ] Sit-to-stand / 30-second chair stand against OpenCap sit-to-stand data
