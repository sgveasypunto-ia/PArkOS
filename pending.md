# Pending — easypunto_parkos (Fase 3: Autenticación y turno de caja)

> **Archivo de tracking diferido**: todo lo que NO se ejecuta durante el ciclo SDD de cada HU de Fase 3 queda acá y se resuelve al **final de todo el plan de ejecucion** (despues de cerrar las 3 HU de Fase 3: F3.1, F3.2, F3.3).
>
> **Fecha de apertura**: 2026-09-15 (post-Fase 2 archive).
> **Rama destino**: `feat/fase-3-auth-turno` (new branch from `dev` post-PR merge of Fase 2).
> **PR target**: `origin/dev` (gitflow).
> **Estado al abrir**: Fase 1 Parte I cerrada (15 HU backend prerequisites, PR #56 abierto), Fase 2 cerrada (24 commits en `feat/fase-2-electron-scaffold`), Fase 3 arranca desde cero.

## 1. HUs restantes (1)

| # | ID | Titulo | Tamano est. | Bloqueador | Notas |
|---|---|---|---|---|---|
| 1 | HU-F3.1 | Login con `email` + `password` (anti-enumeración + cookie `httpOnly`) | 190 LOC | depende F2.2 backend endpoints | ✅ **CERRADO 2026-09-15** — 4 atomic commits `8961303..5fcfe66` archivados en `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` (~1008 net LOC production + tests). 7 new REQ-OPS-106..112 materialized al canonical `openspec/specs/operations/spec.md` (DELTA precedent — first user-facing DELTA en Fase 3, breaking F2.x NO-OP pattern). 5/7 gates PASS source-level + 2/7 SKIPPED-env (G6 e2e + G7 axe-core runtime) + 0 FAIL per F.6 precedent. |
| 2 | HU-F3.2 | Lockout visible (countdown) + refresh transparente (50min auto + pre-flight) | 130 LOC | depende F3.1 | ✅ **CERRADO 2026-09-15** — 4 atomic commits `850ed70..e3e04ac` archivados en `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` (+708/-31 net LOC production + tests + i18n + coverage). 6 new REQ-OPS-113..118 materialized al canonical `openspec/specs/operations/spec.md` (DELTA precedent — second user-facing DELTA en Fase 3, sigue F3.1 precedent). 5/7 gates PASS source-level + 2/7 SKIPPED-env (G6 e2e + G7 axe-core runtime) + 0 FAIL per F.6 precedent. `useCountdown` hook reusable (primer hook genuinely reusable del feature `auth`, forward F4.x/F5.x/F11.x) + countdown visible + form `disabled` durante lockout + auto re-enable al 0 + 50min SWR refresh + pre-flight gate `refreshIfExpiringSoon()` con Mutex F2.2 DEC-FETCH-03 preserved + WCAG 2.1 AA axe-core A1. |
| 3 | HU-F3.3 | Abrir / cerrar turno (caja-sesion con `valor_inicial_efectivo/datafono`) | 260 LOC | depende F3.1 | 5 atomic tasks T1..T5 (AbrirTurno page + CerrarTurno page placeholder + useSesionActiva SWR hook + rutas en App.tsx + e2e turno). Backend POST /caja-sesion/sesiones + GET /caja-sesion/sesion/me + PUT /caja-sesion/sesion/{uuid}/cerrar. 409 sesion_ya_abierta / sesion_ya_cerrada → mensajes claros. |

**Total LOC restante**: ~260 LOC production + tests + configs (Fase 2 done 2026-09-15, ~6265 LOC de presupuesto consumido en F2.1+F2.2+F2.3; restante Fase 3 ~260 — F3.1 ~190 ya consumido + F3.2 130 ya consumed; F3.3 ~260 pendiente).

## 2. Bloqueadores de deployment

- **Backend `api-sucursal` corriendo** en dev local (http://127.0.0.1:8000) — F2.2 baseURL default.
- **Backend `/auth/login` + `/auth/me`** — HU-F1.2 ya shipped (Fase 1 cerrada). Validar antes de F3.1 sdd-apply.
- **Backend `/caja-sesion/sesiones` + `/caja-sesion/sesion/me` + `/{uuid}/cerrar`** — verificar existencia en backend; si NO existe, agregar como FUERA de scope Fase 3 (degradar con mock MSW).
- **Backend `/health` endpoint** — sigue sin existir (F2.3 R2). F3 NO agrega este endpoint; cliente reporta 🔴 hasta que se cree (forward hook a F3.x backend).

## 3. Housekeeping tecnico (LOW pre-existing heredado de Fase 1 + Fase 2)

- §3.2 25 test skips pre-existentes (pg_partman no disponible en postgres:16-alpine local) — documentado en pending Fase 1.
- §3.3 18 archivos con fallas pre-existentes — triage-dedicated.
- 78 errores ruff pre-existentes en `packages/parkos_core/` — triage-dedicated.
- **Fase 2 NEW pre-existing baseline**:
  - 8 strict tsc errors F2.3-introduced (main.ts + kiosko.ts + kiosko.test.ts) — D-tsc LOW follow-up en F3.x backlog.
  - bcryptjs fallback en lugar de native bcrypt — D-env-F.6 LOW follow-up swap a native bcrypt cuando build pipeline tenga node-gyp + python.

## 4. Working tree mess pre-existente (NUEVO para Fase 3)

`apps/electron-sucursal/` poblado por Fase 2 (F2.1 + F2.2 + F2.3 — 24 commits, 4 servicios runtime + bridge IPC + StatusBar + authStore + parkosFetch + shadcn 14 components + 7 i18n namespaces + axe-core + 6 e2e specs).
`apps/ui-kit/` poblado por Fase 2 (Button + cn + tokens + useAuth + parkosFetch + authStore).

**Accion al final del plan**: capturar cualquier working tree mess post-F3.3 en commits housekeeping separados (siguiendo patron Fase 1 + Fase 2).

## 5. Forward hooks (a considerar en futuras HU)

- **HU-F4.x** (catálogos + ocupación en vivo): consume F2.2 `parkosFetch` + F3.3 `useSesionActiva`.
- **HU-F5.1+** (impresión térmica): consume F2.2 `bridge.imprimir` + F2.3 kiosko mode (compatible).
- **HU-F6.x** (ingreso vehicular CU-01): consume F3.3 turno activo + F4.x catálogos.
- **HU-F7.x** (salida + cálculo tarifa CU-02/03): depende de F6.x.
- **HU-F8.x** (cobro + FE CU-04/05): depende de F7.x.
- **HU-F9.x** (suscripciones CU-06): depende de F8.x.
- **HU-F10.x** (arqueos + cierre CU-10): F3.3 deja CerrarTurno placeholder, F10.x completa arqueo.
- **HU-F11.x** (sync UI + alertas CU-07/14): consume F2.3 `bridge.apiStatus.get` + StatusBar.
- **HU-F12.x** (reportería local CU-09 subset): depende de F3.3 turno cerrado.

## 6. Criterio de cierre del `pending.md`

`pending.md` se considera **resuelto** cuando:
1. Las 3 HU de Fase 3 marcadas ✅ con archive cerrado.
2. `apps/electron-sucursal/src/features/auth/{pages,hooks}/` poblado.
3. `apps/electron-sucursal/src/features/caja/{pages,hooks}/` poblado.
4. e2e suite verde (login + lockout + turno, sin regresiones en scaffold + auth + lifecycle).
5. `git status --short` retorna solo `M` legitimos o nada.
6. `tsc --noEmit` limpio en los 3 tsconfigs (base, main, renderer) — exceptuando baseline pre-existing + 8 strict tsc F2.3-introduced documentados.
7. axe-core 0 violaciones en Login + StatusBar + scaffold smoke test.
8. authStore hidrata desde `/auth/me` con `credentials:'include'`.
9. cookie `httpOnly` configurada en backend + browser respeta.

**PR de cierre**: `feat/fase-3-auth-turno` → `dev` con merge commit + tag `fase-3-auth-turno-complete`.

---

**Opened by**: orchestrator (post-Fase 2 archive, pre-Fase 3 explore).
**Engram**: persisted (topic_key=`sdd/fase-3-auth-turno/pending`, project=`easypuinto-parkos-software`).
**Updated**: 2026-09-15 (post-F3.2 archive + Fase 3 HU-2 cierre) — Fase 2 3/3 cerrado (HU-F1.1/F2.1/F2.2/F2.3 archivados 2026-09-15); **Fase 3 2/3 cerrado (HU-F3.1 archivado 2026-09-15, HU-F3.2 archivado 2026-09-15, F3.3 pendiente)**; 32 commits total Fase 2+F3.1+F3.2 (`24500a4..18a34b2`); 4 atomic commits F3.1 (`8961303..5fcfe66`) + 4 atomic commits F3.2 (`850ed70..e3e04ac`) + 2 housekeeping commits (`57a7a43` F3.1 materialize + `18a34b2` F3.2 materialize); `apps/ui-kit/` poblado con `parkosFetch` + `authStore` + `useAuth` con 50min refresh (F2.2 + F3.2 T3); `apps/electron-sucursal/` bridge IPC + preload whitelist (F2.2) + 4 servicios runtime (updater + log-config + api-status + kiosko) + StatusBar (F2.3) + `features/auth/` con `Login` + `LoginForm` + `loginApi` + `loginSchema` + `useCountdown` hook + countdown integration (F3.1 + F3.2) + ruta `/login` (F3.1 T3). Working tree clean post-archive.
