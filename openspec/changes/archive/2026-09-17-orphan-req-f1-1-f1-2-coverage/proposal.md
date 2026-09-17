# Proposal: REQ-OPS huérfanos HU-F1.1 + HU-F1.2

> **Change**: `2026-09-17-orphan-req-f1-1-f1-2-coverage`
> **Phase**: proposal (sdd-propose)
> **Capability**: operations
> **Date**: 2026-09-17
> **Author**: orchestrator
> **Status**: approved

## Intent

Materializar 2 REQ-OPS-NNN en el canon `openspec/specs/operations/spec.md` que cierran HU-F1.1 (router_factory fix) y HU-F1.2 (`GET /auth/me` + cookie httpOnly + lockout real desde `configuracion_seguridad.minutos_bloqueo_login`).

Las 2 HU fueron declaradas en `plan.md` (Fase 1) y su código está implementado y verificado, pero el spec canon nunca recibió la materialización formal del comportamiento — el audit Fase 1 (2026-09-17) lo identificó como gap real.

## Scope

**In scope:**
- 2 REQ-OPS nuevos: REQ-OPS-141 (router_factory guard) + REQ-OPS-142 (`/auth/me` + cookie + lockout)
- 1 entrada nueva en la sección `## ADDED Requirements` del canon (después de `operador-dashboard-hub`)
- 1 commit atómico con delta spec + canon merge

**Out of scope:**
- Cualquier cambio de código (los fixes ya están en `f7cb37a` y `auth.py` respectivamente)
- Tests nuevos (los existentes cubren el comportamiento — ver rationale)
- Otras HU Fase 1 sin cobertura (si las hay)

## Approach

Trabajo documental puro. NO tocar código. El flow es:

1. `proposal.md` (este archivo)
2. `design.md` (corto — el comportamiento ya está implementado, no hay decisiones técnicas)
3. `specs/operations/spec.md` (delta con 2 REQs)
4. `tasks.md` (3 tasks triviales)
5. Aplicar: merge delta al canon + commit
6. `verify-report.md` (trivial — grep verification)
7. `archive-report.md`

## Rationale

**HU-F1.1 (router_factory fix):**
- `plan.md` líneas 567-595 declaran el bug: `stmt.order_by(model_cls.vigente_desde.desc(), model_cls.uuid.asc())` sin `hasattr` guard rompe listados de tablas `[L-W]` (`alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket`).
- Fix verificado en código: `backend/.../api/router_factory.py` líneas 17, 22, 52, 76, 84, 178, 182, 193, 246 — todos con `hasattr(model_cls, "vigente_desde")` / `hasattr(model_cls, "vigente_hasta")` guards + `_order_key(model_cls)` helper compartido.
- `factory_intact` CI gate en `openspec/scripts/check_schema_match.py` referencia el commit `f7cb37a` (fix original).
- Estado: comportamiento entregado y verificado, REQ-OPS formal ausente. Gap real.

**HU-F1.2 (`/auth/me` + cookie + lockout):**
- `plan.md` líneas 597-653 declaran: `POST /auth/login` setea cookie `parkos_session` httpOnly/secure/samesite=lax + access_token Bearer; `GET /auth/me` devuelve user/permisos/sucursal/sucursales_permitidas/expires_at; 5 intentos fallidos → 429 con `Retry-After` desde `configuracion_seguridad.minutos_bloqueo_login`.
- Fix verificado en código:
  - `auth.py:148` POST /auth/login + `auth.py:175` cookie `httponly=True, secure=True, samesite="lax"`
  - `auth.py:291-294` `response.set_cookie(...)` con `httponly=True`
  - `auth.py:419` GET /auth/me → `AuthMeResponse`
  - `auth.py:12-15, 81-99` lockout desde `configuracion_seguridad.minutos_bloqueo_login` (default 15 min) → `429 account_locked` con `Retry-After: minutos*60`
- `models/V/configuracion_seguridad.py:39` columna `minutos_bloqueo_login: Mapped[int | None]` sembrada en MIGRATION 0001
- Estado: comportamiento backend entregado (frontend F3.1 cubre la UI con REQ-OPS-106..112 ya materializados). El contrato backend (cookie + lockout) no tiene REQ-OPS formalizado. Gap real, separado del frontend.

## Risk

**Bajo.** Cero código modificado. El canon merge es aditivo (2 secciones nuevas al final + 1 entrada en `## ADDED Requirements`). Si los REQs son imprecisos, el fix siguiente iteración puede corregirlos sin reescribir comportamiento. No hay riesgo de regresión.

## Forward hooks

- Cualquier verify futuro de Fase 1 puede ahora cruzar HU-F1.1 y HU-F1.2 contra REQ-OPS-141 y REQ-OPS-142 sin marcar gap.
- El audit 2026-09-17 identifica REQ-OPS-141..142 como materialización estructural; ningún plan posterior los referencia explícitamente.

## Acceptance criteria

1. `openspec/specs/operations/spec.md` contiene `### Requirement: REQ-OPS-141` y `### Requirement: REQ-OPS-142` después del REQ-OPS-140 existente
2. La sección `## ADDED Requirements` del canon incluye la línea `## ADDED Requirements (delta: 2026-09-17-orphan-req-f1-1-f1-2-coverage, REQ-OPS-141..142)`
3. `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/` tiene los 7 artifacts del flow SDD
4. Commit en `feature/orphan-req-f1-1-f1-2-coverage`, merge a `dev` con `--no-ff` per AGENTS.md gitflow regla #8