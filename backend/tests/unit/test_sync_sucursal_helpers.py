"""Unit tests — module-level helpers of ``jobs/sync_sucursal``.

Pins the small pure helpers the worker leans on (T-PR12-007 auto-detect and
the legacy wire shape / infra-row guards):

  - B1 — ``_parse_semver`` / ``_version_gte``: version comparison for
    REQ-CUT-005's ``branch_version >= min_branch_version`` decision, with
    the "never raises on garbage" contract (an unparseable segment reads
    as 0, so a malformed version compares as old rather than crashing).
  - B2 — ``_wire_shape``: the exact legacy wire contract
    ``{tabla, uuid_registro, uuid_sucursal, operacion, prioridad, datos}``
    with uuid serialization + ``None``/empty-``datos`` coercion.
  - B3 — ``is_infra_table``: the D21 out-of-catalog guard, including the
    pg_partman child-partition normalization so ``sync_log_p_current`` is
    recognised as infra while a catalog table's own child partition
    (``caja_p_current``) is NOT treated as infra.

The 5 infra names are asserted against the LIVE ``OUT_OF_CATALOG`` set so
a future catalog addition doesn't silently flip an infra guard.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import MagicMock

import pytest
from parkos_core.jobs.sync_cloud import is_infra_table
from parkos_core.jobs.sync_sucursal import _parse_semver, _version_gte, _wire_shape

# ---------------------------------------------------------------------------
# B1 — semver parsing / comparison
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2.3", (1, 2, 3)),
        ("12.3.4", (12, 3, 4)),
        ("0.1", (0, 1, 0)),
        ("0", (0, 0, 0)),
        ("", (0, 0, 0)),
        ("abc", (0, 0, 0)),
        ("1.2.3-beta", (1, 2, 3)),
        ("v2.7.1", (2, 7, 1)),
        ("1.2.3.4.5", (1, 2, 3)),
        ("1..3", (1, 0, 3)),
    ],
)
def test_parse_semver(raw: str, expected: tuple[int, int, int]) -> None:
    assert _parse_semver(raw) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("1.2.3", "1.2.3", True),
        ("1.2.3", "1.2.4", False),
        ("2.0.0", "1.9.9", True),
        ("1.2.3-beta", "1.2.3", True),
        ("0.0.1", "", True),
        ("", "0.0.1", False),
        ("", "", True),
        ("garbage-version", "garbage-version", True),
        ("garbage", "99.0.0", False),
    ],
)
def test_version_gte(a: str, b: str, expected: bool) -> None:
    assert _version_gte(a, b) is expected


def test_version_gte_used_by_autodetect_contract() -> None:
    """REQ-CUT-005's exact decision: catalog accepted only when the branch
    is at least ``min_branch_version``."""
    assert _version_gte("1.4.0", "1.4.0")
    assert not _version_gte("1.3.9", "1.4.0")


# ---------------------------------------------------------------------------
# B2 — _wire_shape contract
# ---------------------------------------------------------------------------


class TestWireShape:
    def test_keys_are_exact_wire_contract(self) -> None:
        row = MagicMock()
        row.tabla = "factura_pagos"
        row.uuid_registro = uuid_lib.uuid4()
        row.uuid_sucursal = uuid_lib.uuid4()
        row.operacion = "insert"
        row.prioridad = 10
        row.datos = {"monto": 5}
        shape = _wire_shape(row)
        assert set(shape) == {
            "tabla",
            "uuid_registro",
            "uuid_sucursal",
            "operacion",
            "prioridad",
            "datos",
        }
        assert shape["tabla"] == "factura_pagos"
        assert shape["uuid_registro"] == str(row.uuid_registro)
        assert shape["uuid_sucursal"] == str(row.uuid_sucursal)
        assert shape["operacion"] == "insert"
        assert shape["prioridad"] == 10
        assert shape["datos"] == {"monto": 5}

    def test_datos_and_operacion_coerce(self) -> None:
        """Empty ``datos`` becomes ``{}`` and ``operacion``/``prioridad``
        pass ``None`` through unchanged — both are current, green behavior."""
        row = MagicMock()
        row.tabla = "caja"
        row.uuid_registro = uuid_lib.uuid4()
        row.uuid_sucursal = uuid_lib.uuid4()
        row.operacion = None
        row.prioridad = None
        row.datos = None
        shape = _wire_shape(row)
        assert shape["operacion"] is None
        assert shape["prioridad"] is None
        assert shape["datos"] == {}

    def test_missing_uuids_coerce_to_none_not_string(self) -> None:
        """A row enqueued without a uuid must not send the string ``'None'``
        over the wire — the legacy receiver parses uuid_registro/uuid_sucursal
        as UUIDs and the literal ``'None'`` string would crash it."""
        row = MagicMock()
        row.tabla = "caja"
        row.uuid_registro = None
        row.uuid_sucursal = None
        row.operacion = None
        row.prioridad = None
        row.datos = None
        shape = _wire_shape(row)
        assert shape["uuid_registro"] is None
        assert shape["uuid_sucursal"] is None


# ---------------------------------------------------------------------------
# B3 — is_infra_table (D21 out-of-catalog guard)
# ---------------------------------------------------------------------------


class TestIsInfraTable:
    def test_infra_names_recognized(self) -> None:
        from parkos_core.sync.catalog.out_of_catalog import OUT_OF_CATALOG

        assert frozenset(
            {"sync_queue", "sync_log", "sync_conflict", "sync_queue_lw_buffer", "alert_types"}
        ) == OUT_OF_CATALOG
        for name in OUT_OF_CATALOG:
            assert is_infra_table(name) is True, f"{name} should be infra"

    def test_partman_child_of_infra_is_infra(self) -> None:
        # pg_partman child naming: `{parent}_p_current` / `_p_default` /
        # `_p{YYYYMMDD}` (no underscore between `p` and the date suffix).
        assert is_infra_table("sync_log_p_current") is True
        assert is_infra_table("sync_log_p20260101") is True
        assert is_infra_table("sync_queue_p_default") is True
        assert is_infra_table("sync_conflict_p_current") is True

    def test_bare_default_partition_of_infra_is_infra(self) -> None:
        # `0001` premade the bare `{parent}_default` partition family (not
        # partman's `_p_default`) on every one of the 8 partman parents —
        # BUG (real finding 2026-09-25): the suffix regex only knew `_p_*`,
        # so `sync_log_default` / `sync_queue_default` resolved to themselves
        # and were treated as NON-infra (unknown_table death) instead of being
        # settled as infra noise.
        assert is_infra_table("sync_log_default") is True
        assert is_infra_table("sync_queue_default") is True

    def test_catalog_table_and_its_partition_are_not_infra(self) -> None:
        from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

        caja = SYNC_CATALOG_BY_NAME["caja"]
        assert caja.name == "caja"
        assert is_infra_table("caja") is False
        assert is_infra_table("caja_p_current") is False
        assert is_infra_table("factura_pagos") is False
        assert is_infra_table("factura_pagos_p_current") is False

    def test_unknown_table_is_not_infra(self) -> None:
        assert is_infra_table("not_a_table") is False
        assert is_infra_table("") is False