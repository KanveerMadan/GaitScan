# GaitScan Rebuild — Progress

Plan: [REBUILD_PLAN_V3.md](REBUILD_PLAN_V3.md). Full history of Phases 0–2 is in git and `phase-reports/`.

- Done and deployed: Phase 0 + Phase 1 merged to main (#1, #2); backend on Render `gaitscan-api`, frontend on Vercel
- Merged since: #11 per-IP rate limits keyed on CLIENT_IP_HEADER (Render: True-Client-IP), #12 pillow 13.0.0 / certifi 2026.10.19
- Phase 2: `rebuild/phase-2-measurement`, draft PR #10, not merged (origin/main merged in 2026-10-23)
- Current phase: **2 — LJMU check of the quality gates** (Topham et al. 2023, CC BY 4.0), then Phase 3
- Next task: LJMU discrepancies (0 steps on P1 E1 90°, None stride time / knee flexion), then side-view and multiple_people gates
- Blockers / human actions:
  - hip_sagittal_excursion hidden from API/PDF/UI (CONDITIONAL); still computed for the Phase 3 check
  - No protocol-conforming real clip yet (walk01 is rejected: no complete step)
  - Dependabot PRs #7–#9 open, untriaged
