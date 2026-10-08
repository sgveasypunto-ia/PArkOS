"""Static gate: a seeded catalog row must not get a random uuid.

Defect class (``0019``/``0020``/``0056``/``0093``/``0095``): seeding a catalog
row with ``gen_random_uuid()`` / ``uuid4()`` makes cloud and every branch mint
a DIFFERENT identifier for the same logical row, and the transactional rows
that reference it break on the other node (FK violation, retried forever).
Identity aliases only paper over it. Seeds must use ``uuid5(NAMESPACE,
'<tabla>:<clave natural>')``.

Applied migrations are immutable, so migrations up to ``LEGACY_LAST_REVISION``
are frozen (their random seeds are converged by ``0095``). Every later
migration and every seed script is checked.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_VERSIONS = _BACKEND / "packages" / "parkos_core" / "migrations" / "versions"
_SCRIPT_DIRS = (_BACKEND / "scripts", _REPO / "infra" / "scripts")

# Highest migration whose seeds predate this gate (immutable once applied).
LEGACY_LAST_REVISION = 94

# Seeded reference catalogs (identical content expected on every node). Per-node
# data (usuarios, permisos_usuario, usuarios_sucursal, sucursal, ...) is NOT a
# catalog and may legitimately use random uuids.
SEEDED_CATALOGS = frozenset(
    {
        "permisos",
        "tipo_persona",
        "tipos_vehiculo",
        "tipo_subscripciones",
        "tipo_tarifa",
        "tipo_sucursal",
        "tipo_arqueo",
        "impuestos",
        "otros_cobros",
        "costos_servicios",
        "empresa",
        "configuracion_tolerancias",
        "configuracion_seguridad",
    }
)

_RANDOM_UUID = re.compile(r"gen_random_uuid\s*\(|uuid_generate_v4\s*\(|\buuid4\s*\(|\buuid_lib\.uuid4\b")
_CATALOG_INSERT = re.compile(r"INSERT\s+INTO\s+(?:prod\.)?(\w+)", re.IGNORECASE)


def _code_without_docstrings_and_comments(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def find_violations(source: str) -> list[str]:
    """Catalog tables a file seeds while it also mints random uuids.

    File-level on purpose: a seed file that inserts into a catalog must not
    contain a random-uuid generator anywhere in its executable code.
    """
    try:
        code = _code_without_docstrings_and_comments(source)
    except SyntaxError:  # .sql or non-Python seed
        code = source
    if not _RANDOM_UUID.search(code):
        return []
    return sorted({t for t in _CATALOG_INSERT.findall(code) if t in SEEDED_CATALOGS})


def _revision_number(path: Path) -> int | None:
    match = re.match(r"(\d+)", path.name)
    return int(match.group(1)) if match else None


def _checked_files() -> list[Path]:
    files = [
        p for p in sorted(_VERSIONS.glob("*.py"))
        if (_revision_number(p) or 0) > LEGACY_LAST_REVISION
    ]
    for directory in _SCRIPT_DIRS:
        files.extend(sorted(directory.glob("*.py")))
        files.extend(sorted(directory.glob("*.sql")))
    return files


# ---------------------------------------------------------------- detector self-checks


def test_detector_flags_a_random_sql_seed() -> None:
    src = 'op.execute("INSERT INTO prod.impuestos (uuid, codigo) VALUES (gen_random_uuid(), \'X\')")'
    assert find_violations(src) == ["impuestos"]


def test_detector_flags_a_python_uuid4_seed() -> None:
    src = (
        "import uuid\n"
        "def seed(conn):\n"
        "    conn.execute('INSERT INTO prod.tipo_arqueo (uuid) VALUES (:u)', {'u': uuid.uuid4()})\n"
    )
    assert find_violations(src) == ["tipo_arqueo"]


def test_detector_accepts_a_deterministic_seed() -> None:
    src = (
        "import uuid\n"
        "NS = uuid.UUID('a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60')\n"
        "u = uuid.uuid5(NS, 'impuestos:IVA')\n"
        "op.execute(f\"INSERT INTO prod.impuestos (uuid) VALUES ('{u}')\")\n"
    )
    assert find_violations(src) == []


def test_detector_ignores_docstrings_and_comments() -> None:
    src = (
        '"""Fixes the seed that used gen_random_uuid() before."""\n'
        "# INSERT INTO prod.impuestos used gen_random_uuid() once\n"
        "op.execute(\"INSERT INTO prod.impuestos (uuid) VALUES ('38766f08-f0ae-5fb3-8960-b9a3019acf99')\")\n"
    )
    assert find_violations(src) == []


def test_detector_ignores_per_node_tables() -> None:
    src = 'op.execute("INSERT INTO prod.permisos_usuario (uuid) SELECT gen_random_uuid()")'
    assert find_violations(src) == []


# ---------------------------------------------------------------- the gate itself


def test_seeded_catalog_names_are_real_catalog_entries() -> None:
    names = {s.name for s in SYNC_CATALOG}
    assert SEEDED_CATALOGS <= names, sorted(SEEDED_CATALOGS - names)


def test_there_are_files_to_check() -> None:
    assert (_VERSIONS / "0095_deterministic_catalog_seed_uuids.py") in _checked_files()


@pytest.mark.parametrize("path", _checked_files(), ids=lambda p: p.name)
def test_seed_code_does_not_mint_random_uuids_for_catalogs(path: Path) -> None:
    offenders = find_violations(path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{path.name} seeds catalog table(s) {offenders} with a random uuid "
        "(gen_random_uuid()/uuid4()). Use uuid5(NAMESPACE, '<tabla>:<clave natural>') "
        "so every node converges on the same identifier."
    )
