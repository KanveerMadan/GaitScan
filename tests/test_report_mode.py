"""F15: the analysis mode survives PDF regeneration (Render's disk is wiped on every deploy)."""

import io
import shutil

from conftest import auth, register, seed_session
from pypdf import PdfReader
from synthetic import synthetic_landmarks


def pdf_text(content):
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_mode_survives_regeneration(client, monkeypatch):
    import app.api.analysis as analysis

    monkeypatch.setattr(analysis, "extract_landmarks", lambda p: synthetic_landmarks())
    _, t = register(client)
    r = client.post(
        "/analyze",
        headers=auth(t),
        data={"mode": "Runner"},
        files={"video": ("w.mp4", b"x" * 64, "video/mp4")},
    )
    sid = r.json()["job_id"]
    assert client.get(f"/sessions/{sid}", headers=auth(t)).json()["mode"] == "Runner"

    shutil.rmtree(f"outputs/{sid}")  # as after a deploy
    text = pdf_text(client.get(f"/report/{sid}", headers=auth(t)).content)
    assert "Runner Mode" in text
    assert "Clinical Mode" not in text


def test_legacy_session_without_mode_is_not_labelled_clinical(client):
    email, t = register(client)
    sid = seed_session(email)  # pre-migration row: mode is NULL
    assert client.get(f"/sessions/{sid}", headers=auth(t)).json()["mode"] is None
    shutil.rmtree(f"outputs/{sid}", ignore_errors=True)
    text = pdf_text(client.get(f"/report/{sid}", headers=auth(t)).content)
    assert "Clinical Mode" not in text
    assert "not recorded" in text.lower()
