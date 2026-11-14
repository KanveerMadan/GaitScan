"""GET /references (Plan V3 Phase 11): the typical knee, hip and ankle curves the result page draws its
bands from, and the GPS band. Public and static (the same for everyone), so the app fetches it once
instead of every result carrying it."""

from gaitcore.norms.thresholds import TYPICAL_SD


def test_references_give_each_joints_typical_band_over_the_gait_cycle(client):
    r = client.get("/references")
    assert r.status_code == 200
    body = r.json()
    assert body["typical_sd"] == TYPICAL_SD
    for joint in ("knee", "hip", "ankle"):
        c = body["curves"][joint]
        assert len(c["mean"]) == len(c["lo"]) == len(c["hi"]) == 101
        assert all(lo < m < hi for lo, m, hi in zip(c["lo"], c["mean"], c["hi"], strict=True))
        assert c["n"] >= 10
    assert body["gps"]["typical"][0] == 0 and body["gps"]["typical"][1] > 0
    assert body["label"]["en"] == "compared with healthy adults measured by this app"
    assert "hi" in body["label"]
    assert "max-age" in r.headers.get("cache-control", "")
