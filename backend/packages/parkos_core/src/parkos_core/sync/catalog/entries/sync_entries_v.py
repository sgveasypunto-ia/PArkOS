"""catalog/entries/sync_entries_v.py — 26 [V] catalog entries (T-PR2-002..006).

Direction and ``broadcast_policy`` are derived from ``modelo_datos_er.mmd``
per D5-rev (REQ-CAT-004); ``apply_strategy="close_and_insert"`` and
``seq_strategy="max_created_at"`` are uniform across every ``[V]`` entry per
proposal.md §6.1's per-table "apply / seq" column.

.. note::
   ``sync-catalog.md`` REQ-CAT-013 states unamended text requiring
   ``seq_strategy="seq_via_datos"`` for "[V] tables with a trigger today".
   proposal.md §6.1 (the amended, ratified per-table enumeration) and
   tasks.md T-PR2-002 both explicitly pin ``max_created_at`` for every
   single ``[V]`` row instead, with no exceptions. This module follows
   proposal.md §6.1 / tasks.md as the more specific and more recently
   amended source — REQ-CAT-013 appears to be pre-amendment boilerplate
   that was not updated in the ER-alignment correction pass. Flagged here,
   not silently resolved; see the PR2 apply report's "Deviations" section.

Groups mirror tasks.md's split (T-PR2-002..006) so each group's `depends_on`
matches REQ-CAT-015 / proposal §6.4 exactly.
"""
from __future__ import annotations

from ....models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from ....models.V.clientes import Clientes
from ....models.V.clientes_b2b import ClientesB2B
from ....models.V.configuracion_seguridad import ConfiguracionSeguridad
from ....models.V.configuracion_tolerancias import ConfiguracionTolerancias
from ....models.V.costos_servicios import CostosServicios
from ....models.V.documentos import Documentos
from ....models.V.empresa import Empresa
from ....models.V.impuestos import Impuestos
from ....models.V.otros_cobros import OtrosCobros
from ....models.V.permisos import Permisos
from ....models.V.permisos_usuario import PermisosUsuario
from ....models.V.resolucion_facturacion import ResolucionFacturacion
from ....models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ....models.V.subscripciones_cliente import SubscripcionesCliente
from ....models.V.sucursal import Sucursal
from ....models.V.tarifas_sucursal import TarifasSucursal
from ....models.V.tipo_arqueo import TipoArqueo
from ....models.V.tipo_persona import TipoPersona
from ....models.V.tipo_subscripciones import TipoSubscripciones
from ....models.V.tipo_sucursal import TipoSucursal
from ....models.V.tipo_tarifa import TipoTarifa
from ....models.V.tipos_vehiculo import TiposVehiculo
from ....models.V.usuarios import Usuarios
from ....models.V.usuarios_sucursal import UsuariosSucursal
from ....models.V.vehiculos import Vehiculos
from ..schema import SyncCatalogEntry

# ---------------------------------------------------------------------------
# T-PR2-002 — group 1: 8 tier-0 global roots (no uuid_sucursal, no dependents)
# ---------------------------------------------------------------------------

_USUARIOS = SyncCatalogEntry(
    name="usuarios",
    model_cls=Usuarios,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_PERMISOS = SyncCatalogEntry(
    name="permisos",
    model_cls=Permisos,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_TIPO_PERSONA = SyncCatalogEntry(
    name="tipo_persona",
    model_cls=TipoPersona,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_TIPOS_VEHICULO = SyncCatalogEntry(
    name="tipos_vehiculo",
    model_cls=TiposVehiculo,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_TIPO_SUBSCRIPCIONES = SyncCatalogEntry(
    name="tipo_subscripciones",
    model_cls=TipoSubscripciones,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_TIPO_TARIFA = SyncCatalogEntry(
    name="tipo_tarifa",
    model_cls=TipoTarifa,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_TIPO_SUCURSAL = SyncCatalogEntry(
    name="tipo_sucursal",
    model_cls=TipoSucursal,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_TIPO_ARQUEO = SyncCatalogEntry(
    name="tipo_arqueo",
    model_cls=TipoArqueo,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

# ---------------------------------------------------------------------------
# T-PR2-003 — group 2: impuestos / otros_cobros / costos_servicios / empresa
# ---------------------------------------------------------------------------

_IMPUESTOS = SyncCatalogEntry(
    name="impuestos",
    model_cls=Impuestos,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_OTROS_COBROS = SyncCatalogEntry(
    name="otros_cobros",
    model_cls=OtrosCobros,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_COSTOS_SERVICIOS = SyncCatalogEntry(
    name="costos_servicios",
    model_cls=CostosServicios,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_EMPRESA = SyncCatalogEntry(
    name="empresa",
    model_cls=Empresa,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    # Tenant filter (proposal §6.1): broadcast only the version reachable
    # from the branch's own sucursal.uuid_empresa — today one operator, so
    # functionally all_branches, but multi-operator-safe. The filter itself
    # is applied by the broadcast resolver (PR4+), not encoded as a distinct
    # broadcast_policy literal here.
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

# ---------------------------------------------------------------------------
# T-PR2-004 — group 3: permisos_usuario + configuracion_{tolerancias,seguridad} (D19)
# ---------------------------------------------------------------------------

_PERMISOS_USUARIO = SyncCatalogEntry(
    name="permisos_usuario",
    model_cls=PermisosUsuario,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=("usuarios", "permisos"),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_CONFIGURACION_TOLERANCIAS = SyncCatalogEntry(
    name="configuracion_tolerancias",
    model_cls=ConfiguracionTolerancias,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    # D19 — global default (uuid_sucursal IS NULL) + per-branch override.
    broadcast_policy="all_branches_with_override",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=True,  # nullable — NULL row is the global default
    seq_strategy="max_created_at",
)

_CONFIGURACION_SEGURIDAD = SyncCatalogEntry(
    name="configuracion_seguridad",
    model_cls=ConfiguracionSeguridad,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    # D19 — global default (uuid_sucursal IS NULL) + per-branch override.
    broadcast_policy="all_branches_with_override",
    apply_strategy="close_and_insert",
    depends_on=(),
    has_uuid_sucursal=True,  # nullable — NULL row is the global default
    seq_strategy="max_created_at",
)

# ---------------------------------------------------------------------------
# T-PR2-005 — group 4: sucursal + 5 single-branch dependents
# ---------------------------------------------------------------------------

_SUCURSAL = SyncCatalogEntry(
    name="sucursal",
    model_cls=Sucursal,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="close_and_insert",
    depends_on=("empresa", "tipo_sucursal"),
    # No uuid_sucursal column on sucursal itself — the row IS the branch
    # identity, single_branch scope comes from the ER "la réplica local de
    # cada sede contiene solo sus filas" narrative, not a self-referencing FK.
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

_RESOLUCION_FACTURACION = SyncCatalogEntry(
    name="resolucion_facturacion",
    model_cls=ResolucionFacturacion,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="close_and_insert",
    depends_on=("sucursal",),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

_USUARIOS_SUCURSAL = SyncCatalogEntry(
    name="usuarios_sucursal",
    model_cls=UsuariosSucursal,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="close_and_insert",
    depends_on=("usuarios", "sucursal"),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

_DOCUMENTOS = SyncCatalogEntry(
    name="documentos",
    model_cls=Documentos,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="close_and_insert",
    depends_on=("sucursal",),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

_TARIFAS_SUCURSAL = SyncCatalogEntry(
    name="tarifas_sucursal",
    model_cls=TarifasSucursal,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="close_and_insert",
    depends_on=("sucursal", "tipos_vehiculo", "tipo_tarifa"),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

_CANTIDAD_VEHICULOS_SUCURSAL = SyncCatalogEntry(
    name="cantidad_vehiculos_sucursal",
    model_cls=CantidadVehiculosSucursal,
    audit_class="V",
    sync_strategy="append",
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="close_and_insert",
    depends_on=("sucursal", "tipos_vehiculo"),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

# ---------------------------------------------------------------------------
# T-PR2-006 — group 5: bidirectional identity masters + junctions (D17, §16 Q1)
# ---------------------------------------------------------------------------
#
# natural_key_normalizer callables (trim/uppercase) are wired in PR5
# (T-PR5-006); this task declares the natural_key tuple fields only.

_CLIENTES = SyncCatalogEntry(
    name="clientes",
    model_cls=Clientes,
    audit_class="V",
    sync_strategy="append",
    direction="bidirectional",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=("tipo_persona",),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
    natural_key=("tipo_identificador", "numero_identificacion"),
)

_CLIENTES_B2B = SyncCatalogEntry(
    name="clientes_b2b",
    model_cls=ClientesB2B,
    audit_class="V",
    sync_strategy="append",
    direction="bidirectional",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=("clientes",),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
    natural_key=("uuid_cliente",),
)

_VEHICULOS = SyncCatalogEntry(
    name="vehiculos",
    model_cls=Vehiculos,
    audit_class="V",
    sync_strategy="append",
    direction="bidirectional",
    broadcast_policy="all_branches",
    apply_strategy="close_and_insert",
    depends_on=("tipos_vehiculo",),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
    natural_key=("placa",),
)

_SUBSCRIPCIONES_CLIENTE = SyncCatalogEntry(
    name="subscripciones_cliente",
    model_cls=SubscripcionesCliente,
    audit_class="V",
    sync_strategy="append",
    direction="bidirectional",
    # §16 Q1 — a subscription is honored only at the branch that sold it.
    broadcast_policy="subscription",
    apply_strategy="close_and_insert",
    depends_on=("clientes", "sucursal", "tipo_subscripciones"),
    has_uuid_sucursal=True,
    seq_strategy="max_created_at",
)

_SUBSCRIPCION_VEHICULOS = SyncCatalogEntry(
    name="subscripcion_vehiculos",
    model_cls=SubscripcionVehiculos,
    audit_class="V",
    sync_strategy="append",
    direction="bidirectional",
    # Follows its parent's scope — target branch resolved transitively
    # through subscripciones_cliente.uuid_sucursal (REQ-CAT-017).
    broadcast_policy="subscription",
    apply_strategy="close_and_insert",
    depends_on=("subscripciones_cliente", "vehiculos"),
    has_uuid_sucursal=False,
    seq_strategy="max_created_at",
)

SYNC_ENTRIES_V: tuple[SyncCatalogEntry, ...] = (
    _USUARIOS,
    _PERMISOS,
    _TIPO_PERSONA,
    _TIPOS_VEHICULO,
    _TIPO_SUBSCRIPCIONES,
    _TIPO_TARIFA,
    _TIPO_SUCURSAL,
    _TIPO_ARQUEO,
    _IMPUESTOS,
    _OTROS_COBROS,
    _COSTOS_SERVICIOS,
    _EMPRESA,
    _PERMISOS_USUARIO,
    _CONFIGURACION_TOLERANCIAS,
    _CONFIGURACION_SEGURIDAD,
    _SUCURSAL,
    _RESOLUCION_FACTURACION,
    _USUARIOS_SUCURSAL,
    _DOCUMENTOS,
    _TARIFAS_SUCURSAL,
    _CANTIDAD_VEHICULOS_SUCURSAL,
    _CLIENTES,
    _CLIENTES_B2B,
    _VEHICULOS,
    _SUBSCRIPCIONES_CLIENTE,
    _SUBSCRIPCION_VEHICULOS,
)

assert len(SYNC_ENTRIES_V) == 26, f"expected 26 [V] entries, got {len(SYNC_ENTRIES_V)}"

__all__ = ["SYNC_ENTRIES_V"]
