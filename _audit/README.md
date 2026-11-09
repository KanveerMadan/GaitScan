# Audit trail

The technical audit that started the rebuild, the plans that followed it, and the evidence for each
phase. Kept as a record: the code and `docs/` describe the current system, this folder explains how it
got there.

| Path | What it is |
|---|---|
| `GAITSCAN_AUDIT.md` | The audit: findings F01–F44 (resolution table in [docs/findings.md](../docs/findings.md)) |
| `FUNDAMENTALS_REVIEW.md` | Review of the measurement fundamentals that led to Plan V3 |
| `REBUILD_PLAN_V3.md` | **The current plan**, phase by phase, with what is done and what is open |
| `REBUILD_PLAN.md`, `REBUILD_PLAN_V2_PROPOSAL.md` | Earlier plans, superseded by V3; kept for the record |
| `REBUILD_PROGRESS.md` | Progress log of the early phases |
| `adr/` | Architecture decision records (ADR-001 to ADR-008) |
| `phase-reports/` | Test and probe output captured at the end of each phase |
| `probes/` | Scripts that probed the API and the pipeline, with their output (`out_*.txt`) |
| `tests/` | The audit's measurement specification; `tests/test_audit_spec.py` must stay a byte-identical copy |

`_audit/sandbox/` (local only, never committed) holds datasets, landmarks and derived video.
