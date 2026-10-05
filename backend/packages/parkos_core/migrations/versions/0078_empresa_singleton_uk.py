"""MIGRATION 0078 -- prod.empresa es un singleton real: UNIQUE parcial
"a lo sumo una fila vigente, sin importar el nit".

Revision ID: 0078_empresa_singleton_uk
Revises: 0077_seed_tipo_sucursal_canonico
Create Date: 2026-10-04

THE PROBLEM THIS PINS
----------------------
``branch-db`` (QA, rama ``qa/integracion-admin-sucursal``) se encontro con
DOS filas ``prod.empresa`` simultaneamente abiertas (``vigente_hasta IS
NULL``):

* ``11de9b03-8be3-5688-93e1-d283b6557f70`` -- ``nit=900000000-0``,
  ``nombre=NULL`` -- exactamente el uuid deterministico que
  ``0020_deterministic_tipo_persona_empresa_uuids.py`` siembra (su propio
  ``INSERT ... SELECT`` solo copia ``uuid``/``nit``/columnas de
  auditoria -- nunca ``nombre``/``regimen``/``mensaje_*`` -- por eso el
  nombre queda vacio).
* ``a317a1ac-02ef-4b51-9ecd-8464da3a12db`` -- ``nit=900123456-8``,
  ``nombre="Parkos S.A.S."`` -- la fila real, editada por un admin.

``cloud-db`` solo tiene la segunda (confirmado en vivo, 2026-10-04):
``SELECT uuid, nit, nombre FROM prod.empresa WHERE vigente_hasta IS NULL``
devuelve una unica fila en cloud, dos en branch.

ROOT CAUSE (diagnostico; el codigo que lo causa vive en
``sync/hooks/impls/identity_reconciler.py`` y
``sync/catalog/entries/sync_entries_v.py`` -- ambos FUERA del alcance de
este cambio, no se tocan aqui)
--------------------------------------------------------------------------
``empresa`` esta en ``SYNC_CATALOG`` con ``hook_pre_insert=identity_
reconciler`` y ``natural_key=("nit",)``. Ese hook solo cierra la fila
LOCAL abierta que comparte el MISMO nit normalizado que la fila entrante;
si no encuentra ninguna, trata la fila entrante como un INSERT ordinario
(``ctx.open_version`` es ``None`` -> ``HookResult(proceed=True)`` sin
``payload_override`` -- ver ``identity_reconciler.py`` lineas 134-146).

El admin edito la empresa en cloud cambiando NO SOLO ``nombre`` sino
tambien ``nit`` (``900000000-0`` -> ``900123456-8``). En cloud esto cierra
correctamente la fila vieja porque el endpoint ``PUT /empresa/{uuid}``
hace ``close_and_insert(current_uuid=<uuid de la URL>, ...)`` -- coincide
por uuid, no por nit. Pero el evento de sync que llega a branch es la fila
NUEVA (``a317a1ac``, ``nit=900123456-8``) via ``fn_enqueue_sync()``
(trigger ``AFTER INSERT`` -- nunca ``AFTER UPDATE``, ver
``0001_initial_schema.py``, por lo que el cierre bi-temporal de la fila
vieja JAMAS se encola como evento propio). En destino, ``identity_
reconciler`` busca una fila local abierta con ``nit=900123456-8``, no la
encuentra (la fila local abierta tiene ``nit=900000000-0``) y la inserta
como fila nueva SIN cerrar la vieja -- las dos quedan abiertas.

Esto es un diseno correcto para un catalogo de muchas filas
(``clientes``, ``vehiculos``: el nit/cedula/placa SI define la identidad
de cada fila). Es la herramienta equivocada para ``empresa``: no existe
columna ``tenant_id`` en ``prod.empresa`` (confirmado,
``models/V/empresa.py``) y tanto ``empresaApi.ts::getEmpresa`` como
``useEmpresa.ts`` tratan "la primera fila de la lista" como LA empresa --
es un singleton real de toda la tabla, no "una fila por nit". La
reconciliacion por natural key nunca puede proteger esa invariante,
porque la invariante no depende de ningun valor de columna.

THE FIX
-------
1. Reconciliacion idempotente de un solo golpe (mismo patron ya
   establecido en 0019/0020/0061): cierra toda fila abierta que NO sea la
   mas reciente (por ``created_at``), dejando exactamente una. No
   requiere intervencion manual de datos -- es codigo de migracion
   versionado, igual que sus 3 precedentes.
2. ``UNIQUE INDEX`` parcial sobre una expresion CONSTANTE
   (``(true)``) acotado a ``WHERE vigente_hasta IS NULL``: Postgres
   garantiza "a lo sumo una fila puede cumplir este predicado" sin
   atar la unicidad a ninguna columna -- ni ``nit`` ni ninguna otra --
   que es exactamente la invariante de singleton real que este dominio
   necesita.

Sin el paso 1, el paso 2 fallaria HOY contra el duplicado real en
branch-db (``CREATE UNIQUE INDEX`` sobre datos que ya lo violan aborta
con ``could not create unique index``) -- de ahi que la reconciliacion
vaya primero, en la MISMA migracion, no como un parche de datos aparte.

DOWNGRADE
---------
No-op deliberado para el paso 1 (mismo razonamiento que 0061: las filas
cerradas siguen existiendo para auditoria; reabrirlas reintroduciria el
bug). El paso 2 SI se revierte (``DROP INDEX``).
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0078_empresa_singleton_uk"
down_revision = "0077_seed_tipo_sucursal_canonico"
branch_labels = None
depends_on = None

_INDEX_NAME = "empresa_singleton_uk"


def _close_stale_open_duplicates(bind) -> None:
    """Keep only the most-recently created open ``prod.empresa`` row;
    close every other currently-open row.

    Idempotent: when at most one row is open, the ``WHERE`` clause
    matches nothing and this is a no-op. Accepts any object exposing the
    SQLAlchemy ``Connection.execute`` sync interface -- the real
    migration passes ``op.get_bind()``; tests pass a plain sync
    ``Engine.connect()`` connection, same shape.
    """
    stale_uuids = (
        bind.execute(
            text(
                """
                SELECT uuid FROM prod.empresa
                WHERE vigente_hasta IS NULL
                AND uuid <> (
                    SELECT uuid FROM prod.empresa
                    WHERE vigente_hasta IS NULL
                    ORDER BY created_at DESC, uuid DESC
                    LIMIT 1
                )
                """
            )
        )
        .scalars()
        .all()
    )
    for stale_uuid in stale_uuids:
        bind.execute(
            text(
                """
                UPDATE prod.empresa
                SET vigente_hasta = clock_timestamp(), estado = 'inactivo'
                WHERE uuid = :uuid AND vigente_hasta IS NULL
                """
            ),
            {"uuid": stale_uuid},
        )


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("SET lock_timeout = '5s'"))
    _close_stale_open_duplicates(bind)
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX_NAME}
        ON prod.empresa ((true))
        WHERE vigente_hasta IS NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS prod.{_INDEX_NAME}")


__all__ = ["_close_stale_open_duplicates", "down_revision", "downgrade", "revision", "upgrade"]
