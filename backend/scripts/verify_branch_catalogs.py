"""GET /catalogos/tipos-vehiculo from the branch api-sucursal.

Demonstrates that rows created on cloud (or inserted directly) are
visible to the branch via the branch API.
"""
import json
import os
import sys
import urllib.request
import uuid as uuid_lib

sys.path.insert(0, r"E:\easypunto_parkos\backend\packages\parkos_core\src")
import psycopg

from parkos_core.auth.tokens import issue_token

with psycopg.connect("postgresql://parkos:parkos@localhost:5432/parkos") as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT uuid FROM prod.usuarios WHERE email = %s LIMIT 1",
            ("admin@parkos.local",),
        )
        admin_uuid = cur.fetchone()[0]

branch_uuid = uuid_lib.UUID("360357ea-3564-4843-a680-7e821dd26383")
jwt = issue_token(
    subject_uuid=admin_uuid,
    issuer="operador-cloud",
    claims={
        "rol": "operador",
        "sucursal": str(branch_uuid),
        "permissions": ["config_catalogo"],
    },
)

req = urllib.request.Request(
    "http://localhost:8100/api/v1/catalogos/tipos-vehiculo?limit=20",
    headers={"Authorization": f"Bearer {jwt}"},
)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())

items = data.get("items", [])
print(f"Total in branch: {len(items)}")
for item in items:
    print(f"  {item.get('tipo'):12s}  uuid={item.get('uuid')[:8]}...  estado={item.get('estado')}")
