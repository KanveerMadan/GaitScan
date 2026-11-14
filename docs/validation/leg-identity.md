# Leg identity on LJMU by visual annotation (Phase 11, decision A): not measurable

Date: 2026-11-14. Tooling: `evaluation/leg_identity.py`.

## Plan (owner decision A, 2026-11-14)
Annotate which leg is which on ~40 LJMU clips × 8 frames, AI-annotated and cross-checked. Then score
MediaPipe's left/right labels and GaitScan's naming rule for the untangled legs against it (the near leg
is the more visible one; someone walking towards image +x shows the camera their right side), and unlock
per-side values only if the D2 gate passes (≥ 95%).

## What was done
`python -m evaluation.leg_identity sheets` made 42 blind contact sheets, 295 tiles. Each tile is a
frame where the feet pass each other, cropped to the legs, raw and with MediaPipe's two leg chains
in red and blue (colours randomised per tile). The visible truth was to be which leg is in front,
occluding the other.

## Finding
Three participants' sheets were inspected before annotating the rest (P13, P37, P51):
- In most participants **both legs wear the same trousers and shoes**, and at 30 fps the passing legs
  are **motion-blurred**. Which leg is in front can't be judged reliably in most tiles.
- Distinguishing marks (P37's torn knee) exist for a few participants, in a few frames. Annotating only
  those would be a biased sample.

A truth that is mostly guesses can't validate a 95% gate, so the annotation wasn't completed.
**Result: leg identity can't be measured this way on LJMU. Per the owner's rule, per-side values and
symmetry verdicts stay hidden** (v1 uses the label-free, both-legs measures of BE-A2).

## What could work
LJMU also has a second camera (`_45` clips, placed opposite the start of the odd-numbered tasks). In a
front-on or oblique view the two legs are side by side, so left and right are easy to see. If its clips
can be time-aligned with the side-view clips (by their step events, which both show), legs labelled in
that view could be carried over to the side view. This is the only route found to a credible
leg-identity truth in LJMU, and it needs the owner's go-ahead.
