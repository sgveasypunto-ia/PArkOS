"""test_observability_metrics.py — T-PR13-001.

Verifies the 4 new observability metrics (``sync_apply_total``,
``sync_dependency_wait``, ``catalog_rows_total``, ``sync_deferred_total``)
exist with the exact label schema design.md §9 documents, that PR12's
``catalog_backfill_complete`` gauge is untouched, and that NO label name
exposed by this module could ever carry payload content (PII) — only
structural identifiers (REQ-OPS-006).
"""
from __future__ import annotations

from parkos_core.sync.observability import metrics as observability_metrics
from prometheus_client import Counter, Gauge


def test_sync_apply_total_is_counter_with_exact_labels() -> None:
    metric = observability_metrics.sync_apply_total
    assert isinstance(metric, Counter)
    assert set(metric._labelnames) == {"status", "tabla", "uuid_sucursal", "audit_class"}


def test_sync_dependency_wait_is_gauge_with_exact_labels() -> None:
    metric = observability_metrics.sync_dependency_wait
    assert isinstance(metric, Gauge)
    assert set(metric._labelnames) == {"tabla", "tabla_padre"}


def test_catalog_rows_total_is_gauge_with_exact_labels() -> None:
    metric = observability_metrics.catalog_rows_total
    assert isinstance(metric, Gauge)
    assert set(metric._labelnames) == {"tabla", "uuid_sucursal"}


def test_sync_deferred_total_is_counter_with_exact_labels() -> None:
    metric = observability_metrics.sync_deferred_total
    assert isinstance(metric, Counter)
    assert set(metric._labelnames) == {"tabla", "tabla_padre"}


def test_catalog_backfill_complete_gauge_unchanged_from_pr12() -> None:
    """T-PR12-008's gauge must remain untouched by this PR's additions."""
    metric = observability_metrics.catalog_backfill_complete
    assert isinstance(metric, Gauge)
    assert set(metric._labelnames) == {"uuid_sucursal"}


# Every label name any metric in this module is allowed to expose.
_ALLOWED_LABEL_NAMES = frozenset(
    {"status", "tabla", "uuid_sucursal", "tabla_padre", "audit_class"}
)

# Field names that would indicate PII/payload content leaking into a label.
_PII_SUSPECT_NAMES = frozenset(
    {"email", "telefono", "direccion", "nombre", "apellido", "payload", "datos", "registro"}
)


def test_no_metric_label_carries_payload_or_pii_content() -> None:
    """No label across ANY metric in this module may carry payload/PII content.

    Structural guarantee for REQ-OPS-006 / the cross-PR constraint
    ("`sync_apply_total` and every other metric label excludes PII").
    """
    checked = 0
    for name in dir(observability_metrics):
        candidate = getattr(observability_metrics, name)
        labelnames = getattr(candidate, "_labelnames", None)
        if labelnames is None:
            continue
        checked += 1
        for label in labelnames:
            assert label in _ALLOWED_LABEL_NAMES, (
                f"{name!r} exposes disallowed label {label!r} outside the allowed set"
            )
            assert label not in _PII_SUSPECT_NAMES, (
                f"{name!r} exposes a PII-suspect label name {label!r}"
            )
    assert checked >= 5, "expected to find at least the 5 known observability metrics"


def test_sync_apply_total_records_structural_label_values_only() -> None:
    """Smoke test: incrementing with realistic label VALUES never needs PII."""
    observability_metrics.sync_apply_total.labels(
        status="APPLIED",
        tabla="clientes",
        uuid_sucursal="00000000-0000-0000-0000-000000000000",
        audit_class="V",
    ).inc()


def test_sync_dependency_wait_gauge_set() -> None:
    observability_metrics.sync_dependency_wait.labels(
        tabla="subscripcion_vehiculos", tabla_padre="vehiculos"
    ).set(3)


def test_catalog_rows_total_gauge_set() -> None:
    observability_metrics.catalog_rows_total.labels(
        tabla="clientes", uuid_sucursal="00000000-0000-0000-0000-000000000000"
    ).set(42)


def test_sync_deferred_total_counter_inc() -> None:
    observability_metrics.sync_deferred_total.labels(
        tabla="subscripcion_vehiculos", tabla_padre="vehiculos"
    ).inc()
