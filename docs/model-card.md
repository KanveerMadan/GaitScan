# Model card: GaitScan measurement pipeline 2.0.0

What GaitScan measures, how well, on what data, and where it fails. Every number here comes from
files in `evaluation/results/`, produced by `make evaluate` (accuracy, repeatability),
`evaluation/degrade.py` (degradation curves) and `evaluation/reliability.py` (reliability model).

## The system
- **Input:** a side-on video of one person walking across the frame and back, at 24 fps or more.
- **Pose model:** MediaPipe Pose Landmarker `pose_landmarker_full` float16/1 (MediaPipe 1.0.1),
  pinned by SHA-256. Frames are downscaled to 640 px on the long side first.
- **Measurement:** `gaitcore`, deterministic and with no learned parameters of its own. It covers
  the recording checks, steady-pass detection, label-free step events from heel separation, and
  per-foot heel strikes (Zeni et al. 2008) for strides and the stride outline.
- **Output:** values with units, the error range below, a quality block, and the pipeline and model
  versions. A video that fails a check gets a reason instead of numbers.

## Intended use
- **For:** tracking your own cadence and step time between recordings filmed the same way; a
  clinician or coach looking at those numbers alongside other information.
- **Not for:** diagnosis, predicting falls or injury, comparing a person to norms, or any decision
  made on GaitScan's numbers alone. It is not a medical device and hasn't been clinically validated.

## Accuracy (`make evaluate`)
- **Data:** the LJMU gait dataset (Topham et al. 2023, *Scientific Data* 10:320, CC BY 4.0),
  90° (side-on) camera. 109 clips from 57 adults walking indoors and outdoors.
- **Reference heel strikes:** there are no lab labels, so the references are:
  - 27 clips counted visually on contact sheets of the original frames (**AI-annotated +
    cross-checked** with RTMPose);
  - 72 clips from an independent pose model (RTMPose-x foot keypoints);
  - 10 clips counted visually because the pipeline and RTMPose disagreed by more than 5 steps/min.
    In both such test clips, RTMPose was the one that was wrong.
- **Split:** 88 tuning clips (where thresholds were chosen) and 21 test clips. The test clips are
  the accepted ones among 102 side-view clips never used before, so their acceptance is 100% by
  construction, and they share participants with the tuning set.

| | Clips accepted | MAE | 95% of errors within | Max | Bias | Limits of agreement |
|---|---|---|---|---|---|---|
| Cadence, all (steps/min) | 97 / 109 | 1.56 | **4.48** | 6.41 | +0.08 | −4.07 to +4.23 |
| Cadence, test | 21 / 21 | 1.06 | 2.75 | 4.62 | +0.32 | −2.69 to +3.33 |
| Step time, all (ms) | 97 / 109 | 7.8 | **23.5** | 40.8 | −0.4 | −22.0 to +21.3 |
| Step time, test | 21 / 21 | 4.9 | 18.9 | 19.3 | −1.6 | −15.9 to +12.6 |

**What the app shows:** the larger of the two 95% figures, rounded up. That gives **±4.5
steps/min** and **±0.024 s**. `tests/test_accuracy.py` keeps `gaitcore/accuracy.py` in step with
these results.

The 12 rejected clips: 7 `irregular_steps`, 4 `too_little_walking`, 1 `legs_not_tracked`.

## Repeatability
For 25 pairs of walks by the same person in the same session (16 participants), the 95% minimal
detectable change is **4.6 steps/min** for cadence and **24.7 ms** for step time (1.96 × the SD
of the difference). A change between two of your sessions smaller than this can't be told apart
from measurement noise. Day-to-day variation isn't in it and is likely larger.

## Not yet validated
| Measurement | Why |
|---|---|
| Step length, walking speed | Need a floor calibration; LJMU has no distance reference. Checked only on simulated walking. Permanent: no more video will be collected (2026-11-12). |
| Treadmill test | No treadmill reference clips; permanent for the same reason. |
| Stride time | Withheld: in LJMU, left/right labels follow position, so 37 of 110 legs read one step as a stride. |

The API, the PDF and the app label these "not yet validated" wherever they appear.

**Removed: peak knee flexion** (2026-11-12). Its only route to validation, OpenCap (Phase 8), was
cancelled, so it is no longer measured or shown, and migration 0013 deleted it from stored results.
On synthetic data it was exact; a camera 30° off side-on read a 60° bend as 53.5°.

**Cadence reference (app only).** With the person's sex and birth year in their settings, the app
shows the mean ± 1 SD cadence of healthy adults of that sex and age group from Mobbs et al. 2025
(*Sensors* 25(2):581, doi:10.3390/s25020581, CC BY 4.0; 313 adults, chest-worn IMU, 50 m walk).
Groups with fewer than 10 people in the study get no band. It is context, not a target: that study
measured with a different instrument, and its authors note the method isn't validated.

## How it degrades
54 clips, one per participant, each re-analysed after a degradation. These are the files
`evaluation/results/degradation_*`. Cadence errors are in steps/min, among the accepted clips.

| Degradation | Level | Accepted | MAE | 95% within | Max |
|---|---|---|---|---|---|
| Original | — | 54 | 1.75 | 4.51 | 6.41 |
| Resolution (long side) | 640 px | 54 | 1.75 | 4.51 | 6.41 |
| | 480 px | 38 | 1.85 | 4.68 | 5.18 |
| | 320 px | 35 | 2.03 | 5.52 | 9.02 |
| Frame rate | 25 fps | 49 | 1.93 | 5.56 | 7.10 |
| | 24 fps | 49 | 1.89 | 4.56 | 6.29 |
| | 15 fps | 0 (rejected: low frame rate) | — | — | — |
| JPEG quality | 20 | 38 | 1.79 | 4.45 | 9.05 |
| | 10 | 33 | 2.08 | 6.45 | 6.98 |
| | 5 | 15 | 1.68 | 4.96 | 5.77 |
| Low light (gain + noise) | ×0.3 | 35 | 1.27 | 4.06 | 4.98 |
| | ×0.2 | 30 | 2.37 | 6.55 | 6.94 |
| | ×0.1 | 0 | — | — | — |
| Camera roll | −10° | 29 | 2.23 | 4.62 | 5.41 |
| | 5° | 41 | 1.80 | 6.51 | 6.68 |
| | 15° | 36 | 2.03 | 4.91 | 6.82 |
| Camera yaw (LJMU's simultaneous 45° camera) | 45° | 0 / 32 (rejected: not side-on) | — | — | — |

What the table shows:
- **The checks remove most of the damage.** As quality drops, acceptance falls steeply while the
  error of what's accepted grows slowly.
- **Some degraded clips still get through with larger errors.** About 6% of accepted degraded runs
  were more than 5 steps/min off, and the worst was 9.0. The ±4.5 range shown in the app is for
  undegraded LJMU video.

## Reliability model (evaluated, not shipped)
A per-clip error model was tried and not used. Gradient boosting on 12 quality features, with
split-conformal intervals, evaluated leave-participant-out on 536 accepted runs.

- **Ranking:** it barely ranks clips by real error (Spearman 0.13).
- **Rejection:** turning down the worst-predicted 10–20% doesn't reduce the share of large errors.
- **Coverage:** its 90% intervals cover 86%.

Within what the checks accept, the remaining error looks like noise that these quality measures
can't predict. Details: [reliability-engine.md](reliability-engine.md).

## Known failure modes
- **Not side-on, or a moving camera.** Rejected when detectable (shoulder width, path convergence);
  the views in between can slip through.
- **Spurious step events between real ones.** Usually caught by the step-regularity check
  (`irregular_steps`, step-time CV > 0.15). That threshold was chosen on LJMU, not on phone video,
  and an uneven gait (e.g. a limp) may be rejected by it.
- **Slow walkers.** Below ~60 steps/min the steadiness window stops growing (1.0 s cap). This hasn't
  been checked on real slow walking.
- **Unknown conditions.** Walking aids, children, crowded scenes and treadmill walking haven't been
  evaluated. Treadmill walking is rejected.
- **Phone recordings.** Three real phone videos have been checked by eye (AI-annotated): 85.0 vs
  85.1, 98.8 vs ~101 and 89.9 vs 88.3 steps/min. That is far too few to state an accuracy for phone
  video.

## Reproduce
```bash
make fetch-ljmu
make evaluate                    # evaluation/results/ljmu_clips.csv, ljmu_summary.json
uv run python -m evaluation.degrade --landmarks data/ljmu/landmarks --videos data/ljmu/videos
uv run --group evaluate python -m evaluation.reliability
```

Pose extraction needs Linux (the Docker image) because of MediaPipe 1.0.1 on macOS. The reference
strikes are in `evaluation/ljmu_reference.csv`.

## References
- Topham LK, Khan W, Al-Jumeily D, Waraich A, Hussain AJ. A diverse and multi-modal gait dataset of
  indoor and outdoor walks acquired using multiple cameras and sensors. *Scientific Data*
  2023;10:320. doi:10.1038/s41597-023-02161-8
- Zeni JA, Richards JG, Higginson JS. Two simple methods for determining gait events during
  treadmill and overground walking using kinematic data. *Gait & Posture* 2008;27(4):710–714.
  doi:10.1016/j.gaitpost.2007.07.007
- Stenum J, Rossi C, Roemmich RT. Two-dimensional video-based analysis of human gait using pose
  estimation. *PLoS Computational Biology* 2021;17(4):e1008935. doi:10.1371/journal.pcbi.1008935
