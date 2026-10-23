# GaitScan Rebuild — Progress

Plan: [REBUILD_PLAN_V3.md](REBUILD_PLAN_V3.md). Full history of Phases 0–2 is in git and `phase-reports/`.

- Done and deployed: Phase 0 + Phase 1 merged to main (#1, #2); backend on Render `gaitscan-api`, frontend on Vercel
- Merged since: #11 per-IP rate limits keyed on CLIENT_IP_HEADER (Render: True-Client-IP), #12 pillow 13.0.0 / certifi 2026.10.19
- Phase 2: `rebuild/phase-2-measurement`, draft PR #10, not merged (origin/main merged in 2026-10-23)
- Current phase: **2 — LJMU check of the quality gates** (Topham et al. 2023, CC BY 4.0), then Phase 3
- LJMU gates done: path-convergence side-view check + view_unconfirmed; duplicate pose = one person; legs_not_tracked (>= 4 s steady, < 6 steps)
- Cadence/step time now label-free (heel-separation peaks); per-leg values hidden with a note when labelled step CV > 0.2
  - 27 AI-annotated + cross-checked clips: MAE 12.0 -> 2.1 steps/min; held-out 60 clips / 34 participants vs RTMPose: 8.1 -> 2.7
- Next task: decide label-free step-CV gate (proposal 0.15) and per-foot labels under brief flips (xfail), then Phase 3
- Blockers / human actions:
  - hip_sagittal_excursion hidden from API/PDF/UI (CONDITIONAL); still computed for the Phase 3 check
  - No protocol-conforming real clip yet (walk01 is rejected: no complete step)
  - Dependabot PRs #7–#9 open, untriaged
