-- Parkos LITE - datos de demo para la sucursal local. Se corre con psql como
-- superusuario DESPUES de `alembic upgrade head`:
--
--   psql -v ON_ERROR_STOP=1 -v sucursal_uuid=<uuid v4 de la sucursal lite> -f seed_demo.sql
--
-- Re-ejecutable (idempotente) y SIN ningun DELETE (AGENTS.md): cada fila [V]
-- se inserta solo si no existe una version vigente (vigente_hasta IS NULL);
-- nunca ON CONFLICT sobre vigente_desde (NOW() cambia en cada corrida).
-- Una fila ya existente (p. ej. una tarifa que el probador edito despues) se
-- respeta: este seed NUNCA pisa ni cierra versiones.
--
-- Credenciales DEMO (solo para pruebas locales): password `Demo1234`.
-- Para cambiar el hash: psql ... -v demo_hash=<bcrypt>.

\if :{?sucursal_uuid}
\else
  \echo 'ERROR: falta -v sucursal_uuid=<uuid>'
  \quit 3
\endif

\if :{?demo_hash}
\else
  \set demo_hash '$2b$12$8GCJeBT.kCOr0kqd2rJkYu4AKm7te2erVe7mK12Rh9SifoB6swg2O'
\endif

BEGIN;

-- 1) Sucursal (FK: empresa singleton y tipo_sucursal 'Con operador', ambos
--    sembrados por las migraciones).
INSERT INTO prod.sucursal
    (uuid, nombre, direccion, telefono, prefijo_nombre, ciudad, horario,
     uuid_tipo_sucursal, uuid_empresa, vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, 'Sucursal Demo', 'Calle Demo 123', '6010000000', 'DEMO',
       'Ciudad Demo', 'Lun-Dom 6:00-22:00',
       (SELECT uuid FROM prod.tipo_sucursal WHERE nombre = 'Con operador' AND vigente_hasta IS NULL LIMIT 1),
       (SELECT uuid FROM prod.empresa WHERE vigente_hasta IS NULL ORDER BY created_at LIMIT 1),
       NOW(), NULL, 'activo'
WHERE NOT EXISTS (SELECT 1 FROM prod.sucursal WHERE uuid = :'sucursal_uuid'::uuid);

-- 2) Usuarios de login (rol `operador`: emiten token operador-, el unico que
--    acepta la API de sucursal) + pertenencia a la sucursal + permisos.
CREATE TEMP TABLE _demo_usuarios (email text, nombre text, apellido text, cedula text) ON COMMIT DROP;
INSERT INTO _demo_usuarios VALUES
    ('demo.operador@parkos.local',  'Operador', 'Demo',     '1000000001'),
    ('demo.operador2@parkos.local', 'Operador', 'Demo Dos', '1000000002');

INSERT INTO prod.usuarios
    (nombre, apellido, cedula, email, password_hash, fecha_cambio_password, rol,
     vigente_desde, vigente_hasta, estado, debe_cambiar_password)
SELECT d.nombre, d.apellido, d.cedula, d.email, :'demo_hash', NOW(), 'operador',
       NOW(), NULL, 'activo', false
FROM _demo_usuarios d
WHERE NOT EXISTS (SELECT 1 FROM prod.usuarios u WHERE u.email = d.email AND u.vigente_hasta IS NULL);

INSERT INTO prod.usuarios_sucursal (uuid_sucursal, uuid_usuario, vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, u.uuid, NOW(), NULL, 'activo'
FROM prod.usuarios u JOIN _demo_usuarios d ON d.email = u.email
WHERE u.vigente_hasta IS NULL
  AND NOT EXISTS (SELECT 1 FROM prod.usuarios_sucursal us
                  WHERE us.uuid_sucursal = :'sucursal_uuid'::uuid
                    AND us.uuid_usuario = u.uuid AND us.vigente_hasta IS NULL);

-- Todos los permisos vivos del catalogo (igual que la cuenta QA del entorno
-- de desarrollo): el demo debe poder recorrer ingreso/salida/caja/config.
INSERT INTO prod.permisos_usuario (uuid_usuario, uuid_permiso, vigente_desde, vigente_hasta, estado)
SELECT u.uuid, p.uuid, NOW(), NULL, 'activo'
FROM prod.usuarios u
JOIN _demo_usuarios d ON d.email = u.email
CROSS JOIN prod.permisos p
WHERE u.vigente_hasta IS NULL AND p.vigente_hasta IS NULL
  AND NOT EXISTS (SELECT 1 FROM prod.permisos_usuario pu
                  WHERE pu.uuid_usuario = u.uuid AND pu.uuid_permiso = p.uuid
                    AND pu.vigente_hasta IS NULL);

-- 2b) Tipos de vehiculo: las migraciones solo siembran `moto` y `otro`;
--     carro/bicicleta/patineta los crea normalmente el panel admin (via sync).
--     En el lite no hay sync, asi que se agregan aqui (UUID fijos, iguales a
--     los del entorno de desarrollo).
INSERT INTO prod.tipos_vehiculo (uuid, tipo, vigente_desde, vigente_hasta, estado)
SELECT v.uuid::uuid, v.tipo, NOW(), NULL, 'activo'
FROM (VALUES
    ('52d92997-cee5-4978-a773-ad141786b24d', 'carro'),
    ('390e3eac-e1f4-4a80-9a31-556a75f30261', 'bicicleta'),
    ('57f054a6-d58e-4ee9-b236-1667f5d28378', 'patineta')
) AS v(uuid, tipo)
WHERE NOT EXISTS (SELECT 1 FROM prod.tipos_vehiculo t WHERE t.tipo = v.tipo AND t.vigente_hasta IS NULL)
  AND NOT EXISTS (SELECT 1 FROM prod.tipos_vehiculo t WHERE t.uuid = v.uuid::uuid);

-- 3) Tarifas (COP) por tipo de vehiculo x tipo de tarifa. Los UUID de
--    tipo_tarifa son fijos (migracion 0071); los tipos de vehiculo se buscan
--    por nombre. La API cotiza solo los tipos que tengan tarifa vigente.
CREATE TEMP TABLE _demo_tarifas (vehiculo text, tarifa text, valor numeric) ON COMMIT DROP;
INSERT INTO _demo_tarifas VALUES
    ('carro',     'hora',     4000), ('carro',     'fraccion',  1000), ('carro',     'plena', 25000), ('carro',     'nocturna', 12000),
    ('moto',      'hora',     2500), ('moto',      'fraccion',   600), ('moto',      'plena', 15000), ('moto',      'nocturna',  8000),
    ('bicicleta', 'hora',     1000), ('bicicleta', 'fraccion',   300), ('bicicleta', 'plena',  6000), ('bicicleta', 'nocturna',  3000),
    ('patineta',  'hora',     1500), ('patineta',  'fraccion',   400), ('patineta',  'plena',  8000), ('patineta',  'nocturna',  4000);

INSERT INTO prod.tarifas_sucursal
    (uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, valor, valor_plena,
     vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, tv.uuid, tt.uuid, d.valor, NULL, NOW(), NULL, 'activo'
FROM _demo_tarifas d
JOIN prod.tipos_vehiculo tv ON tv.tipo = d.vehiculo AND tv.vigente_hasta IS NULL
JOIN prod.tipo_tarifa tt ON tt.tipo = d.tarifa AND tt.vigente_hasta IS NULL
WHERE NOT EXISTS (SELECT 1 FROM prod.tarifas_sucursal t
                  WHERE t.uuid_sucursal = :'sucursal_uuid'::uuid
                    AND t.uuid_tipo_vehiculo = tv.uuid AND t.uuid_tipo_tarifa = tt.uuid
                    AND t.vigente_hasta IS NULL);

-- 4) Resolucion de facturacion de demo (rango propio de la sucursal).
INSERT INTO prod.resolucion_facturacion
    (uuid_sucursal, numero_resolucion, prefijo, rango_desde, rango_hasta,
     fecha_resolucion, fecha_inicio_vigencia, fecha_fin_vigencia,
     vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, '18760000000001', 'DEMO', 1, 5000,
       CURRENT_DATE, CURRENT_DATE, (CURRENT_DATE + INTERVAL '2 years')::date,
       NOW(), NULL, 'activo'
WHERE NOT EXISTS (SELECT 1 FROM prod.resolucion_facturacion r
                  WHERE r.uuid_sucursal = :'sucursal_uuid'::uuid AND r.vigente_hasta IS NULL);

-- 5) Configuracion de caja, tolerancias y cupos de la sucursal.
INSERT INTO prod.configuracion_caja
    (uuid_sucursal, base_inicial_sugerida, redondeo, denominaciones_permitidas,
     vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, 50000, 'ninguno', '[1000, 2000, 5000, 10000, 20000, 50000, 100000]'::jsonb,
       NOW(), NULL, 'activo'
WHERE NOT EXISTS (SELECT 1 FROM prod.configuracion_caja c
                  WHERE c.uuid_sucursal = :'sucursal_uuid'::uuid AND c.vigente_hasta IS NULL);

INSERT INTO prod.configuracion_tolerancias
    (uuid_sucursal, tolerancia_efectivo, tolerancia_datafono, vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, 0, 0, NOW(), NULL, 'activo'
WHERE NOT EXISTS (SELECT 1 FROM prod.configuracion_tolerancias c
                  WHERE c.uuid_sucursal = :'sucursal_uuid'::uuid AND c.vigente_hasta IS NULL);

CREATE TEMP TABLE _demo_cupos (vehiculo text, cantidad int) ON COMMIT DROP;
INSERT INTO _demo_cupos VALUES ('carro', 30), ('moto', 20), ('bicicleta', 10), ('patineta', 10);

INSERT INTO prod.cantidad_vehiculos_sucursal
    (uuid_sucursal, uuid_tipo_vehiculo, cantidad, vigente_desde, vigente_hasta, estado)
SELECT :'sucursal_uuid'::uuid, tv.uuid, d.cantidad, NOW(), NULL, 'activo'
FROM _demo_cupos d
JOIN prod.tipos_vehiculo tv ON tv.tipo = d.vehiculo AND tv.vigente_hasta IS NULL
WHERE NOT EXISTS (SELECT 1 FROM prod.cantidad_vehiculos_sucursal c
                  WHERE c.uuid_sucursal = :'sucursal_uuid'::uuid
                    AND c.uuid_tipo_vehiculo = tv.uuid AND c.vigente_hasta IS NULL);

COMMIT;

-- Resumen (lo lee el TUI): filas vigentes de la sucursal lite.
SELECT 'sucursal' AS tabla, count(*) FROM prod.sucursal WHERE uuid = :'sucursal_uuid'::uuid AND vigente_hasta IS NULL
UNION ALL SELECT 'usuarios_sucursal', count(*) FROM prod.usuarios_sucursal WHERE uuid_sucursal = :'sucursal_uuid'::uuid AND vigente_hasta IS NULL
UNION ALL SELECT 'tarifas_sucursal', count(*) FROM prod.tarifas_sucursal WHERE uuid_sucursal = :'sucursal_uuid'::uuid AND vigente_hasta IS NULL
UNION ALL SELECT 'resolucion_facturacion', count(*) FROM prod.resolucion_facturacion WHERE uuid_sucursal = :'sucursal_uuid'::uuid AND vigente_hasta IS NULL
UNION ALL SELECT 'configuracion_caja', count(*) FROM prod.configuracion_caja WHERE uuid_sucursal = :'sucursal_uuid'::uuid AND vigente_hasta IS NULL;
