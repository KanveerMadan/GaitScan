"""Create load-test accounts directly in a LOCAL throwaway database and write their access tokens
(the API's per-IP sign-up and login limits would otherwise throttle simulated users from one machine).
Uses the same DATABASE_URL and JWT_SECRET as the server under test. Never run against production.

    uv run python loadtest/make_users.py 50 loadtest/out/tokens.txt
"""

import sys
import uuid

from app.core.security import create_access_token, hash_password
from app.db.database import SessionLocal
from app.db.models import User

n, out = int(sys.argv[1]), sys.argv[2]
db = SessionLocal()
tokens = []
try:
    pw = hash_password("load-test-password-1")
    for _ in range(n):
        u = User(email=f"load-{uuid.uuid4().hex[:12]}@example.com", hashed_password=pw, role="patient")
        db.add(u)
        db.flush()
        tokens.append(create_access_token({"sub": u.email}))
    db.commit()
finally:
    db.close()
with open(out, "w") as f:
    f.write("\n".join(tokens) + "\n")
print(f"{n} accounts, tokens in {out}")
