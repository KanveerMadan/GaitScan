# Arm swing against LJMU's upper-arm sensor (Phase 11, owner decision D6)

Date: 2026-11-15. Reproduce with `make fetch-ljmu-arm`, `docker build -t gaitscan-api .` and
`make arm-swing` (landmarks need MediaPipe, which aborts on macOS, so they're extracted in the Docker
image). The numbers are `evaluation/results/arm_swing.json` (per recording: `arm_swing_clips.csv`).
Method: `evaluation/arm_swing.py`.

## Data
LJMU 360 Degree Gait Capture (Topham et al. 2023, *Scientific Data* 10:320, CC BY 4.0).
- **Sensor placement.** In tasks 3 and 4 of each experiment, the MOTI goniometer (an IMU, 84 Hz) is on
  the right arm just above the elbow, so it follows the upper arm. The paper's "Experimental tasks"
  section says this ("Task 3: Sensor placement right arm, walk from a to b. Task 4: … walk from b to a").
- **Recordings.** Experiments 1 and 2 have a side camera: 232 recordings with both a sensor file and a
  side-view clip, from 58 participants.
- **Walk length.** Each task is one 8 m walk, of which the side camera sees a part, typically 6–10 s.
  The app asks for walking across the frame and back.

## Method
- **GaitScan, as the app shows it.** Per stride, the range of the shoulder → wrist line against
  vertical, for each arm seen through at least 80% of the stride, the larger of the two; then the median
  over strides (`gaitcore.kinematics`).
- **GaitScan, upper arm.** The same with shoulder → elbow, which is what the sensor follows. This is
  computed for this check only.
- **Sensor.**
  - The swing angle about the sensor's main rotation axis, as for the thigh (`evaluation.leg_labels.sagittal_angle`).
  - Then the median rise or fall between alternating peaks and troughs (prominence at least 5°),
    leaving out the first and last (starting and stopping).
  - The thigh check's stride-to-stride peaks didn't fit: the arm recordings are short (4–9 s) and the
    arm signal isn't a clean once-per-stride wave.
- **The same caveat as the thigh check** ([kinematics.md](kinematics.md)): the sensor isn't
  time-aligned with the clip, and its recording isn't the same stretch of walking as the clip's steady
  part. So this is an average per recording, not a frame-by-frame comparison. As a rough check that
  they're the same walk, the sensor's median time between forward peaks against the clip's stride time
  gives a bias of 0.1 s and r = 0.48.
- **Which arm.** Walking towards image +x the right side faces the camera ([leg-identity.md](leg-identity.md)).
  So in about half the recordings the sensor's arm (right) is the near arm, which GaitScan sees. In the
  other half GaitScan mostly sees the left arm, which the sensor doesn't measure.

**Agreement criteria, set before the comparison was run:** show an error range (about ±MAE, as for the
other angles) only if, over the recordings the app would accept, the bias is within ±5°, the MAE is at
most 10° and Pearson's r is at least 0.6. Otherwise arm swing stays information only.

## Results
**Recordings.** 139 of 232 pass the app's recording checks, and 137 of those have a usable sensor
value. Most rejections are a single short pass: 51 "too little walking" and 24 "legs not tracked".

| Recordings the app accepts (n = 137) | GaitScan mean | Sensor mean | Bias | MAE | 95% limits | r |
|---|---|---|---|---|---|---|
| **Arm swing as shown** (shoulder → wrist) | 31.1° | 25.8° | **+5.3°** | 8.3° | −14.3 to +24.9° | 0.71 |
| Upper arm (shoulder → elbow) | 28.5° | 25.8° | +2.7° | 7.0° | −16.8 to +22.2° | 0.60 |

By which arm the camera sees:

| | n | Shown: bias / MAE / r | Upper arm: bias / MAE / r |
|---|---|---|---|
| Right arm (the sensor's) facing the camera | 68 | +2.6° / 5.5° / 0.88 | 0.0° / 4.8° / 0.86 |
| Right arm on the far side | 69 | +7.9° / 11.0° / 0.53 | +5.5° / 9.2° / 0.42 |

Without the recording checks (every recording with at least 3 strides, n = 178), the shown measure
gives bias +5.6°, MAE 8.8° and r = 0.67; the upper arm gives +2.5°, 7.7° and 0.52.

## What this supports
- **The shown measure misses the criteria on bias:** +5.3° against the ±5° limit, while MAE (8.3°) and
  r (0.71) pass. **Decision: arm swing stays information only**, with no level and no error range.
  The app and the PDF now say it was checked and how far off it was, instead of "not checked yet".
- **Why it reads high.** The shoulder → wrist line also moves when the elbow bends, so its range is
  wider than the upper arm's. The upper-arm version has almost no bias. Where the camera sees the same
  arm as the sensor, it agrees closely: MAE 4.8°, r = 0.86.
- **Most of the remaining disagreement is the other arm.** When the sensor's arm is on the far side,
  GaitScan measures the left arm against a right-arm sensor. That's not purely an error: left and right
  arm swing differ in healthy walkers.
- **Proposal for the owner (not built):** measure arm swing on the upper arm (shoulder → elbow).
  - It meets the criteria over all accepted recordings (bias +2.7°, MAE 7.0°, r = 0.60, at the r
    limit), so arm swing could show an error range of about ±7°.
  - It would stay information only (D3: arm swing never changes the verdict).
  - It needs a same-method reference rebuilt with the new measure (`make references`) and the golden
    file regenerated.
