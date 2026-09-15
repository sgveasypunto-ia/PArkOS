"""HU-F1.9 / REQ-OPS-058 / DEC-FACT-08 -- NIT Variant A reference tests.

The reference test case ``800.123.456-7`` (DV=7) discriminates DIAN
módulo 11 Variant A canónica (DV = sum % 11) from Variant B
(DV = 11 - (sum % 11)). Both variants are valid proposals but
DIAN Resolución 000175 de 2021 specifies Variant A.

If a future maintainer changes ``mod = sum % 11`` to
``mod = 11 - (sum % 11)``, the first test fails immediately before merge.
"""
from parkos_core.repo.nit_modulo11 import MOD11_WEIGHTS, dv_esperado, validar_nit_modulo11


def test_nit_referencia_800_123_456_7_valido() -> None:
    """Variant A canónica: ``800.123.456`` → DV esperado = 7."""
    # Reference: 800.123.456-7 (NIT ficticio discriminante).
    assert validar_nit_modulo11("800.123.456-7", "7") is True
    # Test without DV separator (raw digits).
    expected = dv_esperado("800.123.456")
    assert expected == 7, (
        f"Variant A canónica discriminada: expected DV=7, got {expected}. "
        f"Si obtienes 4 (11-7), estás aplicando Variant B (incorrecta)."
    )
    # DV esperado is an int in [0, 10].
    assert isinstance(expected, int)
    assert 0 <= expected <= 10
    # Weights tuple sanity check (guarantees no typo in canonical DIAN list).
    assert MOD11_WEIGHTS == (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)


def test_nit_dv_incorrecto_retorna_false() -> None:
    """DV wrong value returns False, NOT raises."""
    # Variant A: DV esperado = 7; sending DV=8 returns False.
    assert validar_nit_modulo11("800.123.456-7", "8") is False
    assert validar_nit_modulo11("800.123.456", 9) is False
    # Malformed DV returns False (catches non-numeric DV without crash).
    assert validar_nit_modulo11("800.123.456-7", "X") is False
    # Int out of [0,10] returns False.
    assert validar_nit_modulo11("800.123.456", -1) is False
    # Empty NIT (digits only after strip) → False (not crash).
    assert validar_nit_modulo11("", "0") is False
    # Too-short NIT (<5 digits) → False (graceful, not crash).
    assert validar_nit_modulo11("123", "0") is False


def test_nit_normaliza_puntuacion_y_espacios() -> None:
    """Normalization handles dots, dashes, spaces, leading zeros."""
    # Punctuation (dash, dot, spaces).
    assert validar_nit_modulo11("800.123.456-7", "7") is True
    assert validar_nit_modulo11("800 123 456 7", "7") is True
    assert validar_nit_modulo11("800-123-456", "7") is True
    # Leading zeros stripped.
    assert validar_nit_modulo11("000800123456-7", "7") is True
    # DV alone (raw digits only).
    assert dv_esperado("800123456") == 7


def test_nit_normalizacion_extremos() -> None:
    """Extreme inputs: all zeros, whitespace-only, non-digit DV."""
    # All zeros collapses to "0" → not enough digits (need ≥5) → False.
    assert validar_nit_modulo11("00000", "0") is False
    # Whitespace-only NIT → digits after strip = "" → False.
    assert validar_nit_modulo11("     ", "0") is False
    # Decimal DV (cast from string "9.5" to int raises ValueError) → False.
    assert validar_nit_modulo11("800123456", "9.5") is False
