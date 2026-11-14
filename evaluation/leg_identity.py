"""Leg identity on LJMU (Plan V3 Phase 11, decision A): `make leg-identity-sheets`, then annotate, then
`make leg-identity`.

Data: LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0), side-view clips.

Truth that can be seen in a frame: as the feet pass each other, which leg is in front, occluding the
other. The front leg is the one nearer the camera. A person walking towards image +x shows the camera
their right side (forward x up = right points at the camera), so the near leg is the right leg when
walking towards +x and the left leg towards -x, for a video that isn't mirrored.

Two things are scored against that:
1. MediaPipe's labels: is the chain it labels "R" the right leg?
2. GaitScan's naming rule for the untangled legs (gaitcore.kinematics, decision B): the near leg is the
   untangled leg whose knee, ankle, heel and toe are more visible over the run (the far leg is partly
   hidden by the body); then near = right when walking towards +x.

`sheets` writes one contact sheet per clip (8 frames where the feet pass, from heel-separation minima
between label-free strikes): each tile is the raw crop of the legs next to the same crop with MediaPipe's
two chains drawn in red and blue, the colours randomised per tile so the annotation is blind to the
labels. The key (`key.csv`, colour of the "L" chain, direction, the naming rule's near chain) is written
alongside; annotations go in `evaluation/leg_identity_annotations.csv` (clip, tile, front: red | blue |
unclear). `score` joins them. Sheets show participants, so they stay in data/ (git-ignored).
"""

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from typing import Any

import numpy as np

from gaitcore.gait import contact_runs, heel_separation, leg_length
from gaitcore.kinematics import TIE_LEGS, _front_heel_speed, _heel_strike, _raw_chains, _untangle
from gaitcore.pipeline import analyse, walking
from gaitcore.signals import SIDES, build_tracks

HERE = os.path.dirname(os.path.abspath(__file__))
ANNOTATIONS = os.path.join(HERE, "leg_identity_annotations.csv")
TILES = 8
SEED = 20261114
LEG_IDX = {s: [SIDES[s][n] for n in ("hip", "knee", "ankle", "heel", "toe")] for s in ("L", "R")}
VIS = ("knee", "ankle", "heel", "toe")


def passing_frames(clip: Any) -> list[dict[str, Any]]:
    """Frames where the feet pass (heel separation lowest between two strikes), with what the scoring
    needs: walking direction and, from the untangling, which labelled chain is the near leg."""
    tracks = build_tracks(clip)
    leg_px = leg_length(tracks)
    if not math.isfinite(leg_px):
        return []
    sep = heel_separation(clip, leg_px)
    out = []
    for seg in walking(clip, tracks, leg_px).segments:
        ch = _raw_chains(clip, tracks, seg.direction)
        speed = _front_heel_speed(ch, clip.fps, leg_px)
        for run in contact_runs(sep, seg, clip.fps):
            step = float(np.median(np.diff(run))) * clip.fps
            frames = [_heel_strike(speed, int(round(t * clip.fps)), step, seg) for t in run]
            if len(frames) < 3:
                continue
            pick = _untangle(ch, frames, TIE_LEGS * leg_px)
            if pick is None:
                continue
            c0 = frames[0]
            rows = np.arange(c0, c0 + len(pick))
            vis = {
                s: clip.landmarks[[f"lm{SIDES[s][n]}_vis" for n in VIS]].to_numpy(float)[rows].mean(axis=1)
                for s in ("L", "R")
            }
            # Visibility of untangled leg P (chain pick) and Q (the other) over the run.
            p_vis = np.where(pick == 0, vis["L"], vis["R"]).mean()
            q_vis = np.where(pick == 0, vis["R"], vis["L"]).mean()
            near_is_p = bool(p_vis >= q_vis)
            for a, b in zip(frames, frames[1:], strict=False):
                window = sep[a + 1 : b]
                if not np.isfinite(window).any():
                    continue
                f = int(a + 1 + int(np.nanargmin(window)))
                p_chain = "L" if pick[f - c0] == 0 else "R"
                near_chain = p_chain if near_is_p else ("R" if p_chain == "L" else "L")
                out.append(
                    {
                        "frame": f,
                        "direction": seg.direction,
                        "rule_near_chain": near_chain,
                        "visibility_gap": round(float(abs(p_vis - q_vis)), 3),
                    }
                )
    return out


def _crop_box(lm: Any, f: int, w: int, h: int, leg_px: float) -> tuple[int, int, int, int]:
    xs, ys = [], []
    for s in ("L", "R"):
        for i in LEG_IDX[s]:
            xs.append(lm[f"lm{i}_x"].iloc[f] * w)
            ys.append(lm[f"lm{i}_y"].iloc[f] * h)
    x0, x1 = min(xs) - 0.5 * leg_px, max(xs) + 0.5 * leg_px
    y0, y1 = min(ys) - 0.25 * leg_px, max(ys) + 0.2 * leg_px
    return int(max(0, x0)), int(max(0, y0)), int(min(w, x1)), int(min(h, y1))


def sheets(clips: list[str], landmark_dirs: list[str], videos: str, out: str) -> None:
    import cv2

    from evaluation.evaluate import load_clip

    rng = np.random.default_rng(SEED)
    os.makedirs(out, exist_ok=True)
    key_rows = []
    for name in clips:
        clip = load_clip(name, landmark_dirs, None)
        if clip is None or not analyse(clip).accepted:
            continue
        cands = passing_frames(clip)
        if not cands:
            continue
        chosen = [cands[int(i)] for i in np.linspace(0, len(cands) - 1, min(TILES, len(cands))).round()]
        tracks = build_tracks(clip)
        leg_px = leg_length(tracks)
        cap = cv2.VideoCapture(os.path.join(videos, f"{name}.mp4"))
        tiles = []
        for t, c in enumerate(chosen):
            cap.set(cv2.CAP_PROP_POS_FRAMES, c["frame"])
            ok, img = cap.read()
            if not ok:
                continue
            h, w = img.shape[:2]
            x0, y0, x1, y1 = _crop_box(clip.landmarks, c["frame"], w, h, leg_px)
            raw = img[y0:y1, x0:x1].copy()
            drawn = raw.copy()
            red_is = "L" if rng.random() < 0.5 else "R"
            colour = {red_is: (0, 0, 255), ("R" if red_is == "L" else "L"): (255, 120, 0)}
            for s in ("L", "R"):
                pts = [
                    (
                        int(clip.landmarks[f"lm{i}_x"].iloc[c["frame"]] * w - x0),
                        int(clip.landmarks[f"lm{i}_y"].iloc[c["frame"]] * h - y0),
                    )
                    for i in LEG_IDX[s]
                ]
                for p, q in zip(pts, pts[1:], strict=False):
                    cv2.line(drawn, p, q, colour[s], 1, cv2.LINE_AA)
                for p in pts:
                    cv2.circle(drawn, p, 2, colour[s], -1, cv2.LINE_AA)
            scale = 300 / max(1, raw.shape[0])
            pair = np.hstack(
                [cv2.resize(raw, None, fx=scale, fy=scale), cv2.resize(drawn, None, fx=scale, fy=scale)]
            )
            label = "ABCDEFGH"[t]
            cv2.putText(pair, label, (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
            tiles.append(pair)
            key_rows.append({"clip": name, "tile": label, **c, "red_is": red_is})
        cap.release()
        if not tiles:
            continue
        width = max(x.shape[1] for x in tiles)
        tiles = [np.pad(x, ((0, 0), (0, width - x.shape[1]), (0, 0))) for x in tiles]
        rows = [
            np.hstack(tiles[i : i + 4] + [np.zeros_like(tiles[0])] * (4 - len(tiles[i : i + 4])))
            for i in range(0, len(tiles), 4)
        ]
        cv2.imwrite(os.path.join(out, f"{name}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    with open(os.path.join(out, "key.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(key_rows[0]))
        wr.writeheader()
        wr.writerows(key_rows)
    print(f"{len({r['clip'] for r in key_rows})} sheets, {len(key_rows)} tiles -> {out}")


def score(key_path: str, annotations: str = ANNOTATIONS) -> dict[str, Any]:
    key = {(r["clip"], r["tile"]): r for r in csv.DictReader(open(key_path))}
    rows = []
    for a in csv.DictReader(open(annotations)):
        k = key.get((a["clip"], a["tile"]))
        if k is None or a["front"] not in ("red", "blue"):
            continue
        front_chain = k["red_is"] if a["front"] == "red" else ("R" if k["red_is"] == "L" else "L")
        near_side = "R" if float(k["direction"]) > 0 else "L"
        rows.append(
            {
                "clip": a["clip"],
                "mediapipe_correct": front_chain == near_side,
                "rule_correct": front_chain == k["rule_near_chain"],
                "visibility_gap": float(k["visibility_gap"]),
            }
        )
    per_clip: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        per_clip[str(r["clip"])].append(r)
    unclear = sum(1 for a in csv.DictReader(open(annotations)) if a["front"] == "unclear")
    out = {
        "frames_scored": len(rows),
        "frames_unclear": unclear,
        "clips": len(per_clip),
        "mediapipe_labels_correct": round(float(np.mean([r["mediapipe_correct"] for r in rows])), 3),
        "naming_rule_correct": round(float(np.mean([r["rule_correct"] for r in rows])), 3),
        "clips_with_every_frame_named_right_by_rule": sum(
            all(r["rule_correct"] for r in v) for v in per_clip.values()
        ),
        "clips_with_every_frame_labelled_right_by_mediapipe": sum(
            all(r["mediapipe_correct"] for r in v) for v in per_clip.values()
        ),
    }
    return out


def main() -> None:
    from evaluation.evaluate import load_reference

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("command", choices=("sheets", "score"))
    p.add_argument("--landmarks", nargs="+", default=[])
    p.add_argument("--videos", default="data/ljmu/videos")
    p.add_argument("--out", default="data/ljmu/leg_identity")
    p.add_argument("--clips", type=int, default=40)
    args = p.parse_args()
    if args.command == "sheets":
        by_participant: dict[int, list[str]] = defaultdict(list)
        for r in load_reference():
            by_participant[r.participant].append(r.clip)
        order = [c for k in sorted(by_participant) for c in sorted(by_participant[k])[:1]]
        order += [c for k in sorted(by_participant) for c in sorted(by_participant[k])[1:]]
        sheets(order[: args.clips + 10], args.landmarks, args.videos, args.out)
    else:
        result = score(os.path.join(args.out, "key.csv"))
        with open(os.path.join(HERE, "results", "leg_identity.json"), "w") as f:
            json.dump(result, f, indent=1)
            f.write("\n")
        print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
