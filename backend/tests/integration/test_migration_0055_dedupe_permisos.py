"""Regression tests for the permission-catalogue deduplication (PR3).

Two artifacts are covered:

``0002_seed_permisos_canonicos``
    Repaired in place. Its seed used ``ON CONFLICT (permiso, vigente_desde)
    DO NOTHING``, which cannot ever match because ``vigente_desde`` was
    ``NOW()``. Every re-run appended a fresh OPEN version of all 16 codes.

``0055_dedupe_permisos_catalogo``
    New. Collapses the duplicate OPEN versions already present in the live
    cloud DB by closing the losers and re-pointing the grants that named
    them.

Together they close the loop: 0002 stops creating the corruption, 0055
repairs the corruption that is already in the database.

A NOTE ON WHY THESE ASSERT ON SQL TEXT
--------------------------------------
The behaviour was ALSO verified by executing both ``upgrade()`` functions
against the live cloud and branch databases, and that is what caught the
one bug a text assertion cannot see: routing the tuples through
``FROM (VALUES ...) AS v(...)`` detaches them from the INSERT target list,
so a bare ``NULL`` for the ``uuid`` column ``created_by`` resolves to
``text`` and the INSERT dies with ``DatatypeMismatchError``. The
``::uuid`` / ``::timestamptz`` / ``::int`` casts that fix it are pinned
here by ``test_0002_values_carry_explicit_casts`` so the shape cannot
regress.

A NOTE ON ``NOW()`` AND WHY THE BUG IS SUBTLE
---------------------------------------------
``NOW()`` is TRANSACTION-scoped in PostgreSQL: it returns one fixed
instant for the whole transaction. Inside a single transaction the old
``ON CONFLICT (permiso, vigente_desde)`` therefore *did* match, and the
seed looked idempotent. The duplication only appeared across SEPARATE
transactions -- which is exactly how Alembic runs migrations, one per
transaction. A test that runs the seed twice inside one transaction
passes against the broken code and proves nothing. That is the trap this
module documents rather than walks into.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from unittest.mock import patch


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"
if str(_VERSIONS) not in sys.path:
    sys.path.insert(0, str(_VERSIONS))

_M0002 = "0002_seed_permisos_canonicos"
_M0055 = "0055_dedupe_permisos_catalogo"


def _render(module_name: str, fn_name: str = "upgrade") -> list[str]:
    """Run ``fn_name`` with ``op.execute`` mocked; return the SQL emitted."""
    mod = importlib.import_module(module_name)
    emitted: list[str] = []
    with patch.object(mod.op, "execute", side_effect=lambda sql: emitted.append(sql)):
        getattr(mod, fn_name)()
    return emitted


def _0002_seed_sql() -> str:
    return _render(_M0002)[0]


def _0055_body(sql: str) -> str:
    """Strip the shared CTE prologue, returning only the statement body.

    0055 prepends the same four CTEs to all three statements, and those
    CTEs themselves reference ``ganador`` (that is how ``perdedores`` is
    defined). Asserting on the full text therefore proves nothing about
    what a given statement actually does. The CTEs are indented four
    spaces and the DML eight, so the body starts at the last eight-space
    DML keyword.
    """
    starts = list(re.finditer(r"^ {8}(?:INSERT INTO|UPDATE)\s+prod\.", sql, re.M))
    assert starts, "no top-level DML statement found in 0055 output"
    return sql[starts[-1].start() :]


def _0055_all() -> str:
    return "\n".join(_render(_M0055))


# ---------------------------------------------------------------------------
# 0002 -- the seed must not re-append a version on every run
# ---------------------------------------------------------------------------


def test_0002_no_longer_uses_on_conflict() -> None:
    """The inert ``ON CONFLICT (permiso, vigente_desde)`` must be gone.

    ``permisos_uk01`` is ``(permiso, vigente_desde)`` and the column was
    ``NOW()``, so the conflict target could never match an existing row.
    Measured on the live cloud DB: 15 codes with two OPEN rows, 47 open
    rows for 32 distinct codes.
    """
    sql = _0002_seed_sql()
    assert "ON CONFLICT" not in sql, (
        "0002 must not use ON CONFLICT against prod.permisos: the conflict "
        "target contains vigente_desde = NOW() and can never match, so every "
        "re-run appends another OPEN version of all 16 codes"
    )


def test_0002_seed_is_not_exists_guarded() -> None:
    sql = _0002_seed_sql()
    assert "NOT EXISTS" in sql, "0002 must guard the seed with NOT EXISTS"
    assert re.search(
        r"WHERE\s+q\.permiso\s*=\s*v\.permiso", sql
    ), "the guard must compare the candidate row's own code against the catalogue"


def test_0002_guard_scopes_to_the_open_version_only() -> None:
    """A CLOSED row must not block the re-seed.

    The catalogue is versioned. If the guard matched any historical row,
    a code that was legitimately closed would never be re-seeded again
    and the seed would go permanently inert after one logical deletion.
    """
    sql = _0002_seed_sql()
    assert "q.vigente_hasta IS NULL" in sql, (
        "the NOT EXISTS guard must test for an OPEN row (vigente_hasta IS "
        "NULL); matching closed history would make the seed permanently "
        "inert after a legitimate logical deletion"
    )


def test_0002_values_carry_explicit_casts() -> None:
    """Guard the ``FROM (VALUES ...)`` type-inference trap.

    Routing the tuples through a VALUES relation detaches them from the
    INSERT target list, so Postgres types each column from the literals
    alone. A bare ``NULL`` for ``created_by`` (a ``uuid`` column) then
    resolves to ``text`` and the migration fails at runtime with
    ``DatatypeMismatchError``. Found by executing the migration, not by
    reading it.
    """
    sql = _0002_seed_sql()
    assert "NULL::uuid" in sql, (
        "created_by is a uuid column; inside FROM (VALUES ...) a bare NULL "
        "is inferred as text and the INSERT raises DatatypeMismatchError"
    )
    assert "NULL::timestamptz" in sql, "vigente_hasta needs an explicit cast in the VALUES list"
    assert re.search(r"0::int", sql), "sync_attempts needs an explicit cast in the VALUES list"


def test_0002_still_seeds_every_canonical_code() -> None:
    """The idempotency repair must not shrink the seed."""
    sql = _0002_seed_sql()
    for code in importlib.import_module(_M0002).CANONICAL_PERMISOS:
        assert f"'{code}'" in sql, f"0002 must still seed the canonical code {code}"


# ---------------------------------------------------------------------------
# 0055 -- the repair migration
# ---------------------------------------------------------------------------


def test_0055_chains_off_0054() -> None:
    assert importlib.import_module(_M0055).down_revision == "0054_grant_admin_all_permissions"


def test_0055_exposes_callable_upgrade_and_downgrade() -> None:
    mod = importlib.import_module(_M0055)
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_0055_never_emits_on_conflict() -> None:
    """``permisos_usuario_uk01`` is ``(uuid_usuario, uuid_permiso, vigente_desde)``.

    An ``ON CONFLICT`` on that target is inert for the same reason as on
    ``permisos``, and the re-point INSERT would append a fresh duplicate
    grant on every run.
    """
    assert "ON CONFLICT" not in _0055_all()


def test_0055_emits_no_delete() -> None:
    """No-physical-DELETE canon: duplicates are CLOSED, never removed."""
    assert not re.search(r"\bDELETE\b", _0055_all(), re.IGNORECASE), (
        "0055 must collapse duplicates with vigente_hasta/estado, not DELETE"
    )


def test_0055_survivor_rule_is_oldest_first() -> None:
    """The survivor must be a pure function of unmodified rows.

    "The row that happens to carry a grant" reads intuitively but is
    UNSTABLE: re-pointing grants changes which rows carry grants, so a
    survivor set recomputed mid-migration could shift under the statements
    still using it. ``vigente_desde ASC`` does not move.
    """
    sql = _0055_all()
    assert re.search(r"ORDER BY\s+vigente_desde ASC", sql), (
        "the survivor must be selected by vigente_desde ASC so the set is stable "
        "while the migration mutates grants"
    )


def test_0055_survivor_rule_ignores_grants() -> None:
    """The ranking must not depend on prod.permisos_usuario.

    If it did, statement 1 would change the input of statements 2 and 3.
    """
    cte = _0055_all().split("perdedores AS")[0]
    assert "permisos_usuario" not in cte, (
        "the survivor CTE must be independent of the grant table, otherwise "
        "re-pointing grants mid-migration can shift the survivor set"
    )


def test_0055_repoints_grants_before_closing_them() -> None:
    """Insert the replacement grant first, then close the superseded one.

    The re-point reads grants on the losing rows, so those rows must still
    be open when it runs. Within the migration transaction the transient
    state (an actor holding two open grants for one code) is not visible.
    """
    stmts = _render(_M0055)
    assert len(stmts) == 3, f"expected 3 statements, got {len(stmts)}"
    repoint, close_grants, close_rows = stmts
    assert "INSERT INTO prod.permisos_usuario" in repoint
    assert "UPDATE prod.permisos_usuario" in close_grants
    assert "UPDATE prod.permisos" in close_rows
    assert "vigente_hasta IS NULL" in close_grants, (
        "only OPEN grants may be closed; re-closing history would corrupt it"
    )
    assert "vigente_hasta IS NULL" in close_rows, (
        "only OPEN catalogue rows may be closed"
    )


def test_0055_repoint_is_not_exists_guarded() -> None:
    """The guard also prevents a pointless second grant.

    When the actor already holds an open grant on the survivor, re-pointing
    is unnecessary -- and the UK is inert, so an unguarded INSERT would add
    a duplicate open grant.
    """
    repoint = _render(_M0055)[0]
    assert "NOT EXISTS" in repoint
    assert re.search(r"ya\.uuid_usuario\s*=\s*pu\.uuid_usuario", repoint)
    assert re.search(r"ya\.uuid_permiso\s*=\s*g\.sobreviviente", repoint)
    assert "ya.vigente_hasta IS NULL" in repoint


def test_0055_grant_closure_targets_only_the_losing_rows() -> None:
    close_grants = _0055_body(_render(_M0055)[1])
    assert "perdedores" in close_grants, "grants must be closed via the loser set"
    assert "ganador" not in close_grants, (
        "a grant on the SURVIVOR must never be closed -- that would revoke access"
    )
    assert "sobreviviente" not in close_grants, (
        "the grant-closing statement must not reference the survivor uuid at all"
    )


def test_0055_downgrade_is_a_documented_noop() -> None:
    """The semantic inverse is the bug, so it must not be implemented.

    Re-opening every losing version recreates the state that made
    ``require_permission`` raise HTTP 500. No marker column identifies
    which rows this migration closed, so a scoped reversal is not
    expressible.
    """
    assert _render(_M0055, "downgrade") == []
    doc = importlib.import_module(_M0055).downgrade.__doc__ or ""
    assert "no-op" in doc.lower(), "the no-op downgrade must say so in its docstring"
