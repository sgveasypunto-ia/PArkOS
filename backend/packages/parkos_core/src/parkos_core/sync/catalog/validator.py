"""catalog/validator.py — AST-checks entries against models/ (T-PR2-017).

Implements ``check_catalog_drift.py`` rules 1-4 (REQ-OPS-003) as importable,
independently-testable functions; the CLI script in
``openspec/scripts/check_catalog_drift.py`` is a thin wrapper that calls
these and formats the result.

  - **Rule 1** — every catalog entry's declared ``name`` matches its
    ``model_cls.__tablename__`` (also enforced at construction time by
    ``schema.py``'s ``__post_init__``; re-checked here so a CI run reports
    every offending table in one pass instead of crashing on the first
    ``SyncCatalogEntrySchemaError`` at import time).
  - **Rule 2** — exactly one catalog per table, exception-free. AST-walks
    every ``.py`` file under ``models/{V,L_E,L_W,L_S,A}/`` for a
    ``__tablename__ = "..."`` assignment and cross-checks the discovered
    name against ``SYNC_CATALOG | LOCAL_ONLY_CATALOG | OUT_OF_CATALOG``.
    AST-based (not import-based) deliberately: the model package
    ``__init__.py`` files are known-stale re-export lists (several ORM
    classes on disk are not yet re-exported — see e.g.
    ``models/L_W/__init__.py``'s empty ``__all__``), so import-based
    discovery would silently miss real tables.
  - **Rule 3** — the 46 / 3 / 5 / 54 counts (proposal.md §6.5).
  - **Rule 4** — ``direction`` / ``broadcast_policy`` re-derived from
    ``modelo_datos_er.mmd`` per REQ-CAT-004's derivation table.

**Rule 4's curated exception sets.** The ER's ``%% [TAG]`` comment plus
``uuid_sucursal`` column presence mechanically derives the correct
``direction``/``broadcast_policy`` for the large majority of tables (every
previously-misclassified ``never_propagated`` [V] root, every
``single_branch`` dependent, every ``[L-E]``/``[L-S]``/``[A]`` entry). It
cannot mechanically derive "written on both sides" — the ER's prose
("el ocasional no requiere fila", etc.) does not state bidirectionality in
a grep-able form. The five bidirectional [V] tables, the sole
``never_propagated`` [L-W] exception, and the ``sucursal``
single-branch-by-identity exception are therefore a small, explicit,
tested constant set curated from proposal.md §6.1's ratified narrative —
not blindly inferred from the ``.mmd`` text. This is flagged in the PR2
apply report's "Deviations" section, not silently presented as a fully
mechanical derivation.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

_AUDIT_DIRS = ("V", "L_E", "L_W", "L_S", "A")

# --- Rule 4 curated exception sets (see module docstring) -------------------

_BIDIRECTIONAL_ALL_BRANCHES: frozenset[str] = frozenset({"clientes", "clientes_b2b", "vehiculos"})
_BIDIRECTIONAL_SUBSCRIPTION: frozenset[str] = frozenset(
    {"subscripciones_cliente", "subscripcion_vehiculos"}
)
_NEVER_PROPAGATED_LW: frozenset[str] = frozenset({"validacion_evento"})
_SINGLE_BRANCH_BY_IDENTITY: frozenset[str] = frozenset({"sucursal"})
# log_transaccional is the sole [A] entry that is bidirectional (cloud
# preserves the branch chain verbatim and only extends it with
# cloud-originated rows, proposal §6.1) instead of the class default
# branch_to_cloud.
_BIDIRECTIONAL_A: frozenset[str] = frozenset({"log_transaccional"})

_ER_TAG_TO_AUDIT_CLASS: dict[str, str] = {
    "V": "V",
    "L-E": "L_E",
    "L-W": "L_W",
    "L-S": "L_S",
    "A": "A",
}


@dataclass(frozen=True)
class DriftViolation:
    rule: int
    detail: str

    def __str__(self) -> str:
        return f"rule {self.rule}: {self.detail}"


# ---------------------------------------------------------------------------
# Rule 1 — name -> ORM class
# ---------------------------------------------------------------------------


def check_rule_1_name_matches_model(entries: list) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    for entry in entries:
        tablename = getattr(entry.model_cls, "__tablename__", None)
        if tablename != entry.name:
            violations.append(
                DriftViolation(
                    1,
                    f"{entry.name}: model_cls.__tablename__={tablename!r} does not match "
                    "the entry's declared name",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Rule 2 — exactly one catalog per table, exception-free
# ---------------------------------------------------------------------------


def discover_model_tablenames(models_root: Path) -> dict[str, Path]:
    """AST-walk ``models/{V,L_E,L_W,L_S,A}/*.py`` for ``__tablename__ = "..."``.

    Returns ``{tablename: source_path}``. Deliberately AST-based, not
    import-based — see the module docstring's Rule 2 note.
    """
    discovered: dict[str, Path] = {}
    for audit_dir in _AUDIT_DIRS:
        dir_path = models_root / audit_dir
        if not dir_path.is_dir():
            continue
        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for stmt in node.body:
                    targets: list[ast.expr] = []
                    value: ast.expr | None = None
                    if isinstance(stmt, ast.Assign):
                        targets = stmt.targets
                        value = stmt.value
                    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                        targets = [stmt.target]
                        value = stmt.value
                    for target in targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "__tablename__"
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                        ):
                            discovered[value.value] = py_file
    return discovered


def check_rule_2_exactly_one_catalog(
    *,
    sync_names: set[str],
    local_only_names: set[str],
    out_of_catalog_names: frozenset[str],
    models_root: Path,
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []

    overlap = (
        (sync_names & local_only_names)
        | (sync_names & out_of_catalog_names)
        | (local_only_names & out_of_catalog_names)
    )
    for name in sorted(overlap):
        violations.append(DriftViolation(2, f"{name}: present in more than one catalog"))

    all_classified = sync_names | local_only_names | out_of_catalog_names
    for tablename, path in sorted(discover_model_tablenames(models_root).items()):
        if tablename not in all_classified:
            violations.append(
                DriftViolation(
                    2,
                    f"{tablename} ({path}): ORM class not present in SYNC_CATALOG, "
                    "LOCAL_ONLY_CATALOG, or OUT_OF_CATALOG",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Rule 3 — counts (46 / 3 / 5 / 54)
# ---------------------------------------------------------------------------


def check_rule_3_counts(
    *, sync_catalog: list, local_only_catalog: list, out_of_catalog: frozenset[str]
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    if len(sync_catalog) != 46:
        violations.append(DriftViolation(3, f"SYNC_CATALOG has {len(sync_catalog)} entries, want 46"))
    if len(local_only_catalog) != 3:
        violations.append(
            DriftViolation(3, f"LOCAL_ONLY_CATALOG has {len(local_only_catalog)} entries, want 3")
        )
    if len(out_of_catalog) != 5:
        violations.append(DriftViolation(3, f"OUT_OF_CATALOG has {len(out_of_catalog)} names, want 5"))
    total = len(sync_catalog) + len(local_only_catalog) + len(out_of_catalog)
    if total != 54:
        violations.append(DriftViolation(3, f"46+3+5 coverage totals {total}, want 54"))
    return violations


# ---------------------------------------------------------------------------
# Rule 4 — direction / broadcast_policy re-derived from modelo_datos_er.mmd
# ---------------------------------------------------------------------------

_BLOCK_START_RE = re.compile(r"^\s{4}(\w+)\s*\{\s*$")
_BLOCK_END_RE = re.compile(r"^\s{4}\}\s*$")
_TAG_RE = re.compile(r"%%\s*\[([A-Za-z-]+)\]")
_UUID_SUCURSAL_LINE_RE = re.compile(r"\buuid_sucursal\b")


@dataclass(frozen=True)
class ERSignal:
    tag: str  # raw ER tag, e.g. "V", "L-W"
    has_uuid_sucursal: bool
    uuid_sucursal_nullable: bool
    cloud_only: bool


def parse_er_entities(mmd_path: Path) -> dict[str, ERSignal]:
    """Parse ``modelo_datos_er.mmd`` entity blocks into ``{table_name: ERSignal}``."""
    lines = mmd_path.read_text(encoding="utf-8").splitlines()
    entities: dict[str, ERSignal] = {}

    name: str | None = None
    block: list[str] = []
    for line in lines:
        if name is None:
            match = _BLOCK_START_RE.match(line)
            if match:
                name = match.group(1)
                block = []
            continue
        if _BLOCK_END_RE.match(line):
            entities[name] = _parse_block(block)
            name = None
            block = []
            continue
        block.append(line)

    return entities


def _parse_block(block: list[str]) -> ERSignal:
    tag = ""
    cloud_only = False
    has_uuid_sucursal = False
    uuid_sucursal_nullable = False

    for line in block:
        tag_match = _TAG_RE.search(line)
        if tag_match and not tag:
            tag = tag_match.group(1)
        if "CLOUD-ONLY" in line:
            cloud_only = True
        if _UUID_SUCURSAL_LINE_RE.search(line) and "uuid uuid_sucursal" in line:
            has_uuid_sucursal = True
            if "NULL" in line and ("default global" in line or "override" in line):
                uuid_sucursal_nullable = True

    return ERSignal(
        tag=tag,
        has_uuid_sucursal=has_uuid_sucursal,
        uuid_sucursal_nullable=uuid_sucursal_nullable,
        cloud_only=cloud_only,
    )


def derive_expected_direction_broadcast(
    name: str, signal: ERSignal
) -> tuple[str | None, str | None] | None:
    """Apply REQ-CAT-004's derivation table + the curated exception sets.

    Returns ``(direction, broadcast_policy)``, where both may be ``None``
    for the sole ``never_propagated`` entry, or ``None`` (the whole tuple)
    when the audit class carries no ER-derivable direction rule (e.g. an
    entry this script does not classify).
    """
    audit_class = _ER_TAG_TO_AUDIT_CLASS.get(signal.tag)

    if audit_class == "V":
        if signal.uuid_sucursal_nullable:
            return ("cloud_to_branch", "all_branches_with_override")
        if name in _BIDIRECTIONAL_SUBSCRIPTION:
            return ("bidirectional", "subscription")
        if name in _BIDIRECTIONAL_ALL_BRANCHES:
            return ("bidirectional", "all_branches")
        if name in _SINGLE_BRANCH_BY_IDENTITY:
            return ("cloud_to_branch", "single_branch")
        if signal.has_uuid_sucursal:
            return ("cloud_to_branch", "single_branch")
        return ("cloud_to_branch", "all_branches")

    if audit_class in ("L_E", "L_S", "A"):
        if name in _BIDIRECTIONAL_A:
            return ("bidirectional", None)
        return ("branch_to_cloud", None)

    if audit_class == "L_W":
        if name in _NEVER_PROPAGATED_LW:
            return (None, None)
        if signal.cloud_only:
            return ("cloud_to_branch", "single_branch")
        return ("branch_to_cloud", None)

    return None


def check_rule_4_direction_matches_er(
    *, sync_catalog: list, er_entities: dict[str, ERSignal]
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    for entry in sync_catalog:
        signal = er_entities.get(entry.name)
        if signal is None:
            # Not every SYNC_CATALOG entry has to have an ER block name match
            # (e.g. entries added by this change with no legacy ER block are
            # not expected in PR2 — none currently). Skip silently rather
            # than false-failing on an unrelated naming mismatch.
            continue

        expected = derive_expected_direction_broadcast(entry.name, signal)
        if expected is None:
            continue

        expected_direction, expected_broadcast = expected
        if expected_direction != entry.direction:
            violations.append(
                DriftViolation(
                    4,
                    f"{entry.name}: declared direction={entry.direction!r}, "
                    f"ER-derived direction={expected_direction!r}",
                )
            )
        # broadcast_policy is only meaningful for a real direction; skip the
        # never_propagated pair (both None) — REQ-CAT-016 covers that case.
        if expected_direction is not None and expected_broadcast != entry.broadcast_policy:
            violations.append(
                DriftViolation(
                    4,
                    f"{entry.name}: declared broadcast_policy={entry.broadcast_policy!r}, "
                    f"ER-derived broadcast_policy={expected_broadcast!r}",
                )
            )
    return violations


__all__ = [
    "DriftViolation",
    "ERSignal",
    "check_rule_1_name_matches_model",
    "check_rule_2_exactly_one_catalog",
    "check_rule_3_counts",
    "check_rule_4_direction_matches_er",
    "derive_expected_direction_broadcast",
    "discover_model_tablenames",
    "parse_er_entities",
]
