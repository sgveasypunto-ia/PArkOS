# TODO Fase 1 — easypunto_parkos (Parte I)

> Tracking de las 15 HU de Fase 1 sobre la rama `feat/fase-1-prerequisites-backend`.
> Cada HU cierra con: commit atómico, reporte (`HU-F1.X-report.md`), observación Engram.
> Marca de estado: `[ ]` pendiente · `[~]` en curso · `[x]` cerrada · `[!]` bloqueada.

## Estado actual

- **Rama:** `feat/fase-1-prerequisites-backend`
- **Base:** `origin/dev` + merge de `feature/motor_sync_correcciones_integridad` (22 commits) + 1 commit pre-Fase-1 (bcrypt real en login)
- **Commits en rama antes de Fase 1:** 23 (1 merge + 22 absorbidos + 1 pre-Fase-1)
- **PR target:** contra `origin/dev` (gitflow)

## HUs (15)

| # | ID | Título | Tamaño est. | Estado | Commit | Reporte | Notas |
|---|---|---|---|---|---|---|---|
| 1 | HU-F1.1 | router_factory.py: orden sin `vigente_desde` para workflows | 60 LOC | `[x]` | `f7cb37a` | `HU-F1.1-report.md` (a generar al cerrar Fase 1) | GAP-BE-02 + cascada a Caja/Arqueo/Sesion |
| 2 | HU-F1.2 | GET /auth/me, cookie httpOnly, lockout real | 210 LOC | `[x]` | `535676d` | `artifacts/HU-F1.2-report.md` | commit: feat(backend): cerrar HU-F1.2 — cookie parkos_session + lockout real + GET /auth/me. 21 tests, 0 CRITICAL |
| 3 | HU-F1.3 | Constraint sesión única + GET /caja-sesion/sesion/me | 110 LOC | `[x]` | `4d530a4` (docs) + `ca3f9bf` (código) + `467b4f0` (archive) | `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/archive-report.md` | migration 0023 (post-0022 ya consumido por F1.8). Defense in depth completa: BD partial unique index `prod.uq_prod_sesion_one_active_per_user` con `CONCURRENTLY` + pre-flight `DO $$`; repo `session_cycle.open_session` captura `IntegrityError` por pgcode `23505` → re-emite `SesionAlreadyActive`; handler `open_sesion` mapea 409 `{"error":"sesion_already_active"}` (pgcode nunca expuesto); handler `get_my_sesion` registrado ANTES del `include_router(make_router(...))` con `_sesion_issuer_dep = requires_issuer("operador-", "admin-")` y 404 `sesion_no_active`. Helper puro `repo/sesion_activa.get_sesion_activa` (+48 LOC) reusable. REQ-OPS-026..029 merged en `openspec/specs/operations/spec.md`. verify-report PASS (0 CRITICAL/HIGH/MEDIUM, 2 LOW pre-existing housekeeping). 7/7 tests GREEN. Siguiente sugerida: F1.5 (160 LOC, no bloqueada por KD-IVA). |
| 4 | HU-F1.4 | Filtro vigente_en en tarifas_sucursal | 60 LOC | `[x]` | `de4d2fc` (código) + `3844524` (docs) + `22b8db6` (archive) | `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/archive-report.md` | solo backend, openspec canónico, REQ-OPS-017..021 mergeados en `openspec/specs/operations/spec.md`. verify-report PASS (0 CRITICAL/HIGH/MEDIUM).
| 5 | HU-F1.5 | mv_ocupacion_diaria + GET /operacion/ocupacion | 160 LOC | `[ ]` | — | — | migración nueva + scheduler |
| 6 | HU-F1.6 | Validaciones reales en POST /operacion/ingresos | 260 LOC | `[ ]` | — | — | depende F1.5 (cupo) + F1.4 (tarifa) |
| 7 | HU-F1.7 | POST /operacion/salidas (rotación + mensualidad) | 220 LOC | `[ ]` | — | — | depende F1.8 (cotización) |
| 8 | HU-F1.8 | calcular_cotizacion + GET /operacion/cotizar | 200 LOC | `[x]` | `9ebaed6` (docs) + `a3d0c39` (código) + `7682a57` (archive) | `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/archive-report.md` | PL/pgSQL VOLATILE (Postgres rechaza FOR SHARE en STABLE, AST walk preserva read-only). REQ-OPS-022..025 merged en openspec/specs/operations/spec.md. REQ-OPS-025 reconciliado. KD-IVA deployment blocker (impuestos.IVA siembra, ownership HU-F14.2 Parte II). verify-report PASS (0 CRITICAL/HIGH/MEDIUM, 2 LOW). 7/7 tests GREEN. |
| 9 | HU-F1.9 | Facturación transaccional + NIT módulo 11 | 330 LOC | `[ ]` | — | — | depende F1.8 |
| 10 | HU-F1.10 | Numeración FE + estado DIAN + reintento | 230 LOC | `[ ]` | — | — | assign_consecutivo ya existe |
| 11 | HU-F1.11 | Workflow reimpresión tiquete (crear + anular) | 170 LOC | `[ ]` | — | — | gap huérfano: anulación |
| 12 | HU-F1.12 | Venta atómica de suscripción | 260 LOC | `[ ]` | — | — | ampliación producto, no CU literal |
| 13 | HU-F1.13 | Endpoints arqueo + siembra cierre_dia | 240 LOC | `[ ]` | — | — | GAP-BE-05 (permiso mal) bundleado acá |
| 14 | HU-F1.14 | GET /sync/estado + 11 alert_types nuevos | 120 LOC | `[ ]` | — | — | 8 técnicos ya existen |
| 15 | HU-F1.15 | GET /usuarios/{uuid}/login histórico | 70 LOC | `[ ]` | — | — | gap huérfano |

## Notas operativas

- **Branch:** pushear al final de cada HU (`git push origin feat/fase-1-prerequisites-backend`).
- **Cada HU:** un sub-agente fresco, fresh context, summary de 5-8 líneas + 5 checks `[OK]`.
- **Verificación externa:** el orquestador valida cada entrega con los 5 checks del prompt §4.3 antes de pushear.
- **Gaps transversales absorbidos en la rama:**
  - GAP-BE-02 (router_factory) → lo cierra HU-F1.1 (mejora además Caja/Arqueo/Sesion por el fix genérico).
  - GAP-BE-05 (permiso mal asignado) → bundleado en HU-F1.13.
  - GAP-BE-06 (rol parkos_app) → ya cerrado en el merge de `feature/motor_sync_correcciones_integridad` (commit `5edb317`).
- **Conventional Commits:** mensajes en español neutral, sin `Co-authored-by:` ni AI trailers.
- **Tope por commit:** <800 LOC (regla `config.yaml rules.tasks`).

## Riesgos vivos a monitorear

- `router_factory.py` ya tenía fix parcial (commit `dd500c2`) para binding PEP 563, pero el bug de `vigente_desde` sin guarda sigue presente (lo cierra HU-F1.1).
- `costos_servicios` necesita un row con concepto='reimpresion' sembrado para HU-F1.11 — verificar al implementar.
- `configuracion_seguridad` no tiene row default global sembrado — verificar al implementar HU-F1.2.
- `impuestos.IVA` necesita estar sembrado para HU-F1.8 (`iva_no_configurado`).
- `tipo_arqueo.cierre_dia` requiere siembra explícita (HU-F1.13).
- `alert_types` ya tiene 8 sembrados (técnicos); HU-F1.14 añade 11 (negocio) — total 19, idempotente.
