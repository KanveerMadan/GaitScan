# GaitScan Rebuild — Progress

Plan: [REBUILD_PLAN_V3.md](REBUILD_PLAN_V3.md). Full history of Phases 0–2 is in git and `phase-reports/`.

- Done and deployed: Phase 0 + Phase 1 merged to main (#1, #2); backend on Render `gaitscan-api`, frontend on Vercel
- Merged since: #11 per-IP rate limits keyed on CLIENT_IP_HEADER (Render: True-Client-IP), #12 pillow 13.0.0 / certifi 2026.10.19
- Phase 2: `rebuild/phase-2-measurement`, draft PR #10, not merged (origin/main merged in 2026-10-23)
- Current phase: **2 — LJMU check of the quality gates** (Topham et al. 2023, CC BY 4.0), then Phase 3
- LJMU gates done: path-convergence side-view check + view_unconfirmed; duplicate pose = one person; legs_not_tracked (>= 4 s steady, < 6 steps); irregular_steps (label-free step CV > 0.15)
- Cadence/step time label-free (heel-separation peaks); per-leg knee hidden with a note when labelled step CV > 0.2; stride time withheld (Phase 3)
  - 27 AI-annotated + cross-checked clips: MAE 12.0 -> 1.6 steps/min (max 4.9); held-out 54 clips / 34 participants vs RTMPose: MAE 1.7 (max 5.4)
- Next task: review PR #10 (both repos, ready for review), then Phase 3
- Blockers / human actions:
  - hip_sagittal_excursion hidden from API/PDF/UI (CONDITIONAL); still computed for the Phase 3 check
  - No protocol-conforming real clip yet (walk01 is rejected: no complete step)
  - Dependabot PRs #7–#9 open, untriaged
