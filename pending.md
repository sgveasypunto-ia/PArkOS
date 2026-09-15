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
| 1 | HU-F2.1 | Scaffold del proyecto + `ui-kit` compartido + shadcn/ui | 700 LOC | ninguno | 9 atomic tasks (T1..T9). Crea `apps/electron-sucursal/` desde cero. `apps/ui-kit/` existe como directorio pero sin `package.json` ni `Button`/`cn`/`tokens` — T5 los pobla. |
| 2 | HU-F2.2 | Cliente HTTP `parkosFetch`, bridge IPC y `authStore` | 450 LOC | depende F2.1 | 7 atomic tasks (T1..T7). 14 + 8 escenarios MSW + axe-core. |
| 3 | HU-F2.3 | Auto-actualizacion, single-instance y kiosko | 450 LOC | depende F2.1 | 7 atomic tasks (T1..T7). 3 e2e (segunda instancia, kiosko Ctrl+W, PIN incorrecto). |

**Total LOC restante**: ~1600 LOC production + tests + configs.

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
**Updated**: 2026-09-15 — Fase 2 arranque; 3 HU pendientes (F2.1, F2.2, F2.3); `apps/electron-sucursal/` por crear; `apps/ui-kit/` por poblar.
