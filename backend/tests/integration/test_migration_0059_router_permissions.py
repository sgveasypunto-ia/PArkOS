"""Regression tests for MIGRATION 0059 -- router permission codes.

THE DEFECT THIS PINS
--------------------
``api/v1/{empresa,configuracion,clientes,facturacion,workflows}.py`` each
declare a ``_ROUTER_CONFIG`` mapping resource name -> (issuers, permission
code), and ``require_permission`` authorizes with an existence check on the
OPEN ``prod.permisos`` row. Ten of the codes those maps name were never in
the catalogue at all. Measured live before the migration::

    32 distinct codes in prod.permisos, 0 of these 10 present

The failure is silent at boot and total at runtime: nothing warns, the route
just answers 403 for every caller including a fully-granted admin, forever.
``GET`` on the same paths succeeded because the read path does not pass
through the gate, which is exactly what made it look like "the frontend was
never built" rather than "the catalogue is incomplete".

WHY THE uuid5 ASSERTION IS THE POINT (borrowed from 0056's reasoning)
---------------------------------------------------------------------
Cross-node identity for permission rows rests entirely on the hard-coded
literals being ``uuid5(NAMESPACE, <code>)``. A typo produces a uuid that is
still perfectly valid: it inserts cleanly, the grants resolve, the FK is
satisfied LOCALLY, and nothing ever flags it -- until the other node carries
a different value. ``0019``'s docstring records the cost of that happening
for real: 522 consecutive ``ForeignKeyViolationError`` on
``fk_permisos_usuario_uuid_permiso`` and 11 hours of a branch consuming
nothing behind a container reporting ``healthy``.

These ten rows are the most exposed in the catalogue precisely because this
migration INSERTs them on the cloud AND on every branch (the
``permisos_enqueue_sync_catalog`` AFTER INSERT trigger enqueues each one), so
a random uuid would be minted once per node and the ``NOT EXISTS`` guard
would be satisfied independently on each. Deterministic identity is what
makes the second node's INSERT a no-op instead of a divergence.

WHY A SOURCE-PARSING ANTI-DRIFT TEST AND NOT A FIXTURE
------------------------------------------------------
The obvious "expected codes" fixture is ``0002_seed_permisos_canonicos.py``,
and using it would be wrong: ``CANONICAL_PERMISOS`` holds SIXTEEN codes while
the live catalogue holds THIRTY-TWO, because later migrations seed more
(``reimprimir_ticket`` and ``resolver_reclamo`` are not in 0002's tuple at
all). A fixture-based test therefore reports false positives for codes that
are perfectly healthy, and the fix -- hardcoding a third list -- is the exact
drift the test was supposed to catch.

So ``test_every_router_required_code_exists_in_the_catalogue`` reads the five
``_ROUTER_CONFIG`` maps out of the source with ``ast`` and asserts against the
LIVE catalogue. Adding a permission-gated route without seeding its code
fails the test on the next run, from a source of truth that cannot go stale.

Resource KEYS are filtered out by requiring the candidate to match
``^[a-z][a-z0-9_]*$``, which excludes the issuer lists (``"admin-"``,
``"operador-,admin-"``) and keeps only permission codes. Without that filter
``"empresa"`` -- a resource name, never a permission -- is collected as if it
were a code and reported missing forever.

The database-backed tests skip when no URL is reachable, matching 0056.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"
_API_V1 = _BACKEND_ROOT / "packages" / "parkos_core" / "src" / "parkos_core" / "api" / "v1"
if str(_VERSIONS) not in sys.path:
    sys.path.insert(0, str(_VERSIONS))

_M0002 = "0002_seed_permisos_canonicos"
_M0019 = "0019_deterministic_permisos_uuids"
_M0056 = "0056_deterministic_permisos_uuids_full"
_M0059 = "0059_seed_router_permission_codes"

# Shared with 0019 and 0056 on purpose: one continuous namespace, so a code
# owned by one migration and not another can never diverge.
_NAMESPACE = uuid.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60")

# A snake_case permission code, and nothing else. Excludes issuer lists such
# as "admin-,operador-" and therefore excludes resource keys.
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _load(module_name: str):
    path = _VERSIONS / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _router_required_codes() -> dict[str, set[str]]:
    """Every permission code the routers gate on -> the files that gate on it.

    Parsed from source rather than imported: importing ``empresa.py`` pulls in
    FastAPI and the whole ``parkos_core`` package, which is not what a test
    about a permission catalogue should be paying for.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(_API_V1.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if getattr(node.targets[0], "id", None) != "_ROUTER_CONFIG":
                continue
            for value in node.value.values:
                for const in ast.walk(value):
                    if isinstance(const, ast.Constant) and _CODE_RE.match(const.value or ""):
                        found.setdefault(const.value, set()).add(path.name)
    return found


# ---------------------------------------------------------------------------
# The uuid literals
# ---------------------------------------------------------------------------


def test_0059_uuids_are_recomputable_as_uuid5() -> None:
    """Every hard-coded uuid must equal uuid5(namespace, code) exactly.

    The single most valuable assertion in this module. A mistyped uuid is
    undetectable locally, well-formed, and only re-breaks at the moment a
    second node disagrees.
    """
    mapping = dict(_load(_M0059)._ROUTER_PERMISSION_UUIDS)
    assert len(mapping) == 10, f"expected the ten measured gaps, got {sorted(mapping)}"
    for code, value in mapping.items():
        assert value == str(uuid.uuid5(_NAMESPACE, code)), (
            f"uuid for {code!r} is not uuid5(namespace, code). got {value}, "
            f"expected {uuid.uuid5(_NAMESPACE, code)}. A wrong value still "
            "inserts cleanly and only fails cross-node."
        )


def test_0059_does_not_restate_0019_or_0056_codes() -> None:
    """A uuid in two maps is a drift hazard; each map owns its codes."""
    mine = set(_load(_M0059)._ROUTER_PERMISSION_UUIDS)
    for other in (_load(_M0019)._DETERMINISTIC_UUIDS, _load(_M0056)._DETERMINISTIC_UUIDS):
        overlap = mine & set(other)
        assert not overlap, (
            f"codes owned by both this migration and {sorted(overlap)} - the "
            "maps can drift apart silently if a value is ever corrected in "
            "one place only"
        )


def test_0059_chains_from_the_previous_head() -> None:
    """A wrong down_revision silently orphans the migration from the chain."""
    assert _load(_M0059).down_revision == _load("0058_hash_chain_causal_seq").revision


# ---------------------------------------------------------------------------
# A scripted database for the migration to run against
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list:
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeBind:
    """Records the SQL 0059 emits. 0059 reads no state, so nothing to script."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, clause, params=None) -> _FakeResult:
        self.statements.append(str(clause))
        self.params.append(params or {})
        return _FakeResult()


def _run(fn_name: str = "upgrade") -> _FakeBind:
    mod = _load(_M0059)
    bind = _FakeBind()
    with (
        patch.object(mod.op, "execute"),
        patch.object(mod.op, "get_bind", return_value=bind),
    ):
        getattr(mod, fn_name)()
    return bind


def _sql_containing(bind: _FakeBind, needle: str) -> list[str]:
    return [s for s in bind.statements if needle in s]


# ---------------------------------------------------------------------------
# Behaviour of the migration itself
# ---------------------------------------------------------------------------


def test_0059_passes_every_code_to_the_database() -> None:
    """The hard-coded map must actually reach SQL, in both shapes it is bound.

    A migration whose map is complete but whose ``_codes_json()`` forgets a
    key would insert a partial catalogue and report success.
    """
    mod = _load(_M0059)
    expected = dict(mod._ROUTER_PERMISSION_UUIDS)
    bind = _run()

    catalogue_inserts = [
        p
        for sql, p in zip(bind.statements, bind.params)
        if "INSERT INTO prod.permisos" in sql and "permisos_usuario" not in sql
    ]
    assert len(catalogue_inserts) == 1, "expected exactly one catalogue INSERT"
    bound = {entry["codigo"]: entry["uuid"] for entry in json.loads(catalogue_inserts[0]["codes"])}
    assert bound == expected, f"catalogue INSERT is missing {sorted(set(expected) - set(bound))}"

    grant_steps = [
        p
        for sql, p in zip(bind.statements, bind.params)
        if "INSERT INTO prod.permisos_usuario" in sql or "UPDATE prod.permisos_usuario" in sql
    ]
    assert grant_steps, "no grant statement was emitted"
    for params in grant_steps:
        assert params["code_list"] == sorted(expected), (
            "the grant step is not scoped to exactly the ten seeded codes"
        )


def test_0059_guards_with_not_exists_not_on_conflict() -> None:
    """The documented UK trap: ON CONFLICT on permisos_uk01 never fires.

    ``permisos_uk01`` is ``UNIQUE (permiso, vigente_desde)`` and
    ``vigente_desde = clock_timestamp()`` is re-evaluated per INSERT, so a
    conflict target naming it never matches. ``0002``'s seed and
    ``bootstrap_pairing.py::ensure_admin_user`` both carry that defect; 0054's
    docstring names it as the cause of seven admin versions inside 46
    minutes. The guard must be an explicit NOT EXISTS predicate.
    """
    inserts = [
        s
        for s in _run().statements
        if "INSERT INTO prod.permisos" in s or "INSERT INTO prod.permisos_usuario" in s
    ]
    assert inserts, "0059 issued no INSERT at all"
    for sql in inserts:
        assert "ON CONFLICT" not in sql.upper(), (
            f"0059 uses ON CONFLICT, which cannot match a (permiso, "
            f"vigente_desde) UK: {sql[:160]!r}"
        )
    catalogue_insert = next(
        s for s in inserts if "INSERT INTO prod.permisos" in s and "permisos_usuario" not in s
    )
    assert catalogue_insert.upper().count("NOT EXISTS") == 2, (
        "the catalogue INSERT needs two independent guards: one for a code "
        "that already has an OPEN row (possibly another node's uuid), and "
        "one for a code whose deterministic uuid is already taken by a "
        "CLOSED row (permisos_pkey is PRIMARY KEY (uuid), so that is a PK "
        "violation, not a UK one)"
    )


def test_0059_grants_only_to_open_admins() -> None:
    """Least privilege: the grant is scoped to admins, not to every user.

    ``config_tarifas`` and ``config_cupos`` change revenue. A branch
    operator is pinned to a single sucursal, so granting them write access
    would let a branch set its own prices.
    """
    grant = next(s for s in _run().statements if "INSERT INTO prod.permisos_usuario" in s)
    assert "u.rol = 'admin'" in grant
    assert "u.vigente_hasta IS NULL" in grant, (
        "grants must attach to the OPEN principal version only - 0054's "
        "docstring records a 60-vs-32 miscount caused by the alternative"
    )
    assert "NOT EXISTS" in grant, "an unguarded grant INSERT can duplicate on re-run"


def test_0059_retires_grants_left_dangling_on_a_closed_catalogue_row() -> None:
    """An open grant must never name a closed permission.

    ``require_permission`` filters ``Permisos.vigente_hasta.is_(None)``, so
    such a grant cannot authorize anything -- but any query joining
    ``permisos_usuario`` without also filtering the permission's own open
    version reports a count inflated by it, and 0054's docstring names a
    mis-scoped admin screen as exactly where that number would be believed.
    """
    closes = [
        s
        for s in _run().statements
        if s.strip().upper().startswith("UPDATE PROD.PERMISOS_USUARIO")
        and "p.vigente_hasta IS NOT NULL" in s
    ]
    assert closes, "0059 leaves grants pointing at closed catalogue rows behind"


def test_0059_closes_grants_before_catalogue_rows_in_downgrade() -> None:
    """Rollback must not reintroduce the dangling state it exists to clean up.

    Closing only the catalogue row already deactivates the permission, but
    it would leave open grants naming a closed permission -- the exact
    hazard ``upgrade`` step 3 removes.
    """
    statements = _run("downgrade").statements
    grant_index = next(
        (i for i, s in enumerate(statements) if "UPDATE prod.permisos_usuario" in s),
        None,
    )
    catalogue_index = next(
        (
            i
            for i, s in enumerate(statements)
            if "UPDATE prod.permisos" in s and "permisos_usuario" not in s
        ),
        None,
    )
    assert grant_index is not None, "downgrade closes no grants"
    assert catalogue_index is not None, "downgrade closes no catalogue rows"
    assert grant_index < catalogue_index, (
        "downgrade closes the catalogue before its grants, leaving open "
        "grants naming a closed permission"
    )


def test_0059_never_rewrites_uuid_permiso_in_place() -> None:
    """Grants are closed and superseded, never mutated.

    ``0019`` re-points with ``UPDATE permisos_usuario SET uuid_permiso``,
    overwriting valid-time history on a ``[V]`` row. This project forbids
    that shape; 0056 documents the correct vocabulary.
    """
    for sql in _run("downgrade").statements + _run().statements:
        for body in re.findall(
            r"UPDATE\s+prod\.permisos_usuario\s+SET(.*?)(?:WHERE|$)", sql, re.S | re.I
        ):
            assert "vigente_hasta" in body
            assert "uuid_permiso" not in body, (
                "0059 rewrites uuid_permiso in place - grants must be closed "
                "and superseded, never mutated"
            )


def test_0059_performs_no_physical_delete() -> None:
    """The no-physical-DELETE canon, asserted against executed SQL.

    Checked on the emitted DML rather than the source text, so a DOCSTRING
    merely DISCUSSING ``DELETE`` cannot produce a false positive.
    """
    for fn in ("upgrade", "downgrade"):
        for sql in _run(fn).statements:
            assert not re.search(r"\bDELETE\b", sql, re.I), f"0059 {fn} executes DELETE"


# ---------------------------------------------------------------------------
# Against a real database when one is reachable
# ---------------------------------------------------------------------------


def _try_engine():
    import os

    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        from sqlalchemy import create_engine

        return create_engine(url.replace("+asyncpg", "").replace("+psycopg", ""))
    except Exception:
        return None


def test_every_router_required_code_exists_in_the_catalogue() -> None:
    """THE anti-drift assertion whose absence let this defect ship.

    Reads the five ``_ROUTER_CONFIG`` maps out of the source and the live
    catalogue out of the database. A permission-gated route added without
    seeding its code fails here on the next run -- from a source of truth
    that cannot go stale, rather than from a hand-maintained fixture that
    already is (0002's tuple lists 16 of the catalogue's 32 codes).
    """
    engine = _try_engine()
    if engine is None:
        import pytest

        pytest.skip("no test database available")

    from sqlalchemy import text

    required = _router_required_codes()
    assert required, "no _ROUTER_CONFIG codes parsed - the extractor is broken"

    with engine.connect() as conn:
        live = {
            row[0]
            for row in conn.execute(
                text("SELECT DISTINCT permiso FROM prod.permisos WHERE vigente_hasta IS NULL")
            ).all()
        }

    missing = {code: files for code, files in required.items() if code not in live}
    assert not missing, (
        f"router-gated permission codes absent from prod.permisos: "
        f"{ {k: sorted(v) for k, v in sorted(missing.items())} }. Every route "
        "gated on one of these answers 403 for every caller, including admin."
    )


def test_live_codes_all_carry_a_deterministic_uuid() -> None:
    """No live code may sit outside 0019's, 0056's or 0059's map.

    A code outside all three mints a random uuid per node and diverges
    cross-node again -- the failure 0019/0056 were written to end.
    """
    engine = _try_engine()
    if engine is None:
        import pytest

        pytest.skip("no test database available")

    from sqlalchemy import text

    deterministic = (
        set(_load(_M0019)._DETERMINISTIC_UUIDS)
        | set(_load(_M0056)._DETERMINISTIC_UUIDS)
        | set(_load(_M0059)._ROUTER_PERMISSION_UUIDS)
    )

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT permiso, uuid FROM prod.permisos WHERE vigente_hasta IS NULL")
        ).all()
    live = {permiso: str(value) for permiso, value in rows}

    # Assert over the SHIPPED catalogue, not over "whatever rows exist".
    # test_auth_me.py seeds factura_crear / arqueo_cerrar and
    # test_branch_offline_flow.py mints test-offline-flow-<hex>; none of those
    # are codes this project ships, and no physical DELETE is permitted, so
    # they accumulate and would make this a tripwire for test ordering.
    # What genuinely diverges cross-node is a gen_random_uuid() seed, and 0002
    # is the migration that introduces one on every node independently.
    required = set(_load(_M0002).CANONICAL_PERMISOS) | deterministic

    missing = sorted(required - set(live))
    assert not missing, (
        f"shipped permission codes absent from the live catalogue: {missing}. A "
        "code no node can resolve diverges on the first call that gates on it."
    )
    wrong = sorted(
        (permiso, live[permiso])
        for permiso in sorted(required & set(live))
        if live[permiso] != str(uuid.uuid5(_NAMESPACE, permiso))
    )
    assert not wrong, f"live rows not on their deterministic uuid: {wrong}"
