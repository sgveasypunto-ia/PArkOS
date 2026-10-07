"""test_mmd_block_count.py — T-PR10-008 acceptance (ADR-002).

Equivalent of ``git grep -c "%% \\[A\\]" modelo_datos_er.mmd``: after PR10's
amendment (two new ``%% [A]`` blocks — ``sync_queue_lw_buffer``,
``alert_types``), the canonical ER carries exactly 14 ``%% [A]`` blocks (12
pre-existing + 2 new). The 3 non-ER operational tables (``idempotency_keys``,
``pairing_tokens``, ``revoked_sync_jwts``) have no ``%% [A]`` block by
definition — they are not ER entities.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ER_PATH = _REPO_ROOT / "modelo_datos_er.mmd"

_A_BLOCK_RE = re.compile(r"%%\s*\[A\]")
_ANY_CLASS_BLOCK_RE = re.compile(r"%%\s*\[([VLA][\w-]*)\]")

# ADR-002 canon was 26 [V] + 3 [L-E] + 6 [L-W] + 2 [L-S] + 14 [A] = 51 entities.
# Commit 2e7e0d65 (reconstitution of migrations 0076-0081) legitimately added
# ``configuracion_caja`` [V] and the [A] tables ``sync_catalog`` and
# ``sync_identity_alias``: the ER file is the source of truth, so the
# canon is now 27 [V] + 3 [L-E] + 6 [L-W] + 2 [L-S] + 16 [A] = 54 entities.
_EXPECTED_A_BLOCK_COUNT = 16
_EXPECTED_TOTAL_ENTITY_COUNT = 54


def _read_er_source() -> str:
    assert _ER_PATH.is_file(), f"expected ER file not found: {_ER_PATH}"
    return _ER_PATH.read_text(encoding="utf-8")


def test_mmd_a_block_count_is_16() -> None:
    """``modelo_datos_er.mmd`` carries exactly 16 ``%% [A]`` blocks (ADR-002 + 0076-0081)."""
    source = _read_er_source()
    count = len(_A_BLOCK_RE.findall(source))
    assert count == _EXPECTED_A_BLOCK_COUNT, (
        f"expected {_EXPECTED_A_BLOCK_COUNT} '%% [A]' blocks in modelo_datos_er.mmd "
        f"(ADR-002: 12 existing + sync_queue_lw_buffer + alert_types, + sync_catalog + sync_identity_alias), got {count}"
    )


def test_mmd_total_entity_count_is_54() -> None:
    """``modelo_datos_er.mmd`` carries exactly 54 class-tagged ER entities."""
    source = _read_er_source()
    count = len(_ANY_CLASS_BLOCK_RE.findall(source))
    assert count == _EXPECTED_TOTAL_ENTITY_COUNT, (
        f"expected {_EXPECTED_TOTAL_ENTITY_COUNT} total ER entities (ADR-002 + 0076-0081), got {count}"
    )


def test_mmd_contains_the_two_new_a_blocks() -> None:
    """The two new ``[A]`` entities from PR10 are present with their header comment."""
    source = _read_er_source()
    assert "sync_queue_lw_buffer {" in source
    assert "alert_types {" in source
    # Each new table block's own first line must be tagged [A].
    for table in ("sync_queue_lw_buffer", "alert_types"):
        idx = source.index(f"{table} {{")
        # The next non-empty line after the opener must carry the [A] tag.
        after = source[idx:idx + 400]
        assert re.search(rf"{table}\s*\{{\s*\n\s*%%\s*\[A\]", after), (
            f"{table} block must be tagged %% [A] as its first line"
        )
