"""HU-F1.9 / REQ-OPS-058 -- DIAN NIT módulo 11 validator.

The Colombian NIT (Número de Identificación Tributaria) MUST be validated
against its check digit (DV) per the algoritmo de módulo 11 established by
DIAN. The check digit is computed from the preceding digits using weights
``[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]`` applied
**right-to-left** on the NIT digits (without DV).

``DV = sum_ponderada % 11`` -- **Variant A canónica** per DIAN
Resolución 000175 de 2021, NOT ``11 - (sum % 11)`` (Variant B).
The reference test case ``800.123.456-7`` (DV=7) discriminates Variants.

Public API:
    validar_nit_modulo11(nit: str, dv: str | int) -> bool
    dv_esperado(nit: str) -> int
"""
from __future__ import annotations

import re

# Weights for módulo 11 (right-to-left, recycled cyclically if NIT >15 digits).
# Source: DIAN Resolución 000175 de 2021, Anexo Técnico de Facturación
# Electrónica, Numeral 11.1 (validación del DV del NIT).
MOD11_WEIGHTS: tuple[int, ...] = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)

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

    Returns an int in [0, 10]. Raises ``ValueError`` if NIT <5 digits.

    Algorithm (Variant A canónica):
        sum = 0
        for i, digit in enumerate(reversed(nit_digits)):
            sum += int(digit) * MOD11_WEIGHTS[i % len(MOD11_WEIGHTS)]
        return sum % 11
    """
    digits = _normalize_nit(nit)
    if len(digits) < 5:
        raise ValueError(f"NIT too short: {digits!r} (min 5 digits)")
    sum_ponderada = 0
    for idx, digit_char in enumerate(reversed(digits)):
        weight = MOD11_WEIGHTS[idx % len(MOD11_WEIGHTS)]
        sum_ponderada += int(digit_char) * weight
    mod = sum_ponderada % 11
    return mod  # DIAN Variant A: DV = mod (NOT 11-mod)


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
        # Strip the trailing DV if present (e.g., "8001234567" → "800123456"
        # when dv="7"). This supports the ergonomic "800.123.456-7" form
        # without forcing callers to split manually.
        dv_str = str(dv_int)
        if dv_str and len(digits) > len(dv_str) and digits.endswith(dv_str):
            base = digits[: -len(dv_str)]
        else:
            base = digits
        expected = dv_esperado(base)
        return dv_int == expected
    except (ValueError, TypeError):
        return False


__all__ = ["MOD11_WEIGHTS", "dv_esperado", "validar_nit_modulo11"]
