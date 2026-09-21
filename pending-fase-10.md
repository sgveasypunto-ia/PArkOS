# Pending — easypunto_parkos (Fase 10: Arqueos de caja y cierre diario, CU-10)

> **Archivo de tracking diferido**: todo lo que NO se ejecuta durante el ciclo SDD de cada HU de Fase 10 queda acá y se resuelve al **final de todo el plan de ejecucion de Fase 10** (después de cerrar las 3 HU: F10.1, F10.2, F10.3).
>
> **Fecha de apertura**: 2026-09-21 (post-Fase 9 archive, Fase 9 cerrada 2026-09-19 con F9.1 + F9.2 mergeados a dev).
> **Rama destino**: cada item puede tener su propia rama `feature/hu-fX-Y-…` o un housekeeping directo a dev, según escale.
> **PR target**: `origin/dev` (gitflow).
> **Estado al abrir**: Fase 9 cerrada (F9.1 + F9.2 mergeados a dev en `9d30bef`), Fase 10 arranca desde cero.

## 1. HUs restantes (3)

| # | ID | Titulo | Tamano est. | Bloqueador | Notas |
|---|---|---|---|---|---|
| 1 | HU-F10.1 | Arqueo parcial (auditoría, sin cierre) | ~385 LOC prod + ~1192 LOC tests = +1566/+1790 con size:exception | depende F1.13 backend `/caja/arqueo` | ✅ **CERRADO 2026-09-21** — archived to `openspec/changes/archive/2026-09-21-fase-10-1-arqueo-parcial/`. spec synced to `openspec/specs/operations/spec.md` REQ-OPS-152..156 (next free gap after REQ-OPS-151). verify-report PASS-WITH-3-WARNINGs (all 3 documented carry-overs, no F10.1 regressions). Merge SHA `033f654`. 8 atomic commits (`3525544..dc16578`) + doc commit `fac0063`. 7 drift anchors resueltos (DA-1..DA-7). Vitest 27/27 + 206/206 print suite verde. e2e 3/3 skipped per F9.x sandbox F.6 precedent. tsc/lint clean en mis archivos. **size:exception RATIFIED** (+1566 vs 800 budget, F9.1 precedente; producción bajo presupuesto, excedente tests por strict_tdd). |
| 2 | HU-F10.2 | Cierre de turno (con arqueo obligatorio) | ~160 LOC | depende F10.1 page + ArqueoParcial logic | pendiente |
| 3 | HU-F10.3 | Cierre diario (cierra todas las sesiones del día) | ~200 LOC | depende F10.2 (cierre_turno pattern) | pendiente |

**Total LOC Fase 10**: ~620 LOC production + tests + configs (F10.1 ya cerrado con size:exception; F10.2+F10.3 pendientes).

## 2. Deferred Items (carry-overs al cierre de Fase 10)

| # | ID | Titulo | Origen | Bloqueador | Notas |
|---|---|---|---|---|---|
| 1 | ABBC-F10.1-BE-1 | Backend `GET /caja/arqueo/resumen` no expone `tolerancia_efectivo`/`tolerancia_datafono` desde `configuracion_tolerancias` | HU-F10.1 apply (detectado en implementación) | no bloquea F10.1 (FE usa defaults 1_000/500 COP; alerta la dispara backend REQ-OPS-094) | **Apertura 2026-09-21**. Solución: backend PR que agrega los campos al payload. Documentado en drift-anchor reconciliation table de `openspec/changes/fase-10-1-arqueo-parcial/specs/spec.md`. Fuera de scope Fase 10 (resolver en Fase 13+ backend admin o como housekeeping independiente). |
| 2 | ABBC-F10.1-BE-2 | Vitest coverage thresholds para los 5 modulos tocados por F10.1 (useArqueo, ArqueoSheet, ArqueoParcial, escposTemplates, escposBuilder) | HU-F10.1 apply tasks.md §Coverage | no bloquea F10.1 (per-module tests dan 80%+ manualmente) | **Apertura 2026-09-21**. Solución: agregar `coverage.thresholds` por path en `apps/electron-sucursal/vitest.config.ts`. Sigue F9.3 pattern. |
| 3 | ABBC-F10.1-LINT-1 | `Dashboard.tsx` tiene 3 lint errors pre-existentes (unused imports `CardDescription`, `Input`, `CobrosPendientesList`) + 2 TS errors (DrawerKind not assignable, `prefijo_nombre` missing) | HU-F10.1 apply (detectado) — pre-existing en `dev` | no bloquea F10.1 (no causado por F10.1) | **Apertura 2026-09-21**. Limpieza housekeeping en rama `fix/dashboard-pre-existing-lint` cuando cierre Fase 10. |
| 4 | ABBC-F10.2-BE-1 | "Arqueo orphan reconciler": si POST /caja/arqueo (cierre_turno) tiene éxito pero PUT /caja-sesion/sesion/{uuid}/cerrar falla, queda un arqueo `[A]` huérfano + sesión abierta. Sin DELETE endpoint (canon arquitectura) | HU-F10.2 propose (drift anchor DA-F10.2-2) | no bloquea F10.2 (FE muestra `uuid_arqueo` en banner de error para remediación manual) | **Apertura 2026-09-21**. Solución: job diario `arqueo_orphan_reconciler` (cloud) que detecta arqueos con `uuid_sesion IS NULL` en estado open + creada >X min ago, y los cierra automáticamente vía PUT retry. Documentado en drift anchor DA-F10.2-2. Fuera de scope Fase 10; post-Fase-13 backend admin. |
| 5 | ABBC-F10.2-SIZE | size:exception para F10.2 (Cierre de turno): +2,037 net LOC vs 800 budget. Production ~575 LOC, over-budget por strict_tdd test surface + `cerrarTurnoChain.ts` extraction | HU-F10.2 apply 2026-09-21 | — | **Apertura 2026-09-21**. **size:exception RATIFIED** per F9.1 + F10.1 precedente. **Patrón emergente**: 3 de 3 HUs strict_tdd en este repo exceden budget 2-5x. Meta-question: ¿subir per-HU budget a 2000 LOC para Fase 11+? Resolver al cierre de Fase 10. |
| 6 | ABBC-F10.2-LINT | Pre-existing lint/TS debt en `fallbackBrowser.test.ts`, `fallbackBrowser.entrada.test.ts`, `nit.test.ts`, `ProtectedRoute.test.tsx`, `StatusBar.test.tsx`, `Listado.test.tsx`, `Venta.test.tsx`, `Venta.tsx`, `Dashboard.tsx` | HU-F10.2 apply (detectado) — pre-existing en `dev` | no bloquea F10.2 | **Apertura 2026-09-21**. Limpieza housekeeping al final de Fase 10 — `fix/pre-existing-lint-fase-10` con la lista completa. Extiende ABBC-F10.1-LINT-1. |

## 3. Working tree mess pre-existente

- `apps/electron-sucursal/test-results/` (playwright test runs leftovers) — gitignored normalmente, agregar a `.gitignore` si no está.
- 4 stale archivos en `openspec/changes/archive/2026-09-19-fase-7-{1,2}/` (fase 7 archive leftovers que no se limpiaron al cierre de F7) — housekeeping al final de Fase 10.

## 4. Forward hooks (a considerar en futuras HU)

- **HU-F11.x** (sync UI + alertas CU-07/14): puede consumir el patrón `bridge.imprimir(escposBuilder.build('arqueo', payload))` que ahora existe; el alert `descuadre_critico` se renderiza en el banner de F11.x si lo cruzan con la lista de alertas activas.
- **HU-F12.x** (reportería local CU-09): el resumen de cierres diarios (F10.3) alimenta el reporte "Mi turno".
- **Post-Fase 10 housekeeping**: ejecutar `python openspec/scripts/check_schema_match.py` para confirmar que el schema ER sigue 100% consistente antes de Fase 13 (Backend admin).

## 5. Criterio de cierre del `pending-fase-10.md`

`pending-fase-10.md` se considera **resuelto** cuando:
1. Las 3 HU de Fase 10 marcadas ✅ con archive cerrado.
2. ABBC-F10.1-BE-1, ABBC-F10.1-BE-2, ABBC-F10.1-LINT-1 resueltos o escalados a Fase 11+/13+.
3. Vitest + Playwright suites verdes en CI (post-Fase 10).
4. axe-core 0 violaciones en `/caja/arqueo-parcial`, `/caja/cerrar-turno` (placeholder de F3.3 + F10.2), `/caja/cierre-diario`.
5. Hash chain `log_transaccional` per `uuid_sucursal` valida sin fork tras los 3 arqueos de prueba.
6. `git status --short` retorna solo legítimos o nada.
7. Merge a `dev` (--no-ff) + push + delete branch per AGENTS.md regla gitflow.

---

**Opened by**: orchestrator (post-Fase 9 archive, Fase 10 first HU = F10.1 already merged).
**Engram**: persisted (topic_key=`sdd/fase-10/pending`, project=`parkos`).
**Updated**: 2026-09-21 — Fase 10 primera HU cerrada con size:exception; 2 ABBC y 3 housekeeping items documentados.
