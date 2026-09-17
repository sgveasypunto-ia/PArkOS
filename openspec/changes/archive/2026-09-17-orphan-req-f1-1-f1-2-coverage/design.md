# Design: orphan REQ-OPS materialization (F1.1 + F1.2)

> **Change**: `2026-09-17-orphan-req-f1-1-f1-2-coverage`
> **Phase**: design (sdd-design)
> **Capability**: operations (REQ-OPS-141 + REQ-OPS-142)
> **Delivery**: single-pr (work is documentary only, ~30 LOC total)

## Technical Approach

Additive merge to canonical `openspec/specs/operations/spec.md`. No code paths change. No tests change. No migrations.

### File operations (atomic commit)

1. `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/specs/operations/spec.md` — created (delta with REQ-OPS-141 + REQ-OPS-142 + ADDED Requirements line)
2. `openspec/specs/operations/spec.md` — modified (append REQ-OPS-141 + REQ-OPS-142 at end, append ADDED Requirements line)
3. `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/{proposal,design,tasks,verify-report,archive-report}.md` — created

Total: 5 new files + 1 modified file. ~30 LOC delta.

### REQ-OPS-141 — router_factory guard for tables without vigente_desde

**Source-of-truth anchor**: `backend/.../api/router_factory.py:52` `_order_key(model_cls)` helper + `hasattr(model_cls, "vigente_desde")` guards at lines 76, 182, 246.

#### Requirement statement

`make_router(model_cls)` MUST NOT apply `ORDER BY vigente_desde DESC, uuid ASC` or cursor pagination on `vigente_desde` when the model lacks that column. Tables mounted with `make_router` that have only `created_at`/`timestamp_evento` (`alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket`) MUST list correctly.

#### Scenarios

1. **GET /workflows/alerta without vigente_desde**: MUST NOT raise `AttributeError` or SQL error; MUST order by `(timestamp_evento DESC, uuid ASC)` (the workflow default).
2. **GET on [V] tables**: MUST preserve current `ORDER BY vigente_desde DESC, uuid ASC` behavior (no regression).
3. **`_order_key` helper**: Returns `(order_col, cursor_field)` tuple shared by ordering and cursor parsing. If `hasattr(model_cls, "vigente_desde")`, returns `(model_cls.vigente_desde, "vigente_desde")`; otherwise returns `(model_cls.uuid, "uuid")` (or `timestamp_evento` for workflow tables).

### REQ-OPS-142 — /auth/me + cookie httpOnly + lockout real

**Source-of-truth anchor**: `backend/.../api/v1/auth.py` lines 12-15, 81-99, 148, 175, 291-294, 419.

#### Requirement statement

`POST /auth/login` MUST set `parkos_session` cookie with `httponly=True, secure=True, samesite="lax"` AND return `access_token` Bearer. `GET /auth/me` MUST return `{user, permisos, uuid_sucursal, sucursales_permitidas, expires_at}` per `AuthMeResponse`. Lockout MUST enforce `minutos_bloqueo_login` window from `prod.configuracion_seguridad`: 5 (or `max_intentos_login`) failed attempts → `429 account_locked` with `Retry-After: minutos_bloqueo_login * 60`.

#### Scenarios

1. **POST /auth/login success**: 200 + `TokenPair` body + `Set-Cookie: parkos_session=...; HttpOnly; Secure; SameSite=Lax` header + `access_token` Bearer in body.
2. **POST /auth/login 5th failure**: 429 `account_locked` + `Retry-After: <minutos_bloqueo_login * 60>` header. Counter is per-`uuid_usuario`.
3. **GET /auth/me authenticated**: 200 + `AuthMeResponse` (user uuid + email + permisos + uuid_sucursal + sucursales_permitidas + expires_at).
4. **GET /auth/me unauthenticated**: 401 `not_authenticated`.
5. **Lockout window expires**: After `Retry-After` seconds elapses, `POST /auth/login` with correct password MUST succeed (counter resets).

### Why formalize these now

- HU-F1.1 fix is referenced by `factory_intact` CI gate at `openspec/scripts/check_schema_match.py` (commit `f7cb37a`). REQ-OPS formalization enables future sdd-verify to assert "this CI gate covers REQ-OPS-141".
- HU-F1.2 backend contract (cookie + lockout from `configuracion_seguridad`) is independent of F3.1 frontend REQ-OPS-106..112 (login UI). Materializing REQ-OPS-142 closes the backend half of the F1.2 story.
- Both REQs are behavioral contracts that future regressions could violate silently; formal REQ-OPS + AST walk + test pinning provides defense in depth.

### What is NOT in this design

- No code changes (the implementations are already merged to `dev` via prior F1.1 + F1.2 work — neither change folder has `archive-report.md` so the historical record is incomplete, but the code is real).
- No new tests (existing F1.1 contract is covered by `tests/static/test_factory_intact.py` and the F1.2 contract by `auth.py` integration tests).
- No migration changes (no schema changes).

## Validation chain

1. `git grep -n "^### Requirement: REQ-OPS-14[12]" openspec/specs/operations/spec.md` returns 2 matches.
2. `git grep -n "ADDED Requirements (delta: 2026-09-17-orphan-req-f1-1-f1-2-coverage" openspec/specs/operations/spec.md` returns 1 match.
3. `python -c "import ast; ast.parse(open('openspec/specs/operations/spec.md').read())"` — not applicable (markdown).
4. `openspec/scripts/check_schema_match.py` still exits 0 (no schema change → no regression).
5. `uv run mypy --strict backend/packages/parkos_core/src/parkos_core/api/router_factory.py` exits 0 (no code touched).
6. `uv run mypy --strict backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` exits 0.

## File inventory

**New files (7):**
- `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/proposal.md` (~75 LOC)
- `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/design.md` (this file, ~80 LOC)
- `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/specs/operations/spec.md` (delta, ~50 LOC)
- `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/tasks.md` (~30 LOC)
- `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/verify-report.md` (~30 LOC)
- `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/archive-report.md` (~50 LOC)

**Modified files (1):**
- `openspec/specs/operations/spec.md` (+~30 LOC: 2 REQ sections + 1 ADDED Requirements line)

## Verification plan

| # | Gate | Method | Expected |
|---|---|---|---|
| G1 | REQ-OPS-141 present in canon | `git grep "^### Requirement: REQ-OPS-141"` | 1 match |
| G2 | REQ-OPS-142 present in canon | `git grep "^### Requirement: REQ-OPS-142"` | 1 match |
| G3 | ADDED Requirements line present | `git grep "ADDED Requirements (delta: 2026-09-17-orphan-req-f1-1-f1-2-coverage"` | 1 match |
| G4 | All 7 artifacts present | `ls openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/` | 7 files |
| G5 | No code modifications | `git diff origin/dev -- backend/` | empty |
| G6 | `factory_intact` still passes | `python openspec/scripts/check_schema_match.py` | exit 0 |
| G7 | mypy strict still passes on router_factory + auth | `uv run mypy --strict ...` | no issues found |
| G8 | Working tree clean after archive move | `git status --short` | empty (modulo pre-existing untracked screenshots) |

All 8 gates deterministic. No env-blocked gates.

## Out of scope

- AST walk tests for REQ-OPS-141 (would be ideal but existing `test_factory_intact.py` covers the contract — separate follow-up if desired).
- AST walk tests for REQ-OPS-142 (similar reasoning — `test_lockout_*.py` integration tests exist).
- The Fase 1 audit's other findings (F1.12 V8/V8b STUB, F1.10/F1.11 missing verify-report.md in archive) — separate follow-up changes.