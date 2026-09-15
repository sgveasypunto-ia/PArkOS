"""HU-F1.6 / KD-FORZADO-01 -- pure helper unit tests for ``validar_kd_forzado``.

Lifecycle:
  - RED: ``from parkos_core.repo.ingreso import validar_kd_forzado``
    raises ``ImportError`` (helper not yet ported).
  - GREEN: 4 tests cover prefix contract + discriminators.

No HTTP, no DB -- this is a pure Python helper.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from parkos_core.repo.ingreso import FORZADO_MIN_MOTIVO_CHARS, validar_kd_forzado


def test_validar_kd_forzado_prefix_y_forzado_true_retorna_motivo_stripped() -> None:
    """T1: prefix present + ``forzado=True`` -> stripped motivo."""
    motivo = "cliente con cita medica urgente"
    observaciones = f"[FORZADO: {motivo}]"
    result = validar_kd_forzado(observaciones, forzado=True)
    assert result == motivo
    assert len(result) >= FORZADO_MIN_MOTIVO_CHARS


def test_validar_kd_forzado_forzado_true_sin_prefix_raises_motivo_forzado_requerido() -> None:
    """T2: ``forzado=True`` sin prefix -> 422 ``motivo_forzado_requerido``."""
    with pytest.raises(HTTPException) as ei:
        validar_kd_forzado("cliente sin placa", forzado=True)
    assert ei.value.status_code == 422
    assert ei.value.detail == {"error": "motivo_forzado_requerido"}


def test_validar_kd_forzado_motivo_corto_raises_motivo_forzado_insuficiente() -> None:
    """T3: prefix with motivo shorter than 10 chars -> 422
    ``motivo_forzado_insuficiente``."""
    with pytest.raises(HTTPException) as ei:
        validar_kd_forzado("[FORZADO: a b]", forzado=True)
    assert ei.value.status_code == 422
    assert ei.value.detail["error"] == "motivo_forzado_insuficiente"
    assert ei.value.detail["min_chars"] == FORZADO_MIN_MOTIVO_CHARS


def test_validar_kd_forzado_prefix_sin_forzado_raises_forzado_contradiccion() -> None:
    """T4: prefix present + ``forzado=False`` -> 422 ``forzado_contradiccion``."""
    with pytest.raises(HTTPException) as ei:
        validar_kd_forzado("[FORZADO: prueba cliente]", forzado=False)
    assert ei.value.status_code == 422
    assert ei.value.detail == {"error": "forzado_contradiccion"}


def test_validar_kd_forzado_sin_prefix_sin_forzado_returns_none() -> None:
    """T-aux: ``forzado=False`` + no prefix -> ``None`` (normal path)."""
    assert validar_kd_forzado("observacion regular", forzado=False) is None
    assert validar_kd_forzado(None, forzado=False) is None


def test_validar_kd_forzado_observaciones_none_con_forzado_raises() -> None:
    """T-aux: ``observaciones=None`` + ``forzado=True`` -> motivo_forzado_requerido."""
    with pytest.raises(HTTPException) as ei:
        validar_kd_forzado(None, forzado=True)
    assert ei.value.detail == {"error": "motivo_forzado_requerido"}


__all__ = [
    "test_validar_kd_forzado_forzado_true_sin_prefix_raises_motivo_forzado_requerido",
    "test_validar_kd_forzado_motivo_corto_raises_motivo_forzado_insuficiente",
    "test_validar_kd_forzado_observaciones_none_con_forzado_raises",
    "test_validar_kd_forzado_prefix_sin_forzado_raises_forzado_contradiccion",
    "test_validar_kd_forzado_prefix_y_forzado_true_retorna_motivo_stripped",
    "test_validar_kd_forzado_sin_prefix_sin_forzado_returns_none",
]
