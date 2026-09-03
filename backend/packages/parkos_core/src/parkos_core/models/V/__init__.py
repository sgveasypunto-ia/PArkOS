"""[V] Versioned ORM models — bi-temporal close+insert (design §3.1).

PR1b ships the auth-domain tables (``usuarios``, ``permisos``, the two
junction tables) plus the smoke-mounted ``tipo_persona`` catalog. PR3 adds the
rest of the catalogs; PR4 adds empresa/sucursal/config; PR5 adds clientes/vehiculos.
"""
from __future__ import annotations

from .permisos import Permisos
from .permisos_usuario import PermisosUsuario
from .tipo_persona import TipoPersona
from .usuarios import Usuarios
from .usuarios_sucursal import UsuariosSucursal

__all__ = [
    "Permisos",
    "PermisosUsuario",
    "TipoPersona",
    "Usuarios",
    "UsuariosSucursal",
]