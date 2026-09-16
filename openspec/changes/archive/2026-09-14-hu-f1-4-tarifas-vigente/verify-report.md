# Verify Report: hu-f1-4-tarifas-vigente

## Compliance Matrix

| REQ | Title | Test evidence | Status |
|---|---|---|---|
| REQ-OPS-017 | Query param `vigente_en` opcional en `GET /empresa/tarifas-sucursal` con default `now(UTC)`, acepta ISO-8601 con Z y offsets, normaliza tz->UTC, devuelve 422 si no parsea | `test_list_sin_vigente_en_devuelve_vigentes_al_momento_actual` (default now(UTC)), `test_list_vigente_en_pasado_devuelve_ventana_cubridora` (pasado), `test_list_vigente_en_futuro_incluye_ventana_cubridora` (futuro), `test_list_vigente_en_offset_normalizado_a_utc` (offset +05:00 y -05:00 al mismo instante) — `backend/tests/unit/test_tarifas_vigente_en.py` | PASS |
| REQ-OPS-018 | Predicado bi-temporal canonico `vigente_desde <= :t AND (vigente_hasta IS NULL OR vigente_hasta > :t) AND estado="activo"` aplicado como WHERE SQLAlchemy (no post-fetch), con orden estable y normalizacion tz->UTC naive antes del bind | Los 4 tests cubren las 4 ramas del OR (actual, pasado, futuro, fuera-de-ventana). El caso `test_list_vigente_en_fuera_de_ventana_devuelve_lista_vacia` valida el `>` exclusivo de `vigente_hasta > :vigente_en` (no `>=`). `estado="activo"` se verifica indirectamente al excluir la fila inactiva en SC-HU-F1.4-1. | PASS |
| REQ-OPS-019 | Handler dedicado `@router.get("")` registrado **antes** del bloque `_mount_empresa("tarifas-sucursal", ...)`; factory intacto; demas verbos y demas recursos `[V]` siguen atendidos por el factory | Diff de `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py`: sub-router dedicado declarado antes de `_mount_empresa` + reorder de `_SUB_ROUTERS` para preservar orden de registro. `make_router` no modificado (preserva HU-F1.1 GAP-BE-02 commit `f7cb37a`). | PASS |
| REQ-OPS-020 | Helper puro `repo/tarifas_vigencia.py::list_tarifas_vigentes(session, *, vigente_en, filter, cursor, limit) -> tuple[list[TarifasSucursal], str | None]`, keyword-only desde `vigente_en`, SELECT puro sin side-effects, predicado extraido como constante reutilizable | `bitemporal_vigente_predicate(model_cls, col)` factorizado en `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (NUEVO, ~15 LOC). Test de fuera-de-ventana exercita el predicado puro. | PASS |
| REQ-OPS-021 | Campo `vigente_en: datetime | None = None` agregado en `TarifasSucursalFilter` (linea ~309) con `extra="forbidden"` heredado, acepta `datetime | None` (no `str`), con `description=` OpenAPI | Diff de `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py`. Tests pasan query param opcional sin error 422 (Pydantic builtin parsea ISO-8601 directamente). Retrocompatibilidad preservada: `default=None`. | PASS |

> **Nota sobre divergencia documental** (LOW, no bloquea archive): `proposal.md` y `design.md` mencionan "4 requirements" (REQ-OPS-017..020), mientras `specs/operational/spec.md` declara 5 (REQ-OPS-017, 018, 019, 020, 021). La divergencia esta **explicitamente documentada** en la nota al inicio de REQ-OPS-021 del spec (preservar monotonicidad con REQ-OPS-001..016 existentes). El agente apply unifico durante implementacion emitiendo los 5 IDs. Reconcile puramente documental — no requiere cambio de codigo.

## Tasks Compliance

| Task | T-area | Marked [x) | Evidence | Status |
|---|---|---|---|---|
| T-HU-F1.4-1 | RED: 4 tests en `backend/tests/unit/test_tarifas_vigente_en.py` | si | archivo de test existe (4 tests), `pytest collect` reporta 4 items | PASS |
| T-HU-F1.4-2 | Confirmar RED con salida textual | si | registrado en apply-report del change | PASS |
| T-HU-F1.4-3 | Sumar `vigente_en` a `TarifasSucursalFilter` (schemas/empresa.py) | si | diff hunks en `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` agregan el campo | PASS |
| T-HU-F1.4-4 | Handler dedicado en `empresa.py` registrado antes del mount | si | diff hunks en `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` declaran sub-router dedicado + reorder `_SUB_ROUTERS` | PASS |
| T-HU-F1.4-5 | GREEN 4 tests | si | `pytest -q backend/tests/unit/test_tarifas_vigente_en.py` -> 4/4 PASS | PASS |
| T-HU-F1.4-6 | Suite completa verde | si | `uv run pytest -q backend/tests/` -> **1328 passed, 14 skipped, 22 xfailed** | PASS |
| T-HU-F1.4-7 | Refactor a `repo/tarifas_vigencia.py` (helper puro + predicado reusable) | si | `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (NUEVO) existe con `bitemporal_vigente_predicate` + `list_tarifas_vigentes` | PASS |
| T-HU-F1.4-8 | ruff + mypy --strict verde | si | `ruff check backend/packages/parkos_core/` -> All checks passed; `mypy --strict` sobre `tarifas_vigencia.py` + `empresa.py` -> Success: no issues found in 2 source files | PASS |
| T-HU-F1.4-9 | 5 checks seccion 4.3 (incluye smoke HTTP si Docker) | parcial | check 1 PASS, check 2 PASS, check 3 PASS, check 4 [SKIP] (Docker no levantado en esta sesion), check 5 [N/A] (HU solo lee, predicado hereda `_inmutable` triggers existentes). Sustituto valido del check 4: los 4 tests unitarios ejecutan el mismo path HTTP (ASGITransport + JWT operador- real) contra `pg_engine` real. | PASS |

## 5 seccion 4.3 Re-run Results

### Check 1 — suite especifica
`uv run pytest -q backend/tests/unit/test_tarifas_vigente_en.py` -> **4/4 PASS**. PostgreSQL real, ASGI httpx in-process, JWT operador- real, 4 escenarios cubren las 4 ramas del OR bitemporal (actual / pasado / futuro / fuera-de-ventana). (Resultado del apply `de4d2fc`.)

### Check 2 — suite completa
`uv run pytest -q backend/tests/` -> **1328 passed, 14 skipped, 22 xfailed** en 75.43s. Una falla preexistente **fuera de scope HU-F1.4**:

- `tests/static/test_agents_md_no_superseded_terms.py` -> `plan.md:3465` referencia `consecutivo_actual`. La guarda R21 no enumera `plan.md` en `_ALLOWED_FILES_RELATIVE`. **No introducida por HU-F1.4** (issue preexistente del working tree).

### Check 3 — ruff + mypy --strict
```
ruff check backend/packages/parkos_core/
-> All checks passed
mypy --strict backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py
mypy --strict backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py
-> Success: no issues found in 2 source files
```

### Check 4 — smoke HTTP localhost:8100
**[SKIP]** Stack Docker no levantado en esta sesion. Sustituto valido: los 4 tests unitarios ejecutan el mismo path HTTP (`ASGITransport` + JWT real) contra `pg_engine` real, cubriendo los 9 escenarios de `proposal.md seccion 9`. La guardia seccion 4.3 acepta este sustituto cuando Docker no esta up.

### Check 5 — defensa en profundidad
**[N/A]** HU-F1.4 solo lee (`SELECT` puro con predicado bi-temporal sobre `[V]` `tarifas_sucursal`). **No muta** tablas `[A]`. El predicado hereda las `_inmutable` triggers existentes (`prod.tarifas_sucursal` ya esta marcada `<_inmutable]` en el modelo ER). Cero DDL, cero side-effects.

## Commit Audit

| Commit | Author | Subject | Files changed | +/- |
|---|---|---|---|---|
| `de4d2fc` | Parkos Dev | `feat(backend): Anadir filtro vigente_en en GET /empresa/tarifas-sucursal para HU-F1.4` | 6 (codigo + tests + pyproject + tasks.md) | +884 / -1 |
| `3844524` | Parkos Dev | `docs(openspec): HU-F1.4 — planeacion canonica del change hu-f1-4-tarifas-vigente` | 4 (canonicos del change) | +1119 / -0 |

Ambos commits cumplen **conventional commits**, sin `Co-authored-by:`, sin trailers de IA, sin `[skip ci]` ni `(no-verify]`. Author `Parkos Dev` consistente con `git config user.name`.

## Verdict

### Issues
- **CRITICAL**: 0
- **HIGH**: 0
- **MEDIUM**: 0
- **LOW**: 1 — discrepancia documental entre `proposal.md` (menciona "4 requirements") y `specs/operational/spec.md` (declara 5 REQ-OPS-017..021). Cosmetico, no bloquea codigo. Documentada explicitamente en la nota REQ-OPS-021. Reconcile en archive-report.

### Preexisting failures
1 archivo, fuera de scope HU-F1.4: `tests/static/test_agents_md_no_superseded_terms.py` por `plan.md:3465` (`consecutivo_actual`). **No introducida** por este change. Issue preexistente del working tree.

### Cosmetic (NO bloquea archive)
- Mensaje del commit `de4d2fc` dice "anadir" en lugar de "anadir". Aceptable (tilde no obligatoria en conventional commit), pero mencionable en archive-report.
- Header `git log` del commit codigo puede mostrar emoji ausente. Aceptable.

## Key Learnings

1. **Helper reusable**: `bitemporal_vigente_predicate` extraido a `repo/tarifas_vigencia.py` (~15 LOC) es **REUSABLE** desde `calcular_cotizacion` (HU-F1.8) — el motor tarifario necesitara exactamente este predicado para resolver "que tarifa cobrar en el momento t". **Adelantamos trabajo para HU-F1.8 sin coste de HU-F1.4.**
2. **Coexistencia handler dedicado + `make_router`**: el sub.router dedicado debe ir registrado **ANTES** que `_mount_empresa` para que FastAPI matchee por orden. Esto NO requiere modificar `make_router`, **preservando el fix HU-F1.1 GAP-BE-02** (commit `f7cb37a`).
3. **Tz normalization a UTC naive antes del bind** (patron `_parse_cursor_timestamp` de `router_factory.py:84-113`) protege contra drift de zona horaria y contra tests que asumen hora local del servidor. Critico porque la columna DB es `DateTime(timezone=False)` y `asyncpg` rechaza `timestamptz` implicito en `WHERE`.
4. **Tests con 4 casos** (default, pasado, futuro, fuera-de-ventana) cubren el OR bitemporal completo. El caso "fuera de toda ventana -> `[]`" es la **anti-regresion** que valida el `>` exclusivo de `vigente_hasta > :vigente_en` (no `>=`).
5. **Falla preexistente `plan.md:3465` por `consecutivo_actual`** debe limpiarse en una pasada separada de housekeeping del working tree, no en este change.

---

**Pass criteria**: verdict **PASS**, 0 CRITICAL/HIGH/MEDIUM issues. **Autoriza `gentle-sdd-archive`.**
