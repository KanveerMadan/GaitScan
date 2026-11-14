# Label-free knee and hip measures on LJMU (Phase 11, BE-A2, decision B)

Date: 2026-11-14. Reproduce with `make kinematics` (and `make fetch-ljmu-imu` for the sensor check); the
numbers are `evaluation/results/kinematics.json` (per clip: `kinematics_clips.csv`). Method:
`gaitcore/kinematics.py`.

## Why label-free
MediaPipe's left/right leg labels can't be trusted on LJMU (docs/validation/leg-labels.md), and today
only 45 of 97 accepted clips pass the label checks that per-leg values need. Owner decision B
(2026-11-14): v1 knee and hip measures don't use the labels. Each leg's role comes from foot motion
and footprints, and values are for both legs pooled.

## Method in short
- **Heel strike:** just before each label-free step event (validated on LJMU), the first frame where the
  front heel (whichever label it carries) slows below `PLANTED` = 2.0 leg lengths/s.
- **Untangling:** per frame and before any filtering, the leg that struck stands on its footprint, so it
  is the chain nearest the footprint. When the other foot is passing, the straighter knee wins. A hidden
  heel is decided by the visible one, or by the previous frame. Then gaps of ≤ 2 frames are bridged, then
  the 6 Hz low-pass.
- **Toe-off:** after the other foot lands, the leg's toe furthest behind the pelvis (Zeni et al. 2008,
  *Gait Posture* 27(4):710), not tuned.
- Angle conventions are in the module docstring (flexion and dorsiflexion positive, as Fukuchi et al.
  2018).

## Choosing PLANTED (tuning clips only)
Heel-strike timing against the reference strikes on the 76 tuning clips: 0.25 → bias −50 ms, MAE 53 ms;
1.0 → −33 ms, 40 ms; **2.0 → 0 ms, 31 ms**; 2.5 → 0 ms, 30 ms; 3.0 → 0 ms, 32 ms. 2.0 was taken (no
bias, flat optimum).

A speed rule was also tried for toe-off and rejected. A planted foot's image speed on LJMU's small
figures (leg ≈ 105 px) reaches 2.4 (heel) and 2.9 (toe) leg lengths/s at the 95th percentile, as fast as
a foot leaving the floor. So stance moved from 55% to 69% with the threshold. Zeni's position rule doesn't
depend on a threshold, and stance and double support were **not** used to choose anything.

## Results (97 accepted clips; 21 held-out test clips)

| | Value |
|---|---|
| Clips with ≥ 3 label-free strides | **95 of 97** (labelled per-leg values today: 45) |
| Heel-strike timing vs reference, **test clips** | bias 0 ms, MAE **17 ms** (143 of 147 strikes matched within 5 frames) |
| … tuning clips | bias 0 ms, MAE 31 ms |

Plausibility (no reference in LJMU; medians over clips, IQR):

| Measure | LJMU | Healthy reference (other method) |
|---|---|---|
| Stance % | 62.3 (60.8–64.1) | 61% (Stenum et al. 2021, motion capture: 0.74 s of a 1.21 s stride) |
| Double support % | 24.9 (19.8–27.6) | 23% (Stenum 2021: 0.14 s per step) |
| Knee at contact | 7.6° (5.0–9.8) | |
| Peak knee flexion in swing | 58.6° (55.5–63.5) | |
| Knee ROM | 57.5° (55.0–60.9) | |
| Peak hip extension (thigh vs trunk) | −21.5° (−24.7 to −17.5) | |
| Peak hip flexion | 31.7° (26.3–35.5) | |
| Hip ROM | 53.6° (49.7–59.1) | |
| Ankle ROM | 33.3° (29.0–36.0) | |
| Trunk lean | −0.3° (−1.3 to 1.1) | |
| Arm swing (visible arm) | 33.5° (22.9–41.2) | |
| Pelvis oscillation (detrended) | 0.11 leg lengths (0.10–0.12) | about twice published values; see below |

**Thigh range against the thigh sensor** (72 clips, on average only, as the sensor isn't time-aligned
with the clips): ours 52.9° vs sensor 44.3°, bias +9.0°, MAE 9.9°, r = 0.44. Wrong-leg frames don't
explain it: about 1% of strides show a jump of > 35° between frames, and a 3-frame median filter changes
the median range by 1.4°. The cause is unexplained (2D projection, hip landmark placement, or the
sensor's own axis and soft tissue).

## What this supports
- Knee and hip key events and ranges are available on almost every clip, and they are unchanged under
  label errors (tests/test_kinematics.py: brief flips and labels that follow position, both within 3°).
- Heel-strike timing is validated on LJMU (test MAE 17 ms). Toe-off, stance and double support are
  plausible but not validated (no toe-off reference).
- **No joint angle is validated**: there's no angle reference in LJMU. The thigh range differs from the
  sensor by +9° on average. Error ranges for angles come from the literature (Stenum 2021, OpenPose),
  labelled as such.
- **Pelvis oscillation** reads about twice the published centre-of-mass excursion even after detrending
  (camera tilt explains 0.03 of 0.12). Recommendation: don't show it in v1.
- Values are pooled over both legs and, in a single pass, come mostly from the leg nearer the camera.

## Open question (owner, 2026-11-14)
Why does the 2D thigh range read 9° higher than LJMU's thigh sensor (r = 0.44)? It doesn't block: the
thigh angle isn't shown to users. Hip range is shown with the literature error (±4.0°, Stenum 2021) and
this offset as a note (docs/verdicts.md). Candidates: hip landmark placement (MediaPipe's hip point vs the
joint centre), 2D projection, or the sensor's own axis and soft-tissue movement.
