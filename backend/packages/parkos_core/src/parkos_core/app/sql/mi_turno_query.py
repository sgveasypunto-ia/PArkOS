"""HU-F12.1 -- pure SQL builder for the ``mi-turno`` aggregate.

The endpoint joins :class:`prod.sesion` against :class:`prod.ingreso`
and :class:`prod.salidas` via an open-window temporal predicate. There
is no FK on those event tables (``prod.ingreso`` is ``[L-E]``,
``prod.salidas`` is ``[A]``; ER.mmd 4FN canon forbids adding columns
to those tables, R-F12.1-1), so the join is purely on
``fecha_ingreso`` / ``fecha_salida`` falling inside
``[sesion.timestamp_apertura, sesion.timestamp_cierre]``.

This module is a **pure function** — same input -> same SQL string, no
DB session, no I/O. The repo helper
(:func:`parkos_core.repo.mi_turno.calcular_resumen_mi_turno`) binds
parameters and executes the SQL.

Design choice (AD-3 verbatim):
    SELECT
      COUNT(*) FILTER (WHERE i.uuid_sucursal = :S_s
                       AND COALESCE(i.fecha_ingreso, i.created_at) >= :t_open
                       AND COALESCE(i.fecha_ingreso, i.created_at) <= :t_close)
        AS ingresos_count,
      COUNT(*) FILTER (WHERE s.uuid_sucursal = :S_s
                       AND COALESCE(s.fecha_salida, s.created_at) >= :t_open
                       AND COALESCE(s.fecha_salida, s.created_at) <= :t_close)
        AS salidas_count
    FROM prod.sesion
    LEFT JOIN prod.ingreso i ON TRUE
    LEFT JOIN prod.salidas  s ON TRUE
    WHERE prod.sesion.uuid = :uuid_sesion

The ``LEFT JOIN ... ON TRUE`` pattern keeps the sesion row in the
result set even when no events exist (zero-state, REQ-OPS-184 S2).

REGRESSION fix (2026-09-22, #1): the previous SQL emitted
``(:t_close IS NULL OR ...)`` when ``t_close is None`` to guard against
post-turn event leaks. With asyncpg, a NULL-bound parameter inside a
boolean expression triggers ``IndeterminateDatatypeError: could not
determine data type of parameter $3`` (the parameter carries no type
hint). The guard was the only purpose of the NULL-OR clause; we now
substitute the literal ``TRUE`` when ``t_close is None`` (the upper
bound is vacuous for an open session by construction — no
post-turn events can leak before the session is closed). This keeps the
defensive intent without the parameter-typing pitfall.

REGRESSION fix (2026-09-22, #2): the columns ``prod.ingreso.fecha_ingreso``
and ``prod.salidas.fecha_salida`` are NULL-able without DB default and
the INSERT path (out of scope for this module) does not always populate
them (the same rows carry a populated ``created_at`` from the audit
trigger). A pure ``fecha_ingreso >= :t_open`` predicate silently
excludes those rows because tri-valued SQL semantics make ``NULL >=
anything`` evaluate to ``NULL`` (filtered out by ``COUNT(*) FILTER``).
The COALESCE wrapper falls back to ``created_at`` (DB-side audit
column, always populated) so the open-window predicate still resolves
correctly for legacy rows. When the upstream INSERT path is fixed to
populate ``fecha_ingreso`` directly, the COALESCE degrades to the
preferred column and stays as a defensive belt-and-braces fallback
(R-F12.1-2 — production reality vs ideal schema).
"""
from __future__ import annotations

import uuid as uuid_lib


def build_mi_turno_counts_sql(
    *,
    uuid_sesion: uuid_lib.UUID,
    s_sucursal: uuid_lib.UUID,
    t_open: str | None,
    t_close: str | None,
) -> str:
    """Build the open-window temporal JOIN that powers ``GET /mi-turno``.

    Args:
        uuid_sesion: ``prod.sesion.uuid`` — the session anchor.
        s_sucursal: resolved ``prod.sesion.uuid_sucursal`` (server-side,
            per REQ-OPS-185). NOT trusted from the wire.
        t_open: ``prod.sesion.timestamp_apertura`` ISO-string, or
            ``None`` to let the repo bind it at execution time (the SQL
            builder always emits the parameter so the repo can supply
            the actual value).
        t_close: ``prod.sesion.timestamp_cierre`` ISO-string, or
            ``None`` for an open session. When ``None``, the upper bound
            is vacuous and the SQL emits literal ``TRUE`` (no parameter
            is bound — this avoids the asyncpg IndeterminateDatatypeError
            that triggered on the previous ``(:t_close IS NULL OR ...)``
            form). When set, the SQL emits
            ``COALESCE(i.fecha_ingreso, i.created_at) <= :t_close`` /
            ``COALESCE(s.fecha_salida, s.created_at) <= :t_close``.

    Returns:
        The SQL string with named bind parameters ``:uuid_sesion``,
        ``:S_s``, ``:t_open``, ``:t_close``. The caller binds them via
        SQLAlchemy text/exec. When ``t_close`` is ``None``, the
        ``:t_close`` parameter is unused — the repo must NOT bind it.
    """
    del s_sucursal  # parameters are referenced via :S_s in the SQL string.
    del t_open  # same.

    # When t_close is None the upper bound is vacuous (no post-turn
    # events can leak before the session is closed). Emit literal TRUE
    # so asyncpg never has to type a NULL parameter. When t_close is
    # set, the bound upper bound replaces the guard.
    if t_close is None:
        upper_predicate_ingreso = "TRUE"
        upper_predicate_salida = "TRUE"
    else:
        upper_predicate_ingreso = "COALESCE(i.fecha_ingreso, i.created_at) <= :t_close"
        upper_predicate_salida = "COALESCE(s.fecha_salida, s.created_at) <= :t_close"

    # REGRESSION fix (2026-09-22, REQ-OPS-184): the previous shape used
    # ``LEFT JOIN prod.ingreso i ON TRUE LEFT JOIN prod.salidas s ON TRUE``
    # — which is a full cross product between the sesion row, ALL
    # ``prod.ingreso`` rows, and ALL ``prod.salidas`` rows. ``COUNT(*)``
    # FILTER then matched each cross-product row against its own
    # predicate. With N ingresos and M salidas, ``salidas_count`` was
    # effectively ``N × M`` instead of ``M`` — multiplying spurious
    # salidas as the operator's turno accumulated eventos (the bug
    # was masked at M=0 because 0 × N = 0).
    #
    # The fix uses scalar subqueries so the two COUNTs are independent
    # and immune to the cross product. Each subquery is a clean
    # point-in-time aggregate against its own event table — no
    # join, no Cartesian explosion. The sesion anchor still appears in
    # the outer SELECT (as ``WHERE prod.sesion.uuid = :uuid_sesion``)
    # so the no-events zero-state degrades to a single-row
    # zero-zero-zero-zero-zero row.
    return (
        "SELECT "
        "(SELECT COUNT(*) FROM prod.ingreso i "
        "WHERE i.uuid_sucursal = :S_s "
        f"AND COALESCE(i.fecha_ingreso, i.created_at) >= :t_open "
        f"AND {upper_predicate_ingreso}"
        ") AS ingresos_count, "
        "(SELECT COUNT(*) FROM prod.salidas s "
        "WHERE s.uuid_sucursal = :S_s "
        f"AND COALESCE(s.fecha_salida, s.created_at) >= :t_open "
        f"AND {upper_predicate_salida}"
        ") AS salidas_count "
        "FROM prod.sesion "
        "WHERE prod.sesion.uuid = :uuid_sesion"
    )


__all__ = ["build_mi_turno_counts_sql"]