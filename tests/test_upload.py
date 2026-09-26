"""F02, F06, F07, F09: upload handling, cleanup, error leakage."""
import glob
import os

import pytest

from conftest import auth, register
from synthetic import synthetic_landmarks


@pytest.fixture
def token(client):
    return register(client)[1]


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Skip MediaPipe: return synthetic landmarks for any uploaded file."""
    import app.api.analysis as m
    monkeypatch.setattr(m, "extract_landmarks", lambda path: synthetic_landmarks())


def leftovers():
    return glob.glob("data/raw/*") + glob.glob("data/processed/*")


def test_rejects_non_video_extension(client, token):
    r = client.post("/analyze", headers=auth(token), files={"video": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_uppercase_extension_accepted(client, token, fake_pipeline):
    r = client.post("/analyze", headers=auth(token), files={"video": ("IMG_0001.MOV", b"x" * 64, "video/quicktime")})
    assert r.status_code == 200, r.text


def test_success_uses_full_uuid_and_keeps_no_raw_or_landmark_files(client, token, fake_pipeline):
    before = set(leftovers())
    r = client.post("/analyze", headers=auth(token), files={"video": ("walk.mp4", b"x" * 64, "video/mp4")})
    assert r.status_code == 200, r.text
    assert len(r.json()["job_id"]) == 36
    assert set(leftovers()) == before


def test_unreadable_video_is_422_without_internal_detail_and_is_deleted(client, token):
    before = set(leftovers())
    r = client.post("/analyze", headers=auth(token),
                    files={"video": ("evil.mp4", b"#!/bin/sh\necho not a video\n" * 50, "video/mp4")})
    assert r.status_code == 422
    body = r.text
    assert "data/raw" not in body and "Traceback" not in body and "Cannot open" not in body
    assert set(leftovers()) == before


def test_unexpected_error_is_generic_500_with_reference(client, token, monkeypatch):
    import app.api.analysis as m

    def boom(path):
        raise RuntimeError("internal detail /srv/app/secret-path")
    monkeypatch.setattr(m, "extract_landmarks", boom)
    before = set(leftovers())
    r = client.post("/analyze", headers=auth(token), files={"video": ("walk.mp4", b"x" * 64, "video/mp4")})
    assert r.status_code == 500
    assert "secret-path" not in r.text and "internal detail" not in r.text
    assert "reference" in r.json()["detail"].lower()
    assert set(leftovers()) == before


def test_upload_size_limit(client, token, monkeypatch):
    import app.api.analysis as m
    monkeypatch.setattr(m.settings, "max_upload_bytes", 1000)
    before = set(leftovers())
    r = client.post("/analyze", headers=auth(token), files={"video": ("big.mp4", b"x" * 5000, "video/mp4")})
    assert r.status_code == 413
    assert set(leftovers()) == before
