import hashlib, psycopg

gen = hashlib.sha256(b"genesis:\x00").hexdigest()
print("hash:", gen)

dsn = "postgresql://parkos:parkos@localhost:5432/parkos"
with psycopg.connect(dsn) as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prod.log_transaccional (
                uuid, fecha_retencion_hasta,
                uuid_usuario, uuid_sucursal, accion, tabla_afectada,
                uuid_registro_afectado, datos_anteriores, datos_nuevos,
                timestamp_evento,
                hash_anterior, hash_actual,
                created_at, created_by
            )
            VALUES (
                gen_random_uuid(), CURRENT_DATE,
                NULL, NULL, 'inicialización', 'log_transaccional',
                NULL, NULL, '{"reason": "NULL sucursal genesis bootstrap"}'::jsonb,
                NOW(),
                %s, %s,
                NOW(), NULL
            )
            ON CONFLICT DO NOTHING
            """,
            (gen, gen),
        )
        print("genesis row inserted")

        cur.execute(
            "SELECT count(*) FROM prod.log_transaccional WHERE uuid_sucursal IS NULL"
        )
        print("NULL sucursal rows:", cur.fetchone()[0])
