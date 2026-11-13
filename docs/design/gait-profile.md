# Design note: gait profile, verdicts and the full report

Status: **approved by the owner on 2026-11-13 with the decisions in §14**, which override anything
above that differs. Building in the PR order of §12, starting with the per-side measurement (BE-A1).
Scope: both repositories. The request is the owner's brief of 2026-11-13; this note says how each part
can be built honestly, what can't, and what the owner must decide first.

## 0. What I found that changes the plan

1. **LJMU has more than the project assumed.** `Participant_Anthropometry.xlsx` in the dataset gives
   sex, age and height for all 65 participants (37 M, 27 F, 1 not given; ages 18–65, median 31). Tasks
   1 and 2 (the E1T1, E1T2 and E2T1 clips we evaluate) also carry a **MOTI digital goniometer on the
   right thigh, just above the knee**, synchronised with the video by the authors (Topham et al. 2023,
   *Scientific Data* 10:320, CC BY 4.0, Methods: "Task 1: Sensor placement right leg"; "The video and
   sensor data are manually synchronised for each recording"). 192 of the 210 clips cached locally are
   tasks 1–2. That gives three new, independent references:
   - **which leg is the right leg** in every frame (the thigh that moves with the sensor);
   - **right-leg stride timing** (one thigh-angle cycle per stride);
   - **right thigh sagittal angle and its range** (a hip-movement reference).

   It gives **no** reference for knee or ankle angles, for toe-off, stance, swing or double support, or
   for the left leg. Tasks 3–4 carry the sensor on the right upper arm (an arm-swing reference) but
   aren't in our reference set; using them means downloading more clips of the same public dataset
   (decision D6).
2. **Telling the legs apart is the bottleneck.** Today the pipeline trusts its left/right labels in
   **33 of 97** accepted LJMU clips (`evaluation/results/ljmu_summary.json`, `per_leg_values_shown`).
   Every per-side metric, every symmetry index and every per-side GPS term depends on it. Showing them
   when the labels aren't trusted would invent asymmetry in healthy people and turn it into 🔴 verdicts.
   The earlier untangling attempt failed for lack of foot-labelled ground truth; the thigh sensor is that
   ground truth. So per-side work starts with a measurement spike (BE-A1) and ships only if it passes
   the gate in §3.
3. **Norms: what exists openly, and what doesn't.** Verified open sources (full text read through
   Europe PMC or the dataset's own files):
   - Mobbs et al. 2025, *Sensors* 25(2):581, CC BY 4.0, Tables 4–5: cadence, step length and gait speed
     by sex and 10-year age band (the cadence part is already in the app).
   - Fukuchi, Fukuchi & Duarte 2018, *PeerJ* 6:e4640, data on figshare 10.6084/m9.figshare.5722711,
     **CC BY 4.0**: 3D marker sagittal hip, knee and ankle curves (`*ang.txt`, 508 files) for 51 healthy
     adults (`WBDSinfo.csv`: young 21–37 y, 10 F / 14 M; older 50–84 y, 12 F / 15 M), overground at
     self-selected speed.
   - Stenum, Rossi & Roemmich 2021, *PLoS Comput Biol* 17(4):e1008935, CC BY 4.0: errors of **2D
     side-view pose estimation (OpenPose)** against motion capture: Table 6 angle MAE hip 3.7–4.0°, knee
     5.1–5.6°, ankle 6.3–7.4°; Tables 2 and 4 timing errors.

   **No openly licensed, age- or sex-specific norms were found** (Europe PMC open-access searches,
   2026-11-13) for: stance %, swing %, double support %, step-time CV, trunk lean, arm swing, pelvis
   oscillation, symmetry-index thresholds, or a GPS for a 2D sagittal subset. The best honest
   alternative is a **same-method reference**: healthy LJMU walkers measured by this pipeline, which
   carries this pipeline's own errors. That makes it a fair comparison for a GaitScan recording, but it
   covers adults aged 18–65 only, with few people over 40 (see §4).
4. **There is no pathological data**, so whether 🟡 or 🔴 picks out anything real can't be measured.
   What can be measured is the **false-alarm rate on healthy people**: the share of LJMU participants
   who would get 🟡 or 🔴 (leave-one-participant-out). I propose it as a release gate (§5).
5. **Snapshots conflict with the current consent text.** Consent v2 says "Never the video or my face."
   Annotated frames need consent v3 and re-consent, and should blur the face (D5).
6. **Regulatory status.** A verdict that says "Consider getting this checked" after screening a walk
   is an intended medical purpose under most regimes (UK MHRA, EU MDR, US FDA SaMD guidance), whatever
   the disclaimer says. The "not a medical device" statement in the README and the app would no longer
   be safe to make as it stands. This is the owner's decision (D4), not a technical one.
7. **Old sessions can't be re-analysed.** Videos are deleted in a `finally:` block and never stored,
   so legacy results stay as they are.
8. **Memory and the PDF are fine.** The CI peak is 386 MB today. The new metrics use landmark arrays
   already in memory. ReportLab 5.0.1 (already used) draws vector charts, and shapes Devanagari through
   `uharfbuzz` (optional dependency, confirmed in `reportlab/pdfbase/ttfonts.py`).

## 1. Metrics

Notation: per stride, from heel strike HS to the next HS of the same foot; TO = toe-off. Angles use
the 2D image of a side-on camera; *d* is the walking direction (+1 or −1).

### 1.1 Events
| Event | Method | Source |
|---|---|---|
| Heel strike (per foot) | Heel furthest ahead of the pelvis along *d* (already in `gaitcore/gait.py`) | Zeni et al. 2008, *Gait Posture* 27(4):710 |
| Toe-off (per foot) | Toe furthest behind the pelvis along *d*, between that foot's HS and the other foot's next HS | Zeni et al. 2008 (same paper, same method) |
| Pooled steps | Label-free heel-separation peaks (unchanged; validated on LJMU) | `gaitcore/gait.py` |

Direction, passes, turns and edge strides are already handled (`segments.steady_segments`,
per-segment direction, visibility masks). A stride counts only if HS, TO and the next HS all lie inside
one steady segment with every needed landmark visible.

### 1.2 Timing and rhythm
| Metric | Formula | Per side | Reference (typical range) | Error shown | Validation |
|---|---|---|---|---|---|
| Cadence | 60 / mean pooled step time | pooled | Mobbs 2025 T4–5 by sex and age | ±4.5 steps/min (LJMU) | LJMU, done |
| Step time | mean ± SD, pooled | pooled; per side if gate passes | same-method LJMU | ±0.024 s (LJMU) | LJMU, done |
| Stride time | HS→HS same foot | per side if gate passes | same-method LJMU | right leg: LJMU thigh sensor (new) | BE-A1 |
| Stance %, swing % | (TO−HS)/stride, 100 − stance | per side if gate passes | same-method LJMU; typical ~60/40 stated as context only | Stenum 2021 T2 (OpenPose, ±0.02 s), labelled "similar method" | none on LJMU (no toe-off reference) |
| Double support % | sum of both-feet-down intervals / stride | pooled | same-method LJMU | Stenum 2021 T2, labelled as above | none on LJMU |
| Step length, speed | calibration only (unchanged) | pooled | Mobbs 2025 T4–5 | not validated | unchanged |
| Step-time CV % | SD/mean of pooled step times | pooled | same-method LJMU | — | LJMU distribution |

### 1.3 Joint movement (sagittal, per side, only when the legs are told apart)
| Metric | Convention (0 and sign) | Reference | Error shown |
|---|---|---|---|
| Knee flexion | 180° − interior hip–knee–ankle angle; 0 = straight, + = flexion | Fukuchi 2018 curves (context); same-method LJMU (levels) | Stenum 2021 T6: 5.1–5.6° MAE (OpenPose), labelled "similar method" |
| Hip flexion | thigh (hip→knee) against the trunk line (shoulder-mid→hip-mid); + = thigh ahead | Fukuchi 2018 (offset by pelvic tilt: 2D has no pelvis segment; stated) | right thigh: LJMU sensor (new); Stenum T6 3.7–4.0° |
| Ankle | shank (knee→ankle) against foot (heel→toe) − 90°; + = dorsiflexion | Fukuchi 2018 (context) | Stenum T6 6.3–7.4° |
| Thigh angle | thigh against vertical | LJMU thigh sensor | LJMU (new) |
| Curves | 101 points HS→HS, mean ± SD over valid strides | — | — |
| Key events | knee at IC; peak knee in swing (TO→HS); peak hip extension in terminal stance; ankle at IC | as above | as above |
| ROM | max − min over the stride, per joint | as above | as above |
| Trunk lean | shoulder-mid→hip-mid line against vertical, + = forward along *d*; mean | same-method LJMU | none |
| Arm swing | shoulder→wrist line against vertical, range per stride | same-method LJMU (or the arm sensor, D6) | none (or LJMU arm sensor) |
| Pelvis oscillation | vertical range of the hip midpoint per stride / leg length (cm with calibration) | same-method LJMU | none |

The angle conventions match Fukuchi's (flexion and dorsiflexion positive). The 2D hip and ankle
differ from 3D marker definitions by a near-constant offset (pelvic tilt; foot-marker placement).
Fukuchi curves are therefore shown **shape-aligned for context only**. Levels for angles come from the
same-method LJMU reference, which carries the same offsets.

### 1.4 Symmetry
Symmetry index SI % = 100 × (L − R) / (0.5 × (L + R)) (Robinson, Herzog & Nigg 1987, *J Manipulative
Physiol Ther*; the formula, not data, is cited; the volume and pages are from memory and will be checked
against the paper in BE-A2). It covers step time, stance %, knee ROM, hip
ROM, peak swing knee flexion and arm swing. The sign says which side moves less. Shown only when the
legs are told apart. Threshold: from the same-method LJMU distribution (§2), because no open threshold
for 2D video was found.

### 1.5 Gait Profile Score
GPS and Gait Variable Scores follow Baker et al. 2009 (*Gait Posture* 30(3):265; RMS over the gait
cycle of the difference from a reference mean curve). The subset is sagittal only: hip, knee and ankle,
per side, so six variables. The reference mean curves and the typical band come from the same-method
LJMU curves (leave-one-participant-out), **not** from Fukuchi or Baker's controls. Against a 3D
marker reference, a 2D score would mostly measure the method's offsets. Stated in the UI and the
report: "GPS against healthy walkers filmed and measured the same way".

## 2. Verdicts

Thresholds live in `gaitcore/norms/thresholds.py` (one module, each with its source) and
`docs/verdicts.md`. Metric value *x*, reference mean μ and SD σ for the person's group, method error
e95.

- **Literature references** (different instrument: Mobbs, Fukuchi): 🟢 if |x − μ| ≤ 2σ + e95; 🟡 if
  ≤ 3σ + e95; 🔴 beyond. Adding e95 means a difference the method can't resolve never counts.
- **Same-method references** (LJMU through this pipeline, which already includes its errors): 🟢 within
  μ ± 2σ of participant means; 🟡 to ± 3σ; 🔴 beyond.
- **Symmetry**: 🟢 |SI| ≤ the healthy LJMU 95th percentile (P95); 🟡 to 2 × P95; 🔴 beyond (D1).
- **Low confidence**: level shown in grey ("low confidence"), never counted in the overall verdict.

Overall (rules tested exhaustively):
- **No verdict** when the quality gate (§3.6 of the brief) fails.
- 🔴 when ≥ 2 *key* metrics are 🔴, or a key symmetry metric is 🔴 at high confidence.
- 🟡 when any key metric is 🟡 or 🔴 and the 🔴 rule doesn't apply.
- 🟢 otherwise.
- Key metrics (proposal, D3): cadence, step-time CV, peak swing knee flexion and knee ROM per side,
  hip ROM per side, GPS, step-time and knee-ROM symmetry, and gait speed when calibrated. Ankle (largest
  error, foot landmarks least reliable), trunk lean, arm swing and pelvis oscillation are shown with a
  level but kept out of the overall verdict in v1.

Findings name the metric, the side and the size in plain words ("Your right knee bends about 11° less
than your left during the swing phase"). They never name a condition. A test scans every generated
string in both languages for the banned list (abnormal, bad, poor, wrong, disease, diagnosis, and named
conditions) and their Hindi equivalents, which the owner reviews.

**Release gate (proposal, D1):** on healthy LJMU participants (leave-one-participant-out), at most 5%
get 🔴 and at most 25% get 🟡. If it's higher, thresholds are widened or metrics leave the key set, and
the shipped numbers are published in `docs/validation/verdicts.md`.

## 3. Per-side gate (BE-A1, before any per-side metric ships)

Using the right-thigh sensor on LJMU tasks 1–2:
1. **Label correctness**: the share of strides where our "right" thigh angle correlates with the sensor
   better than our "left" does. Today's labels and any new untangling method are both measured.
2. **Right stride time** against the sensor's thigh-angle cycle: error per stride and per participant
   mean, compared with the pooled step time ×2.
3. **Right thigh range** against the sensor's per-stride range.

Ship per-side metrics only if, on the LJMU test split, label correctness is ≥ 95% of strides **and**
right stride time is no worse than the pooled method. Otherwise per-side timing stays pooled (said so in
the app), and per-side angles and symmetry show only in clips that pass the existing label checks
(about a third today), with "left/right couldn't be told apart" elsewhere.

## 4. Same-method references from LJMU

Healthy participants' clips go through the pipeline once (`make references`). The tables are committed
with their provenance: clip ids, participant ids and pipeline version, but no landmarks or video. Groups
by sex and age need at least 10 participants (the same rule as Mobbs). Participants in the dataset
(anthropometry sheet; fewer once clips are accepted): 18–40 has F 18, M 29, usable by sex; 41–65 has
F 9, M 8, usable for both sexes together only; over 65 has no
same-method reference, so the all-adult band is used and says so. When age or sex isn't given, the
all-adult band is used and says so. Nothing is extrapolated.

## 5. Results schema v3 (`pipeline_version` 3.0.0)

Values below are illustrative, not measured.

```json
{
  "gait_profile": {
    "schema": 3,
    "reference": {"age_band": "41–50", "sex": "female", "fallback": null},
    "timing": {"cadence": {"value": 109.1, "unit": "steps/min", "sd": null, "n": 18,
               "typical": [92, 131], "level": "typical", "confidence": "high",
               "error_95": 4.5, "source": "mobbs2025:T4"}, "...": {}},
    "kinematics": {"knee": {"left": {"curve": [101 floats], "sd": [101 floats],
                   "events": {"ic": 4.1, "peak_swing": 58.3}, "rom": 57.0, "level": "typical"},
                   "right": {}}, "hip": {}, "ankle": {}, "trunk_lean": {}, "arm_swing": {},
                   "pelvis_oscillation": {}},
    "symmetry": {"knee_rom": {"si": -11.2, "less": "right", "level": "slightly_outside"}},
    "gps": {"value": 6.1, "gvs": {"knee_left": 5.2}, "typical": [3.0, 7.4]},
    "verdict": {"level": "keep_an_eye", "drivers": ["knee_rom_symmetry"], "findings": ["..."],
                "next_steps": ["Re-test in 2–4 weeks."], "notice": "Experimental estimate..."},
    "quality": {"steps": 18, "strides": {"left": 4, "right": 5}, "usable_fraction": 0.61,
                "legs_told_apart": true, "verdict_allowed": true, "tips": []}
  }
}
```

v2 results stay as stored. The API returns them untouched with `gait_profile: null`, and the app shows
the "legacy result" view.

## 6. Database (additive only)

- `session_snapshots` (id, session_id FK, kind `heel_strike` | `toe_off`, jpeg bytea, width, height,
  created_at). Deleted with the session (`delete_session_rows`) and the account; base64 in the export.
- `sessions.result` stays JSON (v3 inside). No column is dropped or rewritten, and no stored value is
  deleted (lesson of 0013). Numbering follows the email-case migration 0014 (PR #36, not merged yet).

## 7. Snapshots and privacy (D5)

2–3 frames at a representative heel strike and toe-off, re-read from the video **after** the pose pass,
while the job still has the file. No frames are held during analysis. Each is at most 640 px wide, JPEG
quality about 70 (≤ 40 KB), with the skeleton drawn on. The **face is blurred** using the face landmarks
plus a margin. They are kept only with consent v3, which replaces "Never the video or my face" with
wording that covers blurred stills; existing users re-consent. They're not in share links unless the
owner wants them there. At 3 × 40 KB per session, a 0.5 GB database (Neon's free plan, if that's the
one in use) holds roughly 4,000 sessions' snapshots.

## 8. PDF

ReportLab 5.0.1 (already used) with `reportlab.graphics` for vector charts, `uharfbuzz` for Devanagari
shaping, and Noto Sans plus Noto Sans Devanagari (SIL OFL 1.1) bundled, about 1 MB. Pages 1–6 follow
the brief; page 5 only when earlier sessions exist. It's built per request in the API process. Fonts
are registered once, and no images are involved apart from the snapshots. A test measures peak memory
while building a Hindi report. The verdict box uses a symbol and a pattern as well as colour, so it reads
in black and white.

## 9. Memory

The new metrics come from the landmark arrays already in memory, and the arrays are freed after
`analyse`. CI's memory test stays on the synthetic 1080p 60 fps 10 s clip with the existing **420 MB**
limit, which is stricter than the brief's 450 MB. LJMU clips and `realworld_clip1.mp4` aren't in the
repository: LJMU is fetched on demand, and the real-world clip is the owner's own video and shouldn't be
committed. So `make memory` measures them locally and records the peaks in `docs/validation/`. CI can't.

## 10. Endpoints

- Results (`GET /sessions/{id}`, the analysis status, shared links) carry `gait_profile`.
- `GET /report/{id}?lang=en|hi` extends the existing report endpoint.
- `GET /me/trends?profile_id=` returns per-session series of cadence, step-time CV, knee ROM per side
  and GPS.
- Clinicians: the same as today (linked patients only, never another profile's sessions).
- The contract is regenerated in each PR.

## 11. Validation (`docs/validation/`)

| Check | Reference | Status |
|---|---|---|
| Cadence, step time (pooled) | LJMU strikes | existing |
| Leg-label correctness; right stride time; right thigh range | LJMU thigh sensor | new, BE-A1 |
| Stance, swing, double support; knee and ankle angles | none in LJMU | literature error (Stenum 2021, OpenPose) shown as "similar method", **not** claimed |
| Verdict false-alarm rate | LJMU healthy participants | new, release gate |
| Golden profiles | synthetic walker in CI; LJMU profiles committed as JSON, checked by `make evaluate` locally | new |

## 12. PR plan (revised from the brief)

1. **This design note** (draft PR) and the plan's Phase 11 with today's decision record. **Stop.**
2. **BE-A1**: LJMU sensor and anthropometry loaders, the label-correctness, right-stride and thigh-range
   evaluation, and the result. Evaluation code only, no product change. **Report and stop if the
   per-side gate fails.**
3. **BE-A2**: toe-off, timing metrics, kinematics, symmetry and GPS in `gaitcore`, with synthetic tests.
4. **BE-B**: references (Mobbs and Fukuchi tables, LJMU same-method tables), verdict engine, quality
   gate and confidence, schema v3, migration (`session_snapshots`), snapshots with consent v3, trends
   and the contract.
5. **BE-C**: the PDF (English and Hindi).
6. **FE-A**: result page.
7. **FE-B**: history dots, progress, settings prompt, clinician view, consent v3 and Hindi strings.

Each backend PR reports tests, CI peak memory and anything the owner must decide.

## 13. Decisions for the owner

- **D1 Thresholds and release gate:** the bands in §2 (2σ / 3σ, + e95 for literature references,
  P95 / 2 × P95 for symmetry) and the healthy false-alarm gate (≤ 5% 🔴, ≤ 25% 🟡).
- **D2 Per-side gate:** ≥ 95% label correctness and no worse than pooled timing on LJMU, else pooled
  timing and per-side angles only where labels pass (§3).
- **D3 Key metrics:** the overall-verdict set in §2 (ankle, trunk, arms and pelvis kept out in v1).
- **D4 Regulatory position:** accept that screening verdicts make GaitScan's intended purpose medical,
  and rewrite the "not a medical device" statements accordingly; or soften the 🔴 wording to
  general-wellness language ("this differs from typical walking; a professional can tell you more").
- **D5 Snapshots:** blurred face, consent v3 and re-consent, not in share links.
- **D6 More LJMU clips:** download the dataset's tasks 3–4 (right upper-arm sensor) to validate arm
  swing. This uses the existing public dataset; no new recordings.
- **D7 GPS reference:** same-method LJMU, as proposed, rather than literature controls.
- **D8 Ages without a reference:** over 65 (and 41–65 by sex) fall back to the all-adult band, said
  plainly.

## 14. Owner decisions (2026-11-13)

These override the proposals above where they differ.

- **D1 Approved.** Bands as in §2. Release gate: on healthy LJMU walkers, ≤ 5% 🔴 and ≤ 25% 🟡.
- **D2 Approved.** Gate: ≥ 95% of strides with correct leg labels, and per-side timing no worse than
  pooled. If it fails globally, per-side metrics are shown **per clip** only when that clip's left/right
  labelling passes a documented confidence test (defined and validated in BE-A1, in
  `docs/validation/leg-labels.md`); otherwise pooled values are shown with a note. Symmetry verdicts
  only on trusted clips.
- **D3 Approved.** The v1 overall verdict uses cadence, step-time CV, knee and hip kinematics, and
  symmetry (trusted clips only). Ankle, trunk lean, arm swing and pelvis oscillation are shown as
  information, without a level.
- **D4 General-wellness positioning.** Keep 🟢/🟡/🔴 and the overall summary, with this wording:
  - 🔴 "Outside the typical range. If you have concerns about your walking, a physiotherapist can assess
    it properly."
  - 🟡 "Slightly outside the typical range — worth re-testing in 2–4 weeks."
  - Keep "not a medical device" and add "for general wellness and information".
  - No screening, detection or referral language anywhere. The overall labels therefore don't use
    "Consider getting this checked", and the brief's 🔴 summary is replaced by the 🔴 wording above.
  - All disclaimers (app, PDF, README) are updated consistently.
- **D5 No real video frames.** "Snapshots" are the pose skeleton drawn on a plain background at heel
  strike and toe-off, rendered from landmarks. No consent change; the current privacy text stays true.
  §7's blurred frames and consent v3 are dropped.
- **D6 Yes.** Download LJMU tasks 3–4 (right upper-arm sensor) of the existing public dataset to check
  arm swing.
- **D7 Yes.** GPS against the same-method LJMU reference, labelled "compared with healthy adults
  measured by this app".
- **D8 Yes.** When there is no age-specific reference: "No age-specific reference for your age;
  compared with all adults."
- **Memory:** keep the 420 MB CI limit.
- **Migrations:** #36 (email case, 0014) and #37 merge before the backend PRs of this phase.
