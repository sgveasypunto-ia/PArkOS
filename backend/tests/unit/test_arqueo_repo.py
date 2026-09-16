"""HU-F1.13 / T2.1 -- repo/arqueo.py module-import + pure-helper tests.

T2.1 RED + GREEN: import the module, verify ``__all__`` exposes
13 helpers + 6 typed exceptions.

Pure Python tests -- no DB, no HTTP. Gated repo unit tests live in
``test_arqueo_repo_db.py`` (added by F1.14 if needed; current
F1.13 scope tests ``__all__`` + pure-Decimal helpers).
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


def test_repo_arqueo_module_imports() -> None:
    """T2.1: module imports + ``__all__`` exposes all 13 helpers + 6 exceptions."""
    from parkos_core.repo import arqueo as repo_arqueo

    public = set(repo_arqueo.__all__)
    expected_helpers = {
        "calcular_diferencia",
        "calcular_esperado_cierre_dia",
        "calcular_esperado_sesion",
        "cerrar_sesiones_del_dia_bulk",
        "construir_resumen_sesion",
        "es_descuadre_critico",
        "insertar_alerta_descuadre_critico",
        "insertar_arqueo",
        "listar_sesiones_abiertas_del_dia",
        "listar_sesiones_del_dia",
        "obtener_cierre_dia_del_dia",
        "resolver_tipo_arqueo_por_uuid",
        "resolver_tolerancia_vigente",
        "validar_sesion_abierta_para_arqueo",
    }
    expected_exceptions = {
        "CierreDiaNoAceptaSesionError",
        "JustificacionRequeridaError",
        "SesionNoEncontradaError",
        "SesionYaCerradaError",
        "TipoArqueoNoEncontradoError",
        "ToleranciaNoConfiguradaError",
    }
    missing = (expected_helpers | expected_exceptions) - public
    assert not missing, f"missing from __all__: {sorted(missing)}"


# ---------------------------------------------------------------------------
# V7 -- pure Decimal math: es_descuadre_critico + calcular_diferencia
# ---------------------------------------------------------------------------


def test_es_descuadre_critico_sobre_tolerancia_returns_true() -> None:
    """V7 REQ-OPS-093 Scenario 2: |diferencia| > tolerancia -> True."""
    from parkos_core.repo.arqueo import es_descuadre_critico

    assert es_descuadre_critico(
        diferencia_efectivo=150,
        diferencia_datafono=0,
        tolerancia_efectivo=100,
        tolerancia_datafono=200,
    )


def test_es_descuadre_critico_igual_tolerancia_returns_false() -> None:
    """V7 REQ-OPS-093 Scenario 3: |diferencia| == tolerancia -> False (strict >)."""
    from parkos_core.repo.arqueo import es_descuadre_critico

    assert not es_descuadre_critico(
        diferencia_efectivo=100,
        diferencia_datafono=0,
        tolerancia_efectivo=100,
        tolerancia_datafono=200,
    )


def test_es_descuadre_critico_dentro_tolerancia_returns_false() -> None:
    """V7 REQ-OPS-093 Scenario 1: |diferencia| < tolerancia -> False."""
    from parkos_core.repo.arqueo import es_descuadre_critico

    assert not es_descuadre_critico(
        diferencia_efectivo=50,
        diferencia_datafono=0,
        tolerancia_efectivo=100,
        tolerancia_datafono=200,
    )


def test_es_descuadre_critico_datafono_branch_triggers() -> None:
    """V7: |diferencia_datafono| > tolerancia_datafono alone triggers."""
    from parkos_core.repo.arqueo import es_descuadre_critico

    assert es_descuadre_critico(
        diferencia_efectivo=0,
        diferencia_datafono=250,
        tolerancia_efectivo=100,
        tolerancia_datafono=200,
    )


def test_calcular_diferencia_substracts() -> None:
    """Pure Decimal math: diferencia = reportado - esperado."""
    from decimal import Decimal

    from parkos_core.repo.arqueo import calcular_diferencia

    assert calcular_diferencia(
        reportado=Decimal("148050"), esperado=Decimal("148000")
    ) == Decimal("50")
    assert calcular_diferencia(
        reportado=Decimal("148000"), esperado=Decimal("148050")
    ) == Decimal("-50")
    assert calcular_diferencia(
        reportado=Decimal("0"), esperado=Decimal("0")
    ) == Decimal("0")


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


def test_typed_exceptions_carry_uuid_context() -> None:
    """Typed exceptions carry their discriminator field (Layer 5 contract)."""
    import uuid as uuid_lib

    from parkos_core.repo.arqueo import (
        CierreDiaNoAceptaSesionError,
        JustificacionRequeridaError,
        SesionNoEncontradaError,
        SesionYaCerradaError,
        TipoArqueoNoEncontradoError,
        ToleranciaNoConfiguradaError,
    )

    s = uuid_lib.uuid4()
    e1 = TipoArqueoNoEncontradoError(uuid_tipo_arqueo=s)
    assert e1.uuid_tipo_arqueo == s
    assert "tipo_arqueo_no_encontrado" in str(e1)

    e2 = SesionNoEncontradaError(uuid_sesion=s)
    assert e2.uuid_sesion == s
    assert "sesion_no_encontrada" in str(e2)

    e3 = SesionYaCerradaError(uuid_sesion=s)
    assert e3.uuid_sesion == s
    assert "sesion_ya_cerrada" in str(e3)

    e4 = ToleranciaNoConfiguradaError(uuid_sucursal=s)
    assert e4.uuid_sucursal == s
    assert "tolerancia_no_configurada" in str(e4)

    e5 = CierreDiaNoAceptaSesionError()
    assert "cierre_dia_no_acepta_uuid_sesion" in str(e5)

    e6 = JustificacionRequeridaError()
    assert "justificacion_requerida" in str(e6)
