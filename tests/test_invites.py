"""F10 (audit): invite codes must come from a CSPRNG, not the seedable `random` module."""

import random


def test_invite_codes_are_not_reproducible_from_random_seed():
    from app.api.clinician import generate_code

    random.seed(1234)
    a = generate_code()
    random.seed(1234)
    b = generate_code()
    assert a != b


def test_invite_code_format_unchanged():
    from app.api.clinician import generate_code

    code = generate_code()
    assert len(code) == 6 and code.isalnum() and code.upper() == code


def test_invite_join_flow_links_patient_once(client):
    from conftest import PASSWORD, auth, promote_to_clinician, register

    doc, _ = register(client)
    promote_to_clinician(doc)
    doc_t = client.post("/auth/login", json={"email": doc, "password": PASSWORD}).json()["access_token"]
    _, pat_t = register(client)
    code = client.post("/clinician/invite", headers=auth(doc_t)).json()["code"]
    assert client.post("/patient/join", headers=auth(pat_t), json={"code": code.lower()}).status_code == 200
    # a used code cannot be redeemed again
    _, other_t = register(client)
    assert client.post("/patient/join", headers=auth(other_t), json={"code": code}).status_code == 404
    names = [p["email"] for p in client.get("/clinician/patients", headers=auth(doc_t)).json()]
    assert len(names) == 1


def test_patient_sessions_for_missing_patient_is_404_not_500(client):
    """A clinician link whose patient row is gone must not crash the endpoint."""
    from conftest import PASSWORD, auth, promote_to_clinician, register

    from app.db.database import SessionLocal
    from app.db.models import ClinicianPatient, User

    doc, _ = register(client)
    promote_to_clinician(doc)
    doc_t = client.post("/auth/login", json={"email": doc, "password": PASSWORD}).json()["access_token"]
    with SessionLocal() as db:
        doc_id = db.query(User).filter(User.email == doc).one().id
        db.add(ClinicianPatient(clinician_id=doc_id, patient_id=999_999))
        db.commit()
    r = client.get("/clinician/patients/999999/sessions", headers=auth(doc_t))
    assert r.status_code == 404


def test_an_invite_code_expires_after_7_days(client):
    from datetime import UTC, datetime, timedelta

    from conftest import auth, promote_to_clinician, register

    from app.db.database import SessionLocal
    from app.db.models import ClinicianInvite

    doc_email, doc = register(client)
    promote_to_clinician(doc_email)
    code = client.post("/clinician/invite", headers=auth(doc)).json()["code"]
    db = SessionLocal()
    inv = db.query(ClinicianInvite).filter(ClinicianInvite.code == code).one()
    inv.created_at = datetime.now(UTC) - timedelta(days=7, minutes=1)
    db.commit()
    db.close()
    _, pt = register(client)
    r = client.post("/patient/join", headers=auth(pt), json={"code": code})
    assert r.status_code == 404


def test_join_attempts_are_rate_limited_per_client(client):
    from conftest import auth, register

    _, pt = register(client)
    codes = [
        client.post("/patient/join", headers=auth(pt), json={"code": f"ZZ{i:04d}"}).status_code
        for i in range(11)
    ]
    assert codes[:10] == [404] * 10 and codes[10] == 429
