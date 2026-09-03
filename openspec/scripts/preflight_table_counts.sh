#!/usr/bin/env bash
# preflight_table_counts.sh — pre-flight gate for the 49-table AUDIT-FIRST schema.
#
# Runs after `0001_initial_schema.py` (or its equivalent in a fresh DB) and
# asserts the live `prod.*` schema has at least 49 tables, 11 [A]-class
# `_inmutable` triggers, and 2 `[L-S]` session-guard triggers. Exits non-zero
# on any miss. The Python helper `check_table_counts.py` is called first to
# ensure the four reconciled docs still reflect the canonical counts.
#
# Usage:
#   bash openspec/scripts/preflight_table_counts.sh
#
# Requirements:
#   - `psql` in PATH (or set PSQL=path/to/psql)
#   - DATABASE_URL env var (postgresql://user:pass@host:port/dbname)
#   - All 4 target doc files (PROJECT_CONTEXT.md, _meta/roadmap.md,
#     _meta/iteration-plan.md, config.yaml) live under ./openspec
#
# Exit codes:
#   0 = all checks passed
#   1 = a check failed (printed to stderr)
#   2 = missing prerequisite (psql, DATABASE_URL, doc file)
set -euo pipefail

PSQL="${PSQL:-psql}"
DOC_ROOT="${DOC_ROOT:-./openspec}"

# --- Prerequisite checks -----------------------------------------------------
if ! command -v "$PSQL" >/dev/null 2>&1; then
  echo "ERROR: psql not found in PATH (override with PSQL env var)" >&2
  exit 2
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL env var is required (e.g. postgresql://parkos:parkos@localhost:5432/parkos)" >&2
  exit 2
fi

# --- Step 1: doc drift check ------------------------------------------------
echo "[1/2] Checking canonical table counts in reconciled docs..."
python "$DOC_ROOT/scripts/check_table_counts.py" "$DOC_ROOT"

# --- Step 2: live schema check -----------------------------------------------
echo ""
echo "[2/2] Checking live prod.* schema via $PSQL..."

# 49 tables in prod.*
TABLE_COUNT="$("$PSQL" "$DATABASE_URL" -tA -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'prod';")"
if [[ "$TABLE_COUNT" -lt 49 ]]; then
  echo "ERROR: expected >= 49 tables in prod.*, found $TABLE_COUNT" >&2
  exit 1
fi
echo "  tables in prod.*: $TABLE_COUNT (>= 49 OK)"

# 11 [A]-class `_inmutable` triggers
TRIGGER_COUNT="$("$PSQL" "$DATABASE_URL" -tA -c "
  SELECT count(*) FROM pg_trigger t
  JOIN pg_class c ON t.tgrelid = c.oid
  JOIN pg_namespace n ON c.relnamespace = n.oid
  WHERE n.nspname = 'prod'
    AND t.tgname LIKE '%\\_inmutable' ESCAPE '\\'
    AND NOT t.tgisinternal;
")"
if [[ "$TRIGGER_COUNT" -lt 11 ]]; then
  echo "ERROR: expected >= 11 _inmutable triggers on [A] tables, found $TRIGGER_COUNT" >&2
  exit 1
fi
echo "  _inmutable triggers on [A] tables: $TRIGGER_COUNT (>= 11 OK)"

# 2 [L-S] session-guard triggers (login + sesion)
LS_GUARD_COUNT="$("$PSQL" "$DATABASE_URL" -tA -c "
  SELECT count(*) FROM pg_trigger t
  JOIN pg_class c ON t.tgrelid = c.oid
  JOIN pg_namespace n ON c.relnamespace = n.oid
  WHERE n.nspname = 'prod'
    AND (t.tgname LIKE 'ls_session%' OR t.tgname LIKE '%ls\\_session%')
    AND NOT t.tgisinternal;
")"
if [[ "$LS_GUARD_COUNT" -lt 2 ]]; then
  echo "ERROR: expected >= 2 ls_session* triggers on [L-S] tables, found $LS_GUARD_COUNT" >&2
  exit 1
fi
echo "  ls_session* triggers on [L-S] tables: $LS_GUARD_COUNT (>= 2 OK)"

echo ""
echo "OK: preflight passed (49+ tables, 11+ _inmutable triggers, 2+ ls_session guards)."
