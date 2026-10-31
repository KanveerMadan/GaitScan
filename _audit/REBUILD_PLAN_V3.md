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

## Phase 3.2 — Reliability engine: done (learned model evaluated, not shipped)
- [x] [M] Degradation curves on LJMU (resolution, fps, compression, low light, camera yaw/roll): how each gait metric's error grows (evaluation/results/degradation_*; yaw = the simultaneous 45 deg clips)
- [x] [M] Learned reliability model: per-clip expected error / reject (gradient boosting or small MLP, conformal intervals), leave-participant-out evaluation (negative result: Spearman 0.11 with real error, rejecting the worst-predicted 20% doesn't reduce large errors; evaluation/results/reliability.json)
- [ ] [M] Ship it in the app: learned ± error next to each metric, learned rejections with reasons (not shipped: the model doesn't beat a constant range; the LJMU range stays)
- [x] [S] arXiv-style write-up (docs/reliability-engine.md)

## Phase 3.5 — Design foundation (before any Phase 4 UI): done (frontend #12)
- [x] [M] Design direction
- [x] [M] Design system: color, typography, spacing tokens, light/dark themes
- [x] [M] Tailwind + shadcn/ui (Radix)
- [x] [M] App shell: navigation and layout
- [x] [M] Migrate existing screens into the shell
- [x] [M] Use design-taste-frontend, frontend-design-toolkit, web-design-guidelines; no generic template look (design-taste-frontend and web-design-guidelines used; frontend-design-toolkit not yet)
- [ ] [M] All Phase 4–5 screens built with this system (ongoing rule)

## Phase 4 — Usability + app features
- [x] [M] Non-blocking analysis: FastAPI background task + status endpoint + polling (no Redis/Celery)
- [ ] [M] In-browser recording with live framing guidance (MediaPipe Tasks for Web, same pinned model; analysis server-side) (framing guidance done: /setup; recording blocked: MediaRecorder frame timing must be checked on real phones)
- [x] [M] Guided first-test onboarding (setup steps + demo + recording) (recording step waits with the item above)
- [x] [M] Personal dashboard: latest results, trends, last test date
- [x] [M] Session comparison: side by side, overlaid knee curves, "real change" vs "within measurement error" (vs same-session repeatability from LJMU; day-to-day variation stated as unknown)
- [x] [M] Session notes/tags
- [x] [M] Split App.jsx per ADR-008 with a typed API client (contract + generated types, drift-checked in both CIs)
- [x] [M] One Playwright e2e test of the main flow, in CI
- [x] [S] Demo mode (sample video, no signup; synthetic or explicitly consented clip) (/demo: the simulated walker's result)
- [ ] [S] Visual explanations: keyframes with skeleton + heel strikes, knee curve with gait cycles, offending frame on rejection (server-rendered images, no video stored) (cut for time; the knee curve per stride is shown)
- [ ] [S] Knee-angle curve with a published normative band (blocked: no verified normative band yet; knee itself awaits Phase 8)
- [ ] [S] Ghost replay: today's walk overlaid on a past session as skeletons, aligned by gait cycle (DTW), differences highlighted (needs per-frame landmarks stored: a privacy decision for the owner)
- [x] [S] Installable PWA (manifest; no service worker on purpose)
- [ ] [S] Goals with progress tracking (cut for time)
- [x] [S] k6 or Locust load test (capacity in the terminal summary) (loadtest/: local 150 users 117 req/s p95 55 ms, collapse by 300 (DB pool < threadpool); analysis ~1 s per s of video)
- [ ] [C] "Analysis done" notification
- [ ] [C] Profile settings: height, units, language, dark mode
- [ ] [C] Timeline search/filters
- [ ] [C] Treadmill mode (user-entered speed)

## Phase 5 — Accounts, sharing, privacy
- [ ] [M] Transactional email (provider justified in the terminal summary; secrets via env) (blocked: needs the owner's provider account and key; mailer interface + console backend ready)
- [x] [M] Password reset with expiring single-use tokens (503 with a reason until a provider is set)
- [x] [M] Email verification (closes F12) (built; F12's generic sign-up waits for the provider)
- [x] [M] Consent screen before first analysis
- [x] [M] Privacy center: export data, delete sessions, delete account
- [x] [M] Patient name on PDF (F40)
- [ ] [S] Professional inbox (shared reports, comments; access-control tests) (cut for time)
- [x] [S] Expiring, revocable, read-only share links (random token, 7-day default, no personal data in URL), with tests
- [ ] [S] Re-test reminders (user schedule, easy unsubscribe) (blocked: email provider)
- [ ] [C] Sign in with Google (cut; also needs OAuth credentials)
- [ ] [C] Multiple adult profiles per account, blocking under-18 profiles (cut)
- [ ] [C] Hindi UI strings (cut)
- [x] [M] Re-run every audit probe; F01–F44 each closed or explicitly accepted (probes: _audit/probes/out_*_phase5.txt; status in REBUILD_PROGRESS.md)

## Phase 6 — Frontend redesign & polish (frontend #15)
- [x] [M] Production-quality redesign of every screen (Phase 3.5 design system on every screen; Phase 6 landing, phone layout, icons)
- [x] [M] Landing page
- [x] [M] Mobile-first responsive layouts (Playwright: no sideways scroll at 360 px on any screen; section links on screen)
- [ ] [M] Loading, empty, error states everywhere (loading skeleton for lazy screens, errors shown with messages; not audited screen by screen)
- [x] [M] WCAG AA (axe WCAG 2.1 A/AA: no serious or critical issues on every screen, light and dark, in CI; Lighthouse accessibility 100. No manual screen-reader pass)
- [x] [M] Lighthouse 90+ (code splitting, image optimization) (mobile landing: 97 / 100 / 100 / 100; first load 808 -> 333 kB)
- [x] [M] Use the design skills; no generic template look (design-taste-frontend, web-design-guidelines)
- [ ] [S] Skeletons, transitions, micro-interactions
- [ ] [S] Consistent chart styling
- [x] [S] Branding: logo, favicon, app icons (Phosphor walking figure on the app's teal; maskable icon)
- [x] [S] Consistent copy (filming tips match the backend's capture tip; accuracy figures read from the API)
- [ ] [C] Visual regression screenshots in CI (cut)

## Phase 7 — Documentation (backend docs PR, frontend #16; Learn pages in frontend #15)
- [x] README and setup (both repos; .env.example now lists MAIL_BACKEND and FRONTEND_URL)
- [x] Architecture docs and ADR updates (docs/architecture.md: as-built table per ADR)
- [x] Model card / "Accuracy & Limitations" page (from `make evaluate`) + evaluate instructions (docs/model-card.md)
- [x] Learn pages per metric with cited sources (frontend /learn; DOIs checked)
- [x] SECURITY.md with threat model
- [x] Capture protocol guide (docs/capture-protocol.md)
- [x] Changelog of all phases (CHANGELOG.md)
- [x] Final findings table (F01–F44) (docs/findings.md)
- [x] Case-study write-up (docs/case-study.md)

## Phase 8 — OpenCap knee-angle validation (optional; knee items scrapped by the owner 2026-10-31: no OpenCap download, and the only open alternative found, Zenodo 19720803, has no video, only YOLOv8n keypoints, so it can't check MediaPipe's knee)
- [ ] Verify a side-on camera exists in the OpenCap data
- [ ] Validate peak knee flexion (and hip sagittal excursion) against its marker data
- [ ] Extend the reliability model to knee angles
- [ ] Update the model card
- [ ] Sit-to-stand / 30-second chair stand against OpenCap sit-to-stand data
- [ ] Isolate which #18 change (step-sized steadiness window vs dropped stretches) raised the share of accepted degraded LJMU runs more than 5 steps/min off from 4.0% to 6.0%: cache the degraded landmarks (degrade.py), then score each change alone (trade-off accepted by the owner 2026-10-28)

## Phase 9 — Owner requests (2026-10-31)
Decisions: no email (no domain, and Render's free tier blocks SMTP); knee validation scrapped; all cut features back in; the owner reviews Hindi strings and sets up Google OAuth; ghost replay stores one averaged stride, not per-frame landmarks.
- [ ] [M] Recovery codes replace emailed reset links (8 single-use codes, hashed, shown once; reset = email + code); email verification removed; F12 stays accepted (no email channel)
- [ ] [M] Re-test reminders without email: repeating .ics calendar file + "next test due" on the dashboard
- [ ] [M] Ghost replay: one averaged stride per session (pelvis-centred, leg-length-scaled, 101 points; no face/hands, no absolute position), deleted with the session, in the export, consent text v2 (users re-consent)
- [ ] [M] Google sign-in (ID token, client ID only; link to an existing account only when Google says the email is verified) (needs the owner's OAuth client ID)
- [ ] [M] In-browser recording (the owner tests on a phone)
- [ ] [M] Phase 6 leftovers: loading/empty/error states audited per screen, skeletons and transitions, consistent chart styling
- [ ] [M] Per-foot heel strikes robust to left/right swaps (ship only if LJMU improves), then stride time
- [ ] [S] Goals with progress tracking
- [ ] [S] Professional inbox (shared reports, comments; access-control tests)
- [ ] [S] Treadmill mode with a user-entered speed (labelled not yet validated: no treadmill clips)
- [ ] [S] "Analysis done" notification (browser notification, no push server)
- [ ] [S] Profile settings: height, units, language, dark mode
- [ ] [S] Timeline search and filters
- [ ] [S] Multiple adult profiles per account, under-18 profiles blocked (self-declared birth year)
- [ ] [S] Hindi UI strings (the owner reviews before release)
- [ ] [ ] Reference norms by age and sex: waiting on the owner's decision

