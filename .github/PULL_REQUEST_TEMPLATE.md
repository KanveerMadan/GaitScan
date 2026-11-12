## What and why
<!-- One logical change. Link the issue or audit finding (Fixes #…, F03). -->

## How it was checked
- [ ] Tests were written first and failed before the change (bug fixes and features)
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` pass
- [ ] API change: `contracts/openapi.json` regenerated (`uv run python tests/test_contract.py --write`)
- [ ] Measurement change: golden file regenerated and the reason given; `make evaluate` re-run if
      the walk's results can change
- [ ] Database change: a new Alembic migration that works on SQLite and Postgres

## Anything a reviewer should know
<!-- Trade-offs, follow-ups, what wasn't tested. Never paste tokens, videos or personal data. -->
