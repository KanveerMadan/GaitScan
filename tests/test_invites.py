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
