# Phase 0 — Stop the bleeding: report

**Status: done** · 2026-09-27
Backend branch `rebuild/phase-0-stop-the-bleeding` (17 commits on `origin/main` 38c8db3). Frontend branch `rebuild/phase-0-stop-the-bleeding` (5 commits on `origin/main` be64af4). Nothing was pushed, merged or deployed.

## Summary

- **Auth and secrets:** the JWT secret now comes from `JWT_SECRET`. The app **fails closed**: `ENV` defaults to production, which refuses to start with a missing, placeholder or short secret, or without `CORS_ORIGINS`. Tokens last 12 h instead of 365 days.
- **Access control:** `/sessions/{id}` and `/report/{id}` now require a token and only serve the owner or a linked clinician. Everyone else gets 404; anonymous requests get 401.
- **Removed:** self-assigned clinician roles, `/debug/links`, the password `print`, the CORS wildcard, and public `/docs` in production.
- **Uploads:** the extension check is case-insensitive, with a 100 MB cap. Unreadable video gets a 422 with a user-facing message. Unexpected errors return a generic 500 with a reference ID. The raw video is always deleted (`finally`), and the full-skeleton CSV is no longer written. Job IDs are full UUIDs.
- **Robustness:** matplotlib uses `Agg`. All PDF text is escaped, so a `<` in LLM text no longer crashes the analysis.
- **Framing:** all diagnostic, injury, fall-risk and "prescribed" wording is replaced with measurement wording in the API, PDF and UI.
  - The risk score is gone from the UI and PDF; the API still returns the number until Phase 2 (ADR-005).
  - A not-a-medical-device disclaimer is shown on every screen and in the PDF.
  - Rows stored before this phase are served with the new wording.
- **LLM:** Groq exercise explanations are opt-in and off by default, so no health data leaves the server unless enabled.
- **Frontend auth hygiene:**
  - It no longer stores the plaintext password, and it purges any copy saved by earlier versions.
  - It no longer logs the token, and the role picker is gone.
  - It downloads PDFs with an authenticated request and signs out on a 401.
- **Scoring logic is numerically unchanged.** I verified identical scores and statuses in 144 combinations, and identical exercise selection in 80.

## Acceptance criteria (REBUILD_PLAN D6 Phase 0)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Security probe PASS for F01–F05, F08–F09 checks (rate limiting and enumeration may still FAIL) | **PASS** | Probe v2 on old vs new code: **0/15 → 11/15 PASS**. Every F01, F02, F03, F04, F06/F07, F08 (token lifetime + CORS) and F09 check passes. F05 is frontend-only and is covered by jest tests 1–3. Remaining FAILs: F12 enumeration and F10 rate limiting (both allowed), F15 PDF-regen mode (Phase 3), F40 patient name (Phase 6). See below. |
| 2 | `grep -riE "abnormal\|injury\|damage\|prescri\|risk score" src ../gaitscan-frontend/src` returns nothing user-facing | **PASS** | The only hits are the identifier `get_exercise_prescription` (`exercise_prescription.py:251`, `main.py:21,107`), which D1 deletes in Phase 2. Beyond grep, `tests/test_language.py` AST-scans **every string literal** in `src/` with a broader pattern, and checks every API response, including legacy DB rows. |
| 3 | App still analyses `walk01.mp4` end to end | **PASS (locally)** | In-process probe: `200 _alice_analyze job_id_len=36 summary='Within reference ranges'`. Real uvicorn in production mode: `analyze: success 36 Within reference ranges`. **Not verified on Render**, since deploying is your action (see verification steps). |
| — | Full test suites pass | **PASS** | Backend 73 passed; frontend 11 passed (below) |
| — | Both apps build and start locally | **PASS** | uvicorn (dev and production mode) serves `/status` 200. CRA dev server "Compiled successfully!". `CI=true react-scripts build` is clean (Vercel treats warnings as errors). |
| — | Production refuses to start with a missing/default secret | **PASS** | `ENV` unset + no secret → `RuntimeError: JWT_SECRET is missing…`, exit 1. Placeholder `change-me` → same, exit 1. No `CORS_ORIGINS` → `RuntimeError: CORS_ORIGINS must list…`, exit 1. The error never echoes the value (`test_error_message_never_echoes_secret_value`). |

Non-negotiables landed this phase:
- JWT from env with the default rejected;
- auth + ownership on session and report endpoints, with A-cannot-read-B and anonymous-gets-401 tests;
- no self-assigned clinician;
- `/debug/links` deleted;
- password print removed;
- no password in `localStorage` and no token logging;
- CORS restricted; `/docs` off in production; no stack traces or internal detail to clients;
- `gaitscan.db` untracked (it was already deleted on `origin/main` by your commit 38c8db3; history cleanup commands below);
- `Agg` set;
- PDF escaping;
- case-insensitive upload check with a size limit;
- risk score removed from UI and PDF;
- diagnostic wording replaced in backend and frontend;
- not-a-medical-device disclaimer;
- `.gitignore` hardened in both repos.

Deferred per plan:
- content sniffing and duration limits (Phase 3 worker);
- removing the score from the API (Phase 2);
- unused/vulnerable dependency cleanup (Phase 1);
- CI, pre-commit, Docker, README (Phase 1+).

## Test output

**Backend: before the fixes** (tests committed first in `2c115ad`, run against 38c8db3 code, `_audit/phase-reports/phase0_tests_before.txt`):
```
66 failed, 7 passed, 17 warnings in 9.64s
```
The 7 passing guard existing behaviour: the owner and linked clinician can read, the own-list filter, `.txt` rejected, and a foreign-signed token rejected.

**Backend: after** (`env -u MPLBACKEND`, which proves the in-code `Agg` fix holds in-process):
```
73 passed, 17 warnings in 9.44s
```
The 17 warnings are pre-existing deprecations (FastAPI `on_event`, SQLAlchemy `declarative_base`, `datetime.utcnow`), handled in Phase 1.

**Frontend: before** (tests committed first in `1ae4331`, run against the unfixed App):
```
Tests:       11 failed, 11 total
```
**Frontend: after**:
```
  ✓ login never stores the password in the browser
  ✓ purges plaintext credentials saved by earlier versions
  ✓ registration offers no role choice and sends no role
  ✓ never logs the bearer token
  ✓ shows the not-a-medical-device disclaimer before and after sign-in
  ✓ upload screen gives the capture protocol, not 'any angle'
  ✓ results show a measurement summary without a risk score
  ✓ report download is an authenticated request
  ✓ history shows no risk score
  ✓ clinician dashboard shows no risk score or attention flag
  ✓ an expired session (401) signs the user out
Tests:       11 passed, 11 total
```

**Audit spec tests** (`_audit/tests/test_angles_audit.py`, unmodified) against the new code: `7 failed, 11 passed`. This is unchanged from the audit, as expected: none of these is fixed until Phase 2, so none were ported yet.

**Security probe v2, same script run against old and new code** (`_audit/phase-reports/phase0_security_probe.txt`):
```
===== before (38c8db3)                                        ===== after (phase-0 branch)
FAIL F03 register_self_assign_clinician  201 role=clinician   PASS  201 role=patient
FAIL F04 plaintext_password_logged       'PASSWORD RECEIVED'  PASS  []
FAIL F12 email_enumeration_via_register  409                  FAIL  409                (Phase 4)
     _alice_analyze job_id_len=8 'No issues detected'              job_id_len=36 'Within reference ranges'
FAIL F02 GET /sessions/{id} no auth      200 findings=4       PASS  401
FAIL F02 GET /report/{id} no auth        200 PDF 617220 B     PASS  401
FAIL F01 forged JWT impersonates email   200 alice            PASS  401 Invalid or expired token
FAIL F01 forged JWT reads session list   200 n=1              PASS  401
FAIL F03 /debug/links leaks links        [{clinician 3, pt 2}] PASS 404
FAIL F08 token lifetime > 1 day          365.0 days           PASS  0.5 days
FAIL F06/F07 non-video left on disk      data/raw/4710569a.mp4 PASS []
FAIL F09 internal detail to client       500 "Cannot open video: data/raw/…"  PASS 422 "We couldn't read this file as a video…"
FAIL F08 CORS allows arbitrary origins   *                    PASS  None
FAIL F15 regenerated PDF wrong mode      Runner→Clinical      FAIL  Runner→Clinical    (Phase 3)
FAIL F40 patient name absent from PDF    absent               FAIL  absent             (Phase 6)
FAIL F10 no login rate limiting          [401]×30             FAIL  [401]×30           (Phase 4)
SUMMARY: 0/15 PASS                                            SUMMARY: 11/15 PASS
```
Other probes (`concurrency_probe.py`, `profile_pipeline.py`, `stability.py`, `view_dependency.py`) test Phase 2/3 behaviour and were not re-run. Pipeline numerics are unchanged by construction (scoring-equivalence check above).

## Diffstat

**Backend** (`38c8db3..HEAD`, excluding `_audit/`): 25 files changed, **+1076 / −360**
```
.env.example 28  .gitignore 24  main.py (deleted, was 0 B)  requirements-dev.txt 3
src/api/auth_router.py 6  src/api/clinician_router.py 17  src/api/main.py 199
src/core/activity_classifier.py 9  src/core/auth.py 13  src/core/config.py 63 (new)
src/core/exercise_prescription.py 123  src/core/extract_landmarks.py 7
src/core/legacy_display.py 54 (new)  src/core/report_generator.py 161  src/core/risk_scoring.py 183
src/utils/visualise.py 4  tests/* 542 (new; tests/test_angles.py deleted, was 0 B)
```
A final commit adds `_audit/` docs, probes and reports (see progress file).

**Frontend** (`be64af4..HEAD`): 3 files changed, **+327 / −157** (`.gitignore` 16, `src/App.js` 271, `src/App.test.js` 197)

## Human actions required

Do these **in this order**. The backend now refuses to start without the new env vars, so step 1 must happen before the backend deploy.

**1. Set Render environment variables (web service → Environment).** Names only:
- `JWT_SECRET`: generate locally with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` and paste it. Never commit it.
- `CORS_ORIGINS`: your Vercel production origin (the README lists `https://gaitscan-frontend-mnt9.vercel.app`), comma-separated with any custom domain. Vercel preview URLs won't be allowed unless you add them.
- `ENV`: leave unset or set to `production`. **Never** set `dev` on Render (it enables `/docs` and an ephemeral secret).
- Optional: `ACCESS_TOKEN_MINUTES` (default 720), `MAX_UPLOAD_MB` (default 100).
- Leave `ENABLE_LLM_EXPLANATIONS` unset. `GROQ_API_KEY` can be deleted.
- Delete any old `SECRET_KEY` / `JWT_SECRET_KEY` vars; the code never read them.

**2. Secret rotation.** Setting the new `JWT_SECRET` *is* the rotation. Every token signed with the committed values stops working, and all users are signed out once (the frontend handles the 401). Treat the committed values as public forever, and never reuse them.

**3. Push branches and open PRs** (I didn't push):
```
cd ~/Desktop/gaitscan           && git push -u origin rebuild/phase-0-stop-the-bleeding
cd ~/Desktop/gaitscan-frontend  && git push -u origin rebuild/phase-0-stop-the-bleeding
```

**4. Deploy order: frontend first, then backend immediately after.** The new frontend works against the old backend: it sends an auth header the old report endpoint ignores, and sends no role. The old frontend's plain report links would 401 against the new backend. In the gap, the old backend's labels (e.g. "Serious abnormality") can still show in the new UI, so keep the gap short.

**5. Review clinician accounts in the production DB.** Anyone could self-register as a clinician until now. In the Render Postgres shell (`psql "$DATABASE_URL"`):
```sql
SELECT id, email, full_name, created_at FROM users WHERE role = 'clinician' ORDER BY created_at;
-- demote everyone you don't recognise:
UPDATE users SET role = 'patient' WHERE role = 'clinician' AND email NOT IN ('you@example.com');
-- promote a real clinician (the only way to create one now):
UPDATE users SET role = 'clinician' WHERE email = 'real.clinician@example.com';
```

**6. Passwords already logged.** Every registration on the old code printed the plaintext password to Render logs. Delete or let expire whatever log retention allows. If any real users exist, tell them to change their password anywhere they reused it. There is no password-change endpoint yet (Phase 4), so for now only a new account or a DB-side reset is possible.

**7. Git history cleanup** (optional but recommended; this rewrites every commit hash, so do it **after** merging the phase-0 PRs and tell any collaborators). It removes the old DB, the curl artifacts, the 3 committed PDF reports (derived from your own walking video) and the committed secret literals:
```bash
pip install git-filter-repo
git clone --mirror https://github.com/KanveerMadan/GaitScan.git gaitscan-mirror && cd gaitscan-mirror
# 1) drop files from all history
git filter-repo --invert-paths --path gaitscan.db --path=-d --path=-H --path-glob 'outputs/*'
# 2) redact the four historical JWT secret values. Find them with:
#      git log -p -S SECRET_KEY -- src/core/auth.py
#    then create secrets.txt with one line per value, e.g.   <old value>==>REDACTED
git filter-repo --replace-text ../secrets.txt
git push --force --mirror
```
Afterwards, re-clone locally. `_audit/probes/api_security_probe.py` reads the leaked value from commit `38c8db3` and will need the new hash of that commit (or will stop finding the value at all, which is the goal).

**8. Local `main` diverges from `origin/main`.** It holds `5f34703` (the same `-H`/`-d` deletion your GitHub commits made). When ready: `git checkout main && git reset --hard origin/main` (your call; I didn't touch it). Your staged README edit is identical to `origin/main`'s README, so nothing is lost.

**9. Verify after deploying** (read-only checks against production):
```bash
API=https://gaitscan.onrender.com
curl -s -o /dev/null -w "docs %{http_code}\n" $API/docs                 # expect 404
curl -s -o /dev/null -w "openapi %{http_code}\n" $API/openapi.json      # expect 404
curl -sI -H "Origin: https://evil.example" $API/status | grep -i access-control || echo "no CORS header (good)"
curl -s -o /dev/null -w "session %{http_code}\n" $API/sessions/any-id   # expect 401
curl -s -o /dev/null -w "report %{http_code}\n" $API/report/any-id      # expect 401
curl -s -o /dev/null -w "debug %{http_code}\n" $API/debug/links         # expect 404
```
Then in the browser: sign in, upload a clip, download the PDF (and check it opens with the disclaimer at the top). In DevTools, check that `localStorage` has no `gaitscan_creds` and the console has no token. Register a throwaway account and confirm its password is **not** in the Render logs.

## Deviations from plan

1. **Branch base:** branched from `origin/main`, not local `main`. Local `main` had diverged (see action 8), and `origin/main` already contains your README, `.env.example` and `gaitscan.db` deletion.
2. **`.env.example` variable name:** your file used `SECRET_KEY`; the plan and code use `JWT_SECRET`. I renamed it and documented all variables.
3. **Test tooling pulled forward:** added `requirements-dev.txt` (`pytest==9.1.1`) and replaced the failing CRA boilerplate test, both Phase 1 items. The tests-before-fixes rule needs a runnable suite now. No CI or linters were added (still Phase 1).
4. **Added to Phase 0 because no phase owned them:** the `Agg` backend (F19, a non-negotiable) and 12 h token expiry with sign-out on 401. The acceptance criteria require the F08 token-lifetime check to pass; refresh tokens stay in Phase 4.
5. **New `src/core/legacy_display.py`:** not in the plan. Without it, sessions already in the production DB would keep serving "Serious abnormality…" and LLM injury text. It is a regex translation layer marked `ponytail:`, to delete once legacy rows are re-analysed or purged.
6. **LLM made opt-in** rather than removed. The Phase 0 copy task says "LLM off by default"; ADR-007 removal stays later.
7. **Risk score still in the API** (`overall_risk_score`, stored and returned) but not displayed anywhere. Removing it from the API is Phase 2 per ADR-005. Status colours (red for "outside range") are unchanged until then too.
8. **Security probe edited to v2** so one script runs against both code versions:
   - env configured before import;
   - the clinician promoted through the DB;
   - PDF checks fetched as the owner;
   - the error-leak check now looks for internal details (path, "Cannot open", traceback) instead of counting every 500 as a leak;
   - a CORS check added.

   The "before" column was re-run with v2 against the old code and still shows 15/15 FAIL, so the comparison is fair. The probe also no longer contains the leaked secret; it reads it from git history.
9. **`tests/test_language.py`** (my new test, not an audit test) exempts exactly one string: the `DISCLAIMER` constant, which must say the tool "does not diagnose".
10. **Test-output redaction:** my first `docs(audit)` commit (`bee2a0f`) included `phase0_tests_before.txt`, which contains pytest failure reprs of bearer tokens for throwaway test users. They were signed with a random per-run secret from `tests/conftest.py` that was never persisted, so they authorize nothing anywhere. A follow-up commit redacts them. I did not amend `bee2a0f` (no history rewrites), so the tokens remain in that unpushed commit; squash-merging the PR drops them from `main`.
11. **Audit report redaction:** removed the literal historical secret values from `_audit/GAITSCAN_AUDIT.md` (F01 evidence row) so no secret value is committed.
12. **Not done, and still planned:**
    - `runtime.txt` stays until the Docker switch in Phase 1, since Render may still read it.
    - The frontend's `.env.example` (`REACT_APP_API_URL`) is still unused; the env-configured URL comes with Vite in Phase 1.
    - Activity "Confidence %" is still displayed; the classifier is removed in Phase 2.
    - Threshold contradictions across UI/PDF/scoring (F35) are Phase 2.

**Disagreement worth flagging:** the audit plan's Phase 0 acceptance allows the F12/F10 FAILs, which is fine. But F15 (the regenerated PDF silently says "Clinical Mode" for a Runner session) is a correctness bug users hit after every Render deploy. It's a one-column fix (store `mode`), but it needs a schema change, and the plan puts migrations in Phase 1 (Alembic). I left it for Phase 3 as planned. Consider pulling "persist mode" into Phase 1 right after the Alembic baseline.

## Review guide (riskiest parts)

1. `src/core/config.py:34-60`: fail-closed startup. A wrong or missing env var on Render **will stop the service from booting**. Confirm this is the behaviour you want (I think it is), and do human action 1 first.
2. `src/api/main.py:202-214` (`get_visible_session`): the entire authorization model for sessions and reports. Check the clinician-link condition, the `user_id is None` legacy case (fails closed → 404), and that 404 (not 403) is acceptable.
3. `src/api/main.py:62-199` (`/analyze` + `save_upload`): the `try/except/finally` flow. Check that the video is deleted on every path, the `succeeded` flag controls the output cleanup, and HTTPExceptions raised inside keep their status codes.
4. `src/core/legacy_display.py:15-31`: the regex replaces stored text containing words like "risk", "fall", "doctor" or "healthy". It can over-replace benign legacy sentences with a generic `"<metric>: <value>."`. That's acceptable for display, but check it matches your intent.
5. `../gaitscan-frontend/src/App.js:11-26, 53-92`: `downloadReport` (blob download, error alert) and `AuthProvider` (synchronous header, credential purge, 401 interceptor). The interceptor also fires on a failed login (401 when no user is signed in), which is a harmless no-op, but worth knowing.
