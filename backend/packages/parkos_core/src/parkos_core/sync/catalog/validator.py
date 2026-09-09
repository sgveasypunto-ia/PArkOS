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
  - **Rule 5** (T-PR3-007, D18/ADR-003) — ``depends_on`` re-derived from
    ``modelo_datos_er.mmd``'s FK-tagged attributes: every table's expected
    parent set is exactly the tables it holds a mandatory (NOT NULL),
    physically FK-tagged column to, that are themselves ``SYNC_CATALOG``
    entries. A nullable FK (or a polymorphic reference with no physical FK
    at all, e.g. ``reclamos.uuid_reclamable``) never belongs in
    ``depends_on`` — the R22 guard.
  - **Rule 6** (R19) — the ``depends_on`` graph (self-chain edges excluded)
    is a DAG; a cycle is reported as a rule violation using the same
    algorithm ``catalog/dependency_graph.py`` runs at import time.
  - **Rule 7** (R12) — ``priority`` is referenced nowhere in the dependency
    ordering code path (AST check, not text-grep).

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


# ---------------------------------------------------------------------------
# Rule 5 — depends_on equals the ER's mandatory-FK parent set (D18, ADR-003, R22)
# ---------------------------------------------------------------------------

# Every ``<type> <column> FK "<description>"`` attribute line in
# modelo_datos_er.mmd uses ``uuid`` as the type (verified: 88/88 FK-tagged
# attributes in the current ER). A plain ``uuid <column> "<description>"``
# line with no ``FK`` token — e.g. ``reclamos.uuid_reclamable`` ("polimórfico,
# sin FK física") or ``log_transaccional.uuid_referencia`` ("opcional: FK al
# evento origen") — is deliberately NOT matched: "FK" appearing inside the
# free-text description does not make it a physically FK-tagged column.
_FK_ATTR_RE = re.compile(r'^\s+uuid\s+(\w+)\s+FK\s+"([^"]*)"')
_NULLABLE_MARKER_RE = re.compile(r"\bNULL\b", re.IGNORECASE)

# Column name -> target table. Spanish singular/plural table naming is not a
# mechanical function of the FK column name (e.g. ``uuid_tipo_vehiculo`` ->
# ``tipos_vehiculo``, ``uuid_otro_cobro`` -> ``otros_cobros``), so — like this
# module's Rule 4 curated exception sets — this is a small, explicit,
# exhaustive dictionary built directly from every FK-tagged attribute line in
# modelo_datos_er.mmd (32 distinct column names; re-derive by grepping
# ``uuid \S+ FK`` against the ER if this ever needs updating). Self-chain
# columns (the ``uuid_..._padre`` family + ``uuid_pago_revertido``) map to
# their OWN table; ``parse_er_mandatory_fk_parents`` filters those out via
# its ``target == table`` check, not by omitting them here — keeping them
# documents the mapping completely instead of relying on silent absence.
_FK_COLUMN_TARGET_TABLE: dict[str, str] = {
    "uuid_usuario": "usuarios",
    "uuid_usuario_cierre": "usuarios",
    "uuid_permiso": "permisos",
    "uuid_sucursal": "sucursal",
    "uuid_tipo_sucursal": "tipo_sucursal",
    "uuid_empresa": "empresa",
    "uuid_tipo_vehiculo": "tipos_vehiculo",
    "uuid_tipo_tarifa": "tipo_tarifa",
    "uuid_tipo_persona": "tipo_persona",
    "uuid_cliente": "clientes",
    "uuid_tipo_subscripcion": "tipo_subscripciones",
    "uuid_subscripcion_cliente": "subscripciones_cliente",
    "uuid_vehiculo": "vehiculos",
    "uuid_ingreso": "ingreso",
    "uuid_costo_servicio": "costos_servicios",
    "uuid_factura": "facturas",
    "uuid_salida": "salidas",
    "uuid_resolucion_facturacion": "resolucion_facturacion",
    "uuid_arqueo": "arqueo",
    "uuid_impuesto": "impuestos",
    "uuid_otro_cobro": "otros_cobros",
    "uuid_sesion": "sesion",
    "uuid_factura_electronica": "factura_electronica",
    "uuid_factura_electronica_reemplazo": "factura_electronica",
    "uuid_tipo_arqueo": "tipo_arqueo",
    # Self-chain columns (self_chain=True) — see the module-comment above.
    "uuid_reimpresion_padre": "reimpresion_ticket",
    "uuid_anulacion_padre": "anulaciones",
    "uuid_reclamo_padre": "reclamos",
    "uuid_alerta_padre": "alerta",
    "uuid_pago_revertido": "factura_pagos",
    "uuid_envio_padre": "envio_dian",
    "uuid_validacion_padre": "validacion_evento",
}


def parse_er_mandatory_fk_parents(
    mmd_path: Path, *, known_tables: set[str] | None = None
) -> dict[str, frozenset[str]]:
    """Derive each table's mandatory-FK parent set from ``modelo_datos_er.mmd``.

    Mechanical rule (ADR-003 Part 1 / D18): a table's expected
    ``depends_on`` is the set of tables it declares a real, ``FK``-tagged
    ``uuid`` attribute pointing at (resolved via
    :data:`_FK_COLUMN_TARGET_TABLE`) whose description carries **no**
    nullability marker (a case-insensitive ``NULL`` word — matches every
    nullable-FK annotation style actually used in the ER: ``NULL =``,
    ``NULL si``, ``NULL en``), excluding:

    - self-references (target == the table's own name — self-chains are
      resolved separately via ``parent_fk_column``, never via
      ``depends_on``);
    - targets outside ``known_tables`` when provided (ADR-003: "that is
      itself a SyncCatalog entry" — excludes ``LocalOnlyCatalog``/
      ``OutOfCatalog`` targets).

    A generic ``uuid`` attribute with no ``FK`` token at all (e.g.
    ``reclamos.uuid_reclamable``, explicitly "sin FK física" — polymorphic,
    no physical constraint) contributes nothing, mechanically, with no
    special-casing required here — ``_FK_ATTR_RE`` simply never matches it.
    """
    lines = mmd_path.read_text(encoding="utf-8").splitlines()
    result: dict[str, frozenset[str]] = {}

    table: str | None = None
    parents: set[str] = set()
    for line in lines:
        if table is None:
            match = _BLOCK_START_RE.match(line)
            if match:
                table = match.group(1)
                parents = set()
            continue
        if _BLOCK_END_RE.match(line):
            result[table] = frozenset(parents)
            table = None
            continue

        fk_match = _FK_ATTR_RE.match(line)
        if not fk_match:
            continue
        column, description = fk_match.group(1), fk_match.group(2)
        target = _FK_COLUMN_TARGET_TABLE.get(column)
        if target is None or target == table:
            continue
        if _NULLABLE_MARKER_RE.search(description):
            continue
        if known_tables is not None and target not in known_tables:
            continue
        parents.add(target)

    return result


def check_rule_5_depends_on_matches_er(
    *, sync_catalog: list, mmd_path: Path
) -> list[DriftViolation]:
    sync_names = {entry.name for entry in sync_catalog}
    expected_by_table = parse_er_mandatory_fk_parents(mmd_path, known_tables=sync_names)

    violations: list[DriftViolation] = []
    for entry in sync_catalog:
        expected = expected_by_table.get(entry.name, frozenset())
        actual = frozenset(entry.depends_on)
        if actual == expected:
            continue

        detail = (
            f"{entry.name}: declared depends_on={sorted(actual)}, "
            f"ER mandatory-FK set={sorted(expected)}"
        )
        unexpected = sorted(actual - expected)
        if unexpected:
            detail += f" — unexpected (nullable FK or no physical FK, R22 guard): {unexpected}"
        missing = sorted(expected - actual)
        if missing:
            detail += f" — missing mandatory FK: {missing}"
        violations.append(DriftViolation(5, detail))
    return violations


# ---------------------------------------------------------------------------
# Rule 6 — the depends_on graph (self-chain edges excluded) is a DAG (R19)
# ---------------------------------------------------------------------------


def check_rule_6_graph_is_dag(*, sync_catalog: list) -> list[DriftViolation]:
    """Rule 6 — ``depends_on`` (self-chain excluded) forms a DAG.

    Reuses the exact algorithm ``catalog/dependency_graph.py`` runs against
    the real ``SYNC_CATALOG`` at import time, applied here to whatever
    ``sync_catalog`` the caller passes — the real catalog for
    ``check_catalog_drift.py``, or a deliberately cyclic fixture list for a
    unit test — without needing to re-import a module that would itself
    fail to import on a real cycle.
    """
    # Local import: avoids a hard import-time coupling from validator.py (a
    # module several other call sites import defensively) to
    # dependency_graph.py (a module that can itself raise at import time).
    from .dependency_graph import DependencyGraphError, _build_graph, _topological_levels

    graph = _build_graph(sync_catalog)
    try:
        _topological_levels(graph)
    except DependencyGraphError as exc:
        return [DriftViolation(6, str(exc))]
    return []


# ---------------------------------------------------------------------------
# Rule 7 — `priority` referenced nowhere in the dependency-ordering code path (R12)
# ---------------------------------------------------------------------------

# The dependency-ordering code path (design.md §11 rule 7 / §3 Module
# Structure) — the only modules allowed to reason about cross-row order.
ORDERING_MODULE_RELATIVE_PATHS: tuple[str, ...] = (
    "parkos_core/sync/catalog/dependency_graph.py",
    "parkos_core/sync/motor/dependency_orderer.py",
)


def check_rule_7_priority_absent_from_ordering(
    *, src_root: Path, relative_paths: tuple[str, ...] = ORDERING_MODULE_RELATIVE_PATHS
) -> list[DriftViolation]:
    """Rule 7 — ``priority`` is never referenced in the ordering code path.

    ``priority`` legally exists as a per-entry FIFO tie-break *within* one
    topological level (ADR-003 Part 1) — that tie-break falls out of
    stable-sorting a batch ``list_pending`` already priority-ordered
    (``motor/dependency_orderer.py``'s module docstring), never an explicit
    read of the field. AST-based (not text-grep): ``ast.walk`` finds every
    ``ast.Name``/``ast.Attribute`` node literally named ``priority``
    regardless of formatting, so a comment merely mentioning the word cannot
    produce a false positive and reformatted code cannot produce a false
    negative.
    """
    violations: list[DriftViolation] = []
    for relative_path in relative_paths:
        module_path = src_root / relative_path
        if not module_path.is_file():
            continue
        try:
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        except SyntaxError as exc:
            violations.append(DriftViolation(7, f"{relative_path}: could not parse ({exc})"))
            continue
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            if name == "priority":
                lineno = getattr(node, "lineno", "?")
                violations.append(
                    DriftViolation(
                        7,
                        f"{relative_path}:{lineno}: 'priority' referenced in the "
                        "dependency-ordering code path",
                    )
                )
    return violations


__all__ = [
    "ORDERING_MODULE_RELATIVE_PATHS",
    "DriftViolation",
    "ERSignal",
    "check_rule_1_name_matches_model",
    "check_rule_2_exactly_one_catalog",
    "check_rule_3_counts",
    "check_rule_4_direction_matches_er",
    "check_rule_5_depends_on_matches_er",
    "check_rule_6_graph_is_dag",
    "check_rule_7_priority_absent_from_ordering",
    "derive_expected_direction_broadcast",
    "discover_model_tablenames",
    "parse_er_entities",
    "parse_er_mandatory_fk_parents",
]
