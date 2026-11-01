# Contributing

Thanks for helping. Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md). Security
problems go through private reporting ([SECURITY.md](SECURITY.md)), not public issues.

## Getting set up
Python 3.11 and [uv](https://docs.astral.sh/uv/); the README's "Run it locally" gets the API running.
`make help` lists the everyday commands.

## Workflow
- Open an issue first for anything larger than a small fix (templates: bug report, feature request).
- Branch from `main`; one logical change per PR; PRs merge only with green CI.
- [Conventional Commits](https://www.conventionalcommits.org/): `feat(api): …`, `fix(pdf): …`,
  `test: …`, `build: …`, `docs: …`. Reference audit finding IDs in the body (`Fixes F03`).
- Bug fixes and features start with a failing test, committed before the change; never weaken an
  existing test to make a change pass.
- Measurement thresholds change only with evidence from a labelled dataset (`make evaluate`), and the
  data behind each threshold is written next to it in the code.
- A pull request fills in the template; `CODEOWNERS` requests the maintainer's review.
- Never commit videos, `.db` files, `.env` files or anything under `_audit/sandbox/`. Test fixtures
  are synthetic (see `tests/synthetic.py`); never use a recording of a real person.

## Checks (run by pre-commit and CI)
```bash
uv run pre-commit install          # once; needs git >= 2.35
uv run ruff check . && uv run ruff format --check .
uv run mypy                        # strict on gaitcore/, default on app/
uv run pytest
make check                         # all of the above
```
`_audit/tests/` is the audit's specification for the Phase 2 measurement fixes. Do not edit, skip
or loosen those tests; port them into `tests/` when the phase that fixes them lands.

## Database changes
Change `app/db/models.py`, then add a migration:
```bash
uv run alembic revision --autogenerate -m "short description"
```
Review the generated file by hand (autogenerate misses renames and server defaults), keep it
working on SQLite (`op.batch_alter_table`) and Postgres, and run `uv run pytest tests/test_migrations.py`
with `TEST_POSTGRES_URL` set. Never edit a migration that has been deployed.

## Dependencies
Add with `uv add <pkg>` (or `uv add --dev`), commit `pyproject.toml` and `uv.lock` together. CI runs
`pip-audit`; any new ignore needs a written reason and an expiry.

## Language
User-facing text describes **measurements**, never diagnoses, injury risk or treatment
(`tests/test_language.py` enforces the banned-word list).
