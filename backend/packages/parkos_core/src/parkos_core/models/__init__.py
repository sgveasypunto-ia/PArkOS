"""parkos_core ORM models — re-exports.

Each subfolder (``V/``, ``L_E/``, ``L_W/``, ``L_S/``, ``A/``) corresponds to one
of the five audit enforcement classes (AGENTS.md §1). Every concrete ORM class
subclasses the matching abstract base from :mod:`parkos_core.models.base`.

Every model class across all five folders is imported here so that any import
of a single class (``from parkos_core.models.V.sucursal import Sucursal``)
also registers every OTHER class's table in the shared declarative metadata as
a side effect (Python always runs a package's ``__init__.py`` before any of
its submodules). This matters because several models declare their foreign
keys by table name (``ForeignKey("prod.sucursal.uuid")``) rather than by
class reference — SQLAlchemy only resolves those lazily, at first mapper
configuration, so a class whose module was never imported leaves its table
unregistered and any FK pointing at it raises ``NoReferencedTableError``.
Previously this file only imported 7 of the ~52 model classes (a PR1b-era
partial list, per its own "extend as tables come online" comment); running a
single test file in isolation — instead of the full suite, where some other
file's imports happened to cover the gap — surfaced the omission as exactly
that error against ``pairing_tokens.uuid_sucursal -> prod.sucursal``.
"""
from __future__ import annotations

from .A.alert_types import AlertTypes
from .A.arqueo import Arqueo
from .A.caja import Caja
from .A.factura_detalle import FacturaDetalle
from .A.factura_impuestos import FacturaImpuestos
from .A.factura_otros_cobros import FacturaOtrosCobros
from .A.factura_pagos import FacturaPagos
from .A.idempotency_keys import IdempotencyKeys
from .A.log_transaccional import LogTransaccional
from .A.pairing_tokens import PairingToken
from .A.revocacion_factura import RevocacionFactura
from .A.revoked_sync_jwts import RevokedSyncJwt
from .A.salidas import Salidas
from .A.sync_conflict import SyncConflict
from .A.sync_cursor import SyncCursor
from .A.sync_log import SyncLog
from .A.sync_queue import SyncQueue
from .A.sync_queue_lw_buffer import SyncQueueLwBuffer
from .L_E.factura_electronica import FacturaElectronica
from .L_E.facturas import Facturas
from .L_E.ingreso import Ingreso
from .L_S.login import Login
from .L_S.sesion import Sesion
from .L_W.alerta import Alerta
from .L_W.anulaciones import Anulaciones
from .L_W.envio_dian import EnvioDian
from .L_W.reclamos import Reclamos
from .L_W.reimpresion_ticket import ReimpresionTicket
from .L_W.validacion_evento import ValidacionEvento
from .V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from .V.clientes import Clientes
from .V.clientes_b2b import ClientesB2B
from .V.configuracion_seguridad import ConfiguracionSeguridad
from .V.configuracion_tolerancias import ConfiguracionTolerancias
from .V.costos_servicios import CostosServicios
from .V.documentos import Documentos
from .V.empresa import Empresa
from .V.impuestos import Impuestos
from .V.otros_cobros import OtrosCobros
from .V.permisos import Permisos
from .V.permisos_usuario import PermisosUsuario
from .V.resolucion_facturacion import ResolucionFacturacion
from .V.subscripcion_vehiculos import SubscripcionVehiculos
from .V.subscripciones_cliente import SubscripcionesCliente
from .V.sucursal import Sucursal
from .V.tarifas_sucursal import TarifasSucursal
from .V.tipo_arqueo import TipoArqueo
from .V.tipo_persona import TipoPersona
from .V.tipo_subscripciones import TipoSubscripciones
from .V.tipo_sucursal import TipoSucursal
from .V.tipo_tarifa import TipoTarifa
from .V.tipos_vehiculo import TiposVehiculo
from .V.usuarios import Usuarios
from .V.usuarios_sucursal import UsuariosSucursal
from .V.vehiculos import Vehiculos

__all__ = [
    "AlertTypes",
    "Alerta",
    "Anulaciones",
    "Arqueo",
    "Caja",
    "CantidadVehiculosSucursal",
    "Clientes",
    "ClientesB2B",
    "ConfiguracionSeguridad",
    "ConfiguracionTolerancias",
    "CostosServicios",
    "Documentos",
    "Empresa",
    "EnvioDian",
    "FacturaDetalle",
    "FacturaElectronica",
    "FacturaImpuestos",
    "FacturaOtrosCobros",
    "FacturaPagos",
    "Facturas",
    "IdempotencyKeys",
    "Impuestos",
    "Ingreso",
    "LogTransaccional",
    "Login",
    "OtrosCobros",
    "PairingToken",
    "Permisos",
    "PermisosUsuario",
    "Reclamos",
    "ReimpresionTicket",
    "ResolucionFacturacion",
    "RevocacionFactura",
    "RevokedSyncJwt",
    "Salidas",
    "Sesion",
    "SubscripcionVehiculos",
    "SubscripcionesCliente",
    "Sucursal",
    "SyncConflict",
    "SyncCursor",
    "SyncLog",
    "SyncQueue",
    "SyncQueueLwBuffer",
    "TarifasSucursal",
    "TipoArqueo",
    "TipoPersona",
    "TipoSubscripciones",
    "TipoSucursal",
    "TipoTarifa",
    "TiposVehiculo",
    "Usuarios",
    "UsuariosSucursal",
    "ValidacionEvento",
    "Vehiculos",
]
