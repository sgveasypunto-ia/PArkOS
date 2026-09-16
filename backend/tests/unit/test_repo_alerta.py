"""HU-F1.6 / REQ-OPS-041.C — alerta INSERT for ``capacidad_agotada_forzado``.

Mocked-async unit tests for
:func:`parkos_core.repo.alerta.insertar_alerta_forzado`. Uses
``unittest.mock.AsyncMock(spec=AsyncSession)`` to capture the
``session.add()`` call without touching a real DB.

Lifecycle:
  - RED: ``from parkos_core.repo.alerta import insertar_alerta_forzado``
    raises ``ImportError``.
  - GREEN: helper builds an :class:`Alerta` row with
    ``tipo_alerta='capacidad_agotada_forzado'``, ``estado='abierta'``,
    ``uuid_sucursal``, ``uuid_usuario``, ``uuid_arqueo=None``,
    ``datos_nuevos={'motivo': <motivo>, 'uuid_ingreso': <uuid>}``;
    calls ``session.add(alerta)`` and ``await session.flush()``.
"""
from __future__ import annotations

import json
import uuid as uuid_lib

import pytest
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.repo.alerta import insertar_alerta_forzado


class _MockSession:
    """Minimal async session stub capturing ``add`` and ``flush``."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_insertar_alerta_forzado_builds_correct_instance() -> None:
    """T1: ``insertar_alerta_forzado`` builds an ``Alerta`` row with
    ``tipo_alerta='capacidad_agotada_forzado'``,
    ``estado='abierta'``, the supplied UUIDs, and a jsonb ``datos_nuevos``
    carrying ``{'motivo': <motivo>, 'uuid_ingreso': <uuid>}``.
    """
    session = _MockSession()
    uuid_sucursal = uuid_lib.uuid4()
    uuid_ingreso = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    motivo = "cupo agotado por cita medica urgente"

    result = await insertar_alerta_forzado(
        session,
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
        actor_uuid=actor_uuid,
        motivo=motivo,
    )

    assert isinstance(result, Alerta)
    assert session.flushed is True
    assert len(session.added) == 1
    alerta = session.added[0]

    # Typed business columns:
    assert alerta.tipo_alerta == "capacidad_agotada_forzado"
    assert alerta.estado == "abierta"
    assert alerta.uuid_sucursal == uuid_sucursal
    assert alerta.uuid_usuario == actor_uuid
    assert alerta.uuid_arqueo is None

    # JSONB payload shape (R-A2 audit; jsonb column added in 0025):
    assert alerta.datos_nuevos is not None, (
        "datos_nuevos must be populated for the capacidad_agotada_forzado alert"
    )
    # datos_nuevos is stored as a Python dict; the helper serializes
    # the motivo + uuid_ingreso into it.
    payload = (
        alerta.datos_nuevos
        if isinstance(alerta.datos_nuevos, dict)
        else json.loads(alerta.datos_nuevos)
    )
    assert payload["motivo"] == motivo
    assert payload["uuid_ingreso"] == str(uuid_ingreso)


@pytest.mark.asyncio
async def test_insertar_alerta_forzado_motivo_con_caracteres_especiales() -> None:
    """T-aux: motivo containing punctuation/unicode is preserved verbatim
    (jsonb handles UTF-8 cleanly)."""
    session = _MockSession()
    motivo = "cliente con cita médica urgente (urgencias) — 2026/09/14"
    uuid_ingreso = uuid_lib.uuid4()

    await insertar_alerta_forzado(
        session,
        uuid_sucursal=uuid_lib.uuid4(),
        uuid_ingreso=uuid_ingreso,
        actor_uuid=uuid_lib.uuid4(),
        motivo=motivo,
    )
    alerta = session.added[0]
    payload = (
        alerta.datos_nuevos
        if isinstance(alerta.datos_nuevos, dict)
        else json.loads(alerta.datos_nuevos)
    )
    assert payload["motivo"] == motivo
    assert payload["uuid_ingreso"] == str(uuid_ingreso)


__all__ = [
    "test_insertar_alerta_forzado_builds_correct_instance",
    "test_insertar_alerta_forzado_motivo_con_caracteres_especiales",
]