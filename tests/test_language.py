"""F36: no diagnostic / injury / prescription language reaches users (audit §6 A3)."""

import ast
import json
import pathlib
import re

import pytest
from conftest import PASSWORD, ROOT, auth, link, promote_to_clinician, register, seed_session
from synthetic import synthetic_landmarks

BANNED = re.compile(
    r"abnormal|injur|damage|prescri|diagnos|risk score|risk assessment|fall[- ]?risk|\blimp|"
    r"affected (leg|side)|\bpain\b|shin splint|compensat|consult a doctor|serious|looks healthy|\ba healthy\b|"
    r"any angle|cctv",
    re.I,
)
# Only this module may contain legacy wording, because it exists to translate old DB rows.
ALLOWED_FILES = {"app/services/display.py"}


def disclaimer():
    # The disclaimer must say what the tool does NOT do ("does not diagnose"); it is the
    # only string exempt from the scan, and only as this exact constant.
    from gaitcore.legacy import DISCLAIMER

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


@pytest.mark.parametrize("mode", ["Clinical", "Runner", "Athlete", "Elderly"])
@pytest.mark.parametrize("activity", ["Walking", "Brisk Walking", "Running", "Asymmetric Walking"])
@pytest.mark.parametrize("knee_scale_R", [1.0, 0.3])
def test_scoring_output_is_clean(mode, activity, knee_scale_R):
    from gaitcore.angles import add_all_angles
    from gaitcore.legacy import calculate_risk_scores

    df = add_all_angles(synthetic_landmarks(knee_scale_R=knee_scale_R))
    assert_clean(calculate_risk_scores(df, activity=activity, mode=mode))


def test_analyze_response_is_clean_and_carries_disclaimer(client, monkeypatch):
    import app.api.analysis as m

    monkeypatch.setattr(m, "extract_landmarks", lambda p: synthetic_landmarks(knee_scale_R=0.3))
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

    captured = {}
    import app.api.sessions as m

    monkeypatch.setattr(
        m,
        "generate_pdf_report",
        lambda results, output_path, plots_dir: (
            captured.update(results) or open(output_path, "wb").write(b"%PDF-stub")
        ),
    )
    import shutil

    shutil.rmtree(f"outputs/{sid}", ignore_errors=True)
    assert client.get(f"/report/{sid}", headers=auth(alice_t)).status_code == 200
    assert_clean(json.loads(json.dumps(captured, default=str)))
