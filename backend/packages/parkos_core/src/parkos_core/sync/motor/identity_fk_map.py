"""motor/identity_fk_map.py -- which columns of which table are foreign keys onto
an identity-reconciled master (a catalog entry whose ``hook_pre_insert`` is
``identity_reconciler``).

``SyncMotor.apply_row`` repoints exactly these columns through
``prod.sync_identity_alias`` before applying a row. The map is explicit (not
derived at runtime) because the ORM models do NOT declare ``ForeignKey`` on
these columns -- the constraints live only in the migrations, so
``Model.__table__.foreign_keys`` is empty for them. Drift is caught by
``tests/integration/test_sync_identity_alias_fk_columns.py``, which compares this
map with ``pg_constraint`` on a migrated database.

Deliberately absent:

* ``uuid``, ``created_by``, ``current_uuid`` -- identity/audit columns, never remapped.
* ``uuid_sucursal`` and the ``sucursal`` table itself -- ``sucursal`` is applied by
  its own uuid (UPDATE in place, ``SyncMotor.apply_row`` special case) and never
  produces an alias, so remapping it would only add a lookup to every row.

A column listed here MUST be a real foreign key: the remap only rewrites a value
that has an alias, and an alias exists only for a collapsed master uuid.
"""

from __future__ import annotations

IDENTITY_FK_COLUMNS: dict[str, frozenset[str]] = {
    "alerta": frozenset({"uuid_usuario"}),
    "anulaciones": frozenset({"uuid_usuario"}),
    "arqueo": frozenset({"uuid_tipo_arqueo"}),
    "cantidad_vehiculos_sucursal": frozenset({"uuid_tipo_vehiculo"}),
    "clientes": frozenset({"uuid_tipo_persona"}),
    "clientes_b2b": frozenset({"uuid_cliente"}),
    "envio_dian": frozenset({"uuid_resolucion_facturacion"}),
    "factura_electronica": frozenset({"uuid_cliente", "uuid_resolucion_facturacion"}),
    "factura_impuestos": frozenset({"uuid_impuesto"}),
    "factura_otros_cobros": frozenset({"uuid_otro_cobro"}),
    "ingreso": frozenset({"uuid_tipo_vehiculo"}),
    "login": frozenset({"uuid_usuario"}),
    "permisos_usuario": frozenset({"uuid_permiso", "uuid_usuario"}),
    "reimpresion_ticket": frozenset({"uuid_costo_servicio", "uuid_usuario"}),
    "sesion": frozenset({"uuid_usuario", "uuid_usuario_cierre"}),
    "subscripcion_vehiculos": frozenset({"uuid_vehiculo"}),
    "subscripciones_cliente": frozenset({"uuid_cliente", "uuid_tipo_subscripcion"}),
    "tarifas_sucursal": frozenset({"uuid_tipo_tarifa", "uuid_tipo_vehiculo"}),
    "tipo_subscripciones": frozenset({"uuid_tipo_vehiculo"}),
    "usuarios_sucursal": frozenset({"uuid_usuario"}),
    "validacion_evento": frozenset({"uuid_usuario"}),
    "vehiculos": frozenset({"uuid_tipo_vehiculo"}),
}

__all__ = ["IDENTITY_FK_COLUMNS"]
