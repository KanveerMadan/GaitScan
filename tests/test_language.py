"""F36: no diagnostic / injury / prescription language reaches users (audit §6 A3)."""

import ast
import pathlib
import re

import pytest
from conftest import PASSWORD, ROOT, auth, link, promote_to_clinician, register, seed_session
from synthetic import synthetic_clip

BANNED = re.compile(
    r"abnormal|injur|damage|prescri|diagnos|risk score|risk assessment|fall[- ]?risk|\blimp|"
    r"affected (leg|side)|\bpain\b|shin splint|compensat|consult a doctor|serious|looks healthy|\ba healthy\b|"
    r"any angle|cctv",
    re.I,
)
# No module may contain legacy wording: the old rows' text now lives only in session_archive.
ALLOWED_FILES: set[str] = set()


def disclaimer():
    # The disclaimer must say what the tool does NOT do ("does not diagnose"); it is the
    # only string exempt from the scan, and only as this exact constant.
    from app.core.copy import DISCLAIMER

    return DISCLAIMER


def flagged(s):
    return BANNED.search(s.replace(disclaimer(), ""))


def string_literals(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def test_no_banned_wording_in_backend_string_literals():
    assert pathlib.Path(ROOT, "app", "main.py").exists()  # guard: never scan an empty tree
    hits = []
    for p in sorted(
        [*pathlib.Path(ROOT, "app").rglob("*.py"), *pathlib.Path(ROOT, "gaitcore").rglob("*.py")]
    ):
        rel = p.relative_to(ROOT).as_posix()
        if rel in ALLOWED_FILES:
            continue
        for line, s in string_literals(p):
            if flagged(s):
                hits.append(f"{rel}:{line}: {s[:80]!r}")
    assert not hits, "\n".join(hits)


def all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_strings(v)


def assert_clean(obj):
    bad = [s for s in all_strings(obj) if flagged(s)]
    assert not bad, bad


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"people": 2}, {"rotate90": True}, {"feet_visibility": 0.2}, {"yaw_deg": 40},
     {"passes": 1, "pass_secs": 3.4}, {"fps": 15}, {"passes": 1, "pass_secs": 2.5}],
)  # fmt: skip
def test_pipeline_output_is_clean(kwargs):
    """Accepted results and every rejection message (replaces the old scoring-output scan)."""
    from gaitcore.pipeline import analyse

    assert_clean(analyse(synthetic_clip(**kwargs)[0]).to_dict())


def test_analyze_response_is_clean_and_carries_disclaimer(client, monkeypatch):
    from conftest import fake_video

    fake_video(monkeypatch)
    _, t = register(client)
    r = client.post("/analyze", headers=auth(t), files={"video": ("w.mp4", b"x" * 64, "video/mp4")})
    assert r.status_code == 200, r.text
    assert_clean(r.json())
    assert "not a medical device" in r.json()["disclaimer"].lower()


def test_legacy_rows_are_served_without_legacy_wording(client, monkeypatch):
    alice, alice_t = register(client)
    bob, _ = register(client)
    promote_to_clinician(bob)
    link(bob, alice)
    bob_t = client.post("/auth/login", json={"email": bob, "password": PASSWORD}).json()["access_token"]
    sid = seed_session(alice, legacy_text=True)

    assert_clean(client.get(f"/sessions/{sid}", headers=auth(alice_t)).json())
    assert_clean(client.get("/sessions", headers=auth(alice_t)).json())
    assert_clean(client.get("/clinician/patients", headers=auth(bob_t)).json())
    pid = client.get("/auth/me", headers=auth(alice_t)).json()["id"]
    assert_clean(client.get(f"/clinician/patients/{pid}/sessions", headers=auth(bob_t)).json())

    # The archived legacy wording is never served: the report for a legacy session is 410.
    r = client.get(f"/report/{sid}", headers=auth(alice_t))
    assert r.status_code == 410
    assert_clean(r.json())
