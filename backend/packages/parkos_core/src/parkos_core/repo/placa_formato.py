"""Placa format rules -- pure, no DB, single source of truth for the backend.

Mirrors the branch frontend (``apps/electron-sucursal/src/lib/validation/
placa.ts``) exactly, so the API is never stricter nor looser than the UI:

* normalization = ``trim + upper + remove ALL whitespace`` (``placa.ts``);
* valid = ``REGEX_AUTO`` (``ABC123``) OR ``REGEX_MOTO`` (``ABC12D``).

The front has NO special cases (no diplomatic / foreign / "otros" format):
vehicles without plate (bici, patineta) are sent with ``placa = null`` and
never reach this check. Do not add formats here without adding them to the
front first.

Matching is ASCII-only on purpose: ``[A-Z]`` / ``[0-9]`` with ``fullmatch``
(``\\d`` and ``str.isdigit`` accept Arabic/fullwidth digits, and ``$``
accepts a trailing newline). ``str.upper()`` is applied BEFORE matching, as
in the front; a character that upper-cases into ASCII (e.g. the
long s U+017F -> ``S``) is rejected by the ASCII check on the ORIGINAL characters
via the ``isascii`` guard below.

NOT applied to sync/apply paths: replicated historical data must not be
rejected (the sync motor never imports this module).
"""
from __future__ import annotations

import re

FORMATO_AUTO = re.compile(r"[A-Z]{3}[0-9]{3}")  # ABC123
FORMATO_MOTO = re.compile(r"[A-Z]{3}[0-9]{2}[A-Z]")  # ABC12D

FORMATOS_ACEPTADOS: tuple[str, str] = ("ABC123", "ABC12D")

_WHITESPACE = re.compile(r"\s+")


class PlacaFormatoInvalidoError(ValueError):
    """The placa does not match any accepted format. ``placa`` is the raw input."""

    def __init__(self, placa: object) -> None:
        self.placa = placa
        super().__init__(
            f"Placa {placa!r} no coincide con ningun formato valido "
            f"(Auto: {FORMATOS_ACEPTADOS[0]}, Moto: {FORMATOS_ACEPTADOS[1]})."
        )


def normalizar_placa(placa: str) -> str:
    """``trim + upper + strip whitespace`` (same as the front's ``placa.ts``)."""
    return _WHITESPACE.sub("", placa.strip().upper())


def validar_placa(placa: object) -> str:
    """Return the canonical placa or raise :class:`PlacaFormatoInvalidoError`."""
    if not isinstance(placa, str):
        raise PlacaFormatoInvalidoError(placa)
    # ``upper()`` can map non-ASCII to ASCII (U+017F -> ``S``); the front's JS
    # regexes would see the upper-cased char too, but accepting a plate that
    # was typed with look-alike unicode only stores garbage -- reject it.
    if not _WHITESPACE.sub("", placa).isascii():
        raise PlacaFormatoInvalidoError(placa)
    canonica = normalizar_placa(placa)
    if FORMATO_AUTO.fullmatch(canonica) or FORMATO_MOTO.fullmatch(canonica):
        return canonica
    raise PlacaFormatoInvalidoError(placa)


__all__ = [
    "FORMATOS_ACEPTADOS",
    "FORMATO_AUTO",
    "FORMATO_MOTO",
    "PlacaFormatoInvalidoError",
    "normalizar_placa",
    "validar_placa",
]
