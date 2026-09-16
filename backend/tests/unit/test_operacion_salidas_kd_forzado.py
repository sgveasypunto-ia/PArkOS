"""HU-F1.7 / KD-FORZADO-01 -- pure helper unit tests for ``validar_kd_forzado``.

The KD-FORZADO-01 prefix contract is REUSED VERBATIM from F1.6
(``repo/ingreso.py::validar_kd_forzado``). This test file verifies the
contract still holds when invoked from the new salida path.

Lifecycle:
  - RED: import fails with ImportError on early develop branches.
  - GREEN: 2 tests pass -- prefix valid returns stripped motivo;
    motivo insuficiente raises 422.

No HTTP, no DB -- this is a pure Python helper test.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from parkos_core.repo.ingreso import FORZADO_MIN_MOTIVO_CHARS, validar_kd_forzado


def test_validar_kd_forzado_reuse_desde_repo_ingreso_para_salida() -> None:
    """T1: prefix present + ``forzado=True`` -> stripped motivo.

    Confirms that the F1.6 verbatim helper is reused from the salida
    path without modification. The stripped motivo is then placed in
    the alerta ``datos_nuevos.motivo`` JSONB column (F1.7 R-A2 analog).
    """
    motivo = "cliente con cita medica urgente"
    observaciones = f"[FORZADO: {motivo}]"
    result = validar_kd_forzado(observaciones, forzado=True)
    assert result == motivo
    assert len(result) >= FORZADO_MIN_MOTIVO_CHARS


def test_validar_kd_forzado_motivo_insuficiente_raises_422() -> None:
    """T2: motivo shorter than 10 chars -> 422 ``motivo_forzado_insuficiente``.

    The F1.7 handler maps this 422 to the salida response body without
    inserting any row in ``prod.salidas`` or ``prod.alerta``.
    """
    with pytest.raises(HTTPException) as ei:
        validar_kd_forzado("[FORZADO: a b]", forzado=True)
    assert ei.value.status_code == 422
    assert ei.value.detail["error"] == "motivo_forzado_insuficiente"
    assert ei.value.detail["min_chars"] == FORZADO_MIN_MOTIVO_CHARS


def test_kd_forzado_no_se_duplica_en_repo_salida() -> None:
    """T3: DRY contract -- ``repo/salida.py`` MUST NOT define
    ``validar_kd_forzado``; the function comes from
    ``repo/ingreso.py`` verbatim.
    """
    import parkos_core.repo.salida as salida_repo

    assert not hasattr(salida_repo, "validar_kd_forzado"), (
        "repo/salida.py MUST NOT redefine validar_kd_forzado; "
        "reuse verbatim from repo/ingreso.py (DEC-FORZADO-01)."
    )


__all__ = [
    "test_validar_kd_forzado_reuse_desde_repo_ingreso_para_salida",
    "test_validar_kd_forzado_motivo_insuficiente_raises_422",
    "test_kd_forzado_no_se_duplica_en_repo_salida",
]
