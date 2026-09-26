"""Regression tests for cross-node permission identity (PR4).

THE DEFECT THIS PINS
--------------------
``0002_seed_permisos_canonicos`` mints every non-canonical permission with
``gen_random_uuid()`` and runs INDEPENDENTLY on the cloud and on each
branch. ``0019_deterministic_permisos_uuids`` fixed this for exactly SIXTEEN
codes and left the rest random, so those codes hold a different uuid on
every node forever.

Consequence measured live: ``job_sync_sucursal`` rejected 522 consecutive
pull batches with ``ForeignKeyViolationError`` on
``fk_permisos_usuario_uuid_permiso`` - a cloud grant naming a
``uuid_permiso`` the branch had never seen - and the branch consumed
nothing from the cloud for 11 hours behind a container reporting
``healthy``.

``0056_deterministic_permisos_uuids_full`` extends ``0019``'s namespace
to the remaining codes so every node converges on the same value.

WHY THE STATIC ASSERTION ON THE HARD-CODED uuids IS THE POINT
---------------------------------------------------------------
The convergence property rests entirely on those literals being
``uuid5(<namespace>, <code>)``. A typo in a single character produces a
uuid that is still a perfectly valid uuid - it inserts cleanly, the
migration reports success, grants re-point to it, and the FK is satisfied
*locally*. It only breaks again when the OTHER node computes or carries a
different value, which is precisely the failure this whole change exists
to end. Nothing at runtime would ever flag it.

``test_map_values_are_recomputable_as_uuid5`` therefore recomputes every
value from the namespace and the code and requires exact equality. That is
the assertion that would have caught a mistyped map before it shipped.

WHY THE SQL ASSERTIONS DRIVE A FAKE BIND INSTEAD OF READING THE FILE
--------------------------------------------------------------------
0056 issues its DML through ``bind.execute(text(...), params)`` and only
uses ``op.execute`` for the lock timeout, so the migration is exercised
here through a scripted bind. Asserting on text() source instead would
also match a DOCSTRING that merely discusses ``uuid_permiso =`` or
``DELETE`` - which is exactly the false positive this file was rewritten
to eliminate.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"
if str(_VERSIONS) not in sys.path:
    sys.path.insert(0, str(_VERSIONS))

_M0019 = "0019_deterministic_permisos_uuids"
_M0056 = "0056_deterministic_permisos_uuids_full"

# Shared on purpose: 0019's sixteen codes and 0056's additions must form
# ONE scheme, or a code migrated by one and not the other never converges.
_NAMESPACE = uuid.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60")

# A stand-in for "some other node's random uuid", i.e. the diverged state.
_STALE = "11111111-1111-1111-1111-111111111111"


def _load(module_name: str):
    path = _VERSIONS / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _maps() -> tuple[dict[str, str], dict[str, str]]:
    return (
        dict(_load(_M0019)._DETERMINISTIC_UUIDS),
        dict(_load(_M0056)._DETERMINISTIC_UUIDS),
    )


# ---------------------------------------------------------------------------
# The uuid literals
# ---------------------------------------------------------------------------


def test_map_values_are_recomputable_as_uuid5() -> None:
    """Every hard-coded uuid must equal uuid5(namespace, code) exactly.

    The single most valuable assertion in this module: a mistyped uuid is
    otherwise undetectable, well-formed, and only re-breaks at the moment a
    second node disagrees.
    """
    m0019, m0056 = _maps()
    for label, mapping in (("0019", m0019), ("0056", m0056)):
        for code, value in mapping.items():
            assert value == str(uuid.uuid5(_NAMESPACE, code)), (
                f"{label}: uuid for {code!r} is not uuid5(namespace, code). "
                f"got {value}, expected {uuid.uuid5(_NAMESPACE, code)}. A wrong "
                "value here still inserts cleanly and only fails cross-node."
            )


def test_0056_does_not_restate_0019_codes() -> None:
    """A uuid in both maps is a drift hazard; each map owns its codes."""
    m0019, m0056 = _maps()
    overlap = set(m0019) & set(m0056)
    assert not overlap, (
        f"codes owned by both 0019 and 0056: {sorted(overlap)} - the two maps "
        "can drift apart silently if a value is ever corrected in one place"
    )


def test_0056_covers_the_fifteen_codes_measured_as_divergent() -> None:
    """Pins the exact set measured divergent between the live nodes.

    Not a tautology: these fifteen were the codes whose cloud uuid differed
    from the branch uuid on 2026-09-26.
    """
    _m0019, m0056 = _maps()
    measured = {
        "abrir_cerrar_caja",
        "administrar_clientes",
        "administrar_subscripciones",
        "administrar_tarifas",
        "administrar_vehiculos",
        "anular_ingreso",
        "anular_reimpresion",
        "anular_salida",
        "configurar_sucursal",
        "login",
        "realizar_arqueo",
        "realizar_ingreso",
        "realizar_salida",
        "reimprimir_ticket",
        "ver_reportes",
    }
    assert measured <= set(m0056), f"0056 no longer covers: {sorted(measured - set(m0056))}"


# ---------------------------------------------------------------------------
# A scripted database for the migration to run against
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list:
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeBind:
    """Captures the SQL 0056 runs, against a scripted database state.

    ``converged=True`` models a node whose open row for every code is
    ALREADY deterministic - the state a second ``upgrade()`` must no-op on.
    ``converged=False`` models the live diverged state, where the open row
    carries some other node's random uuid.
    """

    def __init__(self, converged: bool) -> None:
        self.converged = converged
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, clause, params=None) -> _FakeResult:
        self.statements.append(str(clause))
        self.params.append(params or {})
        if "SELECT uuid FROM prod.permisos" in str(clause):
            code = (params or {})["codigo"]
            if self.converged:
                return _FakeResult([_maps()[1][code]])
            return _FakeResult([_STALE])
        return _FakeResult([])


def _run(converged: bool) -> _FakeBind:
    mod = _load(_M0056)
    bind = _FakeBind(converged)
    with (
        patch.object(mod.op, "execute"),
        patch.object(mod.op, "get_bind", return_value=bind),
    ):
        mod.upgrade()
    return bind


# ---------------------------------------------------------------------------
# Behaviour of the migration itself
# ---------------------------------------------------------------------------


def test_0056_is_a_no_op_on_an_already_converged_node() -> None:
    """Idempotence, proven by execution rather than by reading the source.

    Without the already-converged skip, every boot would re-close and
    re-insert all sixteen codes' grants and grow the tables unboundedly.
    """
    bind = _run(converged=True)
    dml = [s for s in bind.statements if re.search(r"\b(INSERT|UPDATE|DELETE)\b", s)]
    assert dml == [], f"0056 re-applied convergence to a converged node: {dml}"


def test_0056_converges_a_diverged_node_for_every_mapped_code() -> None:
    """Each mapped code gets its deterministic row AND a grant re-point."""
    bind = _run(converged=False)
    _m0019, m0056 = _maps()
    inserts = [
        (sql, params)
        for sql, params in zip(bind.statements, bind.params)
        if "INSERT INTO prod.permisos" in sql and "permisos_usuario" not in sql
    ]
    assert len(inserts) == len(m0056), (
        f"expected a deterministic INSERT for each of {len(m0056)} codes, "
        f"got {len(inserts)}"
    )
    for _sql, params in inserts:
        assert params["det_uuid"] == m0056[params["codigo"]]
    # The re-point step must carry the stale uuid it is superseding.
    repoints = [
        params
        for sql, params in zip(bind.statements, bind.params)
        if "INSERT INTO prod.permisos_usuario" in sql
    ]
    assert repoints
    assert all(params["stale"] == [_STALE] for params in repoints)


def test_0056_never_mutates_the_grant_foreign_key_in_place() -> None:
    """Grants are re-pointed by close+insert, never by rewriting the FK.

    ``0019`` re-points with ``UPDATE permisos_usuario SET uuid_permiso``,
    overwriting valid-time history on a ``[V]`` row. This project forbids
    that shape, so it is pinned against regressing back to it.
    """
    set_clauses = [
        body
        for sql in _run(converged=False).statements
        for body in re.findall(
            r"UPDATE\s+prod\.permisos_usuario\s+SET(.*?)(?:WHERE|$)", sql, re.S | re.I
        )
    ]
    assert set_clauses, "expected 0056 to close superseded grants via UPDATE"
    for body in set_clauses:
        assert "vigente_hasta" in body
        assert "uuid_permiso" not in body, (
            "0056 rewrites uuid_permiso in place - grants must be closed and "
            "superseded, never mutated"
        )


def test_0056_inserts_replacements_before_closing_the_old_grants() -> None:
    """Order matters: closing first would strip access mid-migration.

    The replacement INSERT must precede the closing UPDATE, and must be
    guarded by NOT EXISTS so an actor cannot end up holding two open grants
    for the same code.
    """
    statements = _run(converged=False).statements
    close_index = next(
        (i for i, s in enumerate(statements) if "UPDATE prod.permisos_usuario" in s),
        None,
    )
    assert close_index is not None, "no grant-closing UPDATE was emitted"
    assert any("INSERT INTO prod.permisos_usuario" in s for s in statements[:close_index]), (
        "grants are closed before their replacements are inserted"
    )
    replacements = [s for s in statements if "INSERT INTO prod.permisos_usuario" in s]
    assert replacements
    assert all("NOT EXISTS" in s for s in replacements)


def test_0056_performs_no_physical_delete() -> None:
    """The no-physical-DELETE canon, asserted against executed SQL."""
    for sql in _run(converged=False).statements:
        assert not re.search(r"\bDELETE\b", sql, re.I), f"0056 executes DELETE: {sql[:120]!r}"


def test_0056_downgrade_is_a_documented_no_op() -> None:
    """A downgrade cannot restore uuids that were never recorded."""
    assert _load(_M0056).downgrade() is None


# ---------------------------------------------------------------------------
# Cross-node convergence, against a real database when one is reachable
# ---------------------------------------------------------------------------


def test_every_live_code_has_a_deterministic_uuid() -> None:
    """THE cross-node test: no live code may sit outside both maps.

    This is the assertion whose absence let the defect run for 11 hours.
    Reads the live catalogue rather than a fixture, so a NEW code added by
    any future seed is caught the moment it exists.
    """
    engine = _try_engine()
    if engine is None:
        import pytest

        pytest.skip("no test database available")

    deterministic = set(_maps()[0]) | set(_maps()[1])

    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT permiso, uuid FROM prod.permisos WHERE vigente_hasta IS NULL")
        ).all()

    unmapped = sorted({permiso for permiso, _u in rows} - deterministic)
    assert not unmapped, (
        f"live permission codes with no deterministic uuid: {unmapped}. Each of "
        "these mints a random uuid per node and will diverge cross-node again."
    )
    wrong = sorted(
        (permiso, str(value))
        for permiso, value in rows
        if permiso in deterministic
        and str(value) != str(uuid.uuid5(_NAMESPACE, permiso))
    )
    assert not wrong, f"live rows not on their deterministic uuid: {wrong}"


def _try_engine():
    """Best-effort engine; ``None`` when no database is reachable."""
    import os

    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        from sqlalchemy import create_engine

        return create_engine(url.replace("+asyncpg", "").replace("+psycopg", ""))
    except Exception:
        return None
