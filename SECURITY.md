# Security

GaitScan handles health-adjacent personal data: videos of people walking (deleted after analysis),
the measurements derived from them, and account details. This page states what is protected, how,
and what is knowingly left open.

## Reporting a vulnerability
Use GitHub's private vulnerability reporting on this repository (Security → Report a
vulnerability). Please don't open a public issue. Expect an acknowledgement within a week; this is
a one-person project.

## What is protected
| Asset | Where it lives | Protection |
|---|---|---|
| Walking video | A temp file in `data/raw/` during one analysis | Deleted in a `finally:` block whatever happens (`app/api/analysis.py`); never stored, never sent to a third party |
| Measurements (session results) | Postgres `sessions.result` | Readable only by the owner and a clinician the owner linked to; exportable and deletable by the owner |
| Account (email, name, password hash) | Postgres `users` | bcrypt hashes; no plaintext password is stored or logged |
| Consent records | Postgres `consents` | Versioned; an analysis is refused (403) without current consent |
| Share links | Postgres `share_links` | Only a SHA-256 hash of the token is stored; read-only, one session, 7 days by default (1–30), revocable |
| Recovery codes | Postgres `recovery_codes` | 8 per account, 80 random bits each, single-use, only the SHA-256 stored; shown once |
| Comments on sessions | Postgres `session_comments` | Readable and writable only by the session's owner and a linked clinician (others get 404); deleted with the session or the author's account; in the export |
| Other people on an account (profiles) | Postgres `profiles` | Name and birth year only, adults only; owner-only (others get 404); a linked clinician never sees their sessions; deleting a profile deletes its sessions |
| Google sign-in | No Google token is stored | The ID token is verified against Google's keys and `GOOGLE_CLIENT_ID`; an existing account is linked only when Google says the email is verified |
| Reset / verification links (unused: no email is sent) | Postgres `auth_tokens` | Hashed, single-use, expiring (reset: 30 minutes) |

## Threat model
Attackers considered: an anonymous internet user; a signed-in user trying to reach someone else's
data; someone holding a leaked link or token; a hostile upload. Out of scope: a compromised Render or
Vercel account, a compromised developer machine, and physical access to a user's unlocked device.

| Threat | Control | Test / evidence |
|---|---|---|
| Forged or stolen-secret JWTs | `JWT_SECRET` only from the environment; startup fails without one of ≥ 32 characters or with a placeholder; the historical committed secrets are treated as public | `tests/test_config.py`; audit probe F01 (`_audit/probes/out_api_security_phase5.txt`) |
| Reading another user's sessions, reports or shares | Every session, report and share route checks ownership or an explicit clinician link | `tests/test_access_control.py`; probe F02 |
| Self-promotion to clinician | Role is never taken from the client; clinicians are promoted by an admin | probe F03 |
| Password guessing | 10-character minimum; sliding-window limits: 5 failures per email / 15 min, 20 attempts per IP / 5 min; equal-cost login for unknown emails | `tests/test_auth_hardening.py`; probe F10 |
| Recovery-code guessing | 80-bit codes; 5 attempts per email and 20 per client per 15 min; a used code or a new set ends every earlier login | `tests/test_recovery_codes.py` |
| Long-lived stolen tokens | 12-hour access tokens; changing or resetting the password ends every earlier login (`iat` checked against `password_changed_at`) | `tests/test_account_email.py` |
| Leaked share link | Random 256-bit token, hash stored, expiry, revocation, no personal data in the URL (the token is in the fragment, not sent to servers or in Referer), 60 opens per IP per hour | `tests/test_share_links.py` |
| Invite-code guessing | `secrets`-generated codes, 7-day expiry, 10 joins per IP per 15 min | `tests/test_invites.py` |
| Hostile upload | Extension allow-list (case-insensitive), streamed with a size cap (`MAX_UPLOAD_MB`, 100 MB), opened with OpenCV before the pose model runs; unreadable files get a generic 422 | probe F06/F07 |
| Information leaks through errors | Generic 500s with a reference ID; detail only in server logs; `/docs` only when `ENV=dev` | probe F09 |
| Cross-origin requests | CORS allow-list from `CORS_ORIGINS`; required outside dev | probe F08 |
| Secrets in logs | JSON logs with redaction; SQL parameters hidden; `print` banned by lint; Sentry sends no request bodies or personal data | `tests/test_observability.py` |
| Secrets in git | `detect-secrets` pre-commit hook with a baseline; `.env` ignored | `.pre-commit-config.yaml` |
| Vulnerable dependencies | `uv.lock`; `pip-audit` (backend) and `npm audit` (frontend) in CI; Dependabot | `.github/workflows/ci.yml` in both repos |
| Spoofed client IP evading limits | The client address comes from the edge header (`CLIENT_IP_HEADER`) or a fixed proxy-hop count, never the client-written part of `X-Forwarded-For` | `app/core/ratelimit.py` docstring; `tests/test_client_ip.py` |
| One analysis starving the server | Analyses run as a background task, one at a time per process; `/status` answered in ≤ 0.03 s during an analysis | probe F13 (`out_concurrency_phase5.txt`); `tests/test_memory.py` (peak RSS ≤ 420 MB) |

## Known gaps (accepted for now)
- **Account enumeration at sign-up (F12).** Registration says when an email is taken. Closing it needs
  verified sign-up by email, and GaitScan sends no email (no domain; Render's free tier blocks SMTP).
  Sign-up is rate-limited per client.
- **No recovery without the password or a code.** Password recovery uses recovery codes instead of
  email. Someone who loses both can't get back in; the app says so when it shows the codes.
- **Token in `localStorage` (part of F05).** An XSS bug would expose the access token. Mitigations:
  no third-party scripts, React escaping, 12-hour tokens. Moving to an httpOnly cookie needs CSRF
  protection and a same-site API domain.
- **No scheduled retention purge (part of F06).** Results are kept until the user deletes them
  (privacy center: delete sessions or the whole account, export everything).
- **Rate limits live in process memory.** They are correct for the current single worker and instance,
  but reset on restart and would not be shared across instances.
- **No per-user analysis quota.** Analyses are serialised, so a user submitting many long videos
  delays others; uploads are size-capped, not duration-capped.
- **Render free-tier cold start (F21)** of ~40 s; the app's polling and timeouts tolerate it.

The full audit, with all 44 findings and how each was closed or accepted, is in
[docs/findings.md](docs/findings.md).
