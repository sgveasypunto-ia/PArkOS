"""catalog/normalizers.py — ``natural_key_normalizer`` callables (T-PR5-006, D17).

Design.md Issue #10: "Normalization is part of the rule." Without it,
``ABC-123`` and ``ABC123`` are two different natural-key entities and
``IdentityReconciler`` (``hooks/impls/identity_reconciler.py``) silently
never fires, reintroducing the exact version-chain-inflation bug D17 exists
to prevent.

Each normalizer has an **SQL-equivalent expression** used by the lookup
index in migration ``0008_add_identity_nk_indexes.py``:

  - ``numero_identificacion``: ``regexp_replace(numero_identificacion,
    '[^0-9A-Za-z]', '', 'g')`` — trims separators/whitespace, case preserved.
  - ``placa``: ``upper(regexp_replace(placa, '[^0-9A-Za-z]', '', 'g'))`` —
    trims separators/whitespace, uppercased.

``tests/unit/test_natural_key_normalizer_parity.py`` asserts the Python form
and the SQL form agree over a shared fixture set — a divergence here would
make the functional index miss and silently reintroduce the duplicate the
whole mechanism exists to prevent.

Wired onto the 3 ``natural_key``-declaring entries (T-PR2-006) in
``entries/sync_entries_v.py``: ``clientes``, ``clientes_b2b``, ``vehiculos``.
"""
from __future__ import annotations

import re
from typing import Any

# Matches the SQL functional index expression's character class exactly —
# ``[^0-9A-Za-z]`` — anything that is NOT an ASCII digit or letter is
# stripped (separators, whitespace, punctuation).
_SEPARATORS_RE = re.compile(r"[^0-9A-Za-z]")


def normalize_numero_identificacion(value: str | None) -> str | None:
    """Trim separators/whitespace from a ``numero_identificacion`` value.

    SQL-equivalent: ``regexp_replace(numero_identificacion, '[^0-9A-Za-z]',
    '', 'g')``. Case is preserved — identifier digits/letters are not
    case-folded (unlike ``placa``).
    """
    if value is None:
        return None
    return _SEPARATORS_RE.sub("", value)


def normalize_placa(value: str | None) -> str | None:
    """Uppercase + strip separators from a ``placa`` value.

    SQL-equivalent: ``upper(regexp_replace(placa, '[^0-9A-Za-z]', '', 'g'))``.
    ``ABC-123`` and ``abc123`` both normalize to ``ABC123``.
    """
    if value is None:
        return None
    return _SEPARATORS_RE.sub("", value).upper()


def clientes_natural_key_normalizer(payload: dict[str, Any]) -> dict[str, Any]:
    """``natural_key_normalizer`` for ``clientes`` — ``(tipo_identificador,
    numero_identificacion)``. ``tipo_identificador`` is a short enum code
    (``CC``, ``NIT``, ...) — not subject to separator stripping.
    """
    return {
        "tipo_identificador": payload.get("tipo_identificador"),
        "numero_identificacion": normalize_numero_identificacion(
            payload.get("numero_identificacion")
        ),
    }


def clientes_b2b_natural_key_normalizer(payload: dict[str, Any]) -> dict[str, Any]:
    """``natural_key_normalizer`` for ``clientes_b2b`` — ``(uuid_cliente,)``.

    A UUID foreign key needs no separator/case normalization; this callable
    exists so every ``natural_key``-declaring entry has a normalizer to call
    uniformly (``IdentityReconciler`` never special-cases "no normalizer").
    """
    return {"uuid_cliente": payload.get("uuid_cliente")}


def vehiculos_natural_key_normalizer(payload: dict[str, Any]) -> dict[str, Any]:
    """``natural_key_normalizer`` for ``vehiculos`` — ``(placa,)``."""
    return {"placa": normalize_placa(payload.get("placa"))}


__all__ = [
    "clientes_b2b_natural_key_normalizer",
    "clientes_natural_key_normalizer",
    "normalize_numero_identificacion",
    "normalize_placa",
    "vehiculos_natural_key_normalizer",
]
