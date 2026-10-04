"""The audit spec runs in the normal suite as tests/test_audit_spec.py, which must stay a
byte-identical copy of _audit/tests/test_angles_audit.py (the approved, amended spec)."""

import pathlib

from conftest import ROOT


def test_audit_spec_is_unchanged():
    spec = pathlib.Path(ROOT, "_audit", "tests", "test_angles_audit.py").read_bytes()
    assert pathlib.Path(ROOT, "tests", "test_audit_spec.py").read_bytes() == spec
