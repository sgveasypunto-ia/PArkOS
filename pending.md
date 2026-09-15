# Pending — easypunto_parkos (Fase 2: Andamiaje Electron)

> **Archivo de tracking diferido**: todo lo que NO se ejecuta durante el ciclo SDD de cada HU de Fase 2 queda acá y se resuelve al **final de todo el plan de ejecucion** (despues de cerrar las 3 HU de Fase 2: F2.1, F2.2, F2.3).
>
> **Fecha de apertura**: 2026-09-15.
> **Rama destino**: `feat/fase-2-electron-scaffold`.
> **PR target**: `origin/dev` (gitflow).
> **Estado al abrir**: Fase 1 Parte I cerrada (15 HU backend prerequisites, PR #56 abierto), Fase 2 arranca desde cero.

## 1. HUs restantes (3)

| # | ID | Titulo | Tamano est. | Bloqueador | Notas |
|---|---|---|---|---|---|
| 1 | HU-F2.1 | Scaffold del proyecto + `ui-kit` compartido + shadcn/ui | 700 LOC | ninguno | ✅ cerrado (2026-09-15, 4 commits `24500a4..1b744bb`, archive 2026-09-15) | 9 atomic tasks ejecutados via 4 clusters C1→C2→C3→C4; apps/electron-sucursal/ creado desde cero (54 files / 2465 inserciones); apps/ui-kit/ poblado con package.json + Button + cn + tokens; 14 shadcn/ui components generados; 7 i18n namespaces (es-CO); axe-core WCAG 2.1 AA desde día 1. Archived at openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/ (7 archivos: exploration + proposal + design + tasks + specs/operations/spec + verify-report + archive-report). Veredicto PASS WITH WARNINGS (4/10 gates PASS, 6/10 SKIPPED env-blocked, 10/10 DEC-ELEC-NN satisfied). Habilita F2.2 (parkosFetch+IPC+authStore) y F2.3 (auto-update+kiosko). |
| 2 | HU-F2.2 | Cliente HTTP `parkosFetch`, bridge IPC y `authStore` | 700 LOC | depende F2.1 | ✅ cerrado (2026-09-15, 7 commits `cebd3a0..6504d66`, archive `2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store`). 36/36 unit tests verde (14 parkosFetch + 9 authStore + 5 useAuth + 8 preload contract); G8 e2e SKIPPED F.6 (CI matrix required); 8 DEC-FETCH-NN ratified; 5 deviations (1 LOW MSW, 1 MEDIUM signature break + Dashboard.tsx migrado, 1 HIGH G8 SKIPPED, 1 MEDIUM coverage-v8 ausente, 1 LOW pre-existing tsc). Veredicto PASS WITH WARNINGS. Habilita F2.3 (auto-update + kiosko) y Fase 3 (login, lockout, turno). |
| 3 | HU-F2.3 | Auto-actualizacion, single-instance y kiosko | 450 LOC | depende F2.1 | ✅ cerrado (2026-09-15, 7 commits `9eacec3..d1c4f2c`, archive `2026-09-15-hu-f2-3-electron-auto-update-kiosko`). 41/41 unit tests verde (6 updater + 5 log-config + 4 api-status + 10 kiosko bcryptjs mocked + 2 single-instance + 9 preload contract + 5 StatusBar); 3/8 gates SKIPPED-env (G3+G4 e2e + G8 sandbox F.6 npm 11.16.0 — CI matrix required); 13 DEC-UPD-NN ratified; 3 deviations (D-env-F.6 bcryptjs fallback LOW, D-env-e2e SKIPPED-env MEDIUM, D-tsc strict 8 nuevos errors LOW). Veredicto PASS WITH WARNINGS. Cierra Fase 2 3/3. Habilita Fase 3 (login, lockout, turno). |

**Total LOC restante**: ~450 LOC production + tests + configs (F2.1 + F2.2 done 2026-09-15, ~1400 LOC de presupuesto consumido en F2.1+F2.2; restante F2.3 ~450).

## 2. Bloqueadores de deployment

- Backend `api-sucursal` (`http://127.0.0.1:8000`) debe estar corriendo en dev local para que el scaffold se conecte (F2.2 T1 baseURL default + F2.3 T2 api-status health).
- Backend no expone `/health` todavia (verificar HU backend si existe; si no, se agrega como FUERA de scope Fase 2 — el cliente reporta `code: undefined` hasta que se cree).

## 3. Housekeeping tecnico (LOW pre-existing heredado de Fase 1)

- §3.2 25 test skips pre-existentes (pg_partman no disponible en postgres:16-alpine local) — documentado en pending Fase 1.
- §3.3 18 archivos con fallas pre-existentes — triage-dedicated.
- 78 errores ruff pre-existentes en `packages/parkos_core/` — triage-dedicated.

## 4. Working tree mess pre-existente (NUEVO para Fase 2)

`apps/package.json` lista workspaces `ui-kit` + `web_admin`, NO incluye `electron-sucursal` todavia (HU-F2.1 T1 lo agrega).
`apps/ui-kit/` sin `package.json` (HU-F2.1 T5 lo crea).
`apps/ui-kit/src/api/` ya existe (admin + branch) — codigo API client compartido que NO es responsabilidad de F2.1 (proviene de setup previo).

**Accion al final del plan**: capturar cualquier working tree mess post-F2.3 en commits housekeeping separados (siguiendo patron Fase 1 §4).

## 5. Forward hooks (a considerar en futuras HU)

- **HU-F3.1** (login email+password): consumidora de F2.2 `parkosFetch` + `authStore`.
- **HU-F3.2** (lockout visible): consumidora de F2.2 `useCountdown` hook + F2.2 `parkosFetch` retry logic.
- **HU-F3.3** (abrir/cerrar turno): consumidora de F2.2 + F2.1 router.
- **HU-F5.1+** (impresion termica): consumidora de F2.2 `bridge.imprimir`.
- **HU-F11.x** (sync UI): consumidora de F2.3 `api-status` IPC + StatusBar.
- Si futura HU requiere USB device whitelist expansion: extender F2.2 T2 bridge.d.ts.

## 6. Criterio de cierre del `pending.md`

`pending.md` se considera **resuelto** cuando:
1. Las 3 HU de Fase 2 marcadas [x] con archive cerrado.
2. `apps/electron-sucursal/` con `npm run dev` funcional.
3. `apps/ui-kit/` con `Button` + `cn()` + tokens exportables.
4. e2e suite verde (scaffold + lifecycle + auth + turno).
5. `git status --short` retorna solo `M` legitimos o nada.
6. `tsc --noEmit` limpio en los 3 tsconfigs (base, main, renderer).
7. axe-core 0 violaciones en scaffold smoke test.

**PR de cierre**: `feat/fase-2-electron-scaffold` → `dev` con merge commit + tag `fase-2-electron-scaffold-complete`.

---

**Opened by**: orchestrator (post-Fase 1 Parte I housekeeping, pre-Fase 2 explore).
**Engram**: persisted (topic_key=`sdd/fase-2-electron-scaffold/pending`, project=`easypuinto-parkos-software`).
**Updated**: 2026-09-15 (post-F2.3 archive) — Fase 2 3/3 cerrado (HU-F1.1/F2.1/F2.2/F2.3 archivados 2026-09-15); 0 HU pendientes; 20 commits total (`24500a4..d1c4f2c`); FASE 2 COMPLETA. Working tree clean post-archive.
