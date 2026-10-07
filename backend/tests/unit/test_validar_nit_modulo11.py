"""HU-F1.9 / REQ-OPS-058 -- DIAN NIT módulo 11 check-digit (DV) tests.

Official algorithm (DIAN, Resolución 000070 de 2016 / RUT): weights
``3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71`` applied from the
RIGHTMOST digit leftwards; ``r = S mod 11``; ``DV = r`` if ``r in (0, 1)``
else ``11 - r``.

The previous implementation used ``DV = S mod 11`` with the weight table
reversed ("Variant A"); it matched real NITs only by coincidence. The real
pairs below pin the official behaviour.
"""
import pytest

from parkos_core.repo.nit_modulo11 import MOD11_WEIGHTS, dv_esperado, validar_nit_modulo11

# Publicly known NIT / DV pairs of large Colombian institutions.
REAL_NITS = [
    ("899999068", 1),  # Ecopetrol
    ("890903938", 8),  # Bancolombia
    ("860034313", 7),  # Davivienda
    ("800197268", 4),  # DIAN
    ("860002964", 4),  # Banco de Bogotá
    ("890900608", 9),  # Almacenes Éxito
]


@pytest.mark.parametrize(("nit", "dv"), REAL_NITS)
def test_nits_reales_dv_oficial(nit: str, dv: int) -> None:
    assert dv_esperado(nit) == dv
    assert validar_nit_modulo11(nit, str(dv)) is True
    assert validar_nit_modulo11(f"{nit}-{dv}", dv) is True


def test_nit_900123456_dv_8() -> None:
    """Case reported by a verifier: official DV is 8 (the old code gave 3)."""
    assert dv_esperado("900123456") == 8
    assert validar_nit_modulo11("900.123.456-8", "8") is True
    assert validar_nit_modulo11("900.123.456", "3") is False


def test_pesos_oficiales_derecha_a_izquierda() -> None:
    assert MOD11_WEIGHTS == (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
    # 123456789: S = 665, r = 5, DV = 6.
    assert dv_esperado("123456789") == 6


def test_resto_0_y_1_devuelven_el_resto() -> None:
    # S = 11 * k  ->  r = 0 -> DV 0 ; S = 11 * k + 1 -> r = 1 -> DV 1.
    seen = {}
    for n in range(10_000, 12_000):
        seen.setdefault(dv_esperado(str(n)), n)
    assert 0 in seen and 1 in seen
    for body, expected_r in ((seen[0], 0), (seen[1], 1)):
        total = sum(int(d) * MOD11_WEIGHTS[i] for i, d in enumerate(reversed(str(body))))
        assert total % 11 == expected_r
        assert dv_esperado(str(body)) == expected_r


def test_dv_nunca_es_diez_y_resto_10_da_1() -> None:
    """r = 10 maps to 11 - 10 = 1; a DV of 10 is impossible."""
    produced = {dv_esperado(str(n)) for n in range(10_000, 14_000)}
    assert max(produced) <= 9
    # Find a body whose raw remainder is 10 and check the DV is 1.
    for n in range(10_000, 14_000):
        total = sum(int(d) * MOD11_WEIGHTS[i] for i, d in enumerate(reversed(str(n))))
        if total % 11 == 10:
            assert dv_esperado(str(n)) == 1
            break
    else:  # pragma: no cover
        pytest.fail("no body with remainder 10 found")


def test_nit_corto_menor_a_15_digitos_no_se_rellena() -> None:
    """Leading zeros do not change the sum (zero contributes nothing)."""
    assert dv_esperado("000899999068") == dv_esperado("899999068") == 1


def test_nit_mas_de_15_digitos_cicla_pesos() -> None:
    body = "1234567890123456"
    total = sum(
        int(d) * MOD11_WEIGHTS[i % len(MOD11_WEIGHTS)] for i, d in enumerate(reversed(body))
    )
    r = total % 11
    assert dv_esperado(body) == (r if r < 2 else 11 - r)


def test_nit_dv_incorrecto_retorna_false() -> None:
    assert validar_nit_modulo11("899999068-1", "2") is False
    assert validar_nit_modulo11("899999068", 9) is False
    assert validar_nit_modulo11("899999068-1", "X") is False
    assert validar_nit_modulo11("899999068", -1) is False
    assert validar_nit_modulo11("899999068", 10) is False
    assert validar_nit_modulo11("", "0") is False
    assert validar_nit_modulo11("123", "0") is False


def test_nit_normaliza_puntuacion_y_espacios() -> None:
    assert validar_nit_modulo11("899.999.068-1", "1") is True
    assert validar_nit_modulo11("899 999 068 1", "1") is True
    assert validar_nit_modulo11("899-999-068", "1") is True
    assert validar_nit_modulo11("000899999068-1", "1") is True
    assert dv_esperado("899999068") == 1


def test_nit_normalizacion_extremos() -> None:
    assert validar_nit_modulo11("00000", "0") is False
    assert validar_nit_modulo11("     ", "0") is False
    assert validar_nit_modulo11("899999068", "9.5") is False
