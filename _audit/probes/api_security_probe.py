"""In-process API probe against a throwaway SQLite DB.
Run from a directory containing a `src/` checkout (e.g. _audit/sandbox/before or /after).
Every check prints PASS (secure) / FAIL (vulnerable) with the observed evidence.

v2 (Phase 0): runs unchanged against both the pre-Phase-0 code and the fixed code.
Changes vs v1: env is configured before import; the clinician is promoted through the
DB (self-assignment no longer exists); PDF-content checks fetch as the owner; the
error-leak check looks for internal details instead of treating every 500 as a leak;
adds a CORS-wildcard check.

v3 (Phase 1): imports from app/ when there is no src/ (ADR-001 layout); legitimate
users get passwords of >= 10 characters so the 10-character minimum doesn't stop the
script; the F03 role check registers with a valid-length password so it still tests
the role logic, and the 1-character password is a separate F12 password-policy check.
Every check keeps its v2 pass/fail criterion.

v4 (Plan V3 Phase 2): the quality gate rejects clips it can't measure (walk01 is rejected: no pass
holds a complete step). When the victim's upload is rejected, the victim's session is stored
directly through the DB with the v2 result of the synthetic walker (tests/synthetic.py), so the
access-control checks still have a real session to attack. Run inside the Docker image (MediaPipe
1.0.1 can't extract on macOS). Every check keeps its pass/fail criterion; the F15 mode check now
passes trivially because modes no longer exist (reported as such).
"""
import os, sys, io, contextlib, glob, re, secrets, shutil, subprocess, time
os.environ.update({"DATABASE_URL": "sqlite:///./probe.db", "ENV": "dev", "MPLBACKEND": "Agg",
                   "JWT_SECRET": secrets.token_urlsafe(48), "CORS_ORIGINS": "http://localhost:3000"})
os.environ.pop("GROQ_API_KEY", None)
if os.path.exists("probe.db"):
    os.remove("probe.db")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import jwt  # PyJWT (works in both the audit venv and the project venv)
if os.path.isdir("src"):
    from src.api.main import app
    from src.core.database import SessionLocal
    from src.models.user import User
else:
    from alembic.config import Config
    from alembic import command
    _cfg = Config(os.path.join(os.getcwd(), "alembic.ini"))
    _cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    _cfg.attributes["configure_logger"] = False
    command.upgrade(_cfg, "head")  # tables come from Alembic since Phase 1
    from app.main import app
    from app.db.database import SessionLocal
    from app.db.models import User

VIDEO = sys.argv[1]
c = TestClient(app, raise_server_exceptions=False)
c.__enter__()  # run startup -> init_db
res = {}
def check(name, vulnerable, evidence):
    res[name] = ("FAIL" if vulnerable else "PASS", evidence)
def H(tok):
    return {"Authorization": f"Bearer {tok}"}
def promote(email):
    db = SessionLocal(); u = db.query(User).filter(User.email == email).first(); u.role = "clinician"; db.commit(); db.close()

# 1. Self-assigned clinician role + trivial password + plaintext password in logs   [F03 F04 F12]
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):  # JSON logs go to stderr
    r1 = c.post("/auth/register", json={"email": "trivial@x.io", "password": "a"})
    r = c.post("/auth/register", json={"email": "mallory@x.io", "password": "mallory-pw-12", "role": "clinician"})
check("F12 1-character password accepted at registration", r1.status_code == 201, f"{r1.status_code}")
check("F03 register_self_assign_clinician", r.status_code == 201 and r.json()["role"] == "clinician",
      f"{r.status_code} role={r.json().get('role')}")
check("F04 plaintext_password_logged", any(p in buf.getvalue() for p in ("PASSWORD RECEIVED", "mallory-pw-12")),
      buf.getvalue().strip().splitlines()[:2])
mallory = r.json()["access_token"]

# 2. Account enumeration   [F12]
r = c.post("/auth/register", json={"email": "mallory@x.io", "password": "zzzzzzzzzz"})
check("F12 email_enumeration_via_register", r.status_code == 409, f"{r.status_code} {r.json()}")

# 3. Victim patient uploads a real analysis
r = c.post("/auth/register", json={"email": "alice@x.io", "password": "correct horse", "full_name": "Alice Patient"})
alice = r.json()["access_token"]
with open(VIDEO, "rb") as f:
    r = c.post("/analyze", headers=H(alice),
               files={"video": ("walk.mp4", f, "video/mp4")}, data={"mode": "Runner", "patient_name": "Alice Patient"})
job = r.json().get("job_id")
res["_alice_analyze"] = (r.status_code, {"job_id_len": len(job or ""), "detail": r.json().get("detail")})
if job is None and not os.path.isdir("src"):  # v4: rejected by the quality gate -> seed a v2 session
    import uuid
    sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
    from synthetic import synthetic_clip
    from gaitcore.pipeline import analyse
    from app.db.models import Session as GaitSession
    _result = analyse(synthetic_clip()[0]).to_dict()
    db = SessionLocal(); _uid = db.query(User).filter(User.email == "alice@x.io").first().id
    job = str(uuid.uuid4())
    db.add(GaitSession(id=job, patient_name="Alice Patient", user_id=_uid, pipeline_version=_result["pipeline_version"], result=_result))
    db.commit(); db.close()
    res["_alice_session_seeded"] = ("v4", f"upload rejected ({r.status_code}); synthetic v2 session {len(job)}-char id stored")

# 4. IDOR: no token at all   [F02]
r = c.get(f"/sessions/{job}")
check("F02 GET /sessions/{id} without auth returns another user's health data", r.status_code == 200,
      f"{r.status_code} patient_name={r.json().get('patient_name')} findings={len(r.json().get('findings', []))}")
r = c.get(f"/report/{job}")
check("F02 GET /report/{id} without auth returns PDF", r.status_code == 200 and r.content[:4] == b"%PDF",
      f"{r.status_code} {r.headers.get('content-type')} {len(r.content)} bytes")

# 5. Forged JWT using the secret that was committed in src/core/auth.py   [F01]
#    Read from git history at runtime so the value is never stored in this file.
_old = subprocess.run(["git", "show", "38c8db3:src/core/auth.py"], capture_output=True, text=True,
                      cwd=os.path.dirname(os.path.abspath(__file__))).stdout
LEAKED_SECRET = re.search(r'SECRET_KEY = "([^"]+)"', _old).group(1)
forged = jwt.encode({"sub": "alice@x.io", "role": "patient", "exp": 4102444800}, LEAKED_SECRET, algorithm="HS256")
r = c.get("/auth/me", headers=H(forged))
check("F01 forged JWT with committed secret impersonates any email", r.status_code == 200, r.json())
r = c.get("/sessions", headers=H(forged))
check("F01 forged JWT reads victim session list", r.status_code == 200 and len(r.json()) > 0,
      f"{r.status_code} n={len(r.json()) if r.status_code == 200 else '-'}")

# 6. /debug/links leaks every clinician's patient graph   [F03]
c.post("/auth/register", json={"email": "drbob@x.io", "password": "drbob-pw-123"})
promote("drbob@x.io")
bob = c.post("/auth/login", json={"email": "drbob@x.io", "password": "drbob-pw-123"}).json()["access_token"]
code = c.post("/clinician/invite", headers=H(bob)).json()["code"]
c.post("/patient/join", headers=H(alice), json={"code": code})
r = c.get("/debug/links", headers=H(mallory))
check("F03 /debug/links exposes other clinicians' links", r.status_code == 200 and len(r.json()) > 0, r.json())

# 7. Token lifetime   [F08]
claims = jwt.decode(alice, options={"verify_signature": False})
check("F08 access token lifetime > 1 day", claims["exp"] - time.time() > 86400, f"{(claims['exp']-time.time())/86400:.1f} days")

# 8. Upload: non-video content left on disk; internal detail leaked   [F06 F07 F09]
before = set(glob.glob("data/raw/*"))
r = c.post("/analyze", headers=H(alice),
           files={"video": ("evil.mp4", b"#!/bin/sh\necho not a video\n" * 100, "text/plain")})
after = set(glob.glob("data/raw/*"))
check("F06/F07 non-video bytes left on disk", len(after - before) > 0, f"left on disk: {sorted(after - before)}")
check("F09 internal error detail returned to client",
      any(x in r.text for x in ("data/raw", "Cannot open", "Traceback", "Errno")), f"{r.status_code} {r.text[:160]}")
r = c.post("/analyze", headers=H(alice), files={"video": ("EVIL.MP4", b"x", "video/mp4")})
res["_uppercase_extension"] = (r.status_code, r.text[:80])

# 9. CORS wildcard   [F08]
r = c.get("/status", headers={"Origin": "https://evil.example"})
check("F08 CORS allows arbitrary origins", r.headers.get("access-control-allow-origin") in ("*", "https://evil.example"),
      f"access-control-allow-origin={r.headers.get('access-control-allow-origin')}")

# 10. PDF regeneration (Render disk is ephemeral -> regeneration is the normal path after a deploy)   [F15 F40]
shutil.rmtree(f"outputs/{job}", ignore_errors=True)
r = c.get(f"/report/{job}", headers=H(alice))
from pypdf import PdfReader
txt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
check("F15 regenerated PDF reports wrong mode (Runner -> Clinical)", "Runner" not in txt and "Clinical" in txt,
      f"'Runner' in pdf={('Runner' in txt)}; 'Clinical Mode' in pdf={('Clinical Mode' in txt)}")
check("F40 patient name absent from PDF", "Alice" not in txt, f"'Alice' in pdf={'Alice' in txt}")

# 11. Rate limiting on login   [F10]
codes = [c.post("/auth/login", json={"email": "alice@x.io", "password": f"guess{i}"}).status_code for i in range(30)]
check("F10 no login rate limiting (30 bad attempts)", 429 not in codes, f"status codes: {sorted(set(codes))}")

for k, v in res.items():
    print(f"{v[0]:5} | {k} | {v[1]}")
n_fail = sum(1 for k, v in res.items() if not k.startswith("_") and v[0] == "FAIL")
n = sum(1 for k in res if not k.startswith("_"))
print(f"SUMMARY: {n - n_fail}/{n} PASS, {n_fail}/{n} FAIL")
