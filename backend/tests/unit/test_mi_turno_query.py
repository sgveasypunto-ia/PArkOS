"""HU-F12.1 / T-B1-2 -- pure SQL builder for the ``mi-turno`` aggregation.

The aggregator joins ``prod.sesion`` (anchor) against ``prod.ingreso``
and ``prod.salidas`` via the open-window temporal predicate (no FK on
those tables, per ER.mmd 4FN canon, R-F12.1-1):

    COUNT(*) FILTER (
      WHERE i.uuid_sucursal = :S_s
        AND i.fecha_ingreso >= :t_open
        AND i.fecha_ingreso <= :t_close     -- when t_close IS NOT NULL
        -- otherwise literal TRUE (open session)
    ) AS ingresos_count,

    COUNT(*) FILTER (
      WHERE s.uuid_sucursal = :S_s
        AND s.fecha_salida >= :t_open
        AND s.fecha_salida <= :t_close       -- when t_close IS NOT NULL
        -- otherwise literal TRUE (open session)
    ) AS salidas_count

The builder MUST be a pure function: same input -> same SQL string. No
DB session, no I/O. This test pins the contract at the SQL layer so a
future refactor of ``repo/mi_turno.py`` cannot silently drop the
open-window predicate (which would break the closed-session scenario
in REQ-OPS-186).

S1: open session (t_close IS None) -> the upper bound is the literal
    ``TRUE`` (no parameter is bound). The previous ``(:t_close IS NULL
    OR ...)`` form was retired on 2026-09-22 because asyncpg cannot
    type a NULL parameter inside a boolean expression and the query
    raised IndeterminateDatatypeError.
S2: closed session (t_close IS NOT NULL) -> the predicate adds the
    ``fecha_ingreso <= :t_close`` upper bound (REQ-OPS-186).
S3: branch scope ``S_s`` is interpolated into the COUNT FILTER, NOT
    as a separate WHERE — defends against a copy-paste regression
    where the branch scope is dropped and the SUM double-counts
    cross-branch events.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


def _build_open_session_sql(uuid_sesion: uuid_lib.UUID, s_sucursal: uuid_lib.UUID) -> str:
    """Pure SQL builder entry point under test (mirrors ``app/sql/mi_turno_query.py``)."""

    from parkos_core.app.sql.mi_turno_query import build_mi_turno_counts_sql

    return build_mi_turno_counts_sql(
        uuid_sesion=uuid_sesion,
        s_sucursal=s_sucursal,
        t_open=None,
        t_close=None,
    )


def test_open_session_sql_uses_literal_true_for_upper_bound() -> None:
    """S1 (REQ-OPS-186 + REGRESSION 2026-09-22): open session -> upper bound is literal TRUE."""
    uuid_sesion = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")
    s_sucursal = uuid_lib.UUID("00000000-0000-0000-0000-000000000002")
    sql = _build_open_session_sql(uuid_sesion, s_sucursal)

    # Both ingresos_count and salidas_count FILTER predicates MUST
    # reference the open-window lower bound.
    assert "ingresos_count" in sql
    assert "salidas_count" in sql
    assert ":t_open" in sql
    # The upper bound must be the literal TRUE (vacuous for open
    # session) — NOT a NULL parameter check (asyncpg IndeterminateData
    # typeError on the previous `:t_close IS NULL` form).
    assert "TRUE" in sql
    # The previous NULL-guard form is retired.
    assert ":t_close IS NULL" not in sql
    # :t_close placeholder MUST NOT appear at all when t_close is None
    # (defensive — the repo helper omits the bind in this case, but a
    # stray :t_close placeholder would still trigger asyncpg's typing
    # error even if unused).
    assert ":t_close" not in sql
    # The branch scope MUST appear inside the FILTER (not just as a join
    # clause) — defends against a regression that drops the per-branch
    # tenant guard.
    assert "i.uuid_sucursal = :S_s" in sql
    assert "s.uuid_sucursal = :S_s" in sql
    # Anchored on prod.sesion.
    assert "prod.sesion" in sql


def test_closed_session_sql_adds_upper_bound_predicate() -> None:
    """S2 (REQ-OPS-186): closed session -> SQL pins t_close as a real bound."""
    from parkos_core.app.sql.mi_turno_query import build_mi_turno_counts_sql

    uuid_sesion = uuid_lib.UUID("00000000-0000-0000-0000-000000000003")
    s_sucursal = uuid_lib.UUID("00000000-0000-0000-0000-000000000004")
    sql = build_mi_turno_counts_sql(
        uuid_sesion=uuid_sesion,
        s_sucursal=s_sucursal,
        t_open=None,
        t_close="2026-09-21T20:00:00",
    )

    # Closed-session path: the upper bound is now a real timestamp,
    # not the literal TRUE. Both ingresos and salidas carry the predicate.
    assert "i.fecha_ingreso <= :t_close" in sql
    assert "s.fecha_salida <= :t_close" in sql
    # The closed-session SQL DOES reference :t_close (it's a real bound).
    assert ":t_close" in sql


def test_branch_scope_is_interpolated_not_optional() -> None:
    """S3: per-branch scope MUST appear in BOTH filters; tenant-pin invariant."""
    uuid_sesion = uuid_lib.uuid4()
    s_sucursal = uuid_lib.UUID("00000000-0000-0000-0000-000000000005")
    sql = _build_open_session_sql(uuid_sesion, s_sucursal)

    # Two distinct occurrences (ingresos_filter + salidas_filter).
    assert sql.count("i.uuid_sucursal = :S_s") >= 1
    assert sql.count("s.uuid_sucursal = :S_s") >= 1
