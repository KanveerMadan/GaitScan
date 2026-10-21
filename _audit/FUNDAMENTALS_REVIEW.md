# GaitScan — Fundamentals Review (first principles, before Phase 2)

Date: 2026-10-03 · Author: Claude (review requested by Kanveer) · Scope: should this be built, what should it be, and what can it honestly claim.
Companion files: [`REBUILD_PLAN_V2_PROPOSAL.md`](REBUILD_PLAN_V2_PROPOSAL.md) (revised phases). Inputs: [`GAITSCAN_AUDIT.md`](GAITSCAN_AUDIT.md), [`REBUILD_PLAN.md`](REBUILD_PLAN.md), `adr/`, the code on `rebuild/phase-1-foundations`.

Conventions used throughout:
- **[E]** is evidence, with a citation `[S#]` to the source list in §7.
- **[I]** is my inference or reasoning.
- **[Q]** is an open question that only you can answer (collected in §8).
- "Unverified" means I could not confirm the claim from a primary source. "Summary-level" means I saw only a search abstract or snippet, not the full text.

---

## 0. Executive verdict (≤ 15 lines)

1. **Don't build a physio/sports SaaS (option A).** The SaaS features (risk scores, injury screening, coaching, multi-tenant clinic workflows) need either unvalidated claims or regulatory approval. They also need a sales effort a solo student can't run.
2. **What 2D single-phone video can honestly measure** is a short list, and only from a side view under a strict protocol: cadence and step/stride timing; peak sagittal knee (and hip) angle, ±≈3–6°; and step length and gait speed when there is a floor scale. [E: S1, S2, S5]
3. **Measurements to drop:** frontal-plane knee valgus and pelvic drop; ankle angles with MediaPipe; uncalibrated step length and speed; angle-based L/R symmetry from one side view; and every "risk" output. [E: S4, S9, S10]
4. **No injury or fall risk claim is supported** by these metrics. Even 3D-lab valgus screening fails to predict ACL injury [S19], and gait speed's fall discrimination is weak (sensitivity 35%) [S17]. A risk claim also turns the software into a medical device under CDSCO's 2026 guidance [S33].
5. **Recommendation: option D, research-first with a narrow product.** Build an open-source, privacy-first tool. Pose estimation runs in the browser (video never leaves the phone), and it reports three or four sagittal metrics with measured error bars, built for repeated measurement of the same person. The tool is paired with a properly designed validation and repeatability study submitted as a short paper.
6. **The validation study as planned won't work.** A static goniometer cannot validate *walking* angles. It needs a dynamic reference (frame-annotated video plus a public mocap dataset, or IMUs), at least 20 participants, two sessions, and Bland–Altman, ICC(2,1), SEM and MDC.
7. **Novelty is thin and you should know it.** OpenCap Monocular (Stanford/Utah, 2026 preprint) already gives free single-phone 3D kinematics at 4.8° MAE [S8]. Your contribution can only be the angle they don't cover:
   - on-device and privacy-preserving processing;
   - low-cost Android phones in Indian settings;
   - test–retest/MDC for self-tracking.
8. **Large parts of the plan go away.** Phases 3–4 (job queue, object storage, multi-tenancy) mostly disappear. Phase 5 (validation) becomes the core. The Phase 0–1 engineering stays as portfolio evidence.
9. **If you can't commit about 120–140 h over 6–9 months, choose E (stop now).** It is respectable.

---

## 1. Problem and users

### 1.1 Who might use it, and for what

| User group | Job to be done | How it's done today | What would make them switch | Fit for GaitScan |
|---|---|---|---|---|
| **Physiotherapists (India, outpatient)** | Document gait/ROM objectively, show patients progress, justify treatment | Visual observation and goniometer; timed tests (10 m walk, TUG). Observational gait analysis is only slight-to-moderately reliable [E: S46] | Faster than a goniometer, a number they trust, fits a short session. The top barrier to evidence-based practice in a ~3,000-physio Indian survey was lack of time (51.6%) [E: S47] | Real need, **but** monitoring patients is a medical purpose [E: S33], and clinic sales are hard for a solo student [I]. Serve them only as individual users of a free measurement tool, not as clinics. |
| **Physio students / small-study researchers** | Get cadence, step time and knee angles from walking videos for coursework or small studies | Manual digitising in Kinovea (free; valid for angles in controlled setups) [E: S27]; OpenCap if they have 2 phones and cloud upload is acceptable [E: S7] | Automatic extraction, a known error, no video upload, free | **Strongest realistic fit [I].** The need is genuine (manual digitising is slow), the claims are non-clinical, and they value published accuracy. |
| **Sports academies / coaches** | Technique feedback, injury "screening" | Video apps: OnForm, Dartfish, Kinovea [E: S26, S27, S31] | Injury prediction, which is not supported [E: S19, S18] | **Drop.** What they want (valgus, injury risk) is the least valid metric [E: S9, S10]. Athletes are often minors, which triggers DPDP s.9 (verifiable parental consent; no tracking or behavioural monitoring of children) [E: S35]. |
| **Recreational runners** | Running-form feedback, injury prevention | Ochy (smartphone AI, adidas partnership, €8.49–9.99/month) [E: S25]; Uplift for teams [E: S30] | Better product, which is hard to deliver | **Drop.** A crowded consumer market, running kinematics are harder than walking, and injury claims are unsupported [E: S18]. |
| **Elderly-care settings** | Fall-risk screening, mobility tracking | TUG, gait speed tests, observation. TUG alone is not a significant fall predictor [E: S16] | A validated fall-risk score, which doesn't exist from these metrics [E: S17] | **Drop for v1.** Fall-risk claims are medical-device territory [E: S33]. Gait speed is the one meaningful metric [E: S15] and needs a calibrated setup [E: S1]. |
| **Individuals (self-tracking)** | "Is my walking changing?" | Phone step counters, wearables (not researched) | Free, private, simple | Secondary fit. Acceptable under wellness framing if it makes no disease references [E: S33]. |

### 1.2 Competitive landscape (only tools I could verify exist)

| Tool | What it measures | Accuracy: claimed or validated | Price (public) | Target user |
|---|---|---|---|---|
| **Kinovea** [S27] | Manual and semi-automatic angle/distance tracking in video | Valid and reliable for angles/distances up to 5 m and 45–90° camera perspective (peer-reviewed, PLoS ONE 2019) [S27] | Free, open source | Coaches, physios, researchers |
| **OpenCap** [S7] | 3D kinematics and dynamics from **2+ smartphones** (OpenSim) | Joint angles MAE **4.5°** vs mocap; 10 healthy adults; walking, squat, sit-to-stand, drop jump [S7] | Free web app for research | Researchers |
| **OpenCap Monocular** [S8] | 3D kinematics and kinetics from **one** static smartphone video | Joint angles MAE **4.8°**, within 1° of 2-camera OpenCap. **Preprint (2026-03)**, not yet peer-reviewed [S8] | Free; code on GitHub (per preprint) | Researchers, clinicians |
| **Theia3D** [S32] | Markerless 3D from **8 synchronised cameras** | No bias in walking spatial measures vs marker-based; small temporal differences [S32] | Not public (unverified) | Biomechanics labs |
| **OnForm** (acquired Hudl Technique) [S26] | Video review; AI skeleton showing joint angles | No published accuracy found (unverified) | $9.99–14.99/month individual; $19.99–59.99/month coach [S26] | Coaches, PTs |
| **Dartfish** [S31] | Video analysis, manual angles | Not found | ~$84/year per a third-party blog (**unverified**) | Coaches |
| **Ochy** [S25] | Running form from phone video (joint angles, foot strike, oscillation) | Lab collaborations claimed (Inria, Univ. of Suffolk); **no validation numbers found** (unverified) | €8.49–9.99/month; packs €4.99–90 [S25] | Runners, retailers |
| **Exer (Exer Health / Gait / Physio)** [S28] | ROM, reps, gait metrics via phone/tablet camera | Markets "validated evaluation modules"; independent numbers not found (unverified) | Not public (unverified) | PTs, clinics |
| **Kinetisense (KAMS)** [S29] | 3D-camera movement screen, ROM, balance | Vendor-hosted university report: ICC(3,1) 0.69–0.93 vs Vicon for KAMS variables [S29] | Not public (unverified) | Chiropractors, PTs |
| **Uplift Labs** [S30] | Markerless 3D biomechanics from iPhone | Marketing claims only (unverified) | Not public | Pro sports (MLB) |
| **PostureScreen Mobile** [S14] | Static posture from photos | Good intra/inter-rater reliability, but authors advise against research/serial use; validity vs Vicon poor [S14, S13] | Not checked | Fitness/health pros |

**[I] What this means.**
- Every SaaS niche (coaching, running, PT engagement) has funded incumbents.
- The research niche has a free, academically superior incumbent (OpenCap and now OpenCap Monocular).
- GaitScan cannot win on accuracy, features or distribution.
- It can only differentiate on:
  1. **on-device processing**: no video upload, so ethics approval is easier and there is no DPDP exposure for the video;
  2. **budget Android phones, Indian settings, browser-only**;
  3. **openly published test–retest/MDC numbers for repeat measurement**.

  OpenCap Monocular's deployment runs analysis in the cloud ("secure cloud computing") [S8], so point 1 is a real difference. It is also a modest one.

### 1.3 Verdict (Part 1)
- **Serve:** physio students and small-study researchers, plus individual physios using it as a free measurement aid. Individuals tracking themselves are a secondary audience.
- **Drop:** sports academies (unsupported claims plus minors), runners (crowded, unsupported claims), elderly-care fall screening (regulated plus weak evidence), and clinics as paying tenants.
- **[Q]** Have you spoken to any physiotherapist or physio faculty about this? Everything above about their needs is inferred from literature, not from your users.

---

## 2. Scientific feasibility (most important)

### 2.1 Literature summary [E]
- **Sagittal 2D from one camera is the best case.** Stenum et al. 2021 used OpenPose on single sagittal videos (25 Hz, 3.3 m) of 31 healthy adults vs 3D mocap [S1]:
  - temporal parameters within about 20 ms;
  - step length MAE 0.049 m, under 0.02 m for participant means, with a floor scale of 6.30 m;
  - gait speed within 0.04 m/s;
  - hip/knee/ankle MAE 4.0°/5.6°/7.4°.
- **Stenum et al. 2024 extended this to clinical groups and to change** (32 unimpaired, 44 post-stroke, 19 Parkinson's) [S2]:
  - sagittal step-time errors ≤ 0.01 s;
  - frontal views were clearly worse (step length up to 0.07 m, gait speed up to 0.15 m/s);
  - changes between preferred and fast walking were tracked (r ≥ 0.763).
- **MediaPipe specifically is more variable:**
  - Yang & Park 2024 (20 healthy young adults, OptiTrack reference) found MAE of 1.9–2.4° hip/knee at the best lateral position and 2.3–3.1° ankle at a 45° front-diagonal position [S5];
  - Menychtas et al. 2023 (17 healthy older adults, treadmill, 100 Hz sagittal camera) concluded MediaPipe "cannot be used for gait analyses in its current iteration": the ankle was "completely misidentified" and left/right sides were confused [S4];
  - Washabaugh et al. 2022 found OpenPose most accurate among open-source methods (hip 3.7°, knee 5.1° over the gait cycle) [S3].
- **Field-level caveat.** Open-source pose models were never designed for biomechanics and have inconsistent training labels [S6].
- **Frontal plane.** A systematic review with meta-analysis found 2D frontal-plane kinematic validity "generally low to moderate" and does not support it when accuracy matters [S9]. Specifically:
  - MediaPipe knee valgus at landing showed a bias of about −19° [S10];
  - for single-leg squats, 2D FPPA was not correlated with 3D at all [S51].

### 2.2 Metric-by-metric evidence table

Status key: **R** = reliable, **C** = conditional on a strict protocol, **U** = unreliable or unsupported for single-camera phone video.

| Metric | Reported error vs gold standard | Camera setup | Population | Source | Status |
|---|---|---|---|---|---|
| Sagittal knee angle (waveform / peak) | MAE 5.6° (OpenPose) [S1]; 2.4–2.8° (MediaPipe, best position) [S5]; 3.5–4.0° in PD/stroke [S2]; MediaPipe L/R confusion in older adults on treadmill [S4] | One camera, perpendicular, ~3 m, ≥25 fps | Healthy young/older, stroke, PD | S1, S2, S4, S5 | **C** (side view, single person, healthy or mild impairment; must be re-validated on *our* pipeline) |
| Sagittal hip angle | MAE 4.0° [S1]; 1.9–2.35° MediaPipe [S5]; 2.7–3.3° clinical [S2] | Same | Same | S1, S2, S5 | **C**. GaitScan's "hip" is a trunk–thigh angle (audit F34), so it must be redefined first. |
| Ankle angle | 7.4° (OpenPose) [S1]; MediaPipe "completely misidentified" [S4]; 3.06° only at a 45° oblique view [S5] | Contradictory | — | S1, S4, S5 | **U** for MediaPipe v1 |
| Cadence | Temporal errors ~20 ms ⇒ cadence error well under 1 step/min over steady walking [S1, I]; cadence ICC 0.74–0.95 (app vs markerless, knee OA, summary-level) [S54] | Side (also OK frontal) | Healthy, OA | S1, S2, S54 | **R** (steady-state walking, ≥ several strides) |
| Step time / stride time | 0–0.02 s sagittal; 0.01–0.05 s frontal [S2]; **but** step/stance time ICC ≈ 0 in one app study (summary-level) [S54] | Side; ≥ 25–30 fps | Healthy, stroke, PD | S1, S2, S54 | **C**. Depends on gait-event detection quality; 30 fps = 33 ms per frame [I]. |
| Stance / swing % | Within ~2 frames in mocap comparison [S1]; ICC ≈ 0 in one app [S54] | Side, ideally 60 fps | — | S1, S54 | **C → treat as U in v1** unless our validation shows otherwise |
| Step / stride length **with** floor calibration | 0.049 m per step; < 0.02 m participant mean [S1]; 0.02–0.03 m sagittal, up to 0.07 m frontal [S2] | Side + known floor distance in the walking plane | Healthy, clinical | S1, S2 | **C** |
| Step / stride length **without** calibration | No validation found. Monocular scale is ambiguous [I] | — | — | — | **U** (report only normalised to the body's own segment length, as a relative within-person value [I]) |
| Gait speed | ≤ 0.04 m/s (with scale) [S1]; up to 0.15 m/s frontal [S2] | Side + scale; or a timed distance | Healthy, clinical | S1, S2 | **C** (with calibration); **U** without |
| L/R symmetry (temporal, e.g. step-time asymmetry) | Derived from per-leg events; no direct validation found | Side | — | (S2 indirectly) | **C** |
| L/R symmetry (joint angles, one side view) | Far-leg occlusion; MediaPipe L/R confusion [S4] | One side view sees one leg clearly | — | S4 | **U**. GaitScan's current knee/hip "symmetry index" is in this category (plus audit F28). |
| Trunk lean (sagittal forward lean) | Limited direct evidence; one PD app report of ICC 0.93 (summary-level, source attribution unverified) | Side | PD | — | **C** (low evidence; leave out of v1) |
| Lateral trunk lean / frontal trunk | 2D frontal-plane validity low–moderate [S9] | Frontal | Athletes | S9 | **U** for v1 |
| Knee valgus (FPPA / medial knee displacement) | Bias ≈ −19°, LoA beyond 5° (MediaPipe) [S10]; no 2D–3D correlation in single-leg squat [S51]; low–moderate in review [S9] | Frontal | Athletes | S9, S10, S51 | **U** |
| Pelvic drop | No single-phone validation found; covered by the low–moderate frontal-plane review [S9] | Frontal | — | S9 | **U** |
| Static posture metrics (photo) | Good reliability for e.g. craniovertebral angle (pooled ICC 0.904) [S13]; PostureScreen validity vs Vicon poor; not for serial measurement [S14] | Standardised photos | Mixed | S13, S14 | **C** (screening only); out of scope for a gait tool |
| Static knee ROM (non-gait) | MediaPipe ICC ≥ 0.90, SEM 1.8°, MDC95 5.0° in Active Knee Extension test (summary-level) [S12] | Controlled pose | Healthy | S12 | **C**. Note this validates static ROM, not gait. |

**[I] Two cross-cutting caveats.**
1. Every number above is for *that study's* model, preprocessing and setup. GaitScan must measure its own error. Literature error is a prior, not a property of our code.
2. Most validations are in healthy, unimpaired adults. Errors grow in pathological gait [S2] and in older adults with MediaPipe [S4].

### 2.3 Map against what GaitScan computes or claims

From the code on `rebuild/phase-1-foundations` (`gaitcore/`, `app/`) and the plan (ADR-005/006, D5):

| Current or planned output | Where | Evidence status | Action |
|---|---|---|---|
| Knee symmetry index (on **mean** angle) | `gaitcore/legacy.py` | U (angle symmetry from one side view; also F28 math) | **Drop.** Replace with step-time asymmetry (C), if validated. |
| Hip symmetry index | `legacy.py` | U | **Drop** |
| Knee flexion "range" = 180 − min over the clip | `legacy.py`, `activity.py` | Method invalid (F27); the metric family is C | **Replace** with per-stride peak swing knee flexion (planned ADR-006) |
| Cadence (left-knee threshold crossings) | `legacy.py` | Method invalid (F24); metric is R | **Replace** with per-leg heel-strike cadence (planned) |
| Activity classification + "confidence" | `gaitcore/activity.py` | No validation; unstable (F30) | **Drop** (§3.1) |
| "Knee Drive", "Less-moving Side" findings | `legacy.py` | U (derived from invalid symmetry/min) | **Drop** |
| Mode-specific reference ranges (4 modes) | `legacy.py:MODE_CONFIGS` | Invented ("not clinically validated" in code) | **Drop** (§3.2) |
| Risk / deviation score (stored, hidden) | `legacy.py`, DB `risk_score` | No evidence (§2.4) | **Delete** from API and DB (ADR-005 already planned) |
| Exercise suggestions (+ optional LLM) | `app/services/exercises.py` | No clinical basis | **Drop** (§3.3, §3.4) |
| Hip angle plot (trunk–thigh) | `app/services/plots.py` | C after redefinition | Redefine or drop |
| Ankle trajectory plot | `plots.py` | Ankle U for MediaPipe | **Drop** |
| `shoulder_tilt` (computed, unused) | `gaitcore/angles.py` | Dead, wrong (F33) | **Delete** |
| Planned: stride time, stance %, step-time asymmetry | ADR-005/006 | C / C→U / C | Keep stride time; stance % only if our validation passes; asymmetry is C |
| Planned: ankle angle "if added" | D5 | U | **Don't add** |
| Planned: step length (calibrated) | D5 | C | Keep **only** with a floor-scale protocol; otherwise drop |
| Planned: quality gate (view, single person, visibility) | ADR-005/006 | Necessary for any C metric | **Keep; it's the most important feature** |

### 2.4 "Risk" and clinical interpretation: is any inference supported?

- **Falls.**
  - [E] Slower gait speed is associated with survival: pooled HR 0.88 per 0.1 m/s; 34,485 community-dwelling adults aged ≥ 65; 9 cohorts [S15].
  - [E] For falls, an individual-participant meta-analysis (7,608 participants, 28 studies; *conference abstract*) found that at < 0.8 m/s, accuracy is 58%, **sensitivity 35%**, specificity 77% (RR 1.27), concluding that "discriminative accuracy is low" [S17].
  - [E] TUG ≥ 13.5 s was not a significant fall predictor in community-dwelling older adults (OR 1.01) [S16].
  - [I] So population-level association exists, but *individual* fall-risk prediction is poor even with clinic-measured gait speed. The measurement GaitScan would provide (speed) is also the one that needs calibration.
- **Running injuries.**
  - [E] A systematic review of prospective studies found biomechanical risk-factor evidence "sparse and inconsistent" [S18].
- **ACL / knee valgus.**
  - [E] In 710 elite female soccer/handball players, 3D lab drop-jump valgus measures (including medial knee displacement) were a "poor screening test" for ACL injury [S19].
  - [I] If lab-grade 3D valgus doesn't predict injury, 2D phone valgus (which is not even valid [S9, S10]) cannot.
- **Plainly:** no published evidence supports inferring injury risk or individual fall risk from the metrics GaitScan can measure. The only defensible clinical-interpretation statement is descriptive, for example "gait speed of X m/s; published typical range for your age/sex is Y [S20]". Even that, if used to monitor a patient's condition, is a medical purpose under CDSCO [S33].

### 2.5 Your planned validation study (8–10 people, goniometer + phone video)

**Is that design meaningful? Partly. As described, it validates the wrong thing.**
- [I] A universal goniometer measures **static** angles. During walking the knee passes through ~60° in a fraction of a second, so you cannot goniometer it.
- A goniometer study validates static knee angle in held poses: a real but different claim, already published many times (e.g. [S12]).
- It says nothing about gait-event timing, cadence, or peak swing flexion.

**What would make it credible.** These recommendations are inferences [I] grounded in the cited designs.

| Element | Recommendation | Why / source |
|---|---|---|
| Primary claims | (1) Cadence and stride time; (2) peak swing knee flexion; (3) gait speed with floor scale. Static knee angle optional as a secondary "sanity" claim. | Matches §2.2 R/C metrics |
| Reference for timing/cadence | Frame-by-frame manual annotation of heel strike / toe-off by **2 independent annotators** at 60 fps (inter-rater agreement reported); manual step count | Cheap, high-quality ground truth for temporal metrics [I]; D5 already plans this |
| Reference for gait speed | Timed walk over a marked distance (stopwatch or video timestamps), plus a floor tape scale | Stenum's scaling method [S1] |
| Reference for dynamic knee angle | Best: a public dataset with synchronised video + mocap (OpenCap's [S7]; licence permitting). Practical in-house: an **electrogoniometer** (used by Parati et al. 2023, n = 66 [S11]) or **IMUs**, which have their own ~3–10° error vs optical mocap [S45], so report "agreement with IMU", not "accuracy" | Avoids comparing against a static tool |
| Sample size | Bland–Altman agreement studies have a median n of 65 (IQR 35–124) in PubMed [S43]. Use Lu et al.'s method [S41] (and Bonett 2002 for ICC precision, cited in [S43]) to justify n. **8–10 participants is a pilot**; plan ≥ 20–30 adults with ≥ 3 trials each and model repeated measures. | [S41, S43] |
| Sessions | Two sessions ≥ 2 days apart, same setup, for **test–retest ICC(2,1), SEM, MDC95**. This is the evidence base for longitudinal use (§3.6). | [S40], D5 |
| Statistics | MAE/RMSE; Bland–Altman bias ± 95% LoA (repeated-measures version); ICC form stated per Koo & Li (model/type/definition) [S40]; SEM; MDC95; **pre-specified acceptable LoA** (e.g. cadence ±2 steps/min, knee ±5°) before data collection | [S40, S44] |
| Conditions | Budget Android + one iPhone; 30 and 60 fps; at least two corridors/lighting conditions; one deliberately bad trial per subject (oblique) to test the quality gate | Your real differentiator [I] |
| Reporting | COSMIN standards for measurement-property studies [S44]; pre-register the protocol (e.g. on OSF) [I]; publish code and the anonymised landmark data (not video) | |
| Ethics | Institutional ethics committee approval and written consent. **[Q]** Does your college have an IEC/IRB that reviews student studies? | Required by most journals [I] |

**Is a student-grade validation study publishable, and where?**
- Small and moderate validation studies are routinely published:
  - Yang & Park 2024, n = 20, *Bioengineering* [S5];
  - Parati et al. 2023, n = 66, *Sensors* [S11];
  - an automated marker-free gait analysis in *Sensors* 2023 [S56];
  - a MediaPipe smartphone gait study with n = 155 from low-resource settings in *JMIR Formative Research* [S55].
- [I] A study with n ≥ 20, two sessions, pre-registration and open code is publishable in MDPI *Sensors*, *JMIR Formative Research* or *Gait & Posture* short communications. It could also go to an IEEE EMBC conference paper.
- Fees and acceptance are **unverified**; MDPI and JMIR charge APCs.
- Indian venues such as *Indian Journal of Physiotherapy & Occupational Therapy* and *Journal of Society of Indian Physiotherapists* exist to my knowledge, but **I did not verify their scope, indexing or fees**. Check indexing (Scopus/PubMed) before submitting; avoid predatory journals.
- A Springer proceedings chapter titled "Frontal Plane Gait Assessment Using MediaPipe Pose" exists (likely an Asian conference proceedings) [S57]; authors and venue are unverified.
- **[I] An honest framing that beats "we built an app"** is: *"Test–retest reliability and agreement of on-device browser pose estimation for spatiotemporal gait and sagittal knee kinematics using budget smartphones."*

---

## 3. Product shape

### 3.1 Activity classification
**Noise. Drop it.**
- [E] The audit showed a clean 110 spm walk classified "Unknown", its mirror "Brisk Walking", and label flips under tiny noise (F30).
- [I] No user needs the software to tell them whether the person walked or ran: the person recording knows. A classifier adds a failure mode and a validation burden (per-class precision/recall) for zero value. The protocol should simply say "walk".

### 3.2 Mode-specific reference ranges
- **Where they come from:**
  - [E, code] `gaitcore/legacy.py:MODE_CONFIGS` hard-codes thresholds and labels each mode "not clinically validated".
  - The audit found them contradictory across scoring, PDF and UI (F35). The **Elderly** and **Athlete** cadence ranges have no citation anywhere.
- **Real normative data exists:**
  - Gait speed by age and sex from a meta-analysis of 23,111 adults (143.4 cm/s men 40–49 down to 94.3 cm/s women 80–99) [S20].
  - Cadence ~100 steps/min as the moderate-intensity heuristic, 130 vigorous (CADENCE-Adults) [S21]. This is an *intensity* threshold, not a normality range [I].
  - Public kinematic datasets:
    - Fukuchi et al. 2018: 45 participants, 0.6–1.6 m/s, open on Figshare [S22];
    - 138 able-bodied adults across the lifespan plus 50 stroke [S23];
    - a multimodal dataset at multiple speeds [S24].
  - Sagittal gait kinematics depend strongly on speed, age, sex and BMI [S25b].
- **[I] Critical subtlety.** Normative angle data comes from marker-based models. A markerless 2D pipeline has its *own bias* (e.g. Yang & Park's MAE or [S4]'s systematic issues), so comparing a MediaPipe knee value to a mocap norm mixes method bias with real deviation. Ranges must therefore be:
  - speed-conditioned;
  - limited to spatiotemporal metrics (speed, cadence), where method bias is small;
  - or, for angles, derived from our own healthy-sample data with the same pipeline.

  Until then, show no "typical range" for angles. For a research/self-tracking tool, the person's own baseline is the most honest reference (§3.6).

### 3.3 Exercise suggestions
**A liability. Drop it.**
- [E] CDSCO classes software that informs or drives treatment as medical-device software by significance of information; "Treatment" is the top tier [S33].
- [I] Mapping a measurement to an exercise implies a condition and a treatment. GaitScan can't validate those links, and nothing in §2 supports them. It also contradicts the measurement-only framing already adopted in Phase 0.

### 3.4 LLM explanations (Groq)
**Value ≈ 0; risk > 0; privacy cost > 0. Remove the code, not just the flag.**
- [E] WHO's 2024 guidance on large multi-modal models in health lists hallucination, bias, automation bias and consent problems [S49].
- [I] The underlying findings aren't valid, so fluent prose about them amplifies invalid content.
- Sending health-related measurements to a third-party API makes Groq a processor under DPDP and needs a notice and a contract [S35]. That burden buys nothing.

### 3.5 PDF reports, clinician dashboard, invite codes, multi-tenancy
For the strongest user group (students and researchers, individual physios using it as a measurement aid):

| Feature | Needed in v1? | Note |
|---|---|---|
| Per-recording result with error bars + quality flags | **Yes** | Core |
| CSV/JSON export of per-stride values | **Yes** | Researchers live in spreadsheets/R [I] |
| Session comparison with an MDC indicator | **Yes** (after validation) | §3.6 |
| PDF report | Optional, simple | A print-to-PDF of the results page is enough [I] |
| Clinician dashboard, invite codes, patient linking | **No** | Implies patient monitoring (a medical purpose) [S33] and is complex |
| Multi-tenancy (orgs, memberships, audit log) | **No** | Only needed for a clinic SaaS (option A) |
| Accounts/login | **Probably no** | With on-device processing and local history, none are needed [I] |

### 3.6 Single analysis vs longitudinal tracking
- [E] Change detection has evidence:
  - Stenum 2024 showed pose-estimation-derived *changes* (preferred → fast walking) tracked the reference well, with r ≥ 0.763 for step length and speed changes [S2];
  - markerless test–retest MDC for knee angles ranges from below 3° (a 3D multi-pose system) [S52] to 1.6–9.9° across systems (summary-level) [S52];
  - MediaPipe static knee MDC95 is 5.0° [S12].
- [I] Why longitudinal is more defensible: absolute accuracy suffers from *systematic* bias, from the model, camera angle and the person's anatomy. Within one person, one phone and one marked setup, much of that bias repeats and cancels in a difference. What remains is random error, which MDC quantifies.
- Longitudinal claims are only honest if:
  1. MDC is measured on *our* pipeline (§2.5);
  2. the setup is enforced (same marks on the floor, distance, height, fps); the quality gate should compare setup fingerprints such as body height in pixels and walking-line angle;
  3. the UI says "change smaller than MDC: may be noise".
- So: single-shot absolute values with a reference range are the weakest product; repeat measures against your own baseline are the strongest.

### 3.7 Server-side vs on-device processing
- [E] MediaPipe Pose Landmarker runs in the browser via `@mediapipe/tasks-vision`, with a WASM runtime and a VIDEO running mode [S39].
- **[I] What changes if pose extraction moves to the browser** (the analysis step can stay in Python on landmark JSON, or move too):

| Concern | Server-side (current plan) | On-device pose (browser) |
|---|---|---|
| Raw health video | Uploaded, stored, TTL-deleted (ADR-003), validated (F07) | **Never leaves the device**. F06, F07 and F44 disappear for video. |
| Compute / memory on free tiers | 339–516 MB RSS, 28.7 s event-loop stall (F13, F14) → worker queue (ADR-002) | Landmark JSON analysis is milliseconds of numpy [I] → **no queue, no worker, no object storage** |
| Hosting cost | Web + worker + Postgres + R2 (~US$7+/month per ADR-002) | Static site (free tier) + optional tiny stateless API |
| DPDP exposure | Health-related video + landmarks processed by you as fiduciary or processor | If nothing is uploaded and there are no accounts, you may process no personal data at all (**legal reading unverified**). If landmarks are sent, that's still personal data, but much less than video. |
| Complexity | Python only | JS/TS pose loop + device variability (WebGL/CPU delegates, low-end Android speed: **unverified**, must be benchmarked) |
| Reproducibility | One server environment | Different devices may produce slightly different landmarks, so validation must use the browser pipeline on the phones you claim to support |
| Research use | Batch CLI easy | Keep a Python CLI with the *same* MediaPipe model for batch evaluation; check equivalence with a golden test |

- **ADR consequences:**
  - ADR-002 (job queue) is **superseded**;
  - ADR-003 (object storage) is **superseded**;
  - ADR-004 (tenancy) is **superseded** (no orgs/patients);
  - ADR-007 (consent/retention) is **rewritten** around study-participant consent and "no data leaves the device by default";
  - ADR-006 is **amended** (pose in browser; ankle dropped; metrics narrowed);
  - ADR-008 is **amended** (no job polling; client is a local-first SPA).
  - Two new ADRs are proposed: ADR-009 *On-device pose extraction* and ADR-010 *Intended use and claims policy* (see the V2 proposal).

---

## 4. Regulation and liability

### 4.1 India
**Medical device software (CDSCO):**
- [E] Since S.O. 648(E) of 11 Feb 2020, all medical devices, including software meeting the definition, are regulated under the Medical Devices Rules 2017 from 1 April 2020 [S34].
- [E] CDSCO's **Guidance Document on Medical Device Software**, Doc No. CDSCO/MD/GD/MDSW/01/2026, says it does not apply to software "merely intended for general wellness, promoting a healthy lifestyle, or measure body parameters only for regular tracking and fitness purposes … provided it is not intended for any medical purposes" [S33, §2.0].
- [E] General-wellness software "should not be making any reference to diseases or disorders or pathological conditions" [S33, §5.2 Note i].
- [E] "Software intended to measure, estimate, or report physiologic values for medical or clinical purposes, including screening, diagnosis, monitoring, alerting, or management of a disease or a disorder or a condition, shall NOT be considered as General Wellness Software" [S33, §5.2 Note ii].
- [E] Classification of standalone MDSW uses significance of information (Treatment/diagnosis, Drive clinical management, Inform clinical management) × condition severity (Critical/Serious/Non-serious), giving classes A–D. "To aid in diagnosis by analyzing relevant information to help predict **risk** of a disease or condition" is "Drive clinical management" [S33, §7.1].

[I] What this means for GaitScan:

| Framing | Likely status (inference, not legal advice) |
|---|---|
| "Measures cadence and knee angle from your walking video for personal tracking / education / research; not for any medical purpose" | General wellness / non-medical, so outside MDR-2017 |
| "Helps physiotherapists monitor patients' gait recovery" | Medical purpose (monitoring a condition), so MDSW, probably Class A or B ("Inform", non-serious/serious). Registration or licensing needed; **verify with a regulatory professional** |
| "Injury risk score", "fall risk", "detects abnormal gait" | MDSW, "Drive clinical management"/"Treatment or diagnosis", so Class A–C, plus a clinical-evidence dossier |

The Phase 0 copy (measurement framing plus a disclaimer) is necessary but **not sufficient**: the intended use is judged from the labelling, website and promotional material [S33, §7.0], including a README or resume that says "for physiotherapists to assess patients".

**DPDP Act 2023 / DPDP Rules 2025:**
- [E] The Act has **no separate "sensitive data" category**; all digital personal data is covered (s.2; no special-category provision in the text) [S35].
- [E] It omits IT Act s.43A (the old SPDI "sensitive data" regime) [S35, s.44(2)(a)].
- [E] "Child" means under 18 [S35, s.2(f)]. Section 9 requires verifiable parental consent and forbids "tracking or behavioural monitoring of children" [S35, s.9].
- [E] Penalties (Schedule):
  - up to ₹250 crore for failing reasonable security safeguards;
  - ₹200 crore each for breach-notification failures and for s.9 breaches [S35].
- [E] The DPDP Rules 2025 were notified on 13–14 Nov 2025 with phased commencement over 18 months; most fiduciary obligations apply ~May 2027 [S36] (timeline from secondary summaries of the PIB notice; **verify against the notification**).
- [I] With server-side processing and accounts, you are a Data Fiduciary for health-related video and must provide notice, consent, security safeguards, breach notification, erasure and grievance redress.
- [I] With on-device processing and no upload, most obligations may not arise for the core flow (unverified legal reading). Any **validation study** still collects personal data (video of participants), so it needs written consent, an IEC/IRB, secure storage and deletion: that's research ethics, not product compliance.
- [I] **Sports academies with minors are a hard no:** gait tracking of children is arguably "behavioural monitoring" under s.9 (unverified interpretation).

### 4.2 EU (if presented in Germany)
- [E] MDCG 2019-11 (rev.1, 2025) is the EU guidance for qualifying and classifying software. Software with only lifestyle or well-being purposes is not medical-device software (secondary summaries of the official EC document [S37]).
- [E] Rule 11 (MDR Annex VIII):
  - software providing information used for diagnostic or therapeutic decisions is **class IIa** (IIb/III if wrong decisions could cause serious deterioration or death);
  - software intended to monitor physiological processes is **class IIa** (IIb for vital parameters with immediate danger);
  - all other software is class I [S37, S38].
- [I] A tool for *monitoring patients' gait* would most likely be class IIa: a notified body, QMS (ISO 13485), IEC 62304, and clinical evaluation. That's impossible for a student.
- [I] A non-commercial research prototype presented academically, with an intended use of "research/education, not for medical purposes", is not "placed on the market" as a medical device. This is my reading; **verify** if you ever distribute it in the EU.
- The EU AI Act's classification of a non-medical pose tool was **not researched** (unverified). It is probably minimal risk, but check if relevant.

### 4.3 Wording rules (app, README, resume)

**May say:**
- "Measures cadence (steps/min), stride time and peak knee bend (degrees) from a side-view walking video."
- "Measured agreement in our study: cadence ±X steps/min, knee ±Y° (95% limits of agreement), n = N, side view, healthy adults." Only after the study, with the numbers.
- "For education, research and personal tracking. Not a medical device. Not for diagnosing, screening, monitoring or treating any disease or condition."
- "Processing happens on your device; the video is not uploaded." Only if true.
- Resume: "Built and validated an on-device markerless gait-measurement tool (MediaPipe, browser); test–retest ICC = …, MDC = …; preprint/paper …"

**Must not say** (in the app, README, store listing, posters or resume):
- risk, injury, fall, prevent, predict;
- diagnose, screen, detect, assess (a patient);
- abnormal, normal/healthy gait (as a judgement), deficit, impairment;
- rehabilitation outcome, recovery, treatment, exercise prescription;
- patient (in product copy), clinical-grade, medical-grade, FDA/CE/CDSCO-approved;
- "accurate" or "validated" without numbers and conditions;
- any condition name (Parkinson's, stroke, osteoarthritis, ACL, sarcopenia) as something the tool addresses;
- "AI-powered physiotherapist", "any angle", "CCTV".

---

## 5. What this project should be for you

Context: B.Tech AI/ML, graduating 2027, two papers, MS in AI/ML in Germany, limited time. Effort figures are my estimates [I]. Portfolio value is my judgement, not evidence about admissions committees.

| Option | Effort (from now) | Risk | Portfolio value (MS / jobs) | Real-world usefulness |
|---|---|---|---|---|
| **A. Physio/sports SaaS** (current plan) | ~180 h + regulatory work + sales (open-ended) | **High**: regulatory (§4), unsupported claims (§2.4), no users validated [Q] | Medium: impressive engineering, weak science story; risky if claims are scrutinised | Low unless clinics adopt it, which is unlikely for a solo student |
| **B. Narrow product** (one user, 2–3 reliable metrics, longitudinal) | ~80–100 h | Medium: without validation it's "yet another pose app" | Medium | Low–medium |
| **C. Research-first** (open-source tool + validation paper) | ~120 h + 6–10 weeks calendar time for ethics and data collection | Medium: ethics approval and recruitment; novelty vs OpenCap Monocular [S8] | **High for MS applications**: a third paper, open code and data, statistics literacy | Medium (researchers, educators) |
| **D. B + C combined** | ~130–150 h | Medium; scope creep is the main risk | **Highest**: paper + polished, privacy-first product + Phase 0–1 engineering maturity | Medium |
| **E. Stop now** | ~5–10 h (write-up, archive) | Low | Medium: Phases 0–1 already show audit, security fixes, CI, migrations, honest framing | None |

**Recommendation: D, executed research-first (C is the spine and B is the shell), with a hard gate.**

Why [I]:
1. For a German MS in AI/ML, evidence that you can **evaluate** an ML system against ground truth (agreement statistics, reliability, failure modes) is rarer and more convincing than another web app. It also fits your two existing papers.
2. On-device processing is both the honest product differentiator and the thing that kills the hardest infrastructure work (Phases 3–4). D is therefore *less* engineering than A, not more.
3. The narrowed product gives the paper a usable artefact and demo. The paper gives the product its only defensible claim.
4. **Gate.** If ethics approval or ≥ 20 participants is not realistic by about Feb 2027 [Q], fall back to E plus a short technical report on the Phase 0–1 audit. That is still a strong story ("I audited my own app, found it unsafe and unscientific, fixed what was fixable and stopped claiming what wasn't").

What I would **not** do: build the SaaS features first and validate later. The validation results decide which metrics survive, so they must come first.

---

## 6. Consequences for the rebuild

Summary (full detail in [`REBUILD_PLAN_V2_PROPOSAL.md`](REBUILD_PLAN_V2_PROPOSAL.md)):

| Existing phase | Verdict | Change |
|---|---|---|
| 2: Measurement core v2 | **Keep, shrink, re-target** | Same signal processing (pixel angles, gating, smoothing, events, quality gate), but the input is landmark JSON from the browser. Metrics narrowed to §2.3. Ankle, angle symmetry, classifier, modes and risk deleted. |
| 3: Async jobs + object storage | **Delete** | On-device pose removes video upload, storage, queue and worker |
| 4: Tenancy, auth, consent, deletion | **Delete most** | No orgs, patients or accounts. Consent work moves to the *study* (paper forms, IEC). App: local-first history + export + a "delete all local data" button. |
| 5: Validation harness | **Expand; becomes the core** | Ethics, pre-registration, ≥ 20 participants × 2 sessions, dynamic references, test–retest/MDC, paper |
| 6: Product & report | **Shrink** | Capture guidance + live quality gate, results with error bars, MDC-based session comparison, CSV export. No billing, no clinic PDF, no dashboard. |

ADRs:
- **005 kept and strengthened**: no angle reference ranges until method-matched.
- **006 amended.**
- **008 amended.**
- **002, 003, 004 superseded.**
- **007 rewritten.**
- **New:** 009 on-device pose; 010 intended-use and claims policy.

What from Phases 0–1 becomes unnecessary [I]:
- invite codes and clinician linking (F03 fixes become moot);
- the clinician dashboard;
- server-side upload validation;
- PDF regeneration from DB (F15 work);
- JWT auth, rate limiting and the users table, *if* accounts are dropped;
- Postgres/Alembic, if the stateless landmark API keeps no data.

None of it was wasted:
- it remains in git history as portfolio evidence;
- the CI, Docker, logging and redaction, type-checking and testing discipline carry over unchanged;
- the "fail closed" security work is still the right default for the small API that remains.

---

## 7. Sources

Peer-reviewed unless marked. "Summary-level" means I saw the abstract or search summary, not the full text.

- **S1** Stenum J, Rossi C, Roemmich RT. *Two-dimensional video-based analysis of human gait using pose estimation.* PLoS Comput Biol 2021;17(4):e1008935. https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1008935
- **S2** Stenum J, et al. *Clinical gait analysis using video-based pose estimation: Multiple perspectives, clinical populations, and measuring change.* PLOS Digital Health 2024. https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0000467
- **S3** Washabaugh EP, et al. *Comparing the accuracy of open-source pose estimation methods for measuring gait kinematics.* Gait & Posture 2022;97:188–195. https://www.researchgate.net/publication/362779933_Comparing_the_accuracy_of_open-source_pose_estimation_methods_for_measuring_gait_kinematics (summary-level; MediaPipe-specific numbers not obtained)
- **S4** Menychtas D, et al. *Gait analysis comparison between manual marking, 2D pose estimation algorithms, and 3D marker-based system.* Front Rehabil Sci 2023;4:1238134. https://pmc.ncbi.nlm.nih.gov/articles/PMC10511642/
- **S5** Yang J, Park K. *Improving Gait Analysis Techniques with Markerless Pose Estimation Based on Smartphone Location.* Bioengineering 2024;11(2):141. https://pmc.ncbi.nlm.nih.gov/articles/PMC10886083/
- **S6** Wade L, Needham L, McGuigan P, Bilzon J. *Applications and limitations of current markerless motion capture methods for clinical gait biomechanics.* PeerJ 2022. https://peerj.com/articles/12995/
- **S7** Uhlrich SD, et al. *OpenCap: Human movement dynamics from smartphone videos.* PLoS Comput Biol 2023;19(10):e1011462. https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1011462
- **S8** Gilon S, Miller EY, Uhlrich SD. *OpenCap Monocular: 3D Human Kinematics and Musculoskeletal Dynamics from a Single Smartphone Video.* **Preprint**, 2026-03-25. https://www.alphaxiv.org/abs/2603.24733
- **S9** *Reliability and Validity of Frontal Plane Kinematics of the Trunk and Lower Extremity Measured With 2-Dimensional Cameras During Athletic Tasks: A Systematic Review With Meta-analysis.* JOSPT 2018. https://www.jospt.org/doi/10.2519/jospt.2018.8006 (summary-level)
- **S10** *Reliability and validity of knee valgus angle calculation at single-leg drop landing by posture estimation using machine learning.* Heliyon 2024. https://www.sciencedirect.com/science/article/pii/S2405844024123699 (summary-level)
- **S11** Parati M, et al. *Video-based Goniometer Applications for Measuring Knee Joint Angles during Walking in Neurological Patients: A Validity, Reliability and Usability Study.* Sensors 2023;23(4):2232. https://pmc.ncbi.nlm.nih.gov/articles/PMC9960424/
- **S12** *Reliability and Validity of AI-Based Pose Estimation Algorithms for Assessing Lower-Limb Flexibility and Joint Range of Motion.* Sensors 26(18):5890. https://www.mdpi.com/1424-8220/26/18/5890 (summary-level)
- **S13** *Photogrammetry-based smartphone applications for spinal posture assessment: a systematic review and meta-analysis.* Sci Rep 2025. https://www.nature.com/articles/s41598-025-32708-1 (summary-level)
- **S14** Hopkins et al. *Validity of PostureScreen Mobile® in the Measurement of Standing Posture.* https://www.semanticscholar.org/paper/Validity-of-PostureScreen-Mobile%C2%AE-in-the-of-Posture-Hopkins/94e1c3c4a35ac7b059a382f9627e69df0f6a874f (summary-level)
- **S15** Studenski S, et al. *Gait speed and survival in older adults.* JAMA 2011;305(1):50–58. https://www.semanticscholar.org/paper/Gait-speed-and-survival-in-older-adults.-Studenski-Perera/25de2f67035336224c9f1e37f58c5b531d34b9ed
- **S16** Barry E, et al. *Is the Timed Up and Go test a useful predictor of risk of falls in community dwelling older adults: a systematic review and meta-analysis.* BMC Geriatr 2014;14:14. https://link.springer.com/article/10.1186/1471-2318-14-14
- **S17** Hicks C, Menant J, Lord SR. *Predictive accuracy of gait speed for falls: an individual participant data meta-analysis.* **Conference abstract** (British Geriatrics Society). https://www.bgs.org.uk/predictive-accuracy-of-gait-speed-for-falls-an-individual-participant-data-meta-analysis
- **S18** Ceyssens L, et al. *Biomechanical Risk Factors Associated with Running-Related Injuries: A Systematic Review.* Sports Med 2019;49:1095–1115. https://link.springer.com/article/10.1007/s40279-019-01110-z
- **S19** Krosshaug T, et al. *The Vertical Drop Jump Is a Poor Screening Test for ACL Injuries in Female Elite Soccer and Handball Players.* Am J Sports Med 2016. https://doi.org/10.1177/0363546515625048
- **S20** Bohannon RW, Williams Andrews A. *Normal walking speed: a descriptive meta-analysis.* Physiotherapy 2011;97(3):182–189. https://www.csp.org.uk/journal/article/physiotherapy-september-2011/normal-walking-speed-descriptive-meta-analysis
- **S21** Tudor-Locke C, et al. *Walking cadence (steps/min) and intensity in 21–40 year olds: CADENCE-adults.* IJBNPA 2019. https://pmc.ncbi.nlm.nih.gov/articles/PMC6337834/
- **S22** Fukuchi CA, Fukuchi RK, Duarte M. *A public dataset of overground and treadmill walking kinematics and kinetics in healthy individuals.* PeerJ 2018;6:e4640. https://www.researchgate.net/publication/324730233_A_public_dataset_of_overground_and_treadmill_walking_kinematics_and_kinetics_in_healthy_individuals
- **S23** *A full-body motion capture gait dataset of 138 able-bodied adults across the life span and 50 stroke survivors.* Sci Data 2023. https://www.nature.com/articles/s41597-023-02767-y
- **S24** *A multimodal dataset of human gait at different walking speeds established on injury-free adult participants.* Sci Data 2019. https://www.nature.com/articles/s41597-019-0124-4
- **S25b** *Lower limb sagittal gait kinematics can be predicted based on walking speed, gender, age and BMI.* Sci Rep 2019. https://www.nature.com/articles/s41598-019-45397-4 (summary-level)
- **S25** Ochy: App Store listing https://apps.apple.com/us/app/running-gait-analysis-ochy/id1531481638 and https://www.ochy.io/runners
- **S26** OnForm: https://onform.com/sports/physical-therapy/ ; pricing from App Store listing https://apps.apple.com/us/app/onform-video-analysis-app/id1490334045
- **S27** Kinovea: https://www.kinovea.org/ ; *Validity and reliability of the Kinovea program in obtaining angles and distances using coordinates in 4 perspectives.* PLoS ONE 2019. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6550386/
- **S28** Exer: https://www.exer.ai/product/modules ; launch PR https://www.prnewswire.com/news-releases/exer-launches-gait-and-physio-mobile-apps-to-expand-ai-powered-digital-health-platform-301398864.html
- **S29** Kinetisense validation report (vendor-hosted, University of Calgary): https://www.kinetisense.com/wp-content/uploads/2019/11/3D-Balance-and-KAMS-Detailed-Report-University-of-Calgary-1.pdf (summary-level; not peer-reviewed)
- **S30** Uplift Labs: https://www.uplift.ai/
- **S31** Dartfish/Hudl comparison blog (third-party; price **unverified**): https://blog.callplaybook.com/blog/coach-video-review-software-hudl-dartfish-alternatives
- **S32** Kanko RM, et al. *Concurrent assessment of gait kinematics using marker-based and markerless motion capture.* J Biomech 2021;127:110665. Preprint: https://www.biorxiv.org/content/10.1101/2020.12.10.420075.full.pdf
- **S33** CDSCO. *Guidance Document on Medical Device Software*, Doc No. CDSCO/MD/GD/MDSW/01/2026 (read in full text; sections 2.0, 5.2, 7.0–7.1 quoted). https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/Guidance-document-on-Medical-Device-Software-under-MDR-2017.pdf
- **S34** CDSCO. *Medical Devices Rules, 2017.* https://cdsco.gov.in/opencms/opencms/en/Acts-and-rules/Medical-Devices-Rules/ ; the S.O. 648(E) 11 Feb 2020 summary via https://www.freyrsolutions.com/blog/regulation-of-software-as-medical-device-samd-in-india (secondary)
- **S35** *The Digital Personal Data Protection Act, 2023* (No. 22 of 2023), Gazette text via MeitY (read in full text; s.2(f), s.9, s.44(2)(a), Schedule quoted). https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf
- **S36** *DPDP Rules, 2025 notified* (PIB document): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf (phase timeline from secondary summaries, e.g. https://www.scrut.io/post/dpdp-rules; **verify**)
- **S37** MDCG 2019-11 rev.1, *Guidance on Qualification and Classification of Software in Regulation (EU) 2017/745 – MDR and Regulation (EU) 2017/746 – IVDR.* https://health.ec.europa.eu/document/download/b45335c5-1679-4c71-a91c-fc7a4d37f12b_en?filename=md_mdcg_2019_11_guidance_qualification_classification_software_en.pdf (content from secondary summaries; the PDF itself not parsed)
- **S38** Rule 11 interpretation, Johner Institute: https://blog.johner-institute.com/regulatory-affairs/mdr-rule-11/ (secondary; Rule 11 wording matches the search-reported regulation text)
- **S39** Google AI Edge. *Pose landmark detection guide for Web.* https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/web_js
- **S40** Koo TK, Li MY. *A Guideline of Selecting and Reporting Intraclass Correlation Coefficients for Reliability Research.* J Chiropr Med 2016;15(2):155–163 (erratum: https://pmc.ncbi.nlm.nih.gov/articles/PMC5731844). https://www.semanticscholar.org/paper/A-Guideline-of-Selecting-and-Reporting-Intraclass-Koo-Li/33122fc2f544888a0f46dd221a783ad1ecc1ddad
- **S41** Lu MJ, et al. *Sample Size for Assessing Agreement between Two Methods of Measurement by Bland–Altman Method.* Int J Biostat 2016;12(2). https://www.degruyterbrill.com/document/doi/10.1515/ijb-2015-0039/html
- **S43** *A descriptive study of samples sizes used in agreement studies published in the PubMed repository.* BMC Med Res Methodol 2022. https://link.springer.com/article/10.1186/s12874-022-01723-5
- **S44** Mokkink LB, et al. *The COSMIN checklist for evaluating the methodological quality of studies on measurement properties: a clarification of its content.* BMC Med Res Methodol 2010;10:22. https://link.springer.com/article/10.1186/1471-2288-10-22
- **S45** *Body-worn inertial measurement units track knee flexion angles with similar accuracy to optical motion capture.* 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12633563/ (summary-level; IMU error ranges from the search summary)
- **S46** *Reliability of videotaped observational gait analysis in patients with orthopedic impairments.* BMC Musculoskelet Disord 2005;6:17. https://link.springer.com/article/10.1186/1471-2474-6-17 ; Eastlack et al. 1991 cited therein (summary-level)
- **S47** *Evidence-based practice among physiotherapists in India: a nationwide survey of knowledge, attitude, and implementation behavior.* https://pmc.ncbi.nlm.nih.gov/articles/PMC12882727/ (summary-level)
- **S48** *A qualitative study exploring physiotherapists' insights on the design and development of technology-enhanced gait and balance assessment systems for older adults.* https://pmc.ncbi.nlm.nih.gov/articles/PMC12344322 (summary-level)
- **S49** WHO. *Ethics and governance of artificial intelligence for health: Guidance on large multi-modal models* (18 Jan 2024). Repository listing: https://resources.physio-pedia.com/resource/ethics-and-governance-of-artificial-intelligence-for-health-guidance-on-large-multi-modal-models/ ; summary: https://www.dataprivacyandsecurityinsider.com/2024/02/who-publishes-guidance-for-ethics-and-governance-of-ai-for-healthcare-sector/
- **S50** *Comparison of different symmetry indices for the quantification of dynamic joint angles.* BMC Sports Sci Med Rehabil 2021. https://bmcsportsscimedrehabil.biomedcentral.com/articles/10.1186/s13102-021-00355-4 ; *Assessing functional load symmetry: a case for a 15% threshold in healthy young adults.* https://pubmed.ncbi.nlm.nih.gov/41422617/ (both summary-level; they show the 10% SI threshold is arbitrary)
- **S51** *Concurrent Validity and Reliability of Two-dimensional Frontal Plane Knee Measurements during Multi-directional Cutting Maneuvers.* IJSPT. https://pubmed.ncbi.nlm.nih.gov/35136683/ (summary-level; the single-leg-squat no-correlation finding came from the same search summary)
- **S52** *Validation of a 3D Markerless Motion Capture Tool Using Multiple Pose and Depth Estimations for Quantitative Gait Analysis.* https://pmc.ncbi.nlm.nih.gov/articles/PMC11597901/ (summary-level; MDC range 1.6–9.9° across markerless systems from the same search summary, original source not confirmed)
- **S54** *Gait assessment using a 2D video-based pose estimation app in comparison to a markerless motion capture system in subjects with osteoarthritis of the knee – a pilot study.* https://pmc.ncbi.nlm.nih.gov/articles/PMC13454463/ (summary-level)
- **S55** *Video-Based Gait Assessment Using Machine Learning to Classify Age and Sex in Low-Resource Settings: Cross-Sectional Study.* JMIR Form Res. https://doi.org/10.2196/76755 (summary-level)
- **S56** *Automated Gait Analysis Based on a Marker-Free Pose Estimation Model.* Sensors 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC10384445/
- **S57** *Frontal Plane Gait Assessment Using MediaPipe Pose* (Springer proceedings chapter). https://link.springer.com/chapter/10.1007/978-981-97-0142-1_34 (authors and venue **unverified**; paywalled)

Internal sources: `_audit/GAITSCAN_AUDIT.md` (findings F01–F44), `_audit/REBUILD_PLAN.md` (D5, D6), `_audit/adr/001–008`, `gaitcore/legacy.py`, `gaitcore/activity.py`, `app/services/exercises.py` on `rebuild/phase-1-foundations`.

---

## 8. Questions only Kanveer can answer

1. **Users.** Have you talked to any physiotherapist, physio faculty member or coach about GaitScan? What did they say they would actually use? Is there a named person who would try it?
2. **Goal priority.** Is the main goal (a) MS admission in Germany, (b) a startup, or (c) a useful open tool? Rank them. The recommendation assumes (a) > (c) > (b).
3. **Time.** Realistic hours per week until your MS applications. Which intake are you targeting (winter 2027/28?), and what are the deadlines for your shortlisted programmes?
4. **Ethics.** Does your college have an Institutional Ethics Committee that reviews student human-subject studies? How long does approval take?
5. **Participants and equipment.**
   - Can you recruit ≥ 20 adults for two sessions?
   - Do you have access to a physio department, IMUs, an electrogoniometer or any motion-capture lab (even at a nearby institute)?
   - Which phones (models, fps) can you use?
6. **Co-authorship and supervision.** Is there a faculty member (yours or physio) who would supervise or co-author? Most journals expect one for a human-subject study.
7. **Production reality.**
   - Does the live app have real users or real patient data today?
   - Does production use SQLite or Postgres (Phase 1 human action 2)?
   - Any data you must keep or delete?
8. **Publication budget.** Can you pay an APC (MDPI/JMIR charge one), or do you need a no-fee venue or a preprint plus a conference?
9. **Open source.** Are you willing to release the code and the anonymised landmark data under an open licence?
10. **Your existing papers.** What are they on? If they're in CV/pose or health ML, D fits your narrative; if not, decide whether gait is the story you want to tell.
11. **The SaaS idea.** Is there any commercial commitment (co-founder, incubator, client, grant) that would make dropping option A costly?
