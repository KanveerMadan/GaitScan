"""Privacy center (ADR-007, Plan V3 Phase 5): export your data, delete a session, delete the account."""

from conftest import PASSWORD, auth, link, promote_to_clinician, register, seed_session


def test_export_holds_everything_the_account_owns(client):
    email, t = register(client)
    sid = seed_session(email)
    client.patch(f"/sessions/{sid}", headers=auth(t), json={"notes": "after physio", "tags": ["shoes"]})
    r = client.get("/me/export", headers=auth(t))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["account"]["email"] == email and "hashed_password" not in str(data)
    s = data["sessions"][0]
    assert s["id"] == sid and s["notes"] == "after physio" and s["result"]["metrics"]["cadence"]
    assert data["consents"][0]["version"] and data["analysis_jobs"] == []


def test_the_owner_deletes_a_session_and_nobody_else_can(client):
    email, t = register(client)
    sid = seed_session(email)
    doc_email, doc = register(client)
    promote_to_clinician(doc_email)
    link(doc_email, email)
    assert client.delete(f"/sessions/{sid}", headers=auth(doc)).status_code == 404
    assert client.delete(f"/sessions/{sid}", headers=auth(t)).status_code == 204
    assert client.get(f"/sessions/{sid}", headers=auth(t)).status_code == 404
    assert client.get("/sessions", headers=auth(t)).json() == []


def test_a_legacy_session_and_its_archive_are_deleted_together(client):
    from app.db.database import SessionLocal
    from app.db.models import SessionArchive

    email, t = register(client)
    sid = seed_session(email, legacy=True)
    assert client.delete(f"/sessions/{sid}", headers=auth(t)).status_code == 204
    db = SessionLocal()
    try:
        assert db.get(SessionArchive, sid) is None
    finally:
        db.close()


def test_deleting_the_account_needs_the_password_and_removes_everything(client):
    from app.db.database import SessionLocal
    from app.db.models import (
        AnalysisJob,
        AuthToken,
        ClinicianInvite,
        ClinicianPatient,
        Consent,
        SessionArchive,
        User,
    )
    from app.db.models import Session as SessionRow

    email, t = register(client)
    sid = seed_session(email)
    legacy_sid = seed_session(email, legacy=True)
    doc_email, _ = register(client)
    promote_to_clinician(doc_email)
    link(doc_email, email)
    db = SessionLocal()
    uid = db.query(User).filter(User.email == email).one().id
    db.add(AnalysisJob(id="job-of-deleted-user", user_id=uid, status="done", test="walk", session_id=sid))
    from datetime import UTC, datetime

    db.add(AuthToken(user_id=uid, purpose="reset", token_hash="h" * 64, expires_at=datetime.now(UTC)))
    db.commit()
    db.close()

    assert (
        client.request("DELETE", "/me", headers=auth(t), json={"password": "wrong-password-1"}).status_code
        == 400
    )
    assert client.request("DELETE", "/me", headers=auth(t), json={"password": PASSWORD}).status_code == 204
    assert client.get("/sessions", headers=auth(t)).status_code == 401  # the token's user is gone

    db = SessionLocal()
    try:
        assert db.get(User, uid) is None
        assert db.query(SessionRow).filter(SessionRow.user_id == uid).count() == 0
        assert db.get(SessionArchive, legacy_sid) is None
        assert db.query(Consent).filter(Consent.user_id == uid).count() == 0
        assert db.query(AuthToken).filter(AuthToken.user_id == uid).count() == 0
        assert db.query(AnalysisJob).filter(AnalysisJob.user_id == uid).count() == 0
        assert db.query(ClinicianPatient).filter(ClinicianPatient.patient_id == uid).count() == 0
        assert db.query(ClinicianInvite).filter(ClinicianInvite.patient_id == uid).count() == 0
    finally:
        db.close()
    register(client, email=email)  # the email can be used again


def test_a_clinicians_account_deletion_unlinks_their_patients(client):
    from conftest import db_user

    from app.db.database import SessionLocal
    from app.db.models import ClinicianInvite, ClinicianPatient

    patient_email, pt = register(client)
    doc_email, doc = register(client)
    promote_to_clinician(doc_email)
    link(doc_email, patient_email)
    doc_id = db_user(doc_email)
    client.post("/clinician/invite", headers=auth(doc))
    assert client.request("DELETE", "/me", headers=auth(doc), json={"password": PASSWORD}).status_code == 204
    db = SessionLocal()
    try:
        assert db.query(ClinicianPatient).filter(ClinicianPatient.clinician_id == doc_id).count() == 0
        assert db.query(ClinicianInvite).filter(ClinicianInvite.clinician_id == doc_id).count() == 0
    finally:
        db.close()
    assert client.get("/sessions", headers=auth(pt)).status_code == 200  # the patient is unaffected
