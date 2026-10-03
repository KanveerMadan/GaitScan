# ADR-004: Clinic-scoped multi-tenancy; patients are records, not accounts

**Status:** Proposed · **Date:** 2026-09-27

## Context
Users choose their own role (F03). There is no organisation entity. Patients must self-register and upload themselves, while clinicians cannot upload. The JWT secret is public (F01), tokens last 365 days, and endpoints lack ownership checks (F02).

## Decision
- Entities: `Organization` (clinic/academy) → `Membership(user, org, role ∈ {owner, practitioner})` → `Patient` (belongs to org; name, DOB/age, sex, height, consent records). `Session`/`Analysis` belong to a `Patient` and are created by a practitioner.
- **Patients do not log in in v1.** Patient-facing sharing, if needed later, uses a revocable, expiring share link.
- Auth: email + password (bcrypt via `bcrypt` directly, or `pwdlib`), **PyJWT** (replacing unmaintained python-jose), 15-min access token, refresh token in an httpOnly Secure SameSite cookie, secret from env with startup failure if missing. Owners invite practitioners by email token. Roles are never client-supplied.
- Authorization lives in one dependency, `get_org_scope()`. Every query filters by `org_id`, with tests asserting cross-org access returns 404.
- An `audit_log(actor, org, action, object, at)` row is written on patient view, report download, export and delete.

## Consequences
- Matches how clinics work: a physio records in the clinic.
- A clean boundary for DPDP: the clinic is the fiduciary, GaitScan the processor.
- Existing patient-accounts and invite codes become obsolete, so migrate or retire (there is little real data to preserve; verify in prod DB).
- A managed provider (Clerk/Supabase Auth) was rejected for now: an extra vendor handling health-adjacent identity, and owning the auth flow is interview-explainable. Revisit if SSO is needed.
