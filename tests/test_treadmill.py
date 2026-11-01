"""Treadmill mode (Plan V3 Phase 9): a walk on a treadmill filmed side-on. The walker stays in place,
so the overground pass finder (steady walking across the frame) finds nothing; the treadmill test
measures the stretches where the pelvis stays put instead. The belt speed is entered by the user and
gives step length (speed x step time). Not validated: every value says so."""

import pytest
from conftest import auth, fake_video, register
from synthetic import synthetic_clip

from gaitcore.accuracy import NOT_YET_VALIDATED
from gaitcore.pipeline import analyse
from gaitcore.result import TREADMILL, WALK


def belt(**kw):
    return synthetic_clip(treadmill=True, passes=1, pass_secs=12.0, ramp_secs=0.5, **kw)


@pytest.mark.parametrize("cadence", [90.0, 110.0, 125.0])
def test_a_treadmill_walk_is_measured_with_the_entered_belt_speed(cadence):
    clip, truth = belt(steps_per_min=cadence)
    r = analyse(clip, test=TREADMILL, belt_speed_m_s=truth.speed_m_s)
    assert r.accepted, r.rejection
    m = r.metrics
    assert m["cadence"]["value"] == pytest.approx(cadence, abs=1.5)
    assert m["belt_speed"] == {"value": round(truth.speed_m_s, 2), "unit": "m/s", "source": "entered"}
    assert m["step_length"]["value"] == pytest.approx(truth.step_length_m, rel=0.03)
    assert "walking_speed" not in m  # nothing measured it: the belt speed is what was entered
    assert r.test == TREADMILL and r.passes == [] and r.pass_variability is None


def test_every_treadmill_value_is_marked_not_yet_validated():
    clip, truth = belt()
    acc = analyse(clip, test=TREADMILL, belt_speed_m_s=truth.speed_m_s).to_dict()["accuracy"]
    assert acc and all(a["status"] == NOT_YET_VALIDATED for a in acc.values())
    assert "treadmill" in acc["cadence"]["note"].lower()


def test_the_overground_walk_still_rejects_a_treadmill_clip():
    clip, _ = belt()
    assert not analyse(clip, test=WALK).accepted


def test_walking_across_the_frame_is_not_a_treadmill_walk():
    clip, _ = synthetic_clip()
    r = analyse(clip, test=TREADMILL, belt_speed_m_s=1.2)
    assert r.rejection is not None and r.rejection.code == "not_in_place"
    assert "treadmill" in r.rejection.message.lower()


def test_a_front_view_on_a_treadmill_is_rejected():
    clip, truth = belt(yaw_deg=60)
    r = analyse(clip, test=TREADMILL, belt_speed_m_s=truth.speed_m_s)
    assert r.rejection is not None and r.rejection.code == "not_side_view"


def submit(client, token, **data):
    return client.post(
        "/analyses", headers=auth(token), data=data, files={"video": ("walk.mp4", b"x" * 64, "video/mp4")}
    )


def test_the_api_runs_a_treadmill_walk_and_stores_it(client, monkeypatch):
    clip, truth = belt()
    fake_video(monkeypatch, treadmill=True, passes=1, pass_secs=12.0, ramp_secs=0.5)
    _, t = register(client)
    r = submit(client, t, test="treadmill", belt_speed_kmh=f"{truth.speed_m_s * 3.6:.2f}")
    assert r.status_code == 202, r.text
    s = client.get(r.json()["status_url"], headers=auth(t)).json()
    assert s["status"] == "done", s
    result = s["analysis"]["result"]
    assert result["test"] == "treadmill"
    assert result["metrics"]["belt_speed"]["value"] == pytest.approx(truth.speed_m_s, abs=0.01)


@pytest.mark.parametrize(
    "data, code",
    [
        ({"test": "treadmill"}, "belt_speed_required"),
        ({"test": "treadmill", "belt_speed_kmh": "0.2"}, "bad_belt_speed"),
        ({"test": "treadmill", "belt_speed_kmh": "25"}, "bad_belt_speed"),
        ({"belt_speed_kmh": "4"}, "belt_speed_not_used"),
        (
            {
                "test": "treadmill",
                "belt_speed_kmh": "4",
                **{k: "10" for k in ("calib_x1", "calib_y1", "calib_x2")},
                "calib_y2": "20",
                "calib_distance_m": "2",
            },
            "calibration_not_used",
        ),
    ],
)
def test_the_belt_speed_is_checked_before_anything_is_saved(client, data, code):
    _, t = register(client)
    r = submit(client, t, **data)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == code
