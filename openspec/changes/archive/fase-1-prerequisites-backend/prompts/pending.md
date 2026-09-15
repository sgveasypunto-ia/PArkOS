# Pending — easypunto_parkos (Fase 1 Parte I)

> **Archivo de tracking diferido**: todo lo que NO se ejecuta durante el ciclo SDD de cada HU queda acá y se resuelve al **final de todo el plan de ejecución** (después de cerrar las 15 HU de Fase 1 Parte I).
>
> **Fecha de apertura**: 2026-09-14.
> **Rama destino**: `feat/fase-1-prerequisites-backend`.
> **PR target**: `origin/dev` (gitflow).
> **Estado al abrir**: HU-F1.3 cerrada (4 commits), HU-F1.5 en explore.

## 1. HUs restantes (6)

| # | ID | Título | Tamaño est. | Bloqueador | Notas |
|---|---|---|---|---|---|
| 5 | HU-F1.5 | `mv_ocupacion_diaria` + `GET /operacion/ocupacion` | 160 LOC | ninguno | **cerrado** (2026-09-14, archive `fc72adb`). Migration 0024. |
| 6 | HU-F1.6 | Validaciones reales en `POST /operacion/ingresos` | 260 LOC | depende F1.5 + F1.4 | **cerrado** (2026-09-14, archive `21097c8`). |
| 7 | HU-F1.7 | `POST /operacion/salidas` (rotación + mensualidad) | 220 LOC | ✅ cerrado (2026-09-14, 5 commits `c320d0f..def754d`) | KD-IVA resuelto inline en MIGRATION 0026 Op 2. |
| 9 | HU-F1.9 | Facturación transaccional + NIT módulo 11 | 330 LOC | ✅ cerrado (2026-09-14, 11 commits `6d2c457..f00c848`) | NIT módulo 11 Variant A canónica; 5 capas defense; KD-FACT-01 + KD-FACT-02; MIGRATION 0027. |
| 10 | HU-F1.10 | Numeración FE + estado DIAN + reintento | 230 LOC | ✅ cerrado (2026-09-14, 9 commits `a9a8f47..05bb7ac`) | 11 REQs (064..074) + 3 XR merged. `assign_consecutivo` ya existe. MIGRATION 0028. |
| 11 | HU-F1.11 | Workflow reimpresión tiquete (crear + anular) | 170 LOC | siembra `costos_servicios.concepto='reimpresion'` | gap huérfano (anulación). |
| 12 | HU-F1.12 | Venta atómica de suscripción | 260 LOC | ninguno | ampliación producto, no CU literal. |
| 13 | HU-F1.13 | Endpoints arqueo + siembra `tipo_arqueo.cierre_dia` | 240 LOC | ninguno | GAP-BE-05 (permiso mal) bundleado acá. |
| 14 | HU-F1.14 | `GET /sync/estado` + 11 alert_types nuevos | 120 LOC | ninguno | 8 técnicos ya sembrados; total 19 idempotente. |
| 15 | HU-F1.15 | `GET /usuarios/{uuid}/login` histórico | 70 LOC | ninguno | gap huérfano. |

**Total LOC restante**: 860 LOC en 5 HUs (F1.5 + F1.6 + F1.7 + F1.9 + F1.10 cerradas = -870 LOC).

## 2. Bloqueadores de deployment (KD-IVA)

- ✅ **Siembra `impuestos.IVA`**: **RESUELTA inline en HU-F1.7** (commit `c320d0f`, migration 0026 Op 2: `INSERT INTO prod.impuestos (..., 'IVA', 'IVA', 0.19, ...) ON CONFLICT (codigo, vigente_desde) DO NOTHING`). F1.8 ya retorna IVA real en cotizaciones; F1.7 y F1.9 listas sin siembra adicional. Owner original HU-F14.2 Parte II ya no requiere ejecutar siembra exógena (puede verificar idempotencia en deploy).
- **Siembra `costos_servicios.concepto='reimpresion'`**: verificar existencia antes de HU-F1.11.
- **Siembra `tipo_arqueo.cierre_dia`**: requerida para HU-F1.13.
- **Siembra `configuracion_seguridad` default global**: ya cerrada en F1.2 (lockout real); housekeeping de auditoría pendiente.

## 3. Housekeeping técnico (LOW pre-existing)

Documentado en verify-reports F1.8 (`openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/verify-report.md`) y F1.3 (`openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/verify-report.md`). **NO introducido por F1.3/F1.8** — viene del baseline pre-Fase-1.

### 3.1. 4 errores `mypy --strict` pre-existentes
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` lines 79, 134, 163 — handlers existentes sin return annotation.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` line 344 — `rowcount` attribute error.
- **Acción al final**: agregar `: -> X` return annotations y corregir `rowcount` reference (probable `result.rowcount` vs `result.rowcount()`).

### 3.2. 25 test skips pre-existentes
- Causa raíz: autouse `_bootstrap_global_hash_chain_genesis` requiere `pg_partman` no disponible en `postgres:16-alpine` local (Docker stack local).
- **Acción al final**: o (a) bumear a `postgres:16-pgpartman` en CI local, o (b) skip condicional explícito por marker `@pytest.mark.requires_pgpartman` con colección selectiva.

### 3.3. 18 archivos con fallas pre-existentes en suite completa
Lista: `test_apply_pending_no_self_duplicate.py`, `test_buffer_ttl_escalation.py`, `test_clientes_family_permission_codes.py`, `test_identity_invariant.py`, `test_parent_missing_buffer_drain.py`, `test_reverse_dry_run.py`, `test_router_factory_payload_body_binding.py`, `test_sync_cloud_concurrent_sessions.py`, `test_sync_pull_generalized.py`, `test_versioned_update_preserves_unset_fields.py`, `test_deterministic_permisos_uuids.py`, `test_deterministic_tipo_persona_empresa_uuids.py`, `test_idempotency_inmutable.py`, `test_sync_queue_lw_buffer_schema.py`, `test_agents_md_no_superseded_terms.py::plan.md:3465`, `test_router_factory_no_vigente_desde.py`, `test_stage_runner.py`, `test_verify_chain.py`.
- **Acción al final**: triage dedicado, separado de Fase 1. Probables re-exposures del fix HU-F1.1 (`router_factory_payload_body_binding`) + plan.md:3465 (`consecutivo_actual` superseded term).

### 3.4. `ruff extend-select` deprecation top-level
- En repo-level `pyproject.toml`. Out of scope F1.3/F1.8.
- **Acción al final**: migrar a `lint.select = [...extend-select items]` antes del próximo bump de ruff.

### 3.5. Cosmetic commits pre-existentes
- `a3d0c39` (F1.8) usa mayúscula inicial en "Anadir" — aceptable por conventional commits, no requiere fixup.

## 4. Working tree mess pre-existente (NO introducido por Fase 1)

Ver `git status --short` al inicio de cada sesión. Basado en snapshot 2026-09-14 post-F1.3:

- `D` (unstaged deletions) en `openspec/changes/bootstrap-monorepo-foundation/{design,exploration,proposal,tasks}.md` (4 archivos)
- `D` en `openspec/changes/cloud-edge-sync-architecture/exploration.md`
- `D` en `openspec/changes/create-49-table-apis/{design,exploration,proposal,tasks}.md` + 6 specs/{...}.md (10 archivos)
- `D` en `openspec/changes/fase-1-prerequisites-backend/{artifacts/HU-F1.2-apply.md,prompts/HU-F1.1-report.md,prompts/HU-F1.1-spec.md}` (3 archivos)
- `??` (untracked) en `apps/package-lock.json`, `backend/scripts/{insert_null_genesis,replicate_catalogs_to_branch,verify_branch_catalogs}.py`
- `??` en `docs/{00-general,01-requisitos,02-arquitectura,03-desarrollo,04-qa-testing,05-manuales,README.md}/` (carpetas nuevas sin tracking)
- `??` en `infra/scripts/seed_catalogs.py`
- `??` en `openspec/changes/archive/{bootstrap-monorepo-foundation,cloud-edge-sync-architecture,create-49-table-apis}/` (carpetas archivadas vía mv sin captura git)
- `??` en `openspec/changes/archive/fase-1-prerequisites-backend/{artifacts,prompts/00-ejecutor-fase-1.md,prompts/HU-F1.1-report.md,prompts/HU-F1.1-spec.md}`
- `??` en `openspec/changes/archive/...` (resto del archive mess de cambios previos)
- `??` en `plan.md` (movido fuera de root, ahora en archive)

**Acción al final del plan**:
1. Stage + commit cada bloque como housekeeping commit individual (separado del PR de Fase 1 Parte I), ej:
   ```
   chore(docs): archivar change hu-bootstrap-monorepo-foundation en openspec/changes/archive/
   chore(docs): archivar change hu-cloud-edge-sync-architecture en openspec/changes/archive/
   chore(docs): archivar change hu-create-49-table-apis en openspec/changes/archive/
   chore(docs): archivar change hu-fase-1-prerequisites-backend en openspec/changes/archive/ (parcial)
   chore(docs): incorporar plan.md al repositorio de documentación
   chore(docs): incorporar carpeta docs/ al repositorio
   chore(infra): adicionar scripts de catálogo al repo
   chore(apps): adicionar apps/package-lock.json
   ```

## 5. Forward hooks (a considerar en futuras HU)

- **HU-F1.6** (cupo validation en POST /ingresos): replicar patrón `mv_ocupacion_diaria` JOIN + KD-FORZADO prefix validation.
- **HU-F1.7** (POST /salidas): replicar patrón PL/pgSQL `calcular_cotizacion` con `FOR SHARE` lock + AST walk. Si KD-IVA siembra se completa antes de F1.7, esa HU queda desbloqueada.
- **HU-F4.3** (frontend strip ocupación): consumidora de F1.5. Polling 10s en cliente, no websocket (DEC-SUC-11).
- **Si futura HU requiere "sesión activa de `uuid_usuario` arbitrario desde admin-"**: endpoint separado con query param explícito (FUERA de scope de F1.3, ver REQ-OPS-029).
- **Si futura HU requiere "at most one active row per actor" en otra tabla [L-]**: replicar patrón F1.3 (partial unique index + CONCURRENTLY + pre-flight DO $$).

## 6. Criterio de cierre del `pending.md`

`pending.md` se considera **resuelto** cuando:

1. Las 15 HU de Fase 1 Parte I están marcadas `[x]` en `TODO-fase-1.md`.
2. Las siembras de §2 están completas (o documentado como out-of-scope explícito con handover a Fase 1 Parte II).
3. Los 4 housekeeping de §3 tienen commit individual o issue tracked.
4. El working tree mess de §4 está capturado en commits housekeeping separados.
5. `git status --short` retorna solo `M` legítimos del cambio en curso o nada.
6. Suite completa `uv run pytest -q backend/tests/` retorna 0 CRITICAL y todos los tests pre-existentes están clasificados (fixed/skipped/tracked-as-issue).

**PR de cierre**: `feat/fase-1-prerequisites-backend` → `dev` con merge commit + tag `fase-1-parte-i-complete`.

---

**Opened by**: orchestrator (post-F1.3 archive, pre-F1.5 explore).
**Engram**: persisted (topic_key=`sdd/fase-1-prerequisites-backend/pending`, project=`easypuinto-parkos-software`).
**Updated**: 2026-09-14 post-F1.10 archive — F1.10 cerrado (9 commits `a9a8f47..05bb7ac`), §2 KD-IVA sigue resuelto, §3.1 housekeeping pendiente (4 mypy pre-existentes), §4 working tree mess pre-existente.
