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
                       AND i.fecha_ingreso >= :t_open
                       AND (:t_close IS NULL OR i.fecha_ingreso <= :t_close))
        AS ingresos_count,
      COUNT(*) FILTER (WHERE s.uuid_sucursal = :S_s
                       AND s.fecha_salida >= :t_open
                       AND (:t_close IS NULL OR s.fecha_salida <= :t_close))
        AS salidas_count
    FROM prod.sesion
    LEFT JOIN prod.ingreso i ON TRUE
    LEFT JOIN prod.salidas  s ON TRUE
    WHERE prod.sesion.uuid = :uuid_sesion

The ``LEFT JOIN ... ON TRUE`` pattern keeps the sesion row in the
result set even when no events exist (zero-state, REQ-OPS-184 S2).
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
            ``None`` for an open session. When ``None``, the SQL adds
            the ``:t_close IS NULL`` guard so post-turn events
            (impossible by construction) are still counted correctly
            if a future bug ever inserts rows out of order.

    Returns:
        The SQL string with named bind parameters ``:uuid_sesion``,
        ``:S_s``, ``:t_open``, ``:t_close``. The caller binds them via
        SQLAlchemy text/exec.
    """
    del s_sucursal  # parameters are referenced via :S_s in the SQL string.
    del t_open  # same.

    # When t_close is None the SQL emits the NULL-guard predicate so a
    # future bug that lets events leak post-turn is still bounded by
    # the closed-session window. When t_close is set, the bound IS
    # NOT NULL check is replaced with the actual upper bound.
    if t_close is None:
        upper_predicate_ingreso = ":t_close IS NULL"
        upper_predicate_salida = ":t_close IS NULL"
    else:
        upper_predicate_ingreso = "i.fecha_ingreso <= :t_close"
        upper_predicate_salida = "s.fecha_salida <= :t_close"

    return (
        "SELECT "
        "COUNT(*) FILTER ("
        "WHERE i.uuid_sucursal = :S_s "
        "AND i.fecha_ingreso >= :t_open "
        f"AND ({upper_predicate_ingreso})"
        ") AS ingresos_count, "
        "COUNT(*) FILTER ("
        "WHERE s.uuid_sucursal = :S_s "
        "AND s.fecha_salida >= :t_open "
        f"AND ({upper_predicate_salida})"
        ") AS salidas_count "
        "FROM prod.sesion "
        "LEFT JOIN prod.ingreso i ON TRUE "
        "LEFT JOIN prod.salidas s ON TRUE "
        "WHERE prod.sesion.uuid = :uuid_sesion"
    )


__all__ = ["build_mi_turno_counts_sql"]