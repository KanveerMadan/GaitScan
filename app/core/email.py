"""Email addresses are compared in lower case everywhere (2026-11-12).

Sign-up used to keep an address as typed, sign-in matched it exactly and recovery lowercased it
first, so an account made as Name@example.com could never be recovered with a code. Every request
that carries an address now lowercases it on the way in, and migration 0014 lowercased the stored
ones. (The local part is case-sensitive in theory; no mail provider GaitScan users have treats it so.)
"""

from typing import Annotated

from pydantic import AfterValidator, EmailStr

Email = Annotated[EmailStr, AfterValidator(lambda address: address.lower())]
