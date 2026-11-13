# Left/right labels against LJMU's thigh goniometer (Phase 11, BE-A1)

Date: 2026-11-13. Reproduce with `make fetch-ljmu-imu` then `make leg-labels`; the numbers below are
`evaluation/results/leg_labels.json` (per clip: `leg_labels_clips.csv`).

## Question
Before any per-side metric ships (owner decision D2, 2026-11-13), measure on LJMU:
1. how often the pipeline's left/right leg labels are right (gate: at least 95% of strides);
2. whether per-side timing is at least as good as the pooled method.

## Data
LJMU 360 Degree Gait Capture (Topham et al. 2023, *Scientific Data* 10:320, CC BY 4.0). In tasks 1 and 2
a MOTI digital goniometer (IMU, 84 Hz) is strapped to the **right thigh just above the knee**; the paper
says video and sensor were "manually synchronised for each recording" and the videos "cropped so that
the duration is equal to that of the sensor data". 176 task 1–2 recordings have a sensor file; 102 of
them are side-view clips the pipeline accepts.

The sensor's signed thigh angle comes from its quaternions (rotation from the median orientation about
the main rotation axis). Flexion is positive: the shorter, rising half of a stride is swing. The file's
`MotionDeg` column is unsigned and reads about half the range, so it isn't used.
`tests/test_leg_labels.py` checks both on synthetic recordings.

## Results

**1. The sensor isn't aligned with the side-view clips, so it can't say which leg is which.**

| | Value |
|---|---|
| Video length − sensor length (median, max) | 1.38 s, 9.0 s |
| Labelled right thigh matches the sensor better, aligned at the start | 53.5% of 101 clips (median r −0.00 vs −0.01) |
| … aligned at movement onset (sensor rotation vs pelvis speed) | 54.5% (median r −0.02 vs −0.08) |
| Best match within ±2 s, either leg: median r | 0.65 (IQR 0.53–0.78) |
| … at an offset of (IQR) | −0.60 to +1.47 s |
| … with the labelled right thigh | 35.6% |

Left and right thighs trace the same curve half a stride (~0.55 s) apart. With an offset unknown to
well over half a stride, the best-matching leg is decided by the offset, not by which leg wore the
sensor. Both leg-independent alignments give chance-level results. **The ≥ 95% label gate can't be
measured with this sensor.**

**2. Per-side timing is worse than pooled (coarse reference).** Median stride time per recording,
against the sensor's median stride (sync-free, but the sensor recording and the clip's steady walking
aren't the same stretch of walking, which is why even the validated pooled method differs by ~110 ms):

| Method | Clips | Bias | MAE | P95 abs |
|---|---|---|---|---|
| Pooled (2 × step time), all clips | 102 | −39 ms | 113 ms | 241 ms |
| Labelled right strides, all clips | 101 | −267 ms | 300 ms | 739 ms |
| Pooled, clips whose labels pass today's checks | 45 | −35 ms | 114 ms | 245 ms |
| Labelled right strides, same clips | 44 | −79 ms | 153 ms | 389 ms |

Labelled per-side strides are often a single step (the −267 ms bias), the problem found in Phase 3.
Even on the clips that pass today's label checks they are worse than pooled. **Per-side timing fails
the gate: timing stays pooled.**

**3. Thigh range of motion agrees on average, not per clip.** Per-stride range, median per recording:
ours (labelled right) 43.4° vs sensor 44.6°, bias −2.5°, MAE 7.8°, r = 0.16 (n = 75); labelled left vs
sensor, bias +1.1°, MAE 7.3°, r = 0.40 (n = 39). The 2D thigh range isn't biased against the sensor, but
the sensor can't confirm individual values, for the same reason as above.

## What this means for D2
- Per-side **timing**: pooled, with a note (D2's own rule).
- Per-side **angles and symmetry**: D2's fallback says to show them per clip only when that clip's
  labelling passes a documented confidence test. A test can be defined (today's
  `legs_told_apart`: labelled step times regular, each leg's strides ≈ two steps; passes 45 of 102
  here), but there is **no ground truth on LJMU to validate it**. In particular, it can't catch a clip
  whose labels are swapped consistently (every value right, sides named wrongly).
- Arm swing (D6) would meet the same limit: the arm sensor (tasks 3–4) gives average agreement only.
  Extracting landmarks for those clips also needs MediaPipe on Linux (Docker), which doesn't run on the
  development Mac.

## Options (for the owner)
- **A. Annotate leg identity** on a sample of LJMU frames (existing public videos; no new recordings),
  as was done for heel strikes. In LJMU's side camera the near leg is a fixed physical leg per task,
  and a viewer can see which leg is near. That would measure label correctness and validate a per-clip
  confidence test and a side-naming rule. Roughly 40 clips × 8 frames, cross-checked.
- **B. Role-based, label-free kinematics for v1.** Assign each leg its role from foot motion (the static
  foot is in stance, the moving foot in swing) instead of from MediaPipe's labels, and report knee and
  hip key events, ROM and curves for **both legs pooled**. That's available on most clips, not only the
  45% that pass the label checks, and usable for D3's knee and hip verdicts. Per-side values and
  symmetry wait for A.
- **C. Per-side as information only.** Show per-side angles and symmetry on clips passing
  `legs_told_apart`, labelled "left/right as seen from the camera, not validated", with no symmetry
  verdict.

Recommendation: **B now, and A to unlock per-side values and symmetry verdicts.** C risks naming the
wrong side ("your right knee") without any way to know how often.
