# Capture protocol

How to film a walk so GaitScan can measure it. The measurements are 2D, taken in the image plane, so
they only mean something for videos filmed this way. The recording checks (`gaitcore/quality.py`)
catch the clearest problems and say what to change. They can't catch every problem.

## Set-up
1. **Side-on.** Point the phone at right angles to the walking line. A diagonal view makes the walk
   look shorter and the recording checks turn it down as not side-on.
2. **Landscape**, held still: on a tripod, a shelf or propped on something, at about **waist
   height**.
3. **3–4 m from the walking line**, so the whole body fits with room at both sides. This distance is
   a guideline for a typical phone lens; it has not been validated.
4. **30 frames per second or more** (the phone's normal video mode). Under 24 fps is rejected.
5. Even light, with the light behind the camera rather than behind the person. Clothes that stand
   out from the floor and background. Nothing in front of the legs.

## The walk
1. Walk **across the frame and back** at your usual pace, for **10–20 seconds** in total. Turns
   are fine: the analysis finds the steady part of each pass and leaves out speeding up, slowing
   down and turning.
2. Keep the **whole body in view, including both feet**, for as much of the walk as you can.
3. Film **only the person walking**. If someone else crosses the frame, or the feet leave the
   picture, for a step or more, that part is left out and the rest is measured. The video is only
   turned down when too little walking is left (the reason names the cause).

## What the checks look for
| Check | Passes when |
|---|---|
| Length | at least 3 s of video |
| Frame rate | at least 24 fps |
| Person | a person is detected in at least 10 frames |
| Orientation | the person is upright on screen (trunk within 45° of vertical) |
| Side-on view | the shoulders look narrow (side-on) and the ankle and shoulder paths run parallel (an angle of at most 4.8° between them) |
| Steps | at least 6 steps in the steady walking. Fewer, despite ≥ 4 s of steady walking, means the legs couldn't be followed (light, clothing, view) |
| Regular steps | step times vary by at most 15% (SD / mean); more usually means spurious steps were detected |

Each check's basis (literature, physics or data) is in the table at the top of
`gaitcore/quality.py`. The side-on and regular-step thresholds were chosen on the LJMU dataset
(Topham et al. 2023, CC BY 4.0), not on phone videos.

## Optional: floor calibration
Step length and walking speed need a known distance on the floor. Put two marks (for example tape)
on the floor along the walking line, as far apart as possible, measure the distance between them,
and tap the marks on a frame of the video when the app asks. These two measurements are labelled
**not yet validated**: they have been checked only on simulated walking.

## What isn't supported
- Treadmill walking (the pelvis doesn't cross the frame; rejected as an unconfirmed view).
- Front or back views, and videos filmed while moving the phone.
- Walking aids or assistance haven't been tested; results may be wrong without warning.
