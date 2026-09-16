"""Insert the 4 tipos-vehiculo from cloud into branch-db.

The full sync pipeline (cloud's emit_sync_back_events_loop) is not yet
implemented — PR9b was supposed to land it but the loop body is a no-op
stub (see jobs/sync_cloud.py:185). For the demo, we copy the rows
manually so the branch worker sees them.
"""
import psycopg

dsn_branch = "postgresql://parkos:parkos@localhost:5433/parkos"
dsn_cloud = "postgresql://parkos:parkos@localhost:5432/parkos"

with psycopg.connect(dsn_cloud) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT uuid, tipo, created_at, created_by, vigente_desde,
                   vigente_hasta, estado
            FROM prod.tipos_vehiculo
            WHERE tipo IN ('carro', 'moto', 'bicicleta', 'patineta')
              AND vigente_desde > NOW() - INTERVAL '5 minutes'
            """
        )
        rows = cur.fetchall()
        print(f"Found {len(rows)} recent rows in cloud")

with psycopg.connect(dsn_branch) as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO prod.tipos_vehiculo (
                    uuid, tipo, created_at, created_by, vigente_desde,
                    vigente_hasta, estado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (uuid) DO NOTHING
                """,
                row,
            )
        print(f"Inserted {len(rows)} rows into branch-db")

with psycopg.connect(dsn_branch) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT uuid, tipo, estado FROM prod.tipos_vehiculo ORDER BY created_at"
        )
        print("Branch-db tipos_vehiculo:")
        for r in cur.fetchall():
            print(f"  {r[1]:12s}  uuid={r[0]}  estado={r[2]}")
