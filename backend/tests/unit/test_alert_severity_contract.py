"""Contract: severity vocabulary (DB/wire) <-> severidad vocabulary (sucursal).

``prod.alert_types.severity`` is the canonical vocabulary (info|warning|
critical). ``GET /workflows/alert-types`` keeps answering the legacy
``severidad`` (alta|media|baja) the branch app parses with a strict Zod
schema. ``severity_to_severidad`` is the ONLY translation point; this
module pins the table and guards the vocabularies against drift.
"""
from __future__ import annotations

import re
from typing import get_args

import pytest
from parkos_core.models.A.alert_types import AlertTypes
from parkos_core.repo import alert_types as repo_alert_types
from parkos_core.repo.alert_types import severity_to_severidad
from parkos_core.schemas.workflows import (
    AlertSeveridad,
    AlertSeverity,
    AlertTypeRead,
)


@pytest.mark.parametrize(
    ("severity", "severidad"),
    [("critical", "alta"), ("warning", "media"), ("info", "baja")],
)
def test_severity_to_severidad_table(severity: str, severidad: str) -> None:
    assert severity_to_severidad(severity) == severidad


def test_severity_to_severidad_rejects_unknown_value() -> None:
    with pytest.raises(KeyError):
        severity_to_severidad("alta")


def test_translation_table_covers_both_vocabularies_exactly() -> None:
    table = repo_alert_types._SEVERITY_TO_SEVERIDAD
    assert set(table) == set(get_args(AlertSeverity))
    assert set(table.values()) == set(get_args(AlertSeveridad))


def test_severity_vocabulary_matches_db_check_constraint() -> None:
    checks = [
        str(c.sqltext)
        for c in AlertTypes.__table__.constraints
        if str(getattr(c, "sqltext", "")).startswith("severity IN")
    ]
    assert len(checks) == 1
    in_db = set(re.findall(r"'([a-z]+)'", checks[0]))
    assert in_db == set(get_args(AlertSeverity))


def test_alert_type_read_wire_uses_severidad_vocabulary() -> None:
    annotation = AlertTypeRead.model_fields["severidad"].annotation
    assert set(get_args(annotation)) == set(get_args(AlertSeveridad))
