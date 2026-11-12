# Case study: rebuilding GaitScan around honest numbers

## Where it started
GaitScan began as a demo: upload a walking video, get a "risk score", findings, an activity label
and exercise suggestions written by an LLM. A technical audit (`_audit/GAITSCAN_AUDIT.md`) found 44
problems, and the most serious ones were about the numbers themselves.

**Numbers:**
- Cadence counted one knee crossing 155° on one leg. A simulated walker at 110 steps/min read
  **54.1** (F24).
- Angles were computed on normalised coordinates, so the picture's aspect ratio bent them: a true
  121.9° read 91.1° (F25).
- The risk score was an invented sum of thresholds. Six degraded versions of a clip all scored 0, and
  a simulated 60% loss of knee range scored as "minor findings" (F23).
- Nothing had ever been checked against ground truth (F22).

**Security and privacy:**
- The JWT secret was committed, sessions and PDFs had no auth, and anyone could register as a
  clinician (F01–F03).
- Plaintext passwords were printed to logs (F04).
- There was no consent, retention or deletion (F06).

**Architecture:**
- A CPU-bound pipeline inside `async def` stalled the whole server for **28.7 s** per analysis
  (F13).

## Approach
The rebuild was planned in phases (`_audit/REBUILD_PLAN_V3.md`), each on its own branch and PR,
with a few rules held throughout:
- Tests are written first and committed failing.
- Thresholds change only with evidence from labelled data.
- No number is shown without its error range, or a "not yet validated" label.
- AI-assisted ground truth is labelled as such.

1. **Stop the bleeding (Phase 0).** Secrets from the environment, auth and ownership checks,
   generic errors, measurement wording instead of diagnosis. The audit's security probe went from
   0/15 to 11/15.
2. **Foundations (Phase 1).** Lockfile, Docker, Alembic, structured logging, rate limits keyed on a
   spoof-resistant client IP, CRA → Vite.
3. **Measure correctly (Phase 2).** A framework-free `gaitcore` package:
   - pixel-space angles and visibility masking without filling;
   - steady-pass detection;
   - recording checks that turn a video down with a reason instead of guessing.

   The composite score, symmetry indices, activity labels and LLM text were removed.
4. **Find out how good it is (Phases 3, 3.2).** `make evaluate` on a public dataset, then
   degradation curves and an attempt at a learned per-clip error model.
5. **Make it usable and safe to keep data (Phases 4–6).**
   - Non-blocking analysis, a typed client from the OpenAPI contract, and a design system.
   - Consent, export and deletion, and share links.
   - Accessibility and phone-width checks in CI.

## Key decisions
**Cadence without leg labels.** MediaPipe swaps left and right legs for a frame or two at a time. In
the clips whose cadence read 136–158 steps/min, about 10–12% of consecutive frames were swapped.
Cadence from per-foot heel strikes inherited every swap. The distance between the heels along the
walking direction can't change when labels swap, and it peaks once per step. Timing those peaks
dropped the cadence error on 27 hand-checked clips from a mean of 12.0 to 1.6 steps/min.

**Checks chosen on data, not intuition.** Three checks were set on LJMU clips (Topham et al. 2023,
CC BY 4.0), with the threshold, accuracy and trade-off recorded next to each in
`gaitcore/quality.py`:
- the side-on test (do the ankle and shoulder paths converge?);
- `legs_not_tracked`;
- the step-regularity limit.

**Ground truth, labelled honestly.**
- LJMU has video but no heel-strike labels, so references came from blind visual counts on contact
  sheets of the original frames, cross-checked against an independent pose model (RTMPose).
- Disagreements over 5 steps/min were settled by eye. These are labelled "AI-annotated +
  cross-checked" everywhere they appear.
- Some of those checks found the reference wrong, not the pipeline.

**Ship the negative result.** A gradient-boosted, conformally calibrated model of per-clip error
reached its coverage, but it ranked clips by real error barely better than chance. It wasn't
shipped; the app shows the constant LJMU range.

**Use the real recordings.** Three phone videos exposed what LJMU didn't:
- **Slow walkers lost steps.** A fixed half-second smoothing window cut their passes into pieces too
  short to hold a step.
- **One stray stretch rejected a whole video.** A second person, or feet out of frame, for a few
  seconds was enough.

Both rules were changed only after testing them together on the phone clips and every cached LJMU
clip:
- the window is now one of the walker's own steps;
- the bad stretches are dropped instead of the whole video.

## Results
| | Before | After |
|---|---|---|
| Cadence on the simulated 110 steps/min walker | 54.1 | 109.6 (golden file; 90 and 125 steps/min read 89.9 and 124.5) |
| Cadence error on LJMU (97 accepted side-view clips, 57 adults) | not measured | MAE 1.56, 95% within ±4.5 steps/min; 21 held-out test clips: 95% within ±2.75 |
| Step time error on LJMU | not measured | 95% within ±0.024 s |
| Phone clips (visual count, AI-annotated: 85.1 / ~101 / 88.3) | 84.7 / 101.9 / turned down | 85.0 / 98.8 / 89.9 |
| Server responsiveness during an analysis (`/status`) | 28.7 s | 0.03 s |
| Audit security probe | 0/15 | 15/16 (the open item, account enumeration, waits for an email provider) |
| Tests | 0 | ~300 backend, ~70 frontend unit, Playwright e2e + axe |
| Frontend first load | 808 kB | 333 kB |
| Lighthouse (mobile, landing) | — | 97 / 100 / 100 / 100 |

## What didn't work
- **Per-foot heel strikes robust to label swaps.** A continuity fix passed the synthetic swaps but
  not LJMU, where labels follow position; 37 of 110 legs read one step as a stride. Stride time stays
  withheld.
- **Padding the steady window** to keep edge steps gained one clip but made the error worse; not
  changed.
- **The learned reliability model** (above).

## What's left
- **Step length, walking speed and the treadmill test** stay "not yet validated" for good: no more
  video will be collected (owner decision 2026-11-12). **Knee angle was removed** the same day:
  OpenCap (Phase 8), its only route to a reference, was cancelled.
- **The step-regularity limit and heel-visibility handling** were chosen on lab video and need
  checking on more phone recordings.
- **Accounts:** email delivery (password reset, verified sign-up, which closes account enumeration)
  needs a provider account.

More: [model card](model-card.md) · [architecture](architecture.md) · [findings](findings.md) ·
[changelog](../CHANGELOG.md).
