"""Single source of truth for the pull scope class of every pull-eligible entry.

Shared by the integration matrix (``integration/test_sync_pull_scope_matrix.py``)
and the static gate (``static/test_pull_scope_guardrails.py``). Adding a
``SYNC_CATALOG`` entry that a branch may pull (``direction`` in
``cloud_to_branch`` / ``bidirectional`` with a non-``None`` ``broadcast_policy``)
requires deciding its class here.

Classes:
  global        every branch receives the row (``all_branches``)
  owned         only the branch named by ``uuid_sucursal`` (``single_branch``)
  override      NULL ``uuid_sucursal`` = global default, otherwise only that branch
  subscription  only the branch that sold the subscription (directly or via parent)
  derived       scope derived through bridge tables / ``sucursal.uuid_empresa``
"""

from __future__ import annotations

EXPECTED_SCOPE: dict[str, str] = {
    # global catalogs
    "permisos": "global",
    "tipo_persona": "global",
    "tipos_vehiculo": "global",
    "tipo_subscripciones": "global",
    "tipo_tarifa": "global",
    "tipo_sucursal": "global",
    "tipo_arqueo": "global",
    "impuestos": "global",
    "otros_cobros": "global",
    "costos_servicios": "global",
    # owned by one branch
    "sucursal": "owned",
    "resolucion_facturacion": "owned",
    "usuarios_sucursal": "owned",
    "documentos": "owned",
    "tarifas_sucursal": "owned",
    "cantidad_vehiculos_sucursal": "owned",
    # global default + per-branch override
    "configuracion_tolerancias": "override",
    "configuracion_seguridad": "override",
    # sold by one branch
    "subscripciones_cliente": "subscription",
    "subscripcion_vehiculos": "subscription",
    # reachable only through bridge tables
    "usuarios": "derived",
    "permisos_usuario": "derived",
    "empresa": "derived",  # own sucursal.uuid_empresa by NIT (test_sync_pull_scope_empresa)
    "clientes": "derived",
    "clientes_b2b": "derived",
    "vehiculos": "derived",
}

# class -> the ``broadcast_policy`` literal it must be declared with.
POLICY_OF_CLASS: dict[str, str] = {
    "global": "all_branches",
    "owned": "single_branch",
    "override": "all_branches_with_override",
    "subscription": "subscription",
    "derived": "derived",
}

# Entries allowed to stay ``all_branches``: reference catalogs with no personal
# data. Anything holding personal data (usuarios, clientes, vehiculos, ...) must
# be scoped (``derived`` / ``owned`` / ...).
ALL_BRANCHES_ALLOWLIST: frozenset[str] = frozenset(
    {
        "permisos",
        "tipo_persona",
        "tipos_vehiculo",
        "tipo_subscripciones",
        "tipo_tarifa",
        "tipo_sucursal",
        "tipo_arqueo",
        "impuestos",
        "otros_cobros",
        "costos_servicios",
    }
)

# Pull-eligible direction with ``broadcast_policy=None``: not pulled by design.
# ``log_transaccional`` is the sole ``[A]`` entry that is bidirectional (cloud
# extends the branch hash chain); it has no pull scope and ``_fetch_pull_rows``
# skips it.
PULL_DIRECTION_WITHOUT_POLICY: frozenset[str] = frozenset({"log_transaccional"})
