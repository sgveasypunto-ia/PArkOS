"""HU-F1.9 / REQ-OPS-058 -- DIAN NIT módulo 11 validator.

The Colombian NIT (Número de Identificación Tributaria) MUST be validated
against its check digit (DV) per the official DIAN algorithm (RUT,
Resolución 000070 de 2016): weights
``[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]`` applied
**from the rightmost digit leftwards** on the NIT digits (without DV);
``r = sum % 11``; ``DV = r`` if ``r in (0, 1)`` else ``11 - r``.

History: an earlier version computed ``DV = sum % 11`` with the weight
table reversed ("Variant A"). It agreed with real NITs only by chance and
rejected valid ones (e.g. 900123456 -> 8, not 3). Pinned against real
institutional NITs in ``tests/unit/test_validar_nit_modulo11.py``.

Public API:
    validar_nit_modulo11(nit: str, dv: str | int) -> bool
    dv_esperado(nit: str) -> int
"""
from __future__ import annotations

import re

# Weights for módulo 11; index 0 applies to the RIGHTMOST digit (recycled
# cyclically if NIT >15 digits). Source: DIAN RUT check-digit algorithm.
MOD11_WEIGHTS: tuple[int, ...] = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)

_NON_DIGIT_RE = re.compile(r"\D+")


def _normalize_nit(nit: str) -> str:
    """Strip non-digits, leading zeros. Returns digits-only string.

    Examples:
        '800.123.456-7' → '800123456'
        '000123' → '123' (then DV; the DV is separate)
        '800 123 456' → '800123456'
        '   ' or '' → '0' (sentinel; downstream rejects insufficient length)
    """
    digits = _NON_DIGIT_RE.sub("", nit)
    return digits.lstrip("0") or "0"


def dv_esperado(nit: str) -> int:
    """Compute DV expected for the given NIT (without DV digit).

    Returns an int in [0, 9]. Raises ``ValueError`` if NIT <5 digits.

    Algorithm (official DIAN):
        sum = Σ digit_i * MOD11_WEIGHTS[i]   (i = 0 at the rightmost digit)
        r = sum % 11
        return r if r < 2 else 11 - r
    """
    digits = _normalize_nit(nit)
    if len(digits) < 5:
        raise ValueError(f"NIT too short: {digits!r} (min 5 digits)")
    sum_ponderada = 0
    for idx, digit_char in enumerate(reversed(digits)):
        weight = MOD11_WEIGHTS[idx % len(MOD11_WEIGHTS)]
        sum_ponderada += int(digit_char) * weight
    mod = sum_ponderada % 11
    return mod if mod < 2 else 11 - mod


def validar_nit_modulo11(nit: str, dv: str | int) -> bool:
    """Validate NIT against DIAN módulo 11 algorithm.

    Returns True iff ``dv == dv_esperado(nit)``.

    Accepts both shapes:

    - ``"800.123.456"`` + ``"7"`` (NIT and DV provided separately)
    - ``"800.123.456-7"`` + ``"7"`` (DV also appended to NIT; the
      trailing digit(s) matching the ``dv`` argument are stripped
      before computing the expected check digit).

    Normalizes the NIT (strip non-digits, leading zeros) and casts the
    DV to int (raises ``ValueError`` → returns False on malformed DV).
    Returns False on any internal ``ValueError`` (e.g., NIT <5 digits
    after stripping).
    """
    try:
        dv_int = int(dv) if isinstance(dv, str) else dv
        digits = _normalize_nit(nit)
        # The NIT may arrive with or without its DV appended
        # ("800.197.268-4" + "4"). A bare body that happens to END in the
        # DV digit (860002964 + "4") is also legitimate, so try the body as
        # given first, then the body with the trailing DV stripped.
        if dv_int == dv_esperado(digits):
            return True
        dv_str = str(dv_int)
        if dv_str and len(digits) > len(dv_str) and digits.endswith(dv_str):
            return dv_int == dv_esperado(digits[: -len(dv_str)])
        return False
    except (ValueError, TypeError):
        return False


__all__ = ["MOD11_WEIGHTS", "dv_esperado", "validar_nit_modulo11"]
