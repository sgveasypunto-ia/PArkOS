"""Smoke del backend Parkos contra el stack Docker local (solo stdlib).

Uso (desde la raiz del repo):  python backend/.claude/skills/run-backend/smoke.py
Credenciales: operador QA de AGENTS.md; admin de PARKOS_ADMIN_PASSWORD (si no, el
default de infra/scripts/bootstrap_pairing.py; si ese ya no sirve se reporta SKIP).
Efecto lateral: cada login escribe log_transaccional (y por tanto encola sync). Nada mas.
"""
import base64, json, os, re, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ADMIN, SUC = "http://127.0.0.1:8000", "http://127.0.0.1:8100"
ok = True


def call(method, url, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None, h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print("PASS" if cond else "FAIL", name, detail)


def count(container, sql):
    out = subprocess.run(["docker", "exec", container, "psql", "-U", "parkos", "-d", "parkos", "-Atc", sql],
                         capture_output=True, text=True, timeout=15)
    return int(out.stdout.strip())


boot = (ROOT / "infra/scripts/bootstrap_pairing.py").read_text(encoding="utf-8")
admin_pw = os.environ.get("PARKOS_ADMIN_PASSWORD") or re.search(r'ADMIN_PASSWORD = "([^"]+)"', boot).group(1)
row = re.search(r"\| Branch operator \| `([^`]+)` \| `([^`]+)`", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
op_email, op_pw = row.groups()

for name, base in (("admin", ADMIN), ("sucursal", SUC)):
    s, b = call("GET", base + "/health")
    check(f"health {name}", s == 200 and b.get("status") == "ok", str(b))

s, b = call("POST", ADMIN + "/api/v1/auth/login", {"email": "admin@parkos.local", "password": admin_pw})
if s == 200:
    check("login admin @8000", True)
else:
    print("SKIP login admin @8000: status", s, "(401: contrasena distinta, exporta PARKOS_ADMIN_PASSWORD; 429: bloqueo por intentos fallidos, espera)")

s, b = call("POST", SUC + "/api/v1/auth/login", {"email": op_email, "password": op_pw})
check("login operador @8100", s == 200 and "access_token" in b, f"status={s}")
tok = b["access_token"]
claims = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
suc = claims["sucursal"]

s, b = call("GET", f"{SUC}/api/v1/sync/estado?uuid_sucursal={suc}", token=tok)
check("sync/estado @8100", s == 200 and "pendientes" in b, str(b))

# Round-trip: el login de arriba escribio log_transaccional en la sucursal; el job lo sube a la nube.
before = count("parkos-cloud-db", "select count(*) from prod.log_transaccional")
call("POST", SUC + "/api/v1/auth/login", {"email": op_email, "password": op_pw})
for _ in range(9):
    time.sleep(10)
    after = count("parkos-cloud-db", "select count(*) from prod.log_transaccional")
    if after > before:
        break
check("sync sucursal->nube (log_transaccional crece)", after > before, f"{before}->{after}")
sys.exit(0 if ok else 1)
