# Can a phone-video gait pipeline predict its own error? A negative result

*GaitScan technical note, 2026-10. Code: `evaluation/degrade.py`, `evaluation/reliability.py`.
Results: `evaluation/results/degradation_*`, `reliability.json`.*

## Abstract
GaitScan measures cadence and step time from side-on phone video. It shows one error range for
every recording: ±4.5 steps/min, the 95th-percentile error on a public dataset. We asked whether a
per-recording error estimate, learned from quality measures the app already computes, could replace
that constant range or flag bad recordings.

We degraded 54 clips from the LJMU gait dataset in five ways at three levels each, and added
LJMU's simultaneous 45° camera. Each run was scored against reference heel strikes. A
gradient-boosted error model with split-conformal intervals was then evaluated
leave-participant-out on the 536 accepted runs.

The predicted error barely ranked runs by their real error (Spearman ρ = 0.13). Rejecting the
worst-predicted 10–20% didn't reduce the share of large errors. The intervals were wider than the
constant one without better coverage. The model wasn't shipped; the app keeps the constant range.

## 1. Question
A constant error range is honest on average, but the same for a crisp video and a dim, compressed
one. Two uses of a per-clip estimate would matter to users:
1. a narrower or wider ± per recording;
2. rejecting recordings likely to be badly wrong, beyond the rule-based recording checks.

Both need the estimate to rank recordings by their real error.

## 2. Data
- **Clips.** One accepted 90° clip per participant from the LJMU dataset (Topham et al. 2023,
  CC BY 4.0): 54 participants.
- **References.** Heel strikes from the GaitScan accuracy check (`make evaluate`): visual counts on
  contact sheets of the original frames (AI-annotated, cross-checked with RTMPose), RTMPose-x foot
  keypoints, or visual counts where those two disagreed by more than 5 steps/min.
- **Degradations.** Applied to the decoded frames, then the same pinned pose model and pipeline as
  the app:

| Degradation | Levels |
|---|---|
| Resolution, long side (INTER_AREA) | 640, 480, 320 px |
| Frame rate (nearest-frame resampling) | 25, 24, 15 fps |
| JPEG quality, every frame | 20, 10, 5 |
| Low light: gain × (0.3, 0.2, 0.1), then Gaussian sensor noise | SD 5, 6, 8 levels |
| Roll | −10°, 5°, 15° |
| Yaw: LJMU's simultaneous 45° camera (not simulated) | 45° |

That gives 896 runs. A run's error is the pipeline's cadence (or step time) minus the reference,
over the pipeline's own steady window. The reference strikes are mapped to the new frame clock at
other frame rates.

## 3. Method
- **Features.** Twelve quality measures available without a reference: frame rate, share of
  frames with a pose, share with both feet visible, shoulder-width view ratio, path convergence
  angle, seconds of steady walking, steps detected, step-time CV, usable-frame fraction, frame
  height, mean leg-landmark visibility, and heel jitter (median absolute second difference of the
  foot x-coordinates).
- **Scale model.** It predicts log(|error| + ε), with ε = 0.2 steps/min or 2 ms (about the
  reference's own resolution). Two models were tried: gradient boosting (150 trees, depth 2,
  learning rate 0.05, subsample 0.8) and standardised ridge regression.
- **Intervals.** Normalised split-conformal:
  - Within each training fold, a quarter of the participants calibrate.
  - The score is |error| / ŝ(x), and q is its ⌈(n+1)(1−α)⌉/n quantile, with α = 0.1.
  - The interval is ±q·ŝ(x).
  - The baseline is the constant interval ±q₀, with q₀ the same quantile of |error|.
- **Evaluation.** Five-fold GroupKFold by participant, so no participant's runs are seen in
  training or calibration. Reported:
  - **Coverage and width** of the intervals.
  - **Discrimination:** Spearman ρ between the predicted and the real |error|.
  - **Rejection:** the share of runs beyond the 95th-percentile error after rejecting the
    worst-predicted 10% and 20%, against the 5% that random rejection leaves.

## 4. Results
Accepted runs: 536 of 896, from 54 participants. Everything at 15 fps, at ×0.1 light and at 45° yaw
was rejected by the recording checks.

| Cadence | Coverage (target 0.90) | Mean width (steps/min) |
|---|---|---|
| Gradient boosting | 0.862 | 8.87 |
| Ridge | 0.821 | 7.82 |
| Constant | 0.856 | 7.79 |

| Step time | Coverage | Mean width (ms) |
|---|---|---|
| Gradient boosting | 0.871 | 41.7 |
| Ridge | 0.802 | 37.6 |
| Constant | 0.860 | 39.5 |

| Discrimination | Cadence | Step time |
|---|---|---|
| Spearman ρ (predicted vs real \|error\|) | 0.13 | 0.13 |
| Share beyond the 95th percentile, nothing rejected | 0.050 | 0.050 |
| … rejecting the worst-predicted 10% | 0.052 | 0.054 |
| … rejecting the worst-predicted 20% | 0.054 | 0.056 |

Coverage falls short of 0.90 even for the constant interval. Calibration and test participants
differ more than split-conformal's exchangeability assumption allows. An earlier run of the same
evaluation, on the pipeline before its real-world recording changes (527 runs), gave the same
picture: ρ = 0.11, coverage 0.89–0.91.

## 5. Discussion
- **The degradations do matter.** Acceptance falls steeply as quality drops: 54 → 35 clips at
  320 px, 54 → 15 at JPEG quality 5. The rule-based checks remove most of the damage, though, so
  the accepted runs' errors grow only slowly.
- **What's left looks like noise.** Within what the checks accept, the remaining error is close to
  the reference's own uncertainty. The cadence MAE is 1.75 steps/min on the original clips and
  1.27–2.37 on the accepted degraded ones. None of the twelve quality measures predicts it.
- **What the large errors trace to.** The few large ones (up to 9 steps/min) come from single
  spurious or missed step events, which these whole-clip summaries can't see.
- **Limitations.**
  - Simulated degradations are not real phone recordings.
  - 54 participants is small for a 12-feature model.
  - References from a second pose model carry errors of their own; the reliability of the reference
    bounds what any error model can learn.
- **What might work instead.** Event-level features, such as the prominence of each heel-separation
  peak and the consistency of the step-time series, or real phone recordings with lab references.

## 6. Decision
Not shipped. The app shows the constant LJMU range. The model card states that about 6% of accepted
degraded runs were off by more than 5 steps/min, beyond that range.

## References
Topham LK, Khan W, Al-Jumeily D, Waraich A, Hussain AJ. A diverse and multi-modal gait dataset of
indoor and outdoor walks acquired using multiple cameras and sensors. *Scientific Data*
2023;10:320. doi:10.1038/s41597-023-02161-8
