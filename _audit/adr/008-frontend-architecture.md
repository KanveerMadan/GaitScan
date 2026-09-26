# ADR-008: Frontend — Vite + TypeScript + React Router + TanStack Query + generated API client

**Status:** Proposed · **Date:** 2026-09-27

## Context
The frontend is one 1,102-line `App.js` on Create React App (deprecated, 48 npm advisories). It has inline styles, a hardcoded API URL, no router (results are not linkable), swallowed errors shown as empty states, the plaintext password in `localStorage`, and no responsive layout or accessibility (F05, F39).

## Decision
- **Vite + TypeScript** (strict). CRA → Vite is a small, mechanical migration.
- **React Router**: `/login`, `/patients`, `/patients/:id`, `/patients/:id/sessions/:sid`, `/jobs/:id`.
- **TanStack Query** for server state (polling job status, cache, retries, error/empty/loading states). Only auth/session state goes in React context. No Redux.
- **Typed client generated from FastAPI's OpenAPI** with `openapi-typescript` + `openapi-fetch`, regenerated in CI; a CI check fails on drift.
- Styling: CSS Modules or Tailwind. Pick one and delete inline style objects gradually, page by page.
- `VITE_API_BASE_URL` per environment (Vercel preview/prod).
- Auth: access token in memory, refresh via httpOnly cookie (ADR-004). Nothing sensitive in `localStorage`.
- Tests: Vitest + Testing Library for the upload → poll → results flow with MSW mocks, plus a Playwright smoke test against staging (later).

## Consequences
- Contract drift between API and UI becomes a compile error.
- The migration can be incremental: move the existing screens into routes first, then refactor.
