# Verdicts (Plan V3 Phase 11)

How a gait profile becomes a verdict: `gaitcore/norms/thresholds.py` (every constant), `gaitcore/norms/`
(the references), `gaitcore/verdict.py` (the rules) and `app/core/verdict_copy.py` (the words, English and
draft Hindi). The verdict is worked out each time a result is read, from the person's current sex and
birth year (Settings, or the profile of the person measured), so it never goes stale and no stored result
is rewritten. Shared links compare with all adults, so they reveal no age or sex.

## Positioning (owner decision D4)
For general wellness and information; GaitScan is not a medical device. The verdict says what to do next,
never what is wrong. No condition is named, the ruled-out words never appear (tested in English and
Hindi), and there's no screening, detection or referral language. Every verdict carries "Experimental
estimate from a phone video, not a medical assessment."

| Overall | Headline | Text |
|---|---|---|
| typical | Looks typical. | Your walk looks typical for the comparison group. |
| keep_an_eye | Worth keeping an eye on. | Slightly outside the typical range — worth re-testing in 2–4 weeks. |
| outside | Outside the typical range. | Outside the typical range. If you have concerns about your walking, a physiotherapist can assess it properly. |

## Metrics (owner decision D3)
**Key** (they decide the overall verdict): cadence, step-time variability (CV), peak knee flexion in swing,
knee range of motion, hip range of motion, peak hip extension. **Information** (value, typical range, no
level): knee and ankle at heel strike, peak hip flexion, ankle range, trunk lean, arm swing, stance,
swing, double support, and the Gait Profile Score. **Not shown:** pelvis oscillation (stored only), and
any left/right value or symmetry (leg identity can't be checked: docs/validation/leg-identity.md).

## References
| Metric | Reference | Kind |
|---|---|---|
| Cadence | Mobbs et al. 2025, *Sensors* 25(2):581, CC BY 4.0: Tables 4–5 by sex and 10-year age, Table 3 both sexes; all adults pooled from Table 3 | literature (chest-worn IMU) |
| All others | Healthy LJMU walkers measured by this app (Topham et al. 2023, CC BY 4.0): `gaitcore/norms/ljmu_references.json`, `make references` | same method |

A group is used only with ≥ 10 people. Fallbacks are said in the result: "No sex-specific reference;
compared with adults of your age." and (D8) "No age-specific reference for your age; compared with all
adults." Same-method groups: all adults, adults/women/men aged 18–40, adults aged 41–65 (LJMU has no one
over 65).

## Bands (owner decision D1, widened by its release gate)
- Same-method: typical within mean ± **2.5 SD**, slightly outside to **3.5 SD**, clearly outside beyond.
- Literature (cadence): the same, plus GaitScan's error (±4.5 steps/min), so a difference the app can't
  resolve never counts.
- Step-time variability is only "outside" when high.
- D1 proposed 2 / 3 SD. On healthy LJMU walkers that gave 34.5% "keep an eye on it", over the 25% gate.
  With six key metrics at 2 SD, about 26% is expected by chance alone. 2.25 SD gave 27.6%; **2.5 / 3.5
  gives 13.8% "keep an eye on it" and 0% "outside"** (29 participants judged, leave-one-participant-out).
  See `release_gate` in `ljmu_references.json`.

## Overall rules
- No verdict if fewer than 10 steps, under 40% of frames in steady walking, or no key metric at medium or
  high confidence; the result says why and how to re-record.
- **outside**: ≥ 2 key metrics clearly outside. **keep_an_eye**: any key metric outside. Otherwise
  **typical**.
- Data confidence per metric: high with ≥ 6 strides (steps for timing) and leg landmark visibility
  ≥ 0.8; low below 3 or visibility < 0.6. Low-confidence metrics are shown but not counted.

## Error ranges
Cadence ±4.5 steps/min and step time ±0.024 s (LJMU). Angles (no reference in LJMU) carry the error of a
similar method, Stenum et al. 2021 (OpenPose vs motion capture, Table 6): knee ±5.6°, hip ±4.0°, ankle
±7.4°. Hip also notes that on LJMU the thigh range read 9° higher than a thigh sensor on average
(docs/validation/kinematics.md).
