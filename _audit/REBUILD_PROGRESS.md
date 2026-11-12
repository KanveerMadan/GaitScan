# GaitScan Rebuild — Progress

Plan: [REBUILD_PLAN_V3.md](REBUILD_PLAN_V3.md). Full history of each phase is in git, `phase-reports/` and [CHANGELOG.md](../CHANGELOG.md).

**State on 2026-11-12: Phases 0–7, 9 and 10 are built and in `main` on both repositories (backend on Render `gaitscan-api`, frontend on Vercel). Phase 8 is cancelled. No item is data-blocked any more: no more video will be collected, so those items are closed (owner decisions 2026-11-12, recorded at the top of the plan).**

- Backend PRs merged to main: #1, #2 (Phases 0–1), #10 (Phase 2), #11 rate limits, #12 deps, #13 CI smoke, #14 (Phase 3), #20 (Phase 3.2; #15 had merged into the stacked Phase 3 branch), #16 (Phase 4), #17 (Phase 5), #18 real-world gates, #21 scipy out (Phase 7 docs reached main with it; #19 closed, nothing to merge), #22–#23 (Phase 9: recovery codes, walking figure), #24 reminders, #33 the rest of Phases 9–10 (stack #25–#31), #34 analysis job logs
- Frontend PRs merged to main: #1, #2, #10, #11 (Phase 3), #12 (Phase 3.5), #14 (Phase 5, carried Phase 4 after #13 closed), #15 (Phase 6), #16 (Phase 7), #19–#20 (Phase 9: recovery codes, experience), #21 settings, #32 the rest of Phases 9–10 (stack #22–#31, which remain open with no new commits), #33 sign-up autofill fix, #34 analysis survives navigation and never waits forever
- Measurements: cadence ±4.5 steps/min, step time ±0.024 s (LJMU, Topham et al. 2023, CC BY 4.0; MDC95 4.6 steps/min). Step length and walking speed (floor calibration only) and every treadmill value stay "not yet validated" for good. Stride time and hip excursion are withheld; knee angle was removed on 2026-11-12 (migration 0013 deleted it from stored results)
- Cadence reference (2026-11-12): optional sex and birth year (settings) and sex (profiles); the app shows Mobbs et al. 2025 (Sensors 25(2):581, CC BY 4.0) mean ± 1 SD for that sex and age group, groups with at least 10 people only, with the source
- Google sign-in configured (GOOGLE_CLIENT_ID / VITE_GOOGLE_CLIENT_ID); 2026-11-12 review: never signs in to a password account (pre-hijacking), case-insensitive addresses, token must have exp and sub
- Memory: CI peak 386 MB for a 1080p 60 fps 10 s clip (Render limit 512 MB); each job logs `analysis started/ended` with wait and run time (#34)
- Findings F01–F44: all closed or accepted. Accepted: F05 part (token in localStorage), F06 part (no scheduled purge; the Privacy page says data stays until deleted), F12 (enumeration: no email channel), F21 (cold start; an external uptime check calls GET /healthz every 10 minutes, one SELECT 1), F40 part (clinicians can't upload)
- Accepted trade-offs: #18's degraded-video share > 5 steps/min off 4.0% → 6.0%; the learned reliability model not shipped (no retry); visual explanations, step-timing breakdown and visual regression CI cut
- Licence: MIT (both repositories, 2026-11-12)
- Open for the owner: review the Hindi draft text; try in-browser recording on a phone; Dependabot PRs (backend #3–#9, #32; frontend #3, #4, #7–#9, #17, #18, #28); close the leftover frontend stack PRs #22–#31
