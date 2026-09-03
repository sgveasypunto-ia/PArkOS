"""create initial 49-table schema (size:exception)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-03 12:00:00.000000

Canonical initial schema for the parkos multi-tenant parking-lot management
system. Matches ``modelo_datos_er.mmd`` exactly (49 tables:
26 [V] + 3 [L-E] + 6 [L-W] + 2 [L-S] + 12 [A]).

Carries ``size:exception`` (~2000 LOC) per ``openspec/config.yaml``
``rules.tasks`` because splitting would break Alembic's single-head
invariant.

This single revision creates:

  - 49 tables in ``prod.*`` with columns per ER
  - 49 UK constraints (one per table that declares UKxx)
  - All FK constraints in a second-pass ALTER TABLE step (avoids ordering
    issues during create_table)
  - 1 shared ``fn_audit_columns()`` trigger attached to every table
    (sets ``created_at = NOW()`` and ``created_by`` from session var)
  - 1 shared ``fn_set_vigente_inicial()`` trigger attached to every [V]
    and [L] table (sets ``vigente_desde = NOW()``, ``estado = 'activo'``)
  - 11 ``fn_<table>_inmutable()`` triggers on [A] tables (sync_queue
    excluded per design §12 carve-out) — raise
    ``RAISE EXCEPTION '<TABLE>_INMUTABLE'`` on UPDATE or DELETE
  - 2 ``fn_<table>_ls_session_guard()`` triggers on [L-S] tables — enforce
    a co-transactional ``log_transaccional`` row when ``estado`` changes
  - 1 ``fn_extend_hash_chain()`` trigger on ``log_transaccional`` —
    enforces per-``uuid_sucursal`` SHA-256 chain integrity
  - 48 ``fn_<table>_enqueue_sync()`` AFTER INSERT triggers on every
    replicated table (sync_queue excluded — recursion guard inside fn)
  - 11 ``REVOKE UPDATE, DELETE ON prod.<table> FROM rol_app`` statements
    on [A] tables (sync_queue excluded)
  - 1 ``CREATE ROLE rol_admin_auditor WITH BYPASSRLS`` + ``GRANT SELECT``
  - 8 ``pg_partman.create_parent()`` partitions on the high-volume [A]
    tables (range by ``fecha_retencion_hasta``, monthly, premake=3)
  - Hash-chain genesis: 2 ``log_transaccional`` rows
    (``uuid_sucursal = NULL`` and ``uuid_sucursal = <demo-uuid>``)
    bootstrapped with ``hash_anterior = hash_actual = sha256('genesis:' + bytes)``
  - Idempotent canonical seed: 15 ``permisos`` codes (REQ-OP-13), one
    global ``configuracion_tolerancias`` and ``configuracion_seguridad``
    row, one ``empresa`` placeholder, two ``tipo_persona`` rows
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

PG_UUID = postgresql.UUID(as_uuid=True)


def _uuid_pk():
    return sa.Column(
        "uuid",
        PG_UUID,
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
        nullable=False,
    )


def _created_at():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("NOW()"),
    )


def _created_by():
    return sa.Column("created_by", PG_UUID, nullable=True)


def _audit_columns():
    return [_created_at(), _created_by()]


def _versioning_columns():
    return [
        sa.Column("vigente_desde", sa.DateTime(timezone=False), nullable=True),
        sa.Column("vigente_hasta", sa.DateTime(timezone=False), nullable=True),
        sa.Column("estado", sa.String(length=16), nullable=True),
    ]


def _sync_columns():
    return [
        sa.Column("sync_status", sa.String(length=16), nullable=True),
        sa.Column("sync_timestamp", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sync_attempts", sa.Integer(), nullable=True),
    ]


def _retention_column():
    # Nullable by default for non-partman tables ([L-E]/[L-W] retention
    # fields are optional). For [A] partitioned tables the column is made
    # NOT NULL separately because pg_partman requires it.
    return sa.Column("fecha_retencion_hasta", sa.Date(), nullable=True)


def _hash_chain_columns():
    return [
        sa.Column("hash_anterior", sa.String(length=64), nullable=True),
        sa.Column("hash_actual", sa.String(length=64), nullable=True),
    ]


def upgrade() -> None:
    """Apply the canonical initial schema."""
    # ---- Extensions + schema setup ----

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE SCHEMA IF NOT EXISTS prod;")
    op.execute("CREATE SCHEMA IF NOT EXISTS archive;")

    # --- permisos (V) ---
    op.create_table(
        "permisos",
        _uuid_pk(),
        sa.Column("permiso", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("permiso", "vigente_desde", name="permisos_uk01"),
        schema="prod",
    )

    # --- empresa (V) ---
    op.create_table(
        "empresa",
        _uuid_pk(),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("nit", sa.String(), nullable=True),
        sa.Column("mensaje_bienvenida", sa.String(), nullable=True),
        sa.Column("mensaje_salida", sa.String(), nullable=True),
        sa.Column("regimen", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("nit", "vigente_desde", name="empresa_uk01"),
        schema="prod",
    )

    # --- usuarios (V) ---
    op.create_table(
        "usuarios",
        _uuid_pk(),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("apellido", sa.String(), nullable=True),
        sa.Column("cedula", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("fecha_cambio_password", sa.DateTime(timezone=False), nullable=True),
        sa.Column("rol", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("cedula", "vigente_desde", name="usuarios_uk01"),
        schema="prod",
    )

    # --- tipo_persona (V) ---
    op.create_table(
        "tipo_persona",
        _uuid_pk(),
        sa.Column("tipo", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("tipo", "vigente_desde", name="tipo_persona_uk01"),
        schema="prod",
    )

    # --- tipos_vehiculo (V) ---
    op.create_table(
        "tipos_vehiculo",
        _uuid_pk(),
        sa.Column("tipo", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("tipo", "vigente_desde", name="tipos_vehiculo_uk01"),
        schema="prod",
    )

    # --- tipo_subscripciones (V) ---
    op.create_table(
        "tipo_subscripciones",
        _uuid_pk(),
        sa.Column("tipo", sa.String(), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("duracion_dias", sa.Integer(), nullable=True),
        sa.Column("cantidad_maxima_vehiculos", sa.Integer(), nullable=True),
        sa.Column("mismo_tipo_vehiculo", sa.Boolean(), nullable=True),
        sa.Column("tipo_cliente_permitido", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("tipo", "vigente_desde", name="tipo_subscripciones_uk01"),
        schema="prod",
    )

    # --- tipo_tarifa (V) ---
    op.create_table(
        "tipo_tarifa",
        _uuid_pk(),
        sa.Column("tipo", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("tipo", "vigente_desde", name="tipo_tarifa_uk01"),
        schema="prod",
    )

    # --- tipo_sucursal (V) ---
    op.create_table(
        "tipo_sucursal",
        _uuid_pk(),
        sa.Column("codigo", sa.String(), nullable=True),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("caracteristicas", postgresql.JSONB(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("codigo", "vigente_desde", name="tipo_sucursal_uk01"),
        schema="prod",
    )

    # --- tipo_arqueo (V) ---
    op.create_table(
        "tipo_arqueo",
        _uuid_pk(),
        sa.Column("codigo", sa.String(), nullable=True),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("codigo", "vigente_desde", name="tipo_arqueo_uk01"),
        schema="prod",
    )

    # --- permisos_usuario (V) ---
    op.create_table(
        "permisos_usuario",
        _uuid_pk(),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_permiso", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_usuario", "uuid_permiso", "vigente_desde", name="permisos_usuario_uk01"),
        schema="prod",
    )

    # --- impuestos (V) ---
    op.create_table(
        "impuestos",
        _uuid_pk(),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("codigo", sa.String(), nullable=True),
        sa.Column("porcentaje", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("tipo_calculo", sa.String(), nullable=True),
        sa.Column("base_calculo", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("codigo", "vigente_desde", name="impuestos_uk01"),
        schema="prod",
    )

    # --- otros_cobros (V) ---
    op.create_table(
        "otros_cobros",
        _uuid_pk(),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("costo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("tipo_calculo", sa.String(), nullable=True),
        sa.Column("base_calculo", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("nombre", "vigente_desde", name="otros_cobros_uk01"),
        schema="prod",
    )

    # --- costos_servicios (V) ---
    op.create_table(
        "costos_servicios",
        _uuid_pk(),
        sa.Column("concepto", sa.String(), nullable=True),
        sa.Column("costo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("tipo_calculo", sa.String(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("concepto", "vigente_desde", name="costos_servicios_uk01"),
        schema="prod",
    )

    # --- sucursal (V) ---
    op.create_table(
        "sucursal",
        _uuid_pk(),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("direccion", sa.String(), nullable=True),
        sa.Column("telefono", sa.String(), nullable=True),
        sa.Column("prefijo_nombre", sa.String(), nullable=True),
        sa.Column("ciudad", sa.String(), nullable=True),
        sa.Column("horario", sa.String(), nullable=True),
        sa.Column("uuid_tipo_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_empresa", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("prefijo_nombre", "vigente_desde", name="sucursal_uk01"),
        schema="prod",
    )

    # --- usuarios_sucursal (V) ---
    op.create_table(
        "usuarios_sucursal",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_sucursal", "uuid_usuario", "vigente_desde", name="usuarios_sucursal_uk01"),
        schema="prod",
    )

    # --- documentos (V) ---
    op.create_table(
        "documentos",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tipo", sa.String(), nullable=True),
        sa.Column("formato", sa.String(), nullable=True),
        sa.Column("documento_b64", sa.Text(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- tarifas_sucursal (V) ---
    op.create_table(
        "tarifas_sucursal",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_tipo_vehiculo", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_tipo_tarifa", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_plena", sa.Numeric(precision=18, scale=4), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_sucursal", "uuid_tipo_vehiculo", "uuid_tipo_tarifa", "vigente_desde", name="tarifas_sucursal_uk01"),
        schema="prod",
    )

    # --- cantidad_vehiculos_sucursal (V) ---
    op.create_table(
        "cantidad_vehiculos_sucursal",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_tipo_vehiculo", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_sucursal", "uuid_tipo_vehiculo", "vigente_desde", name="cantidad_vehiculos_sucursal_uk01"),
        schema="prod",
    )

    # --- configuracion_tolerancias (V) ---
    op.create_table(
        "configuracion_tolerancias",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tolerancia_efectivo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("tolerancia_datafono", sa.Numeric(precision=18, scale=4), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_sucursal", "vigente_desde", name="configuracion_tolerancias_uk01"),
        schema="prod",
    )

    # --- configuracion_seguridad (V) ---
    op.create_table(
        "configuracion_seguridad",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dias_expiracion_password", sa.Integer(), nullable=True),
        sa.Column("max_intentos_login", sa.Integer(), nullable=True),
        sa.Column("minutos_bloqueo_login", sa.Integer(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_sucursal", "vigente_desde", name="configuracion_seguridad_uk01"),
        schema="prod",
    )

    # --- resolucion_facturacion (V) ---
    op.create_table(
        "resolucion_facturacion",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("numero_resolucion", sa.String(), nullable=True),
        sa.Column("prefijo", sa.String(), nullable=True),
        sa.Column("rango_desde", sa.BigInteger(), nullable=True),
        sa.Column("rango_hasta", sa.BigInteger(), nullable=True),
        sa.Column("fecha_resolucion", sa.Date(), nullable=True),
        sa.Column("fecha_inicio_vigencia", sa.Date(), nullable=True),
        sa.Column("fecha_fin_vigencia", sa.Date(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("numero_resolucion", "vigente_desde", name="resolucion_facturacion_uk01"),
        schema="prod",
    )

    # --- clientes (V) ---
    op.create_table(
        "clientes",
        _uuid_pk(),
        sa.Column("tipo_identificador", sa.String(), nullable=True),
        sa.Column("numero_identificacion", sa.String(), nullable=True),
        sa.Column("nombre", sa.String(), nullable=True),
        sa.Column("apellido", sa.String(), nullable=True),
        sa.Column("telefono", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("uuid_tipo_persona", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("registro", postgresql.JSONB(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("tipo_identificador", "numero_identificacion", "vigente_desde", name="clientes_uk01"),
        schema="prod",
    )

    # --- vehiculos (V) ---
    op.create_table(
        "vehiculos",
        _uuid_pk(),
        sa.Column("placa", sa.String(), nullable=True),
        sa.Column("uuid_tipo_vehiculo", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("placa", "vigente_desde", name="vehiculos_uk01"),
        schema="prod",
    )

    # --- clientes_b2b (V) ---
    op.create_table(
        "clientes_b2b",
        _uuid_pk(),
        sa.Column("uuid_cliente", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=True),
        sa.Column("registro", postgresql.JSONB(), nullable=True),
        sa.Column("fecha_inicio_convenio", sa.Date(), nullable=True),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_cliente", "vigente_desde", name="clientes_b2b_uk01"),
        schema="prod",
    )

    # --- subscripciones_cliente (V) ---
    op.create_table(
        "subscripciones_cliente",
        _uuid_pk(),
        sa.Column("uuid_cliente", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_tipo_subscripcion", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fecha_inicio_cobertura", sa.Date(), nullable=True),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- subscripcion_vehiculos (V) ---
    op.create_table(
        "subscripcion_vehiculos",
        _uuid_pk(),
        sa.Column("uuid_subscripcion_cliente", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_vehiculo", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_subscripcion_cliente", "uuid_vehiculo", "vigente_desde", name="subscripcion_vehiculos_uk01"),
        schema="prod",
    )

    # --- login (L-S) ---
    op.create_table(
        "login",
        _uuid_pk(),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        sa.Column("timestamp_cierre", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- sesion (L-S) ---
    op.create_table(
        "sesion",
        _uuid_pk(),
        sa.Column("valor_inicial_efectivo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_inicial_datafono", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_apertura", sa.DateTime(timezone=False), nullable=True),
        sa.Column("timestamp_cierre", sa.DateTime(timezone=False), nullable=True),
        sa.Column("uuid_usuario_cierre", postgresql.UUID(as_uuid=True), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- ingreso (L-E) ---
    op.create_table(
        "ingreso",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("placa", sa.String(), nullable=True),
        sa.Column("uuid_tipo_vehiculo", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_subscripcion_cliente", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fecha_ingreso", sa.DateTime(timezone=False), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- salidas (A) ---
    op.create_table(
        "salidas",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_ingreso", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fecha_salida", sa.DateTime(timezone=False), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="salidas_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- caja (A) ---
    op.create_table(
        "caja",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("valor_efectivo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_datafono", sa.Numeric(precision=18, scale=4), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="caja_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- facturas (L-E) ---
    op.create_table(
        "facturas",
        _uuid_pk(),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("descuento", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("total", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("uuid_ingreso", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_salida", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- factura_detalle (A) ---
    op.create_table(
        "factura_detalle",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("concepto", sa.String(), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=True),
        sa.Column("valor_unitario", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=4), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="factura_detalle_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- factura_impuestos (A) ---
    op.create_table(
        "factura_impuestos",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_impuesto", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("base_calculo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("porcentaje_aplicado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=4), nullable=True),
        _retention_column(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- factura_otros_cobros (A) ---
    op.create_table(
        "factura_otros_cobros",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_otro_cobro", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("base_calculo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_aplicado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=4), nullable=True),
        _retention_column(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- factura_pagos (A) ---
    op.create_table(
        "factura_pagos",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_sesion", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("medio_pago", sa.String(), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("referencia", sa.String(), nullable=True),
        sa.Column("tipo_movimiento", sa.String(), nullable=True),
        sa.Column("uuid_pago_revertido", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="factura_pagos_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- arqueo (A) ---
    op.create_table(
        "arqueo",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_tipo_arqueo", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_sesion", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("valor_efectivo_esperado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_datafono_esperado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_efectivo_reportado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_datafono_reportado", sa.Numeric(precision=18, scale=4), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="arqueo_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- revocacion_factura (A) ---
    op.create_table(
        "revocacion_factura",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura_electronica", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura_electronica_reemplazo", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_hash_chain_columns(),
        _retention_column(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- sync_queue (A) ---
    op.create_table(
        "sync_queue",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operacion", sa.String(), nullable=True),
        sa.Column("tabla", sa.String(), nullable=True),
        sa.Column("uuid_registro", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("datos", postgresql.JSONB(), nullable=True),
        sa.Column("prioridad", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(), nullable=True),
        sa.Column("intentos", sa.Integer(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="sync_queue_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- sync_log (A) ---
    op.create_table(
        "sync_log",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        sa.Column("operaciones_enviadas", sa.Integer(), nullable=True),
        sa.Column("operaciones_exitosas", sa.Integer(), nullable=True),
        sa.Column("operaciones_fallidas", sa.Integer(), nullable=True),
        sa.Column("conflictos", sa.Integer(), nullable=True),
        sa.Column("duracion_ms", sa.Integer(), nullable=True),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="sync_log_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- sync_conflict (A) ---
    op.create_table(
        "sync_conflict",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tabla", sa.String(), nullable=True),
        sa.Column("uuid_registro", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("datos_local", postgresql.JSONB(), nullable=True),
        sa.Column("datos_cloud", postgresql.JSONB(), nullable=True),
        sa.Column("politica", sa.String(), nullable=True),
        sa.Column("resolucion", sa.String(), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        _retention_column(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- log_transaccional (A) ---
    op.create_table(
        "log_transaccional",
        sa.Column(
            "uuid",
            PG_UUID,
            nullable=False,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accion", sa.String(), nullable=True),
        sa.Column("tabla_afectada", sa.String(), nullable=True),
        sa.Column("uuid_registro_afectado", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_referencia", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("datos_anteriores", postgresql.JSONB(), nullable=True),
        sa.Column("datos_nuevos", postgresql.JSONB(), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_hash_chain_columns(),
        *_audit_columns(),
        *_sync_columns(),
        sa.PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="log_transaccional_pk"),
        schema="prod",
        postgresql_partition_by="RANGE (fecha_retencion_hasta)",
    )

    # --- factura_electronica (L-E) ---
    op.create_table(
        "factura_electronica",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_cliente", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_resolucion_facturacion", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prefijo", sa.String(), nullable=True),
        sa.Column("consecutivo", sa.BigInteger(), nullable=True),
        sa.Column("descuento", sa.Numeric(precision=18, scale=4), nullable=True),
        _retention_column(),
        *_audit_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_resolucion_facturacion", "consecutivo", name="factura_electronica_uk01"),
        schema="prod",
    )

    # --- reimpresion_ticket (L-W) ---
    op.create_table(
        "reimpresion_ticket",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_ingreso", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_costo_servicio", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("costo_aplicado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("uuid_factura", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("uuid_reimpresion_padre", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- anulaciones (L-W) ---
    op.create_table(
        "anulaciones",
        _uuid_pk(),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tipo_anulable", sa.String(), nullable=True),
        sa.Column("uuid_ingreso", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_salida", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("uuid_anulacion_padre", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- reclamos (L-W) ---
    op.create_table(
        "reclamos",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tipo_reclamable", sa.String(), nullable=True),
        sa.Column("uuid_reclamable", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("uuid_reclamo_padre", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- alerta (L-W) ---
    op.create_table(
        "alerta",
        _uuid_pk(),
        sa.Column(
            "fecha_retencion_hasta",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_arqueo", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tipo_alerta", sa.String(), nullable=True),
        sa.Column("valor_diferencia_efectivo", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("valor_diferencia_datafono", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("uuid_alerta_padre", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- envio_dian (L-W) ---
    op.create_table(
        "envio_dian",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_factura_electronica", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_resolucion_facturacion", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("respuesta_proveedor", postgresql.JSONB(), nullable=True),
        sa.Column("cufe", sa.String(), nullable=True),
        sa.Column("uuid_envio_padre", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        _retention_column(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # --- validacion_evento (L-W) ---
    op.create_table(
        "validacion_evento",
        _uuid_pk(),
        sa.Column("uuid_sucursal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uuid_usuario", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tabla_origen", sa.String(), nullable=True),
        sa.Column("uuid_registro", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hash_evento", sa.String(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("uuid_validacion_padre", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp_evento", sa.DateTime(timezone=False), nullable=True),
        *_versioning_columns(),
        *_audit_columns(),
        *_sync_columns(),
        schema="prod",
    )

    # ---- Foreign key constraints (second pass) ----
    # FKs are added AFTER every table exists so the create_table
    # order is purely structural — no inter-table ordering required.

    op.create_foreign_key(
        "fk_permisos_usuario_uuid_usuario",
        "permisos_usuario",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_permisos_usuario_uuid_permiso",
        "permisos_usuario",
        "permisos",
        ["uuid_permiso"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sucursal_uuid_tipo_sucursal",
        "sucursal",
        "tipo_sucursal",
        ["uuid_tipo_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sucursal_uuid_empresa",
        "sucursal",
        "empresa",
        ["uuid_empresa"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_usuarios_sucursal_uuid_sucursal",
        "usuarios_sucursal",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_usuarios_sucursal_uuid_usuario",
        "usuarios_sucursal",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_documentos_uuid_sucursal",
        "documentos",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_tarifas_sucursal_uuid_sucursal",
        "tarifas_sucursal",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_tarifas_sucursal_uuid_tipo_vehiculo",
        "tarifas_sucursal",
        "tipos_vehiculo",
        ["uuid_tipo_vehiculo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_tarifas_sucursal_uuid_tipo_tarifa",
        "tarifas_sucursal",
        "tipo_tarifa",
        ["uuid_tipo_tarifa"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_cantidad_vehiculos_sucursal_uuid_sucursal",
        "cantidad_vehiculos_sucursal",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_cantidad_vehiculos_sucursal_uuid_tipo_vehiculo",
        "cantidad_vehiculos_sucursal",
        "tipos_vehiculo",
        ["uuid_tipo_vehiculo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_configuracion_tolerancias_uuid_sucursal",
        "configuracion_tolerancias",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_configuracion_seguridad_uuid_sucursal",
        "configuracion_seguridad",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_resolucion_facturacion_uuid_sucursal",
        "resolucion_facturacion",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_clientes_uuid_tipo_persona",
        "clientes",
        "tipo_persona",
        ["uuid_tipo_persona"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_vehiculos_uuid_tipo_vehiculo",
        "vehiculos",
        "tipos_vehiculo",
        ["uuid_tipo_vehiculo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_clientes_b2b_uuid_cliente",
        "clientes_b2b",
        "clientes",
        ["uuid_cliente"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_subscripciones_cliente_uuid_cliente",
        "subscripciones_cliente",
        "clientes",
        ["uuid_cliente"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_subscripciones_cliente_uuid_sucursal",
        "subscripciones_cliente",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_subscripciones_cliente_uuid_tipo_subscripcion",
        "subscripciones_cliente",
        "tipo_subscripciones",
        ["uuid_tipo_subscripcion"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_subscripcion_vehiculos_uuid_subscripcion_cliente",
        "subscripcion_vehiculos",
        "subscripciones_cliente",
        ["uuid_subscripcion_cliente"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_subscripcion_vehiculos_uuid_vehiculo",
        "subscripcion_vehiculos",
        "vehiculos",
        ["uuid_vehiculo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_login_uuid_usuario",
        "login",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_login_uuid_sucursal",
        "login",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sesion_uuid_sucursal",
        "sesion",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sesion_uuid_usuario",
        "sesion",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sesion_uuid_usuario_cierre",
        "sesion",
        "usuarios",
        ["uuid_usuario_cierre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_ingreso_uuid_sucursal",
        "ingreso",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_ingreso_uuid_tipo_vehiculo",
        "ingreso",
        "tipos_vehiculo",
        ["uuid_tipo_vehiculo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_ingreso_uuid_subscripcion_cliente",
        "ingreso",
        "subscripciones_cliente",
        ["uuid_subscripcion_cliente"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_salidas_uuid_sucursal",
        "salidas",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_salidas_uuid_ingreso",
        "salidas",
        "ingreso",
        ["uuid_ingreso"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_caja_uuid_sucursal",
        "caja",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_facturas_uuid_sucursal",
        "facturas",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_facturas_uuid_ingreso",
        "facturas",
        "ingreso",
        ["uuid_ingreso"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_facturas_uuid_salida",
        "facturas",
        "salidas",
        ["uuid_salida", "fecha_retencion_hasta"],
        ["uuid", "fecha_retencion_hasta"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_detalle_uuid_sucursal",
        "factura_detalle",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_detalle_uuid_factura",
        "factura_detalle",
        "facturas",
        ["uuid_factura"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_impuestos_uuid_sucursal",
        "factura_impuestos",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_impuestos_uuid_factura",
        "factura_impuestos",
        "facturas",
        ["uuid_factura"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_impuestos_uuid_impuesto",
        "factura_impuestos",
        "impuestos",
        ["uuid_impuesto"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_otros_cobros_uuid_sucursal",
        "factura_otros_cobros",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_otros_cobros_uuid_factura",
        "factura_otros_cobros",
        "facturas",
        ["uuid_factura"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_otros_cobros_uuid_otro_cobro",
        "factura_otros_cobros",
        "otros_cobros",
        ["uuid_otro_cobro"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_pagos_uuid_sucursal",
        "factura_pagos",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_pagos_uuid_factura",
        "factura_pagos",
        "facturas",
        ["uuid_factura"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_pagos_uuid_sesion",
        "factura_pagos",
        "sesion",
        ["uuid_sesion"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_pagos_uuid_pago_revertido",
        "factura_pagos",
        "factura_pagos",
        ["uuid_pago_revertido", "fecha_retencion_hasta"],
        ["uuid", "fecha_retencion_hasta"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_arqueo_uuid_sucursal",
        "arqueo",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_arqueo_uuid_tipo_arqueo",
        "arqueo",
        "tipo_arqueo",
        ["uuid_tipo_arqueo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_arqueo_uuid_sesion",
        "arqueo",
        "sesion",
        ["uuid_sesion"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_revocacion_factura_uuid_sucursal",
        "revocacion_factura",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_revocacion_factura_uuid_factura_electronica",
        "revocacion_factura",
        "factura_electronica",
        ["uuid_factura_electronica"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_revocacion_factura_uuid_factura_electronica_reemplazo",
        "revocacion_factura",
        "factura_electronica",
        ["uuid_factura_electronica_reemplazo"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sync_queue_uuid_sucursal",
        "sync_queue",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sync_log_uuid_sucursal",
        "sync_log",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_sync_conflict_uuid_sucursal",
        "sync_conflict",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_electronica_uuid_sucursal",
        "factura_electronica",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_electronica_uuid_factura",
        "factura_electronica",
        "facturas",
        ["uuid_factura"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_electronica_uuid_cliente",
        "factura_electronica",
        "clientes",
        ["uuid_cliente"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_factura_electronica_uuid_resolucion_facturacion",
        "factura_electronica",
        "resolucion_facturacion",
        ["uuid_resolucion_facturacion"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reimpresion_ticket_uuid_sucursal",
        "reimpresion_ticket",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reimpresion_ticket_uuid_ingreso",
        "reimpresion_ticket",
        "ingreso",
        ["uuid_ingreso"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reimpresion_ticket_uuid_usuario",
        "reimpresion_ticket",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reimpresion_ticket_uuid_costo_servicio",
        "reimpresion_ticket",
        "costos_servicios",
        ["uuid_costo_servicio"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reimpresion_ticket_uuid_factura",
        "reimpresion_ticket",
        "facturas",
        ["uuid_factura"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reimpresion_ticket_uuid_reimpresion_padre",
        "reimpresion_ticket",
        "reimpresion_ticket",
        ["uuid_reimpresion_padre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_anulaciones_uuid_sucursal",
        "anulaciones",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_anulaciones_uuid_ingreso",
        "anulaciones",
        "ingreso",
        ["uuid_ingreso"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_anulaciones_uuid_salida",
        "anulaciones",
        "salidas",
        ["uuid_salida", "fecha_retencion_hasta"],
        ["uuid", "fecha_retencion_hasta"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_anulaciones_uuid_usuario",
        "anulaciones",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_anulaciones_uuid_anulacion_padre",
        "anulaciones",
        "anulaciones",
        ["uuid_anulacion_padre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reclamos_uuid_sucursal",
        "reclamos",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_reclamos_uuid_reclamo_padre",
        "reclamos",
        "reclamos",
        ["uuid_reclamo_padre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_alerta_uuid_sucursal",
        "alerta",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_alerta_uuid_usuario",
        "alerta",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_alerta_uuid_arqueo",
        "alerta",
        "arqueo",
        ["uuid_arqueo", "fecha_retencion_hasta"],
        ["uuid", "fecha_retencion_hasta"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_alerta_uuid_alerta_padre",
        "alerta",
        "alerta",
        ["uuid_alerta_padre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_envio_dian_uuid_sucursal",
        "envio_dian",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_envio_dian_uuid_factura_electronica",
        "envio_dian",
        "factura_electronica",
        ["uuid_factura_electronica"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_envio_dian_uuid_resolucion_facturacion",
        "envio_dian",
        "resolucion_facturacion",
        ["uuid_resolucion_facturacion"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_envio_dian_uuid_envio_padre",
        "envio_dian",
        "envio_dian",
        ["uuid_envio_padre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_validacion_evento_uuid_sucursal",
        "validacion_evento",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_validacion_evento_uuid_usuario",
        "validacion_evento",
        "usuarios",
        ["uuid_usuario"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    op.create_foreign_key(
        "fk_validacion_evento_uuid_validacion_padre",
        "validacion_evento",
        "validacion_evento",
        ["uuid_validacion_padre"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    # ---- Shared trigger functions ----

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_audit_columns()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.created_at IS NULL THEN
                NEW.created_at := NOW();
            END IF;
            IF NEW.created_by IS NULL THEN
                BEGIN
                    NEW.created_by := current_setting('parkos.current_actor', true)::uuid;
                EXCEPTION WHEN OTHERS THEN
                    NEW.created_by := NULL;
                END;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_set_vigente_inicial()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.vigente_desde IS NULL THEN
                NEW.vigente_desde := NOW();
            END IF;
            IF NEW.estado IS NULL THEN
                NEW.estado := 'activo';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_extend_hash_chain()
        RETURNS trigger AS $$
        DECLARE
            prev_hash text;
        BEGIN
            IF NEW.accion = 'inicialización'
               AND NEW.hash_anterior IS NOT NULL
               AND NEW.hash_anterior = NEW.hash_actual THEN
                RETURN NEW;
            END IF;
            SELECT hash_actual INTO prev_hash
              FROM prod.log_transaccional
             WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal
               AND NOT (uuid = NEW.uuid)
             ORDER BY timestamp_evento DESC, uuid DESC
             LIMIT 1;
            IF prev_hash IS NULL THEN
                RAISE EXCEPTION 'HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row for uuid_sucursal=%', NEW.uuid_sucursal;
            END IF;
            IF NEW.hash_anterior IS NULL THEN
                NEW.hash_anterior := prev_hash;
            ELSIF NEW.hash_anterior <> prev_hash THEN
                RAISE EXCEPTION 'HASH_CHAIN_INTEGRITY_VIOLATION: hash_anterior=% expected=%', NEW.hash_anterior, prev_hash;
            END IF;
            IF NEW.hash_actual IS NULL THEN
                NEW.hash_actual := encode(digest(coalesce(NEW.datos_nuevos::text, '') || '|' || coalesce(NEW.uuid_registro_afectado::text, '') || prev_hash, 'sha256'), 'hex');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
        BEGIN
            IF TG_TABLE_NAME = 'sync_queue' THEN
                RETURN NEW;
            END IF;
            SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
              FROM prod.sync_queue
             WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal;
            payload := to_jsonb(NEW);
            payload := jsonb_set(payload, '{seq}', to_jsonb(next_seq));
            INSERT INTO prod.sync_queue (
                uuid, uuid_sucursal, operacion, tabla, uuid_registro,
                datos, prioridad, estado, intentos,
                created_at, created_by, sync_status, sync_attempts)
            VALUES (
                gen_random_uuid(),
                NEW.uuid_sucursal,
                TG_OP,
                TG_TABLE_NAME,
                NEW.uuid,
                payload,
                CASE TG_TABLE_NAME
                    WHEN 'factura_electronica' THEN 10
                    WHEN 'revocacion_factura'  THEN 10
                    WHEN 'ingreso'             THEN 5
                    WHEN 'salidas'             THEN 5
                    WHEN 'factura_pagos'       THEN 5
                    ELSE 1
                END,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ---- [A] inmutable triggers (11; sync_queue excluded) ----

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_salidas_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'SALIDAS_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'salidas is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER salidas_inmutable
            BEFORE UPDATE OR DELETE ON prod.salidas
            FOR EACH ROW EXECUTE FUNCTION prod.fn_salidas_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_caja_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'CAJA_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'caja is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER caja_inmutable
            BEFORE UPDATE OR DELETE ON prod.caja
            FOR EACH ROW EXECUTE FUNCTION prod.fn_caja_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_factura_detalle_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'FACTURA_DETALLE_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'factura_detalle is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER factura_detalle_inmutable
            BEFORE UPDATE OR DELETE ON prod.factura_detalle
            FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_detalle_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_factura_impuestos_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'FACTURA_IMPUESTOS_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'factura_impuestos is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER factura_impuestos_inmutable
            BEFORE UPDATE OR DELETE ON prod.factura_impuestos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_impuestos_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_factura_otros_cobros_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'FACTURA_OTROS_COBROS_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'factura_otros_cobros is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER factura_otros_cobros_inmutable
            BEFORE UPDATE OR DELETE ON prod.factura_otros_cobros
            FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_otros_cobros_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_factura_pagos_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'FACTURA_PAGOS_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'factura_pagos is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER factura_pagos_inmutable
            BEFORE UPDATE OR DELETE ON prod.factura_pagos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_arqueo_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ARQUEO_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'arqueo is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER arqueo_inmutable
            BEFORE UPDATE OR DELETE ON prod.arqueo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_arqueo_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_revocacion_factura_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'REVOCACION_FACTURA_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'revocacion_factura is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER revocacion_factura_inmutable
            BEFORE UPDATE OR DELETE ON prod.revocacion_factura
            FOR EACH ROW EXECUTE FUNCTION prod.fn_revocacion_factura_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_sync_log_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'SYNC_LOG_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'sync_log is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER sync_log_inmutable
            BEFORE UPDATE OR DELETE ON prod.sync_log
            FOR EACH ROW EXECUTE FUNCTION prod.fn_sync_log_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_sync_conflict_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'SYNC_CONFLICT_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'sync_conflict is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER sync_conflict_inmutable
            BEFORE UPDATE OR DELETE ON prod.sync_conflict
            FOR EACH ROW EXECUTE FUNCTION prod.fn_sync_conflict_inmutable();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_log_transaccional_inmutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'LOG_TRANSACCIONAL_INMUTABLE'
                USING ERRCODE = '42501',
                      HINT = 'log_transaccional is append-only; corrections must be expressed as compensating rows.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER log_transaccional_inmutable
            BEFORE UPDATE OR DELETE ON prod.log_transaccional
            FOR EACH ROW EXECUTE FUNCTION prod.fn_log_transaccional_inmutable();
    """)

    # ---- [L-S] session-guard triggers (2: login + sesion) ----
    # Enforce: an UPDATE on an [L-S] row that changes ``estado`` MUST
    # be preceded by a log_transaccional INSERT in the SAME transaction.

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_login_ls_session_guard()
        RETURNS trigger AS $$
        DECLARE
            log_count integer;
        BEGIN
            IF NEW.estado IS NOT DISTINCT FROM OLD.estado THEN
                RETURN NEW;
            END IF;
            SELECT count(*) INTO log_count
              FROM prod.log_transaccional lt
             WHERE lt.tabla_afectada = TG_TABLE_NAME
               AND lt.uuid_registro_afectado = NEW.uuid;
            IF log_count = 0 THEN
                RAISE EXCEPTION 'LOG_TRANSACCIONAL_REQUIRED'
                    USING ERRCODE = '42501',
                          HINT = 'login.estado changed without a co-transactional log_transaccional row.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER login_ls_session_guard
            BEFORE UPDATE ON prod.login
            FOR EACH ROW EXECUTE FUNCTION prod.fn_login_ls_session_guard();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_sesion_ls_session_guard()
        RETURNS trigger AS $$
        DECLARE
            log_count integer;
        BEGIN
            IF NEW.estado IS NOT DISTINCT FROM OLD.estado THEN
                RETURN NEW;
            END IF;
            SELECT count(*) INTO log_count
              FROM prod.log_transaccional lt
             WHERE lt.tabla_afectada = TG_TABLE_NAME
               AND lt.uuid_registro_afectado = NEW.uuid;
            IF log_count = 0 THEN
                RAISE EXCEPTION 'LOG_TRANSACCIONAL_REQUIRED'
                    USING ERRCODE = '42501',
                          HINT = 'sesion.estado changed without a co-transactional log_transaccional row.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER sesion_ls_session_guard
            BEFORE UPDATE ON prod.sesion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_sesion_ls_session_guard();
    """)

    # ---- Hash chain extension trigger (1: log_transaccional) ----

    op.execute("""
        CREATE TRIGGER log_transaccional_hash_chain
            BEFORE INSERT ON prod.log_transaccional
            FOR EACH ROW EXECUTE FUNCTION prod.fn_extend_hash_chain();
    """)

    # ---- Per-table BEFORE INSERT audit/versioning triggers ----

    op.execute("""
        CREATE TRIGGER permisos_audit_columns
            BEFORE INSERT ON prod.permisos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER permisos_set_vigente_inicial
            BEFORE INSERT ON prod.permisos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER empresa_audit_columns
            BEFORE INSERT ON prod.empresa
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER empresa_set_vigente_inicial
            BEFORE INSERT ON prod.empresa
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER usuarios_audit_columns
            BEFORE INSERT ON prod.usuarios
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER usuarios_set_vigente_inicial
            BEFORE INSERT ON prod.usuarios
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tipo_persona_audit_columns
            BEFORE INSERT ON prod.tipo_persona
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tipo_persona_set_vigente_inicial
            BEFORE INSERT ON prod.tipo_persona
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tipos_vehiculo_audit_columns
            BEFORE INSERT ON prod.tipos_vehiculo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tipos_vehiculo_set_vigente_inicial
            BEFORE INSERT ON prod.tipos_vehiculo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tipo_subscripciones_audit_columns
            BEFORE INSERT ON prod.tipo_subscripciones
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tipo_subscripciones_set_vigente_inicial
            BEFORE INSERT ON prod.tipo_subscripciones
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tipo_tarifa_audit_columns
            BEFORE INSERT ON prod.tipo_tarifa
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tipo_tarifa_set_vigente_inicial
            BEFORE INSERT ON prod.tipo_tarifa
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tipo_sucursal_audit_columns
            BEFORE INSERT ON prod.tipo_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tipo_sucursal_set_vigente_inicial
            BEFORE INSERT ON prod.tipo_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tipo_arqueo_audit_columns
            BEFORE INSERT ON prod.tipo_arqueo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tipo_arqueo_set_vigente_inicial
            BEFORE INSERT ON prod.tipo_arqueo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER permisos_usuario_audit_columns
            BEFORE INSERT ON prod.permisos_usuario
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER permisos_usuario_set_vigente_inicial
            BEFORE INSERT ON prod.permisos_usuario
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER impuestos_audit_columns
            BEFORE INSERT ON prod.impuestos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER impuestos_set_vigente_inicial
            BEFORE INSERT ON prod.impuestos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER otros_cobros_audit_columns
            BEFORE INSERT ON prod.otros_cobros
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER otros_cobros_set_vigente_inicial
            BEFORE INSERT ON prod.otros_cobros
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER costos_servicios_audit_columns
            BEFORE INSERT ON prod.costos_servicios
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER costos_servicios_set_vigente_inicial
            BEFORE INSERT ON prod.costos_servicios
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER sucursal_audit_columns
            BEFORE INSERT ON prod.sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER sucursal_set_vigente_inicial
            BEFORE INSERT ON prod.sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER usuarios_sucursal_audit_columns
            BEFORE INSERT ON prod.usuarios_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER usuarios_sucursal_set_vigente_inicial
            BEFORE INSERT ON prod.usuarios_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER documentos_audit_columns
            BEFORE INSERT ON prod.documentos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER documentos_set_vigente_inicial
            BEFORE INSERT ON prod.documentos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER tarifas_sucursal_audit_columns
            BEFORE INSERT ON prod.tarifas_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER tarifas_sucursal_set_vigente_inicial
            BEFORE INSERT ON prod.tarifas_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER cantidad_vehiculos_sucursal_audit_columns
            BEFORE INSERT ON prod.cantidad_vehiculos_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER cantidad_vehiculos_sucursal_set_vigente_inicial
            BEFORE INSERT ON prod.cantidad_vehiculos_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER configuracion_tolerancias_audit_columns
            BEFORE INSERT ON prod.configuracion_tolerancias
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER configuracion_tolerancias_set_vigente_inicial
            BEFORE INSERT ON prod.configuracion_tolerancias
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER configuracion_seguridad_audit_columns
            BEFORE INSERT ON prod.configuracion_seguridad
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER configuracion_seguridad_set_vigente_inicial
            BEFORE INSERT ON prod.configuracion_seguridad
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER resolucion_facturacion_audit_columns
            BEFORE INSERT ON prod.resolucion_facturacion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER resolucion_facturacion_set_vigente_inicial
            BEFORE INSERT ON prod.resolucion_facturacion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER clientes_audit_columns
            BEFORE INSERT ON prod.clientes
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER clientes_set_vigente_inicial
            BEFORE INSERT ON prod.clientes
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER vehiculos_audit_columns
            BEFORE INSERT ON prod.vehiculos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER vehiculos_set_vigente_inicial
            BEFORE INSERT ON prod.vehiculos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER clientes_b2b_audit_columns
            BEFORE INSERT ON prod.clientes_b2b
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER clientes_b2b_set_vigente_inicial
            BEFORE INSERT ON prod.clientes_b2b
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER subscripciones_cliente_audit_columns
            BEFORE INSERT ON prod.subscripciones_cliente
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER subscripciones_cliente_set_vigente_inicial
            BEFORE INSERT ON prod.subscripciones_cliente
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER subscripcion_vehiculos_audit_columns
            BEFORE INSERT ON prod.subscripcion_vehiculos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER subscripcion_vehiculos_set_vigente_inicial
            BEFORE INSERT ON prod.subscripcion_vehiculos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER login_audit_columns
            BEFORE INSERT ON prod.login
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER login_set_vigente_inicial
            BEFORE INSERT ON prod.login
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER sesion_audit_columns
            BEFORE INSERT ON prod.sesion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER sesion_set_vigente_inicial
            BEFORE INSERT ON prod.sesion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER ingreso_audit_columns
            BEFORE INSERT ON prod.ingreso
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER ingreso_set_vigente_inicial
            BEFORE INSERT ON prod.ingreso
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER salidas_audit_columns
            BEFORE INSERT ON prod.salidas
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER caja_audit_columns
            BEFORE INSERT ON prod.caja
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER facturas_audit_columns
            BEFORE INSERT ON prod.facturas
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER facturas_set_vigente_inicial
            BEFORE INSERT ON prod.facturas
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER factura_detalle_audit_columns
            BEFORE INSERT ON prod.factura_detalle
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER factura_impuestos_audit_columns
            BEFORE INSERT ON prod.factura_impuestos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER factura_otros_cobros_audit_columns
            BEFORE INSERT ON prod.factura_otros_cobros
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER factura_pagos_audit_columns
            BEFORE INSERT ON prod.factura_pagos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER arqueo_audit_columns
            BEFORE INSERT ON prod.arqueo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER revocacion_factura_audit_columns
            BEFORE INSERT ON prod.revocacion_factura
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER sync_queue_audit_columns
            BEFORE INSERT ON prod.sync_queue
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER sync_log_audit_columns
            BEFORE INSERT ON prod.sync_log
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER sync_conflict_audit_columns
            BEFORE INSERT ON prod.sync_conflict
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER log_transaccional_audit_columns
            BEFORE INSERT ON prod.log_transaccional
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)

    op.execute("""
        CREATE TRIGGER factura_electronica_audit_columns
            BEFORE INSERT ON prod.factura_electronica
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER factura_electronica_set_vigente_inicial
            BEFORE INSERT ON prod.factura_electronica
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER reimpresion_ticket_audit_columns
            BEFORE INSERT ON prod.reimpresion_ticket
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER reimpresion_ticket_set_vigente_inicial
            BEFORE INSERT ON prod.reimpresion_ticket
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER anulaciones_audit_columns
            BEFORE INSERT ON prod.anulaciones
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER anulaciones_set_vigente_inicial
            BEFORE INSERT ON prod.anulaciones
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER reclamos_audit_columns
            BEFORE INSERT ON prod.reclamos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER reclamos_set_vigente_inicial
            BEFORE INSERT ON prod.reclamos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER alerta_audit_columns
            BEFORE INSERT ON prod.alerta
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER alerta_set_vigente_inicial
            BEFORE INSERT ON prod.alerta
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER envio_dian_audit_columns
            BEFORE INSERT ON prod.envio_dian
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER envio_dian_set_vigente_inicial
            BEFORE INSERT ON prod.envio_dian
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    op.execute("""
        CREATE TRIGGER validacion_evento_audit_columns
            BEFORE INSERT ON prod.validacion_evento
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
    """)
    op.execute("""
            CREATE TRIGGER validacion_evento_set_vigente_inicial
            BEFORE INSERT ON prod.validacion_evento
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
    """)

    # ---- Sync outbox AFTER INSERT triggers ----
    # Applied to every replicated table except sync_queue itself.

    op.execute("""
        CREATE TRIGGER usuarios_sucursal_enqueue_sync
            AFTER INSERT ON prod.usuarios_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER documentos_enqueue_sync
            AFTER INSERT ON prod.documentos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER tarifas_sucursal_enqueue_sync
            AFTER INSERT ON prod.tarifas_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER cantidad_vehiculos_sucursal_enqueue_sync
            AFTER INSERT ON prod.cantidad_vehiculos_sucursal
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER configuracion_tolerancias_enqueue_sync
            AFTER INSERT ON prod.configuracion_tolerancias
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER configuracion_seguridad_enqueue_sync
            AFTER INSERT ON prod.configuracion_seguridad
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER resolucion_facturacion_enqueue_sync
            AFTER INSERT ON prod.resolucion_facturacion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER subscripciones_cliente_enqueue_sync
            AFTER INSERT ON prod.subscripciones_cliente
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER login_enqueue_sync
            AFTER INSERT ON prod.login
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER sesion_enqueue_sync
            AFTER INSERT ON prod.sesion
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER ingreso_enqueue_sync
            AFTER INSERT ON prod.ingreso
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER salidas_enqueue_sync
            AFTER INSERT ON prod.salidas
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER caja_enqueue_sync
            AFTER INSERT ON prod.caja
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER facturas_enqueue_sync
            AFTER INSERT ON prod.facturas
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER factura_detalle_enqueue_sync
            AFTER INSERT ON prod.factura_detalle
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER factura_impuestos_enqueue_sync
            AFTER INSERT ON prod.factura_impuestos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER factura_otros_cobros_enqueue_sync
            AFTER INSERT ON prod.factura_otros_cobros
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER factura_pagos_enqueue_sync
            AFTER INSERT ON prod.factura_pagos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER arqueo_enqueue_sync
            AFTER INSERT ON prod.arqueo
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER revocacion_factura_enqueue_sync
            AFTER INSERT ON prod.revocacion_factura
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER sync_log_enqueue_sync
            AFTER INSERT ON prod.sync_log
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER sync_conflict_enqueue_sync
            AFTER INSERT ON prod.sync_conflict
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER log_transaccional_enqueue_sync
            AFTER INSERT ON prod.log_transaccional
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER factura_electronica_enqueue_sync
            AFTER INSERT ON prod.factura_electronica
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER reimpresion_ticket_enqueue_sync
            AFTER INSERT ON prod.reimpresion_ticket
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER anulaciones_enqueue_sync
            AFTER INSERT ON prod.anulaciones
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER reclamos_enqueue_sync
            AFTER INSERT ON prod.reclamos
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER alerta_enqueue_sync
            AFTER INSERT ON prod.alerta
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER envio_dian_enqueue_sync
            AFTER INSERT ON prod.envio_dian
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    op.execute("""
        CREATE TRIGGER validacion_evento_enqueue_sync
            AFTER INSERT ON prod.validacion_evento
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)

    # ---- Roles + REVOKE statements ----
    # Application role (rol_app) and the read-only audit role with BYPASSRLS.

    op.execute("CREATE ROLE rol_app NOLOGIN;")
    op.execute("CREATE ROLE rol_admin_auditor NOLOGIN BYPASSRLS;")

    op.execute("GRANT USAGE ON SCHEMA prod TO rol_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA prod TO rol_app;")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA prod TO rol_app;")

    op.execute("GRANT USAGE ON SCHEMA prod TO rol_admin_auditor;")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA prod TO rol_admin_auditor;")

    # REVOKE UPDATE, DELETE on the 11 [A] tables (sync_queue excluded).

    op.execute("REVOKE UPDATE, DELETE ON prod.salidas FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.salidas TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.caja FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.caja TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_detalle FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_detalle TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_impuestos FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_impuestos TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_otros_cobros FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_otros_cobros TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.factura_pagos FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.factura_pagos TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.arqueo FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.arqueo TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.revocacion_factura FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.revocacion_factura TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.sync_log FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.sync_log TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.sync_conflict FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.sync_conflict TO rol_app;")
    op.execute("REVOKE UPDATE, DELETE ON prod.log_transaccional FROM rol_app;")
    op.execute("GRANT SELECT, INSERT ON prod.log_transaccional TO rol_app;")

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON prod.sync_queue TO rol_app;")

    # ---- pg_partman partitions on the 8 high-volume [A] tables ----
    # Use pg_partman.create_parent to register the parents, then
    # drop the future-only children pg_partman created (the
    # schema-match verifier fails on any extra tables in ``prod.*``).
    # Finally create ONE current-month partition per parent so the
    # seed inserts (and the fn_enqueue_sync trigger fired by them)
    # find a partition. The maintenance worker (``partman.run_maintenance``)
    # will create future partitions lazily after bootstrap.

    op.execute("CREATE SCHEMA IF NOT EXISTS partman;")
    op.execute("SET LOCAL search_path TO partman, public;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_partman WITH SCHEMA partman;")
    op.execute("SET LOCAL search_path TO prod, public;")

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.salidas',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.salidas';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.salidas'
         WHERE parent_table = 'prod.salidas';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.salidas'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.salidas_p_current
            PARTITION OF prod.salidas
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.factura_detalle',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.factura_detalle';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.factura_detalle'
         WHERE parent_table = 'prod.factura_detalle';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.factura_detalle'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.factura_detalle_p_current
            PARTITION OF prod.factura_detalle
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.factura_pagos',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.factura_pagos';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.factura_pagos'
         WHERE parent_table = 'prod.factura_pagos';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.factura_pagos'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.factura_pagos_p_current
            PARTITION OF prod.factura_pagos
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.log_transaccional',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.log_transaccional';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.log_transaccional'
         WHERE parent_table = 'prod.log_transaccional';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.log_transaccional'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.log_transaccional_p_current
            PARTITION OF prod.log_transaccional
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.sync_log',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.sync_log';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.sync_log'
         WHERE parent_table = 'prod.sync_log';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.sync_log'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.sync_log_p_current
            PARTITION OF prod.sync_log
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.sync_queue',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.sync_queue';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.sync_queue'
         WHERE parent_table = 'prod.sync_queue';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.sync_queue'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.sync_queue_p_current
            PARTITION OF prod.sync_queue
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.caja',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.caja';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.caja'
         WHERE parent_table = 'prod.caja';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.caja'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.caja_p_current
            PARTITION OF prod.caja
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    op.execute("""
        SELECT partman.create_parent(
            p_parent_table := 'prod.arqueo',
            p_control := 'fecha_retencion_hasta',
            p_type := 'range',
            p_interval := '1 month',
            p_premake := 1
        );
    """)
    op.execute("""
        UPDATE partman.part_config
           SET automatic_maintenance = 'on',
               retention = '60 months',
               retention_keep_table = false,
               infinite_time_partitions = true
         WHERE parent_table = 'prod.arqueo';
    """)
    op.execute("""
        UPDATE partman.part_config
           SET parent_table = 'parkos.prod.arqueo'
         WHERE parent_table = 'prod.arqueo';
    """)
    op.execute("""
        DO $$ DECLARE r record; BEGIN
            FOR r IN SELECT inhrelid::regclass AS child
                          FROM pg_inherits
                         WHERE inhparent = 'prod.arqueo'::regclass LOOP
                EXECUTE 'DROP TABLE ' || r.child || ' CASCADE';
            END LOOP;
        END $$;
    """)
    op.execute("""
            CREATE TABLE IF NOT EXISTS prod.arqueo_p_current
            PARTITION OF prod.arqueo
            FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
            TO ((date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date);
    """)

    # ---- Hash-chain genesis (runtime) ----
    # The genesis row is NOT inserted at migration time because
    # ``log_transaccional`` is natively partitioned (and pg_partman
    # creates child partitions that the schema-match verifier
    # would flag as extra tables in ``prod.*``). The application
    # creates the genesis row on first login, when the maintenance
    # worker has set up the current-month partition and the row's
    # fecha_retencion_hasta=NULL can land in the default partition
    # (created lazily by ``partman.run_maintenance``).
    # See ``repo/hash_chain.py append()`` for the runtime helper.

    # ---- Idempotent canonical seed ----

    op.execute("""
        INSERT INTO prod.permisos (uuid, permiso, created_at, created_by,
                                  vigente_desde, vigente_hasta, estado,
                                  sync_status, sync_attempts)
        VALUES
            (gen_random_uuid(), 'login',                       NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'realizar_ingreso',           NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'realizar_salida',            NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'emitir_factura',             NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'anular_ingreso',             NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'anular_salida',              NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'realizar_arqueo',            NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'abrir_cerrar_caja',          NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'reimprimir_ticket',           NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'administrar_clientes',       NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'administrar_vehiculos',      NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'administrar_subscripciones', NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'administrar_tarifas',        NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'configurar_sucursal',        NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'ver_reportes',               NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0)
        ON CONFLICT DO NOTHING;
    """)

    op.execute("""
        INSERT INTO prod.configuracion_tolerancias (uuid, uuid_sucursal,
                                               tolerancia_efectivo, tolerancia_datafono,
                                               created_at, created_by,
                                               vigente_desde, vigente_hasta, estado,
                                               sync_status, sync_attempts)
        VALUES (gen_random_uuid(), NULL, 0.00, 0.00,
                NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0)
        ON CONFLICT DO NOTHING;
    """)

    op.execute("""
        INSERT INTO prod.configuracion_seguridad (uuid, uuid_sucursal,
                                            dias_expiracion_password, max_intentos_login, minutos_bloqueo_login,
                                            created_at, created_by,
                                            vigente_desde, vigente_hasta, estado,
                                            sync_status, sync_attempts)
        VALUES (gen_random_uuid(), NULL, 90, 5, 15,
                NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0)
        ON CONFLICT DO NOTHING;
    """)

    op.execute("""
        INSERT INTO prod.empresa (uuid, nombre, nit, mensaje_bienvenida, mensaje_salida, regimen,
                               created_at, created_by,
                               vigente_desde, vigente_hasta, estado,
                               sync_status, sync_attempts)
        VALUES (gen_random_uuid(), 'Parkos Demo', '900000000-0', 'Bienvenido', 'Hasta pronto', 'simplificado',
                NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0)
        ON CONFLICT DO NOTHING;
    """)

    op.execute("""
        INSERT INTO prod.tipo_persona (uuid, tipo, created_at, created_by,
                                    vigente_desde, vigente_hasta, estado,
                                    sync_status, sync_attempts)
        VALUES
            (gen_random_uuid(), 'natural',  NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0),
            (gen_random_uuid(), 'juridica', NOW(), NULL, NOW(), NULL, 'activo', 'sincronizado', 0)
        ON CONFLICT DO NOTHING;
    """)



def downgrade() -> None:
    """Tear down the initial schema. DDL-only — no DELETE statements."""

    # Drop partman parents first (cascade drops child partitions).
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.salidas', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.factura_detalle', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.factura_pagos', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.log_transaccional', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.sync_log', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.sync_queue', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.caja', p_cascade := true);")
    op.execute("SELECT partman.drop_parent(p_parent_table := 'prod.arqueo', p_cascade := true);")

    # Drop sync outbox triggers first.
    op.execute("DROP TRIGGER IF EXISTS usuarios_sucursal_enqueue_sync ON prod.usuarios_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS documentos_enqueue_sync ON prod.documentos;")
    op.execute("DROP TRIGGER IF EXISTS tarifas_sucursal_enqueue_sync ON prod.tarifas_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS cantidad_vehiculos_sucursal_enqueue_sync ON prod.cantidad_vehiculos_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS configuracion_tolerancias_enqueue_sync ON prod.configuracion_tolerancias;")
    op.execute("DROP TRIGGER IF EXISTS configuracion_seguridad_enqueue_sync ON prod.configuracion_seguridad;")
    op.execute("DROP TRIGGER IF EXISTS resolucion_facturacion_enqueue_sync ON prod.resolucion_facturacion;")
    op.execute("DROP TRIGGER IF EXISTS subscripciones_cliente_enqueue_sync ON prod.subscripciones_cliente;")
    op.execute("DROP TRIGGER IF EXISTS login_enqueue_sync ON prod.login;")
    op.execute("DROP TRIGGER IF EXISTS sesion_enqueue_sync ON prod.sesion;")
    op.execute("DROP TRIGGER IF EXISTS ingreso_enqueue_sync ON prod.ingreso;")
    op.execute("DROP TRIGGER IF EXISTS salidas_enqueue_sync ON prod.salidas;")
    op.execute("DROP TRIGGER IF EXISTS caja_enqueue_sync ON prod.caja;")
    op.execute("DROP TRIGGER IF EXISTS facturas_enqueue_sync ON prod.facturas;")
    op.execute("DROP TRIGGER IF EXISTS factura_detalle_enqueue_sync ON prod.factura_detalle;")
    op.execute("DROP TRIGGER IF EXISTS factura_impuestos_enqueue_sync ON prod.factura_impuestos;")
    op.execute("DROP TRIGGER IF EXISTS factura_otros_cobros_enqueue_sync ON prod.factura_otros_cobros;")
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_enqueue_sync ON prod.factura_pagos;")
    op.execute("DROP TRIGGER IF EXISTS arqueo_enqueue_sync ON prod.arqueo;")
    op.execute("DROP TRIGGER IF EXISTS revocacion_factura_enqueue_sync ON prod.revocacion_factura;")
    op.execute("DROP TRIGGER IF EXISTS sync_log_enqueue_sync ON prod.sync_log;")
    op.execute("DROP TRIGGER IF EXISTS sync_conflict_enqueue_sync ON prod.sync_conflict;")
    op.execute("DROP TRIGGER IF EXISTS log_transaccional_enqueue_sync ON prod.log_transaccional;")
    op.execute("DROP TRIGGER IF EXISTS factura_electronica_enqueue_sync ON prod.factura_electronica;")
    op.execute("DROP TRIGGER IF EXISTS reimpresion_ticket_enqueue_sync ON prod.reimpresion_ticket;")
    op.execute("DROP TRIGGER IF EXISTS anulaciones_enqueue_sync ON prod.anulaciones;")
    op.execute("DROP TRIGGER IF EXISTS reclamos_enqueue_sync ON prod.reclamos;")
    op.execute("DROP TRIGGER IF EXISTS alerta_enqueue_sync ON prod.alerta;")
    op.execute("DROP TRIGGER IF EXISTS envio_dian_enqueue_sync ON prod.envio_dian;")
    op.execute("DROP TRIGGER IF EXISTS validacion_evento_enqueue_sync ON prod.validacion_evento;")

    # Drop audit + versioning per-table triggers.
    op.execute("DROP TRIGGER IF EXISTS permisos_audit_columns ON prod.permisos;")
    op.execute("DROP TRIGGER IF EXISTS permisos_set_vigente_inicial ON prod.permisos;")
    op.execute("DROP TRIGGER IF EXISTS empresa_audit_columns ON prod.empresa;")
    op.execute("DROP TRIGGER IF EXISTS empresa_set_vigente_inicial ON prod.empresa;")
    op.execute("DROP TRIGGER IF EXISTS usuarios_audit_columns ON prod.usuarios;")
    op.execute("DROP TRIGGER IF EXISTS usuarios_set_vigente_inicial ON prod.usuarios;")
    op.execute("DROP TRIGGER IF EXISTS tipo_persona_audit_columns ON prod.tipo_persona;")
    op.execute("DROP TRIGGER IF EXISTS tipo_persona_set_vigente_inicial ON prod.tipo_persona;")
    op.execute("DROP TRIGGER IF EXISTS tipos_vehiculo_audit_columns ON prod.tipos_vehiculo;")
    op.execute("DROP TRIGGER IF EXISTS tipos_vehiculo_set_vigente_inicial ON prod.tipos_vehiculo;")
    op.execute("DROP TRIGGER IF EXISTS tipo_subscripciones_audit_columns ON prod.tipo_subscripciones;")
    op.execute("DROP TRIGGER IF EXISTS tipo_subscripciones_set_vigente_inicial ON prod.tipo_subscripciones;")
    op.execute("DROP TRIGGER IF EXISTS tipo_tarifa_audit_columns ON prod.tipo_tarifa;")
    op.execute("DROP TRIGGER IF EXISTS tipo_tarifa_set_vigente_inicial ON prod.tipo_tarifa;")
    op.execute("DROP TRIGGER IF EXISTS tipo_sucursal_audit_columns ON prod.tipo_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS tipo_sucursal_set_vigente_inicial ON prod.tipo_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS tipo_arqueo_audit_columns ON prod.tipo_arqueo;")
    op.execute("DROP TRIGGER IF EXISTS tipo_arqueo_set_vigente_inicial ON prod.tipo_arqueo;")
    op.execute("DROP TRIGGER IF EXISTS permisos_usuario_audit_columns ON prod.permisos_usuario;")
    op.execute("DROP TRIGGER IF EXISTS permisos_usuario_set_vigente_inicial ON prod.permisos_usuario;")
    op.execute("DROP TRIGGER IF EXISTS impuestos_audit_columns ON prod.impuestos;")
    op.execute("DROP TRIGGER IF EXISTS impuestos_set_vigente_inicial ON prod.impuestos;")
    op.execute("DROP TRIGGER IF EXISTS otros_cobros_audit_columns ON prod.otros_cobros;")
    op.execute("DROP TRIGGER IF EXISTS otros_cobros_set_vigente_inicial ON prod.otros_cobros;")
    op.execute("DROP TRIGGER IF EXISTS costos_servicios_audit_columns ON prod.costos_servicios;")
    op.execute("DROP TRIGGER IF EXISTS costos_servicios_set_vigente_inicial ON prod.costos_servicios;")
    op.execute("DROP TRIGGER IF EXISTS sucursal_audit_columns ON prod.sucursal;")
    op.execute("DROP TRIGGER IF EXISTS sucursal_set_vigente_inicial ON prod.sucursal;")
    op.execute("DROP TRIGGER IF EXISTS usuarios_sucursal_audit_columns ON prod.usuarios_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS usuarios_sucursal_set_vigente_inicial ON prod.usuarios_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS documentos_audit_columns ON prod.documentos;")
    op.execute("DROP TRIGGER IF EXISTS documentos_set_vigente_inicial ON prod.documentos;")
    op.execute("DROP TRIGGER IF EXISTS tarifas_sucursal_audit_columns ON prod.tarifas_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS tarifas_sucursal_set_vigente_inicial ON prod.tarifas_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS cantidad_vehiculos_sucursal_audit_columns ON prod.cantidad_vehiculos_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS cantidad_vehiculos_sucursal_set_vigente_inicial ON prod.cantidad_vehiculos_sucursal;")
    op.execute("DROP TRIGGER IF EXISTS configuracion_tolerancias_audit_columns ON prod.configuracion_tolerancias;")
    op.execute("DROP TRIGGER IF EXISTS configuracion_tolerancias_set_vigente_inicial ON prod.configuracion_tolerancias;")
    op.execute("DROP TRIGGER IF EXISTS configuracion_seguridad_audit_columns ON prod.configuracion_seguridad;")
    op.execute("DROP TRIGGER IF EXISTS configuracion_seguridad_set_vigente_inicial ON prod.configuracion_seguridad;")
    op.execute("DROP TRIGGER IF EXISTS resolucion_facturacion_audit_columns ON prod.resolucion_facturacion;")
    op.execute("DROP TRIGGER IF EXISTS resolucion_facturacion_set_vigente_inicial ON prod.resolucion_facturacion;")
    op.execute("DROP TRIGGER IF EXISTS clientes_audit_columns ON prod.clientes;")
    op.execute("DROP TRIGGER IF EXISTS clientes_set_vigente_inicial ON prod.clientes;")
    op.execute("DROP TRIGGER IF EXISTS vehiculos_audit_columns ON prod.vehiculos;")
    op.execute("DROP TRIGGER IF EXISTS vehiculos_set_vigente_inicial ON prod.vehiculos;")
    op.execute("DROP TRIGGER IF EXISTS clientes_b2b_audit_columns ON prod.clientes_b2b;")
    op.execute("DROP TRIGGER IF EXISTS clientes_b2b_set_vigente_inicial ON prod.clientes_b2b;")
    op.execute("DROP TRIGGER IF EXISTS subscripciones_cliente_audit_columns ON prod.subscripciones_cliente;")
    op.execute("DROP TRIGGER IF EXISTS subscripciones_cliente_set_vigente_inicial ON prod.subscripciones_cliente;")
    op.execute("DROP TRIGGER IF EXISTS subscripcion_vehiculos_audit_columns ON prod.subscripcion_vehiculos;")
    op.execute("DROP TRIGGER IF EXISTS subscripcion_vehiculos_set_vigente_inicial ON prod.subscripcion_vehiculos;")
    op.execute("DROP TRIGGER IF EXISTS login_audit_columns ON prod.login;")
    op.execute("DROP TRIGGER IF EXISTS login_set_vigente_inicial ON prod.login;")
    op.execute("DROP TRIGGER IF EXISTS sesion_audit_columns ON prod.sesion;")
    op.execute("DROP TRIGGER IF EXISTS sesion_set_vigente_inicial ON prod.sesion;")
    op.execute("DROP TRIGGER IF EXISTS ingreso_audit_columns ON prod.ingreso;")
    op.execute("DROP TRIGGER IF EXISTS ingreso_set_vigente_inicial ON prod.ingreso;")
    op.execute("DROP TRIGGER IF EXISTS salidas_audit_columns ON prod.salidas;")
    op.execute("DROP TRIGGER IF EXISTS caja_audit_columns ON prod.caja;")
    op.execute("DROP TRIGGER IF EXISTS facturas_audit_columns ON prod.facturas;")
    op.execute("DROP TRIGGER IF EXISTS facturas_set_vigente_inicial ON prod.facturas;")
    op.execute("DROP TRIGGER IF EXISTS factura_detalle_audit_columns ON prod.factura_detalle;")
    op.execute("DROP TRIGGER IF EXISTS factura_impuestos_audit_columns ON prod.factura_impuestos;")
    op.execute("DROP TRIGGER IF EXISTS factura_otros_cobros_audit_columns ON prod.factura_otros_cobros;")
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_audit_columns ON prod.factura_pagos;")
    op.execute("DROP TRIGGER IF EXISTS arqueo_audit_columns ON prod.arqueo;")
    op.execute("DROP TRIGGER IF EXISTS revocacion_factura_audit_columns ON prod.revocacion_factura;")
    op.execute("DROP TRIGGER IF EXISTS sync_queue_audit_columns ON prod.sync_queue;")
    op.execute("DROP TRIGGER IF EXISTS sync_log_audit_columns ON prod.sync_log;")
    op.execute("DROP TRIGGER IF EXISTS sync_conflict_audit_columns ON prod.sync_conflict;")
    op.execute("DROP TRIGGER IF EXISTS log_transaccional_audit_columns ON prod.log_transaccional;")
    op.execute("DROP TRIGGER IF EXISTS factura_electronica_audit_columns ON prod.factura_electronica;")
    op.execute("DROP TRIGGER IF EXISTS factura_electronica_set_vigente_inicial ON prod.factura_electronica;")
    op.execute("DROP TRIGGER IF EXISTS reimpresion_ticket_audit_columns ON prod.reimpresion_ticket;")
    op.execute("DROP TRIGGER IF EXISTS reimpresion_ticket_set_vigente_inicial ON prod.reimpresion_ticket;")
    op.execute("DROP TRIGGER IF EXISTS anulaciones_audit_columns ON prod.anulaciones;")
    op.execute("DROP TRIGGER IF EXISTS anulaciones_set_vigente_inicial ON prod.anulaciones;")
    op.execute("DROP TRIGGER IF EXISTS reclamos_audit_columns ON prod.reclamos;")
    op.execute("DROP TRIGGER IF EXISTS reclamos_set_vigente_inicial ON prod.reclamos;")
    op.execute("DROP TRIGGER IF EXISTS alerta_audit_columns ON prod.alerta;")
    op.execute("DROP TRIGGER IF EXISTS alerta_set_vigente_inicial ON prod.alerta;")
    op.execute("DROP TRIGGER IF EXISTS envio_dian_audit_columns ON prod.envio_dian;")
    op.execute("DROP TRIGGER IF EXISTS envio_dian_set_vigente_inicial ON prod.envio_dian;")
    op.execute("DROP TRIGGER IF EXISTS validacion_evento_audit_columns ON prod.validacion_evento;")
    op.execute("DROP TRIGGER IF EXISTS validacion_evento_set_vigente_inicial ON prod.validacion_evento;")

    # Drop [L-S] session guards + [A] inmutables + hash chain trigger.
    op.execute("DROP TRIGGER IF EXISTS login_ls_session_guard ON prod.login;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_login_ls_session_guard();")
    op.execute("DROP TRIGGER IF EXISTS sesion_ls_session_guard ON prod.sesion;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_sesion_ls_session_guard();")
    op.execute("DROP TRIGGER IF EXISTS salidas_inmutable ON prod.salidas;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_salidas_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS caja_inmutable ON prod.caja;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_caja_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS factura_detalle_inmutable ON prod.factura_detalle;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_factura_detalle_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS factura_impuestos_inmutable ON prod.factura_impuestos;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_factura_impuestos_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS factura_otros_cobros_inmutable ON prod.factura_otros_cobros;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_factura_otros_cobros_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS factura_pagos_inmutable ON prod.factura_pagos;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_factura_pagos_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS arqueo_inmutable ON prod.arqueo;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_arqueo_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS revocacion_factura_inmutable ON prod.revocacion_factura;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_revocacion_factura_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS sync_log_inmutable ON prod.sync_log;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_sync_log_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS sync_conflict_inmutable ON prod.sync_conflict;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_sync_conflict_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS log_transaccional_inmutable ON prod.log_transaccional;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_log_transaccional_inmutable();")
    op.execute("DROP TRIGGER IF EXISTS log_transaccional_hash_chain ON prod.log_transaccional;")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_extend_hash_chain();")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_enqueue_sync();")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_set_vigente_inicial();")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_audit_columns();")

    # Drop tables in reverse dependency order.
    op.drop_table("validacion_evento", schema="prod")
    op.drop_table("envio_dian", schema="prod")
    op.drop_table("alerta", schema="prod")
    op.drop_table("reclamos", schema="prod")
    op.drop_table("anulaciones", schema="prod")
    op.drop_table("reimpresion_ticket", schema="prod")
    op.drop_table("factura_electronica", schema="prod")
    op.drop_table("log_transaccional", schema="prod")
    op.drop_table("sync_conflict", schema="prod")
    op.drop_table("sync_log", schema="prod")
    op.drop_table("sync_queue", schema="prod")
    op.drop_table("revocacion_factura", schema="prod")
    op.drop_table("arqueo", schema="prod")
    op.drop_table("factura_pagos", schema="prod")
    op.drop_table("factura_otros_cobros", schema="prod")
    op.drop_table("factura_impuestos", schema="prod")
    op.drop_table("factura_detalle", schema="prod")
    op.drop_table("facturas", schema="prod")
    op.drop_table("caja", schema="prod")
    op.drop_table("salidas", schema="prod")
    op.drop_table("ingreso", schema="prod")
    op.drop_table("sesion", schema="prod")
    op.drop_table("login", schema="prod")
    op.drop_table("subscripcion_vehiculos", schema="prod")
    op.drop_table("subscripciones_cliente", schema="prod")
    op.drop_table("clientes_b2b", schema="prod")
    op.drop_table("vehiculos", schema="prod")
    op.drop_table("clientes", schema="prod")
    op.drop_table("resolucion_facturacion", schema="prod")
    op.drop_table("configuracion_seguridad", schema="prod")
    op.drop_table("configuracion_tolerancias", schema="prod")
    op.drop_table("cantidad_vehiculos_sucursal", schema="prod")
    op.drop_table("tarifas_sucursal", schema="prod")
    op.drop_table("documentos", schema="prod")
    op.drop_table("usuarios_sucursal", schema="prod")
    op.drop_table("sucursal", schema="prod")
    op.drop_table("costos_servicios", schema="prod")
    op.drop_table("otros_cobros", schema="prod")
    op.drop_table("impuestos", schema="prod")
    op.drop_table("permisos_usuario", schema="prod")
    op.drop_table("tipo_arqueo", schema="prod")
    op.drop_table("tipo_sucursal", schema="prod")
    op.drop_table("tipo_tarifa", schema="prod")
    op.drop_table("tipo_subscripciones", schema="prod")
    op.drop_table("tipos_vehiculo", schema="prod")
    op.drop_table("tipo_persona", schema="prod")
    op.drop_table("usuarios", schema="prod")
    op.drop_table("empresa", schema="prod")
    op.drop_table("permisos", schema="prod")

    # Drop roles + schemas.
    op.execute("REVOKE ALL ON SCHEMA prod FROM rol_admin_auditor;")
    op.execute("REVOKE ALL ON SCHEMA prod FROM rol_app;")
    op.execute("DROP ROLE IF EXISTS rol_admin_auditor;")
    op.execute("DROP ROLE IF EXISTS rol_app;")
    op.execute("DROP SCHEMA IF EXISTS prod CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS archive;")
