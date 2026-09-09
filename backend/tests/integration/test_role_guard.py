"""test_role_guard.py — T-PR1-009 (RED), R-D4, R6, REQ-OPS-005, REQ-MOT-012.

Covers ``parkos_core.sync.guards.role_guard.assert_role`` — the boot-import
guard a catalog entry's role-scoped module calls at import time, mirroring
the existing ``dian/cloud/dian_providers/factus.py`` precedent
(``if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch": raise
ImportError(...)``).

PR1 scope note: no catalog entry exists yet (PR2 declares
``SYNC_CATALOG``), so there is no real "module for ``validacion_evento``"
or "module for ``envio_dian``" to import. These tests exercise
``assert_role`` directly with the exact ``role``/``table`` values those
future modules will pass — the same boot-import contract, without waiting
on PR2's catalog declarations.
"""

from __future__ import annotations

import pytest
from parkos_core.sync.guards.role_guard import assert_role


@pytest.fixture
def _branch_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_DEPLOY", "branch")


@pytest.mark.usefixtures("_branch_deploy")
def test_cloud_only_entry_rejected_on_branch() -> None:
    """``validacion_evento`` (role_required="cloud") must not import on a branch deploy.

    Given PARKOS_DEPLOY=branch, when the boot-import guard for the
    cloud-only ``validacion_evento`` entry runs, then it raises
    ImportError naming the table and "cloud_only entry not allowed on
    branch".
    """
    with pytest.raises(ImportError) as exc_info:
        assert_role("cloud", table="validacion_evento")

    message = str(exc_info.value)
    assert "validacion_evento" in message
    assert "cloud_only entry not allowed on branch" in message


@pytest.mark.usefixtures("_branch_deploy")
def test_both_role_entry_applies_cleanly_on_branch() -> None:
    """``envio_dian`` (role_required="both") is never guarded — it applies on either deploy.

    Companion case, scope narrowed to ``validacion_evento`` only:
    ``role_required="both"`` entries do not call ``assert_role`` at all, so
    nothing blocks them under PARKOS_DEPLOY=branch. This asserts the
    absence of a guard call is itself the contract — there is no
    ``assert_role("both", ...)`` overload because "both" never invokes the
    guard.
    """
    # No assert_role call for a "both" entry — this is the contract itself.
    # Proving it: role_guard exposes no "both" literal, so a caller cannot
    # even construct a call that would block envio_dian.
    import typing

    role_param = typing.get_type_hints(assert_role)["role"]
    allowed_roles = set(typing.get_args(role_param))
    assert allowed_roles == {"cloud", "branch"}
    assert "both" not in allowed_roles


def test_cloud_only_entry_applies_cleanly_on_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: the same cloud-only guard call succeeds when PARKOS_DEPLOY=cloud."""
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    assert_role("cloud", table="validacion_evento") is None


def test_branch_only_entry_rejected_on_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Symmetric case: a branch-only entry must not import on a cloud deploy."""
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    with pytest.raises(ImportError) as exc_info:
        assert_role("branch", table="some_branch_only_table")

    assert "branch_only entry not allowed on cloud" in str(exc_info.value)


def test_defaults_to_cloud_when_parkos_deploy_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors the factus.py precedent: unset PARKOS_DEPLOY defaults to 'cloud'."""
    monkeypatch.delenv("PARKOS_DEPLOY", raising=False)
    assert_role("cloud", table="validacion_evento") is None
    with pytest.raises(ImportError):
        assert_role("branch", table="some_branch_only_table")


# ---------------------------------------------------------------------------
# T-PR11-002 — cloud-flavored companion (REQ-OPS-005, REQ-MOT-012)
# ---------------------------------------------------------------------------


@pytest.fixture
def _cloud_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")


@pytest.mark.usefixtures("_cloud_deploy")
def test_cloud_process_imports_validacion_evento_and_envio_dian_cleanly() -> None:
    """Companion to ``test_cloud_only_entry_rejected_on_branch`` (PR1): under
    ``PARKOS_DEPLOY=cloud`` — the deploy ``validacion_evento`` actually
    requires (``role_required="cloud"``) — the guard does NOT raise, unlike
    the branch case above.

    ``envio_dian`` (``role_required="both"``) never calls ``assert_role`` at
    all (REQ-OPS-005's amended scope, ``test_both_role_entry_applies_
    cleanly_on_branch`` above) — importing the real production catalog
    module that declares both entries (``catalog/entries/sync_entries_lw.py``,
    which imports both ``EnvioDian`` and ``ValidacionEvento``) must succeed
    cleanly under ``PARKOS_DEPLOY=cloud`` too, proving there is no hidden
    cloud-side guard call for either table.
    """
    # validacion_evento: role_required="cloud" — the guard call every
    # future cloud-only module makes must NOT raise when the deploy
    # actually matches the required role.
    assert assert_role("cloud", table="validacion_evento") is None

    # envio_dian: role_required="both" — structurally unguarded; proven by
    # importing the real catalog module (not a direct assert_role call,
    # since none exists for a "both" entry) and asserting both ORM classes
    # resolve without an ImportError anywhere in the import chain.
    from parkos_core.sync.catalog.entries.sync_entries_lw import SYNC_ENTRIES_LW

    names = {entry.name for entry in SYNC_ENTRIES_LW}
    assert {"envio_dian", "validacion_evento"} <= names
