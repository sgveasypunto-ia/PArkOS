"""test_grafana_alerts.py — T-PR13-004, T-PR13-005.

Validates ``infra/grafana/alerts/sync.yaml`` against the shape of Grafana's
real alert-rule file-provisioning schema (``apiVersion: 1``, ``groups`` ->
``rules``, each rule carrying ``uid``/``title``/``condition``/``data``/
``noDataState``/``execErrState``/``for``/``annotations``/``labels``, each
``data`` entry carrying ``refId``/``datasourceUid``/``model`` — see
https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/),
that every referenced ``tipo_alerta`` is one of the 8 identifiers seeded by
migration ``0013_add_alert_types.py`` (T-PR8-002), that no rule mentions
the third-party DIAN provider by name (REQ-OPS-016 / addendum #5), and that
every ``runbook_url`` resolves to one of the 8 stub files T-PR13-005 ships.
"""
from __future__ import annotations

from pathlib import Path

import yaml

# tests/unit/test_grafana_alerts.py -> tests/unit -> tests -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
SYNC_YAML_PATH = REPO_ROOT / "infra" / "grafana" / "alerts" / "sync.yaml"
RUNBOOKS_DIR = REPO_ROOT / "docs" / "runbooks" / "sync"

_EXPECTED_RULE_TITLES = frozenset(
    {
        "SyncBacklogHigh",
        "SyncConflictRateHigh",
        "HashChainBreak",
        "OrphanWorkflowChain",
        "BranchImportError",
        "CatalogBackfillIncomplete",
        "FEProviderError",
        "FENumberingExhausted",
    }
)

_EXPECTED_RUNBOOK_FILENAMES = frozenset(
    {
        "sync_backlog.md",
        "conflict_rate.md",
        "chain_break.md",
        "orphan_workflow.md",
        "import_error.md",
        "dependency_wait.md",
        "backfill_stalled.md",
        "client_volume.md",
    }
)

# The 8 canonical identifiers seeded by migration 0013_add_alert_types.py
# (T-PR8-002). Mirrored here rather than imported: Alembic migration
# filenames start with a digit and are not importable as a plain module.
_SEEDED_ALERT_TYPES = frozenset(
    {
        "hash_chain_anomaly",
        "dian_rechazada",
        "dian_timeout",
        "dian_error",
        "branch_offline_reauth_required",
        "orphan_workflow_chain",
        "fe_provider_error",
        "fe_numbering_exhausted",
    }
)

# REQ-OPS-016 / addendum #5 — the actual third-party DIAN provider adapter
# module is parkos_core/dian/cloud/dian_providers/factus.py. No artifact
# this change touches may name it.
_BANNED_VENDOR_NAME_FRAGMENTS = ("factus",)


def _load_yaml() -> dict:
    assert SYNC_YAML_PATH.exists(), f"missing {SYNC_YAML_PATH}"
    with SYNC_YAML_PATH.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict)
    return doc


def _all_rules(doc: dict) -> list[dict]:
    return [rule for group in doc["groups"] for rule in group["rules"]]


def test_yaml_parses_and_has_api_version_1() -> None:
    doc = _load_yaml()
    assert doc["apiVersion"] == 1
    assert isinstance(doc["groups"], list)
    assert doc["groups"]


def test_group_shape_matches_grafana_provisioning_schema() -> None:
    doc = _load_yaml()
    for group in doc["groups"]:
        for required in ("orgId", "name", "folder", "interval", "rules"):
            assert required in group, f"group missing {required!r}"
        assert isinstance(group["rules"], list)
        assert group["rules"]


def test_exactly_8_rules_with_the_exact_expected_titles() -> None:
    doc = _load_yaml()
    titles = {rule["title"] for rule in _all_rules(doc)}
    assert titles == _EXPECTED_RULE_TITLES
    assert len(_all_rules(doc)) == 8


def test_rule_uids_are_unique() -> None:
    doc = _load_yaml()
    uids = [rule["uid"] for rule in _all_rules(doc)]
    assert len(uids) == len(set(uids)) == 8


def test_every_rule_matches_grafana_rule_schema_shape() -> None:
    doc = _load_yaml()
    for rule in _all_rules(doc):
        for required in (
            "uid",
            "title",
            "condition",
            "data",
            "noDataState",
            "execErrState",
            "for",
            "annotations",
            "labels",
        ):
            assert required in rule, f"{rule.get('title')} missing {required!r}"
        assert isinstance(rule["data"], list)
        assert rule["data"]
        for query in rule["data"]:
            for required in ("refId", "datasourceUid", "model"):
                assert required in query, f"{rule['title']}'s query missing {required!r}"
            assert "refId" in query["model"]
        # `condition` MUST reference one of the declared query refIds.
        ref_ids = {q["refId"] for q in rule["data"]}
        assert rule["condition"] in ref_ids, (
            f"{rule['title']}'s condition {rule['condition']!r} doesn't match any refId"
        )


def test_every_rule_has_severity_and_runbook_url() -> None:
    doc = _load_yaml()
    for rule in _all_rules(doc):
        assert "runbook_url" in rule["annotations"], rule["title"]
        assert "severity" in rule["labels"], rule["title"]
        assert rule["labels"]["severity"] in ("info", "warning", "critical"), rule["title"]


def test_every_runbook_url_resolves_to_exactly_one_of_the_8_stub_files() -> None:
    doc = _load_yaml()
    referenced: set[str] = set()
    for rule in _all_rules(doc):
        url = rule["annotations"]["runbook_url"]
        filename = Path(url).name
        assert filename in _EXPECTED_RUNBOOK_FILENAMES, (
            f"{rule['title']}'s runbook_url {url!r} is not one of the 8 expected files"
        )
        assert (RUNBOOKS_DIR / filename).exists(), (
            f"{rule['title']}'s runbook_url points to a non-existent file: {filename}"
        )
        referenced.add(filename)
    # All 8 files are referenced exactly once each (bijection: one stub per rule).
    assert referenced == _EXPECTED_RUNBOOK_FILENAMES


def test_all_8_runbook_stub_files_exist_and_are_non_empty() -> None:
    for filename in _EXPECTED_RUNBOOK_FILENAMES:
        path = RUNBOOKS_DIR / filename
        assert path.exists(), f"missing runbook stub: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"empty runbook stub: {path}"


def test_every_referenced_tipo_alerta_is_one_of_the_8_seeded_identifiers() -> None:
    doc = _load_yaml()
    found_any = False
    for rule in _all_rules(doc):
        tipo_alerta = rule["labels"].get("tipo_alerta")
        if tipo_alerta is not None:
            found_any = True
            assert tipo_alerta in _SEEDED_ALERT_TYPES, (
                f"{rule['title']} references unknown tipo_alerta {tipo_alerta!r}"
            )
    assert found_any, "expected at least one rule to reference a seeded tipo_alerta"


def test_no_rule_mentions_the_third_party_dian_provider_by_name() -> None:
    """REQ-OPS-016 / addendum #5 — generic identifiers only, in this YAML
    and in the 8 runbook stubs it links to."""
    raw_text = SYNC_YAML_PATH.read_text(encoding="utf-8").lower()
    for banned in _BANNED_VENDOR_NAME_FRAGMENTS:
        assert banned not in raw_text, f"found banned vendor fragment {banned!r} in sync.yaml"

    for filename in _EXPECTED_RUNBOOK_FILENAMES:
        runbook_text = (RUNBOOKS_DIR / filename).read_text(encoding="utf-8").lower()
        for banned in _BANNED_VENDOR_NAME_FRAGMENTS:
            assert banned not in runbook_text, (
                f"found banned vendor fragment {banned!r} in {filename}"
            )
