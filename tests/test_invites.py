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
