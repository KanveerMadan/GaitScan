# Phase 1 — Foundations: report

Branches: backend `rebuild/phase-1-foundations`, frontend `rebuild/phase-1-foundations`, both **stacked on
the unmerged `rebuild/phase-0-stop-the-bleeding`** (checked 2026-10-03: Phase 0 is not in `origin/main`
in either repo). **Nothing pushed:** both GitHub repos are public, see Human action 1.

## Summary

Phase 1 is complete locally. Both repos now have reproducible builds, lint, type checks, tests, CI
definitions and pre-commit hooks. The backend is two packages, `gaitcore/` (strict mypy) and `app/`. It
has a Docker image that migrates and then serves, a Render Blueprint, and Alembic migrations proven
against real legacy `create_all` databases on SQLite and Postgres. The frontend moved from CRA to Vite +
Vitest + TypeScript (`allowJs`). npm advisories went from 48 to 0, and Python advisories from 40 to 2
(protobuf, pinned by mediapipe, ignored in CI with a Phase 2 expiry). Analysis output is unchanged: the
golden test passes, and the walk01 output is byte-identical to Phase 0 in all four modes.

The security probe went from 11/16 to **14/16 PASS** (F10 rate limiting, F15 mode on PDF regeneration,
password policy). The two expected FAILs are F12 enumeration (mitigated; closure is Phase 4) and F40
(Phase 6).

Work this session found and fixed four latent bugs:
- **Production could not have started on Postgres.** SQLAlchemy 2.1 maps `postgresql://` to psycopg 3,
  but only psycopg2 was installed.
- **Bcrypt password hashes reached the JSON logs** through SQLAlchemy exception text. Fixed with
  `hide_parameters=True`.
- **The baseline migration would have silently kept two historical schema drifts** that `create_all`
  never fixed: no `sessions.user_id`, and a native-enum `users.role`.
- **Per-IP rate limits would have bucketed every user behind Render's proxy together.** uvicorn's
  `--proxy-headers` would instead have let clients choose their own bucket.

Two acceptance criteria need you: CI green on a PR, and Render deploying the image.

## Acceptance criteria

Plan (REBUILD_PLAN D6 Phase 1) and the additional instructions for this session:

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | CI green on a PR | **BLOCKED (human)** | Not pushed (public repos, action 1). Every CI step was run locally and passes: ruff + format + mypy + pytest on SQLite and Postgres 16 + pip-audit (with the 2 documented ignores), and `docker build`. Frontend: eslint, prettier, tsc, vitest, build, `npm audit --omit=dev --audit-level=high`. Workflow and Dependabot files validate against the GitHub JSON schemas (`check-jsonschema`). |
| 2 | `docker build && docker run` serves the API locally | **PASS** | `phase1_docker_e2e.txt`: image run against `postgres:16` seeded with the oldest legacy schema. Alembic `0001→0002`, `/healthz` 200, `/docs` 404, all 6 tables' rows kept, `users.role` converted to varchar, register 201, `/auth/me` 200, `/analyze` reaches MediaPipe (synthetic blank clip → 400 "Could not detect a person"), spoofed-XFF login limit 429 at attempt 21 while another client gets 401, 0 error lines, 0 bcrypt hashes in logs. |
| 3 | Render deploys the Docker image | **BLOCKED (human)** | `render.yaml` validates against `https://render.com/schema/render.yaml.json`. Deploying is yours (actions 3–6). |
| 4 | Golden test identical to pre-refactor | **PASS** | `tests/test_golden.py` passes (synthetic landmarks). Local uncommitted check on walk01: Phase 0 `src/` vs Phase 1 `gaitcore/` JSON output for all 4 modes is **byte-identical** (`cmp`), 488 frames, mediapipe 0.10.9 in both. |
| 5 | `pip-audit` and `npm audit --omit=dev`: 0 high/critical | **npm PASS · pip PARTIAL** | npm: 48 → **0** (all deps and runtime). pip: 40 → **2**, both protobuf 3.20.3 (PYSEC-2026-1805/1806, parsing DoS on untrusted input). Unfixable while mediapipe 0.10.9 pins `protobuf<4`; we parse only MediaPipe's bundled model. Ignored in CI only, with the expiry "remove in Phase 2 with the mediapipe upgrade" (`.github/workflows/ci.yml`), and Dependabot holds mediapipe/protobuf. `phase1_pip_audit.txt`. |
| 6 | 429 after the limit | **PASS** | `test_auth_hardening.py` (email, IP and registration limits) and probe F10 `[401, 429]`. |
| 7 | Equal-cost unknown-email login | **PASS** | `test_unknown_email_login_costs_a_bcrypt_verification` (dummy hash at `app/api/auth.py:14,89`). |
| 8 | Mode round-trips through PDF regeneration | **PASS** | `test_report_mode.py`; probe F15 PASS (`'Runner' in pdf=True`). |
| 9 | Password ≥ 10 on register/change; legacy short password still logs in | **PASS** | `test_auth_hardening.py` (7 tests); frontend tests for the hint and the change-password form. |
| 10 | Rate-limit client IP: proxy users not bucketed together; spoofed XFF can't bypass | **PASS (assumption to verify)** | `tests/test_client_ip.py` (5 tests, incl. end-to-end) and the Docker run. Trust assumption documented in `app/core/ratelimit.py:1-30`. Render's behaviour is **not in Render's docs**, see action 7. |
| 11 | mypy strict on `gaitcore/`, no blanket ignores, no `Any` to silence errors | **PASS** | `uv run mypy`: no issues in 26 files. Ignores: **gaitcore 1** (`gaitcore/landmarks.py:4`, `[import-untyped]`, mediapipe has no stubs), **app 0**, tests 0. `ignore_missing_imports` removed (stubs added for reportlab and scipy). |
| 12 | Start sequence runs `alembic upgrade head` before uvicorn | **PASS** | `Dockerfile:37`; seen in the Docker run log. |
| 13 | Migration test on a legacy `create_all` DB with rows in every table | **PASS** | `tests/test_migrations.py::test_upgrade_keeps_every_row_and_column_of_a_create_all_database`, 2 legacy shapes × SQLite/Postgres: every row and value kept, schema diff empty, new rows insertable. |
| 14 | Docker image run against a Postgres container | **PASS** | See #2. |
| 15 | Protobuf CI ignore with a documented expiry, not hidden elsewhere | **PASS** | Only in `.github/workflows/ci.yml` (comment + 2 `--ignore-vuln`). |
| 16 | Pre-commit: ruff + mypy (backend), eslint + prettier (frontend) | **PASS** | `pre-commit run --all-files` passes in both (also runs detect-secrets in the backend). Needs git ≥ 2.35 (action 10). |
| 17 | `.env.example` in both repos; accurate README with capture protocol | **PASS** | Backend README: side view, landscape, full body, one person, 3–4 m from a ≥5 m walkway, ≥10 s, no turns. The distance is marked as an unvalidated guideline. |
| 18 | Both apps build and start locally | **PASS** | Backend: Docker run above and the test client. Frontend: `npm run build`, `vite preview` serving the bundle (title GaitScan, API URL baked in), `vite` dev server 200. |

## Test output

Full files are in `_audit/phase-reports/`: `phase1_tests_after.txt`, `phase1_fe_tests_after.txt`,
`phase1_security_probe.txt`, `phase1_docker_e2e.txt`, `phase1_pip_audit.txt`.

**Backend** (start of session: 104 passed, 1 skipped, the Postgres test skipped):
```
$ TEST_POSTGRES_URL=postgresql://…@localhost:55432/gaitscan_test uv run pytest -q
119 passed in 52.43s
$ uv run pytest -q _audit/tests        # audit spec, unchanged since Phase 0; Phase 2 fixes these
7 failed, 11 passed                    # same 7 as before Phase 1
$ uv run ruff check . && uv run ruff format --check . && uv run mypy
All checks passed! · 47 files already formatted · Success: no issues found in 26 source files
```

**Frontend** (start: 11 passed under react-scripts/Jest):
```
$ npx vitest run      Tests  18 passed (18)     # the 11 Phase 0 specs unchanged + 7 new
$ npx eslint . --max-warnings 0 → 0 problems · prettier: all formatted · tsc --noEmit: ok
```

**Security probe v3**, same script on Phase 0 code (`_audit/.venv`) and Phase 1 code (project venv):
```
check                                               phase-0  phase-1
F12 1-character password accepted at registration   FAIL     PASS (422)
F03 register_self_assign_clinician                  PASS     PASS
F04 plaintext_password_logged (stdout + stderr)     PASS     PASS
F12 email_enumeration_via_register                  FAIL     FAIL  (409 generic text; residual until Phase 4)
F02 ×2, F01 ×2, F03 /debug/links, F08 ×2, F06/F07, F09   PASS     PASS
F15 regenerated PDF reports wrong mode              FAIL     PASS
F40 patient name absent from PDF                    FAIL     FAIL  (Phase 6)
F10 no login rate limiting (30 bad attempts)        FAIL     PASS  ([401, 429])
SUMMARY                                             11/16    14/16
```
Probe changes from v2 to v3 are listed in the script docstring. Every v2 pass/fail criterion is kept;
the role check and the password check are now separate so neither masks the other. Other probes
(`concurrency`, `profile_pipeline`, `stability`, `view_dependency`, `signal_analysis`) measure
Phase 2/3 behaviour and were not re-run.

## Diffstat

Measured against the Phase 0 branch:
- **Backend:** 41 commits (18 of them from the earlier session), plus this report commit.
  - In total: 87 files changed, +10,882 / −1,841.
  - Excluding `uv.lock` and `_audit/`: 77 files, +9,316 / −1,815.
  - Most of that is the `src/` → `app/` + `gaitcore/` move, which counts as additions plus deletions.
- **Frontend:** 8 commits.
  - In total: 26 files, +5,693 / −17,568.
  - Excluding `package-lock.json`: 25 files, +2,447 / −1,219. Most of that is Prettier reformatting `App.jsx`.

<details><summary>Backend commits this session (after <code>b063d73</code>)</summary>

```
9b2a713 test: failing test for clinician session list when the patient row is missing
4eb8129 fix(clinician): 404 instead of 500 when a linked patient row is missing
d16de70 refactor(db): SQLAlchemy 2.0 DeclarativeBase with typed Mapped columns
024e5c8 build(types): mypy strict on gaitcore, default checking on app
d792c67 fix(logging): route remaining print() calls through logging; lint bans print
99a88f8 build: pre-commit hooks for ruff, ruff format, mypy and detect-secrets
7eedc3e fix(pre-commit): honour ruff excludes when hooks pass explicit filenames
36eb5bb test: failing tests for proxy-aware, spoof-resistant client IP (F10)
e294b21 fix(ratelimit): derive client IP from trusted proxy hops, not the socket peer
77ccbe2 test: failing tests for /healthz
b282fb8 feat(api): /healthz checks database connectivity for the Render health check
e0ee698 test: failing test for the Postgres driver SQLAlchemy 2.1 selects
7edd884 fix(deps): use psycopg 3, the driver SQLAlchemy 2.1 picks for postgresql://
ee1208b test: upgrade a real create_all database with rows in every table
89afcf8 fix(db): baseline reconciles legacy create_all drift when adopting tables
4d45898 test: failing test for bound parameters (password hashes) in DB error text
a2fd9aa fix(logging): hide SQL bound parameters from exceptions and logs
26ec903 test: legacy fixture advances Postgres sequences; upgraded DB must accept new rows
abd6785 build(docker): slim non-root image that migrates, then serves one uvicorn worker
b90ffdf build(render): Blueprint for the Docker web service with /healthz
5f3d886 ci: lint, typecheck, test on SQLite+Postgres, pip-audit, docker build; Dependabot
7ddc49b docs: accurate README with capture protocol, CONTRIBUTING, architecture, env vars
c43d05c docs(audit): security probe v3 for the app/ layout; Phase 1 evidence
```
</details>

## Human actions required

Do these in order. All commands are copy-pasteable. Values in `<angle brackets>` are yours to fill in.

**1. Decide how to publish. Both repos are PUBLIC.** The phase branches contain `_audit/`, which
describes exploitable holes that are **still live in production** until Phase 0 is deployed: forging
JWTs with the four committed secrets, and unauthenticated session/report reads. Pushing these branches
publishes that write-up. Recommended:
- deploy first (steps 3–6), using a private fork or making the repo private while CI runs;
- or push the branches without `_audit/` until production is fixed.

If you accept the risk, push as-is:
```bash
cd ~/Desktop/gaitscan          && git push -u origin rebuild/phase-0-stop-the-bleeding rebuild/phase-1-foundations
cd ~/Desktop/gaitscan-frontend && git push -u origin rebuild/phase-0-stop-the-bleeding rebuild/phase-1-foundations
```
Then open PRs: Phase 0 → `main`, and Phase 1 → `rebuild/phase-0-stop-the-bleeding` (retarget to `main`
after Phase 0 merges). CI runs on PRs. **Acceptance #1 = both CI workflows green.**

**2. Check whether production uses SQLite or Postgres.** Render dashboard → the API service →
**Environment**: is `DATABASE_URL` set?
- Not set: the pre-Phase-1 code silently used SQLite on the instance's ephemeral disk, and every
  deploy or restart wiped it. Nothing survives to back up. Go to 2a.
- Set: confirm it is Postgres without printing the credentials. Service → **Shell**:
  `echo "${DATABASE_URL%%:*}"`. Expect `postgres` or `postgresql`. Go to 2b.

**2a. Provision Postgres** (only if it isn't already). Render → New → **Postgres**, in the same
region as the API (Free tier databases expire after 30 days; use a paid plan for real data). Copy its
**Internal Database URL** into the API service's `DATABASE_URL`.

**2b. Back up production before the first Alembic run.** On your machine, using the database's
**External Database URL** (Render → the database → Connect):
```bash
export PROD_DB='<external database url>'        # don't paste it into files or shell history you keep
pg_dump --format=custom --no-owner --no-privileges "$PROD_DB" -f gaitscan-prod-$(date +%F).dump
pg_restore --list gaitscan-prod-$(date +%F).dump | grep -c "TABLE DATA"   # expect 6
psql "$PROD_DB" -c '\d users' -c '\d sessions'   # note role's type and whether user_id exists
```
Optional rehearsal: restore the dump into a local Postgres and run the image against it. This is the
same check I ran with synthetic data:
```bash
docker run -d --name prod-copy -e POSTGRES_PASSWORD=local -p 55433:5432 postgres:16-alpine
sleep 5 && pg_restore --no-owner -d postgresql://postgres:local@localhost:55433/postgres gaitscan-prod-$(date +%F).dump
docker build -t gaitscan-api ~/Desktop/gaitscan
docker run --rm -p 18001:8000 -e ENV=production -e JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e CORS_ORIGINS=http://localhost:3000 -e DATABASE_URL=postgresql://postgres:local@host.docker.internal:55433/postgres gaitscan-api
# expect "Running upgrade -> 0001" and "0001 -> 0002", then: curl localhost:18001/healthz → {"status":"ok"}
docker rm -f prod-copy && rm gaitscan-prod-*.dump   # the dump holds health data: delete it when done
```

**3. Vercel (frontend).** Project → Settings → Environment Variables, for both **Production** and
**Preview**:
- `VITE_API_BASE_URL` = `https://gaitscan.onrender.com` (or the new service URL from step 4);
- optionally `VITE_SENTRY_DSN`.

Builds now **fail** without `VITE_API_BASE_URL`, deliberately. The framework preset should be Vite
(output `dist`), not Create React App. Change it under Settings → Build & Development if Vercel
doesn't detect it.

**4. Render (backend): switch to Docker.** Render may not let an existing native-Python service change
runtime in place. Try Settings first. If it isn't offered:
- create a new service from the Blueprint (New → Blueprint → this repo; it reads `render.yaml`);
- move any custom domain, or point `VITE_API_BASE_URL` at the new URL.

Environment for the API service:

| Variable | Value |
|---|---|
| `ENV` | `production` |
| `JWT_SECRET` | new: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` (this rotates it; everyone is signed out once) |
| `CORS_ORIGINS` | `https://gaitscan-frontend-mnt9.vercel.app` plus any custom domain |
| `DATABASE_URL` | Internal URL from step 2 |
| `TRUSTED_PROXY_HOPS` | `2` (step 7 verifies it) |
| `SENTRY_DSN` | optional |

Leave `ENABLE_LLM_EXPLANATIONS` false.

**5. Deploy order when Phase 0 and Phase 1 ship together:**
1. Backup done (2b) and env vars set (3, 4).
2. Merge the frontend PRs (Phase 0, then Phase 1). Vercel deploys. The new UI works against the old
   API: change-password simply 404s there, and other calls are compatible.
3. Merge the backend PRs (Phase 0, then Phase 1) **immediately after**. Render builds the image; the
   container runs `alembic upgrade head` (adopting the existing tables, `0001`, then `0002`) and only
   then starts uvicorn. If migration fails, the container exits and the old one keeps serving. Read the
   deploy log before retrying.
4. Run the Phase 0 report's checks (its action 9), plus `curl -s https://<api>/healthz`, which should
   return `{"status":"ok"}`.
5. Then do Phase 0's actions 5 (clinician review) and 6 (logged passwords). Phase 1 adds a
   change-password form, so users can now rotate passwords themselves.

**6. After deploy:** delete the old `GROQ_API_KEY`, `SECRET_KEY` and `JWT_SECRET_KEY` vars if they're
still there. Keep the Phase 0 history cleanup (its action 7) for after merging.

**7. Verify the rate-limit client IP on Render.** This needs a deploy, which is why it falls to you.
I could not confirm Render's header behaviour from Render's own docs. The only evidence is second-hand:
[a GitHub issue](https://github.com/FullmetalBober/Indexterity/issues/574) and
[a PR](https://github.com/DarshanPotnis/CollabEditor/pull/6) report that requests arrive from a 10.x
peer with `X-Forwarded-For: <client>, <Cloudflare edge>`. The run below sends 22 failed logins with a
rotating forged leftmost XFF; the limit is 20 per IP per 5 min:
```bash
API=https://<your api host>
for i in $(seq 1 22); do curl -s -o /dev/null -w '%{http_code} ' $API/auth/login -H 'content-type: application/json' \
  -H "X-Forwarded-For: 10.9.$i.1" -d "{\"email\":\"rl-check-$i@example.com\",\"password\":\"wrong-password-x\"}"; done; echo
```

| What you see | Meaning | Action |
|---|---|---|
| 20× `401`, then `429 429`; then from a **different network** (e.g. phone hotspot) one login gives `401` | Correct | None |
| No `429` at all | `TRUSTED_PROXY_HOPS` too high (reads a client-written entry) | Set `1`, redeploy, wait 5 min, re-run |
| `429` also from the other network | Too low (everyone shares a proxy address) | Raise by 1 and re-run |

Wait 5 minutes between runs, since the window has to expire.

**8. Sentry (optional):** create backend and frontend projects, then set `SENTRY_DSN` (Render) and
`VITE_SENTRY_DSN` (Vercel). Both are off when unset.

**9. Local tooling on this Mac:**
- `/usr/local/bin/git` is **2.15 (2017)** and shadows Homebrew's 2.51 at `/opt/homebrew/bin/git`.
  pre-commit needs ≥ 2.35. Fix with `export PATH=/opt/homebrew/bin:$PATH` in `~/.zshrc`, or remove the
  old git. Then run `uv run pre-commit install` in the backend, and `pre-commit install` in the
  frontend (with pre-commit installed via `uv tool install pre-commit`).
- Node is 22.17. Some new tools want ≥ 22.22 (jsdom 30), so I pinned jsdom 29. Upgrading Node to the
  current 22.x LTS lets Dependabot move it.

**10. Clean-up I left for you.**
- A Postgres container is running locally: `docker rm -f gaitscan-pg-test`. I stopped the API test
  container.
- The `gaitscan-api:phase1` image can be deleted.
- Docker Desktop was started for this run.

## Deviations from plan

1. **`pydantic-settings` → a plain pydantic `BaseModel`** (earlier session). This avoids module-level
   global state conflicting with test isolation. It reads env vars the same way, with the same
   fail-closed rules. No new dependency.
2. **psycopg2 → psycopg 3.** Not in the plan, but required: SQLAlchemy 2.1, which the dependency bump
   brought in, maps `postgresql://` to psycopg 3, so production could not have started.
3. **`0001_baseline` edited after its first commit** to reconcile legacy drift. It was never deployed or
   pushed, so no database has run the old version.
4. **SQLAlchemy models converted to typed `Mapped[]`** (D1 lists `DeclarativeBase` for Phase 1). Column
   arguments are unchanged; the migration diff test proves the schema is identical.
5. **ADRs stay in `_audit/adr/`**, and `docs/architecture.md` links to them. The progress note said
   "move ADRs to docs/adr", but the plan and audit link to `_audit/adr/` by relative path, so moving
   would break those links.
6. **No `vercel.json`.** There's no client-side router yet (ADR-008 adds one), and Vercel detects Vite.
   It will be needed with React Router's SPA rewrites.
7. **Version pins against `@latest`:**
   - `typescript ~6.0`, because typescript-eslint doesn't support TS 7 yet;
   - `jsdom ^29`, because 30 needs Node ≥ 22.22 and this machine has 22.17.
8. **ESLint `react-hooks/set-state-in-effect` off**, with a reason, until data fetching moves to
   TanStack Query (ADR-008). Two silent `catch {}` blocks in the clinician dashboard got `ponytail:`
   comments rather than new UI. Error states are ADR-008 work (F39).
9. **Frontend pre-commit uses the `pre-commit` framework** (same as the backend) instead of
   husky/lint-staged, so no new npm dependencies.
10. **Plan task 6 ("security probe as tests")** is covered by `tests/test_access_control.py`,
    `test_auth*.py` and `test_client_ip.py`; the probe script itself stays in `_audit/probes/` (now v3).
11. **Rate limiter stays in-process** (`ponytail:` note in `ratelimit.py`). The image runs one uvicorn
    worker on one instance; scaling out needs Postgres/Redis-backed counts.
12. **Mistakes made and corrected this session** (no history rewritten):
    - I committed `99a88f8` (pre-commit) before noticing its ruff hooks ignored the excludes. Its first
      run reformatted `_audit/` and `alembic/versions/`, including the audit test spec. I restored those
      files to HEAD before any commit (`_audit/tests/test_angles_audit.py` is unchanged since Phase 0;
      verified with `git diff`), and fixed the hook in `7eedc3e`.
    - My first Docker e2e seed used explicit ids without advancing Postgres sequences, which caused a
      500 on register. That was a fixture artifact, not a migration bug. The fixture now mirrors
      production, and the migration test asserts new rows can be inserted (`26ec903`). The same run is
      what exposed the bcrypt-hash log leak.
13. **New findings (not in the audit), all fixed with a failing test first:**
    - Postgres driver mismatch (would have stopped production starting);
    - bcrypt hashes in error logs (F41 gap);
    - baseline drift reconciliation;
    - 500 on a missing linked patient (found by mypy);
    - FastAPI list-shaped `detail` crashing React (found while adding 429 handling).
14. **Remaining `print()` calls** (13 in `src/` per F41) were still present after the earlier F41
    commit. They now go through `logging`, and ruff `T20` bans new ones outside tests.

Findings closed in Phase 1: **F11** (npm fully; Python except the 2 protobuf advisories, expiry
Phase 2), **F15** (mode), **F16**, **F17**, **F38** (both repos have real suites), **F41**, **F10**.
F10 still needs the Render verification in action 7. Partial: **F12** (password policy and equal-cost
login done; enumeration residual until Phase 4 invite-only sign-up), **F39** (Vite, env-based API URL,
lint; router/split/typed client are ADR-008 work).

## Review guide (riskiest parts)

1. **`app/core/ratelimit.py:1-30, 72-82`** with **`render.yaml:22-23`** and **`Dockerfile:34-37`**. This
   is the client-IP trust model:
   - if `TRUSTED_PROXY_HOPS` is wrong by one, clients can either choose their own bucket or share one;
   - uvicorn's own proxy handling is deliberately off;
   - verify with action 7.
2. **`alembic/versions/0001_baseline.py:27-29, 125-141`**. The idempotent adoption plus
   `_reconcile_legacy_drift` runs against production data on the first deploy. Check:
   - that the FK name and `USING role::text` suit your Postgres;
   - that `DROP TYPE` only targets the enum the column used.

   `tests/legacy_schema.py` documents which commits produced which shapes.
3. **`Dockerfile:37`** (migrate-then-serve in `CMD`). A failing migration stops the container and the
   deploy. If you ever run more than one instance, both will try to migrate at once: move it to
   Render's pre-deploy command then (paid plans).
4. **`app/db/database.py:10`** (`hide_parameters=True`) and **`app/db/models.py`** (typed models). The
   former is security-relevant; the latter must stay schema-identical, and `test_migrations` enforces
   that.
5. **Frontend `vite.config.ts:7`** (the build fails without `VITE_API_BASE_URL`, so set it on Vercel
   first) and **`src/App.jsx:19-34`** (`errorMessage`, now on every error path).
