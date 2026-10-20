# GaitScan Rebuild — Progress

Plan: [REBUILD_PLAN_V3.md](REBUILD_PLAN_V3.md). Full history of Phases 0–2 is in git and `phase-reports/`.

- Current phase: **3 — Honest results + new measurements** (not started)
- Done: Phase 0 (merged to main), Phase 1 (pushed, not merged), Phase 2 (`rebuild/phase-2-measurement`, pushed, stacked on Phase 1)
- Phase 3 tasks done: none
- Next task: confirm the pipeline supports multiple passes, a second test type and a treadmill speed (refactor if not); then OpenCap data download + `make evaluate`
- Blockers / human actions:
  - Phase 1 PRs open (#2 in both repos): GitHub CI green; Vercel preview builds fail (VITE_API_BASE_URL for Preview?). Nothing deployed (DB backup required before migration 0003)
  - hip_sagittal_excursion hidden from API/PDF/UI (CONDITIONAL); still computed for the Phase 3 check
  - No protocol-conforming real clip yet (walk01 is rejected: no complete step)
  - OpenCap lab data licence/README to be confirmed at download (stop and report if no sagittal comparison is possible)
