"""HU-R02..R07 / T1.4 -- MIGRATION 0053 + 0054 contract tests.

BACKGROUND
----------
``admin@parkos.local`` could authenticate and then received HTTP 403 on
every permission-gated write route. ``require_permission`` authorizes
with::

    PermisosUsuario.uuid_usuario == actor_uuid
    AND PermisosUsuario.vigente_hasta IS NULL
    AND Permisos.permiso == codigo

``auth.py`` resolves the actor with ``Usuarios.vigente_hasta IS NULL``, so
both sides of that join key off the OPEN version. The open admin version
held ZERO grants: seven bootstrap runs created seven ``usuarios`` rows
sharing ``cedula = '1234567890'``, six closed with 7 grants each, and the
open one with none.

The granting defects are systemic and all share one shape -- a UK that
carries ``vigente_desde``:

  * ``usuarios_uk01`` = ``(cedula, vigente_desde)``
  * ``permisos_usuario_uk01`` = ``(uuid_usuario, uuid_permiso, vigente_desde)``

``vigente_desde = NOW()`` is re-evaluated per INSERT, so ``ON CONFLICT``
targeting either one can never fire. The canonical seed
``0002_seed_permisos_canonicos.py`` still carries that pattern, which is
why ``prod.permisos`` holds 47 rows for 32 distinct codes.

MIGRATION 0053 seeds the ``resolver_reclamo`` code -- the only one of the
six admin workflows whose transition had no permission code.
MIGRATION 0054 grants every live code to the open admin and closes the
grants stranded on closed principals.

These are source-level contract tests. The DB layer is exercised in gated
integration tests, not here.
"""
from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path
from unittest.mock import patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

sys.path.insert(
    0,
    str(_BACKEND_ROOT / "packages" / "parkos_core" / "migrations" / "versions"),
)

_M0053 = "0053_seed_resolver_reclamo_permiso"
_M0054 = "0054_grant_admin_all_permissions"


def _render(module_name: str, fn_name: str) -> list[str]:
    """Run ``fn_name`` with ``op.execute`` mocked; return the SQL emitted."""
    mod = importlib.import_module(module_name)
    emitted: list[str] = []
    with patch.object(mod.op, "execute", side_effect=lambda sql: emitted.append(sql)):
        getattr(mod, fn_name)()
    return emitted


# ---------------------------------------------------------------------------
# Metadata + revision chain
# ---------------------------------------------------------------------------


def test_0053_chains_off_0052_and_0054_chains_off_0053() -> None:
    """Both migrations import with the canonical revision chain.

    0053 must chain off the F1.11 head ``0052_reimpresion_ticket_forupdate
    _lock_grant``; 0054 must chain off 0053. A wrong ``down_revision``
    silently detaches the migration from the chain and leaves it unapplied.
    """
    m53 = importlib.import_module(_M0053)
    m54 = importlib.import_module(_M0054)

    assert m53.revision == _M0053, f"unexpected 0053 revision: {m53.revision!r}"
    assert m53.down_revision == "0052_reimpresion_ticket_forupdate_lock_grant", (
        "0053 must chain off the 0052 head; got " f"{m53.down_revision!r}"
    )
    assert m54.revision == _M0054, f"unexpected 0054 revision: {m54.revision!r}"
    assert m54.down_revision == _M0053, (
        f"0054 must chain off 0053; got {m54.down_revision!r}"
    )


def test_both_expose_callable_upgrade_and_downgrade() -> None:
    """Alembic requires both symbols on every revision module."""
    for name in (_M0053, _M0054):
        mod = importlib.import_module(name)
        assert callable(mod.upgrade), f"{name}.upgrade is not callable"
        assert callable(mod.downgrade), f"{name}.downgrade is not callable"


# ---------------------------------------------------------------------------
# The systemic no-ON-CONFLICT guard
# ---------------------------------------------------------------------------


def test_either_migration_never_emits_on_conflict() -> None:
    """Neither migration may use ``ON CONFLICT``.

    Every UK in play carries ``vigente_desde``, which is set to ``NOW()``
    and re-evaluated per INSERT. A conflict target including it is
    unreachable, so ``ON CONFLICT DO NOTHING`` is a silent no-op that
    appends a duplicate version on every run. That is the exact mechanism
    that produced seven admin rows and stranded the grants.
    """
    for name, fn in ((_M0053, "upgrade"), (_M0054, "upgrade"), (_M0054, "downgrade")):
        for sql in _render(name, fn):
            assert "ON CONFLICT" not in sql.upper(), (
                f"{name}.{fn}() emits ON CONFLICT, which cannot fire against a UK "
                "carrying vigente_desde. Use a NOT EXISTS guard on the open version."
            )


def test_0054_grant_is_guarded_by_not_exists() -> None:
    """The 0054 grant INSERT is guarded by ``NOT EXISTS`` on the open grant.

    This is the guard that makes re-running converge instead of append.
    Without it, 0054 would plant the same duplicate-version disease it
    exists to repair.
    """
    grant_sqls = [s for s in _render(_M0054, "upgrade") if "INSERT INTO prod.permisos_usuario" in s]
    assert len(grant_sqls) == 1, f"expected exactly one grant INSERT; got {len(grant_sqls)}"
    assert "NOT EXISTS" in grant_sqls[0], "the grant INSERT must be NOT EXISTS-guarded"


def test_0053_seed_is_guarded_by_not_exists() -> None:
    """The 0053 seed only inserts when no open ``resolver_reclamo`` exists."""
    seed_sqls = [s for s in _render(_M0053, "upgrade") if "INSERT INTO prod.permisos" in s]
    assert len(seed_sqls) == 1, f"expected exactly one seed INSERT; got {len(seed_sqls)}"
    sql = seed_sqls[0]
    assert "'resolver_reclamo'" in sql, "0053 must seed the resolver_reclamo code"
    assert "NOT EXISTS" in sql, "the seed INSERT must be NOT EXISTS-guarded"


# ---------------------------------------------------------------------------
# 0054: grant targeting
# ---------------------------------------------------------------------------


def test_0054_targets_role_not_a_hardcoded_email() -> None:
    """0054 selects admins by ``rol``, never by a literal address.

    A migration ships to prod, staging and CI. A hardcoded
    ``admin@parkos.local`` predicate no-ops silently in any environment
    where the admin has a different address, which is the same class of
    invisible failure this migration exists to fix.
    """
    grant_sql = [s for s in _render(_M0054, "upgrade") if "INSERT INTO prod.permisos_usuario" in s][0]
    assert "rol = 'admin'" in grant_sql, "0054 must select admins via rol = 'admin'"
    assert "@" not in grant_sql, (
        "0054 must not embed a literal email address; that would no-op outside the "
        "dev environment and silently restore the bug being fixed"
    )


def test_0054_grants_one_row_per_distinct_code() -> None:
    """The grant joins ``DISTINCT ON (permiso)``, not a bare catalogue cross join.

    ``prod.permisos`` carries 47 rows for 32 distinct codes (duplicate
    damage from 0002's unreachable ``ON CONFLICT``). A plain join emits one
    grant per physical ROW, handing the admin 47 grants. ``DISTINCT ON``
    with ``ORDER BY permiso, vigente_desde DESC`` also picks the LATEST
    version of each code, which is the correct bi-temporal answer.
    """
    grant_sql = [s for s in _render(_M0054, "upgrade") if "INSERT INTO prod.permisos_usuario" in s][0]
    assert "DISTINCT ON (permiso)" in grant_sql, (
        "0054 must resolve grants via DISTINCT ON (permiso) so duplicate catalogue "
        "rows do not multiply grants"
    )
    assert "vigente_desde DESC" in grant_sql, (
        "DISTINCT ON must be ordered by vigente_desde DESC to select the latest version"
    )


def test_0054_grant_scopes_to_open_user_and_open_permission() -> None:
    """Both the principal and the permission must be the OPEN version."""
    grant_sql = [s for s in _render(_M0054, "upgrade") if "INSERT INTO prod.permisos_usuario" in s][0]
    assert "u.vigente_hasta IS NULL" in grant_sql, "the grant must target the OPEN admin version"
    assert "FROM prod.permisos" in grant_sql, "the grant must resolve against the permission catalogue"
    # The open-version filter on the catalogue lives inside the DISTINCT ON
    # subquery, where the rows are not yet aliased as ``p``.
    assert re.search(
        r"FROM prod\.permisos\s+WHERE vigente_hasta IS NULL",
        grant_sql,
    ), "the grant must resolve only OPEN permission versions"


# ---------------------------------------------------------------------------
# 0054: closing grants stranded on closed principals
# ---------------------------------------------------------------------------


def test_0054_closes_grants_whose_principal_is_closed() -> None:
    """Step 2 closes the 28 grants left on closed admin versions.

    Inert for authorization -- a closed version can never become
    ``actor_uuid`` -- but they inflate any query that joins
    ``permisos_usuario`` to ``usuarios`` without also filtering
    ``usuarios.vigente_hasta IS NULL``. Not hypothetical: while verifying
    this migration a ``count(*)`` reported 60 grants for an admin holding
    32, because it spanned all seven user versions.
    """
    updates = [
        s
        for s in _render(_M0054, "upgrade")
        if s.lstrip().upper().startswith("UPDATE PROD.PERMISOS_USUARIO")
    ]
    assert len(updates) == 1, f"expected exactly one closure UPDATE; got {len(updates)}"
    assert "vigente_hasta IS NOT NULL" in updates[0], (
        "the closure UPDATE must target grants whose principal version is CLOSED"
    )
    assert "SET vigente_hasta = NOW()" in updates[0], "retraction must CLOSE, never DELETE"


# ---------------------------------------------------------------------------
# No-physical-DELETE canon
# ---------------------------------------------------------------------------


def test_neither_migration_emits_a_delete() -> None:
    """AGENTS.md forbids physical DELETE at every layer, migrations included."""
    for name in (_M0053, _M0054):
        for fn in ("upgrade", "downgrade"):
            for sql in _render(name, fn):
                assert "DELETE" not in sql.upper(), (
                    f"{name}.{fn}() emits a physical DELETE, violating the "
                    "no-physical-DELETE canon. Close the version instead."
                )


# ---------------------------------------------------------------------------
# The bootstrap that produced the bug
# ---------------------------------------------------------------------------

_BOOTSTRAP = _BACKEND_ROOT.parents[0] / "infra" / "scripts" / "bootstrap_pairing.py"


def _bootstrap_sql_statements() -> list[str]:
    """Every string literal actually passed to ``cur.execute(...)`` / ``op.execute(...)``.

    Grepping the raw file would match the docstrings, which deliberately
    QUOTE the broken queries to document the bug -- so a naive substring
    check reports the defect in prose while the code is already fixed. This
    walks the AST and returns only SQL that can actually run.
    """
    assert _BOOTSTRAP.is_file(), f"bootstrap script missing: {_BOOTSTRAP}"
    tree = ast.parse(_BOOTSTRAP.read_text(encoding="utf-8"))
    statements: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "execute":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                statements.append(arg.value)
    return statements


def test_bootstrap_never_uses_on_conflict_against_a_versioned_table() -> None:
    """No SQL the bootstrap RUNS may rely on an unreachable conflict target.

    Scoped to executable SQL rather than the file text: the docstrings
    quote ``ON CONFLICT (cedula, vigente_desde)`` verbatim to document why
    it was removed, and a text grep would flag that explanation as a defect.
    """
    for sql in _bootstrap_sql_statements():
        target = next(
            (t for t in ("prod.usuarios", "prod.permisos_usuario") if t in sql),
            None,
        )
        if target is None or "ON CONFLICT" not in sql.upper():
            continue
        assert "ON CONFLICT (uuid)" not in sql.upper(), (
            f"ON CONFLICT against {target} in bootstrap_pairing.py: any UK on these "
            "tables carries vigente_desde, which is re-evaluated per INSERT, so the "
            "conflict target is unreachable and DO NOTHING appends a duplicate version"
        )


def test_bootstrap_resolves_the_open_user_not_an_arbitrary_one() -> None:
    """The admin lookup filters the open version and is deterministically ordered.

    The old ``SELECT uuid FROM prod.usuarios WHERE email = %s LIMIT 1`` had
    no ``ORDER BY`` and no ``vigente_hasta IS NULL``, so grants landed on
    whichever row the planner returned -- six times out of seven, a closed one.
    """
    lookups = [
        sql
        for sql in _bootstrap_sql_statements()
        if "FROM prod.usuarios" in sql and "email" in sql
    ]
    assert lookups, "bootstrap must resolve the admin user by email"
    for sql in lookups:
        assert "vigente_hasta IS NULL" in sql, (
            "the admin lookup must filter for the OPEN version; got " f"{sql.strip()!r}"
        )
        assert "ORDER BY" in sql.upper(), (
            "the admin lookup must be deterministically ordered; got " f"{sql.strip()!r}"
        )


def test_bootstrap_permission_lookup_uses_the_open_version() -> None:
    """The catalogue lookup must not resolve against a closed permission version."""
    lookups = [
        sql
        for sql in _bootstrap_sql_statements()
        if "FROM prod.permisos" in sql and "permiso =" in sql and "NOT EXISTS" not in sql
    ]
    for sql in lookups:
        assert "vigente_hasta IS NULL" in sql, (
            "a permission lookup must filter for the OPEN version; got " f"{sql.strip()!r}"
        )


def test_bootstrap_grant_is_not_exists_guarded() -> None:
    """The bootstrap grant path is NOT EXISTS-guarded like migration 0054."""
    grants = [sql for sql in _bootstrap_sql_statements() if "INSERT INTO prod.permisos_usuario" in sql]
    assert grants, "bootstrap must still grant permissions to the admin"
    for sql in grants:
        assert "NOT EXISTS" in sql, "the bootstrap grant must be NOT EXISTS-guarded"
        assert "DISTINCT ON (permiso)" in sql, (
            "the grant must resolve one row per distinct code, matching migration 0054, "
            "so duplicate catalogue rows do not multiply grants"
        )


def test_bootstrap_no_longer_hardcodes_a_permission_list() -> None:
    """The 7-item ``REQUIRED_PERMISSIONS`` tuple is gone.

    It was a hand-maintained list that silently drifted from the 32-code
    catalogue. The bootstrap now grants every live code, matching
    migration 0054.
    """
    tree = ast.parse(_BOOTSTRAP.read_text(encoding="utf-8"))
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.add(target.id)
    assert "REQUIRED_PERMISSIONS" not in assigned, (
        "the hand-kept REQUIRED_PERMISSIONS tuple drifted from the catalogue; "
        "0054 and the bootstrap now both grant every live code"
    )


def test_bootstrap_does_not_rewind_the_password_needlessly() -> None:
    """A matching password must be a no-op, not a new version.

    Before the fix, every run re-hashed and always INSERTed, so the seven
    duplicate rows accumulated even when nothing had changed. The rewrite
    compares with ``bcrypt.checkpw`` and only rotates on an actual drift,
    closing the current version and inserting a new one rather than
    mutating in place.
    """
    source = _BOOTSTRAP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    checkpw_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "checkpw"
    ]
    assert checkpw_calls, (
        "the bootstrap must compare the stored hash with bcrypt.checkpw so a "
        "matching password is a genuine no-op"
    )
    fn_src = ast.get_source_segment(source, checkpw_calls[0].func) or ""
    assert "checkpw" in fn_src
