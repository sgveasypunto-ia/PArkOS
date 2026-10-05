"""MIGRATION 0077 -- siembra prod.tipo_sucursal (AUTO / MANUAL).

Revision ID: 0077_seed_tipo_sucursal_canonico
Revises: 0076_seed_configuracion_caja_sync_catalog
Create Date: 2026-10-04

**Scope.** QA (rama ``qa/integracion-admin-sucursal``) encontro
``prod.tipo_sucursal`` completamente vacio en CLOUD y en BRANCH -- ninguna
migracion previa lo siembra, y ``infra/scripts/seed_catalogs.py`` tampoco
lo menciona. Esto rompe el flujo de aprovisionamiento de sucursales desde
cero: ``apps/web_admin/src/features/sucursales/components/SucursalForm.tsx``
auto-rellena ``uuid_tipo_sucursal`` tomando la PRIMERA fila de
``GET /api/v1/catalogos/tipo-sucursal``; con cero filas no hay nada que
elegir, asi que crear una sucursal desde el admin -- el flujo completo de
aprovisionamiento de sedes -- no puede funcionar en una instalacion nueva.
(Los 7 ``prod.sucursal`` existentes en cloud hoy tienen
``uuid_tipo_sucursal IS NULL`` -- la columna es FK nullable -- que es el
sintoma, no un permiso para dejar el catalogo vacio.)

**Por que no hay una lista de valores canonicos en los requisitos.**
``modelo_datos_er.mmd`` (bloque ``tipo_sucursal``, lineas ~146-154) solo
declara columnas (``codigo`` UK, ``nombre``, ``descripcion``,
``caracteristicas`` json) con el comentario "catalogo: clasifica
sucursales por modelo operativo; sus caracteristicas habilitan modulos" --
no enumera valores. ``docs/01-requisitos/funcionales.md``,
``docs/02-arquitectura/modelo-datos.md`` y ``plan.md`` (HU-F14.2, HU-F15.1,
ABIERTO-05, ABIERTO-108) tratan el catalogo como ya sembrado y
administrable vía CRUD generico, pero ninguno prescribe que filas debe
contener. ``openspec/changes/archive/2026-09-09-sync-overhaul/**`` solo lo
registra como entrada ``[V]`` ``cloud_to_branch``/``all_branches`` del
catalogo de sync -- tampoco enumera valores.

**La unica evidencia concreta de una taxonomia pensada para este catalogo
en todo el repositorio** es el propio
``backend/tests/unit/test_tipo_sucursal_crud.py`` (PR3, pre-existente, no
escrito por esta migracion): sus payloads de ejemplo usan
``codigo="AUTO"`` / ``nombre="Autoservicio"`` / ``descripcion="Punto sin
operador, sólo lector de placas."`` / ``caracteristicas={"captura_placa_auto":
True, "sin_operador": True}``, y por separado ``codigo="MANUAL"`` /
``nombre="Con operador"``. Esta migracion adopta esos 2 codigos tal cual
-- AUTO con su descripcion/caracteristicas copiadas literalmente del test;
MANUAL con una descripcion/caracteristicas simetricas inferidas por este
autor (el test original solo fija su ``nombre``, documentado aqui como
inferencia, no como hecho confirmado). Son el conjunto minimo defendible:
alcanza para desbloquear el auto-llenado de ``SucursalForm`` sin inventar
una taxonomia de negocio sin respaldo (no existe ningun otro "modelo
operativo" mencionado en el corpus).

**Siembra.** Idempotente: mismo patron ``DO $$`` por fila que
``0071_seed_tipo_tarifa_modalidades`` -- inserta solo cuando no existe fila
con ese ``uuid`` fijo exacto. UUIDs ``uuid5`` deterministas (mismo
namespace privado que ``0019``/``0020``:
``a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60``, computado offline, nunca en
runtime de la migracion) -- ``tipo_sucursal`` es ``cloud_to_branch``/
``all_branches`` en ``SYNC_CATALOG`` (``sync_entries_v.py``), asi que un
``gen_random_uuid()`` produciria un uuid distinto por nodo y las mismas 2
filas "logicas" sincronizarian como 4 filas duplicadas. ``vigente_hasta
=NULL`` deja la fila vigente; el trigger ``tipo_sucursal_set_vigente_inicial``
(``0001_initial_schema.py``) ya setea ``vigente_desde``/``estado`` cuando
vienen NULL, pero igual los fijamos explicitamente aqui (mismo estilo que
0071) para que la siembra sea reproducible sin depender del reloj del
trigger.
"""

from __future__ import annotations

import json
from typing import NamedTuple

from alembic import op

# revision identifiers, used by Alembic.
revision = "0077_seed_tipo_sucursal_canonico"
down_revision = "0076_seed_configuracion_caja_sync_catalog"
branch_labels = None
depends_on = None


class _SeedRow(NamedTuple):
    codigo: str
    uuid_fijo: str
    nombre: str
    descripcion: str
    caracteristicas: dict[str, bool]


# uuid5(namespace=UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), codigo) --
# el MISMO namespace privado que 0019/0020 -- computado una sola vez,
# offline, nunca en runtime.
_SEED_ROWS: tuple[_SeedRow, ...] = (
    _SeedRow(
        codigo="AUTO",
        uuid_fijo="aeb855ea-1247-5956-8e41-7b8fdc1daae8",
        nombre="Autoservicio",
        # Copiado literal de test_tipo_sucursal_crud.py::TestOptionalFields.test_create_full.
        descripcion="Punto sin operador, sólo lector de placas.",
        caracteristicas={"captura_placa_auto": True, "sin_operador": True},
    ),
    _SeedRow(
        codigo="MANUAL",
        uuid_fijo="9bf3a91b-d368-5107-912b-2ebea775ffb7",
        # "Con operador" viene literal de
        # test_tipo_sucursal_crud.py::TestReadList.test_with_cursor; la
        # descripcion/caracteristicas son el complemento simetrico de
        # AUTO inferido por esta migracion (no estaban en el test).
        nombre="Con operador",
        descripcion="Punto con operador en sitio: gestiona ingresos y salidas manualmente.",
        caracteristicas={"captura_placa_auto": False, "sin_operador": False},
    ),
)


def upgrade() -> None:
    """Siembra idempotente: inserta AUTO/MANUAL con uuid fijo deterministico."""
    for row in _SEED_ROWS:
        caracteristicas_json = json.dumps(row.caracteristicas)
        op.execute(
            f"""
            DO $$
            DECLARE
                siembra_count INTEGER;
            BEGIN
                SELECT COUNT(*) INTO siembra_count
                FROM prod.tipo_sucursal
                WHERE uuid = '{row.uuid_fijo}';

                IF siembra_count = 0 THEN
                    INSERT INTO prod.tipo_sucursal (
                        uuid, codigo, nombre, descripcion, caracteristicas,
                        vigente_desde, vigente_hasta, estado,
                        created_at, created_by, sync_status, sync_attempts
                    ) VALUES (
                        '{row.uuid_fijo}',
                        '{row.codigo}',
                        '{row.nombre}',
                        '{row.descripcion}',
                        '{caracteristicas_json}'::jsonb,
                        NOW(), NULL, 'activo',
                        NOW(), NULL, 'sincronizado', 0
                    )
                    ON CONFLICT (codigo, vigente_desde) DO NOTHING;
                    RAISE NOTICE '0077_op: siembra inserted (codigo=%, uuid=%)', '{row.codigo}', '{row.uuid_fijo}';
                ELSE
                    RAISE NOTICE '0077_op: siembra already present (codigo=%, uuid=%), no-op',
                                  '{row.codigo}', '{row.uuid_fijo}';
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    """Reverse: cierre bi-temporal (vigente_hasta=NOW()) de las 2 filas
    canonicas. Las filas permanecen en la tabla para auditoria (canon
    insert-only de 4NF)."""
    for row in _SEED_ROWS:
        op.execute(
            f"""
            UPDATE prod.tipo_sucursal
            SET vigente_hasta = NOW()
            WHERE uuid = '{row.uuid_fijo}' AND vigente_hasta IS NULL;
            """
        )


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]
