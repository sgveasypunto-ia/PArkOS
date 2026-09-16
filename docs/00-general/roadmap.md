# easypunto_parkos — Roadmap

> Base del plan: `openspec/_meta/roadmap.md` y `openspec/_meta/iteration-plan.md`
> (documentos de planeación temprana, generados 2026-08-30, organizados en
> "vertical slicing": fases F0-F2 de fundación + iteraciones IT-1 a IT-12,
> cada una atómica y cruzando todos los componentes: UI admin, UI sucursal,
> API admin, API sucursal, sync y DB).
>
> **Este documento no repite ese plan: lo contrasta contra el código, los
> routers, las páginas de frontend y el historial de commits reales**, a
> fecha 2026-09-10, rama `feature/motor_sync_correcciones_integridad`.
> Metodología al final del documento.

## Resumen ejecutivo

El plan original asumía que cada iteración (IT-1…IT-12) se entregaría como
una rebanada vertical completa (las dos UIs + las dos APIs + sync + DB). En
la práctica, la ejecución real tomó otra forma:

- El **backend** avanzó muy por delante del plan original: casi todos los
  routers de negocio de las fases 1 a 5 ya existen, entregados como dos
  cambios grandes (`create-49-table-apis` y luego `sync-overhaul`) en lugar
  de 12 iteraciones independientes.
- El **motor de sincronización** fue reescrito por completo en un cambio
  (`sync-overhaul`) que el plan original no contemplaba en este nivel de
  detalle (catálogo declarativo, grafo de dependencias, motor genérico por
  hooks). Ver [`openspec/changes/archive/2026-09-09-sync-overhaul/`](../../openspec/changes/archive/2026-09-09-sync-overhaul/).
- El **frontend** quedó muy por detrás: `apps/web_admin` tiene solo dos
  páginas (`Login`, `Dashboard`) y `web_sucursal` **no existe** como
  aplicación. Por lo tanto, ninguna iteración cumple hoy la definición
  estricta de "atómica y cruza las dos UIs" — todas quedan como máximo en
  **Parcial**.

| Estado | Significado |
|---|---|
| ✅ Hecho | La evidencia de código cubre el alcance descrito en el plan |
| 🟡 Parcial | Backend/API/DB cubren parte o todo el alcance; falta UI (una o ambas), o el alcance se entregó de forma distinta a la planeada |
| ⬜ No iniciado | Sin evidencia de código |

## Estado en una mirada

| Fase / Iteración | Alcance planeado | Estado | Evidencia clave |
|---|---|---|---|
| **F1** — Esqueleto de fundación | Schema, Docker, Alembic, `/health`, JWT stub | ✅ Hecho | `backend/packages/parkos_core/migrations/versions/`, commits `e6b729d`, `ab1c3c5`; `openspec/scripts/check_schema_match.py` en 100% |
| **F2** — Building blocks | Stubs DIAN/sync, JWT 3 emisores, `infra/sync_policy.yaml`, `apps/ui-kit` | ✅ Hecho (luego superado por `sync-overhaul`) | `backend/packages/parkos_core/src/parkos_core/dian/`, `.../sync/`, `apps/ui-kit/` (scaffold) |
| **IT-1** — Login end-to-end | Login admin + operador, ambas UIs, sync de usuarios | 🟡 Parcial | Backend real: `api/v1/auth.py` (`POST /auth/login`, `/refresh`, `/logout`). `apps/web_admin/src/pages/Login.tsx` es un **placeholder explícito** ("PR10c will wire the actual admin-issuer JWT flow"). `web_sucursal` no existe |
| **IT-2** — Sucursales CRUD + pairing | CRUD sucursales, token de pairing, `PairingWizard` en sucursal | 🟡 Parcial | Backend: `api/v1/sucursal.py`, `api/v1/pairing.py`; pairing cerrado y probado (`AGENTS.md` — "Pairing-token replay CLOSED by PR8a/b/c", `tests/integration/test_pairing_flow.py`, 9 escenarios). No se encontró UI de CRUD de sucursales ni `PairingWizard` (no hay app de sucursal) |
| **IT-3** — Ingreso de vehículo | Formulario sucursal, endpoint, sync, listado admin | 🟡 Parcial | Backend: `api/v1/operacion.py` + tabla `ingreso` (commit `1b1061e`). No se confirmó UI en `web_admin` (solo existen las páginas `Login` y `Dashboard`) ni en sucursal (no existe la app) |
| **IT-4** — Salida de vehículo | Simétrico a IT-3, tabla `salidas` `[A]` | 🟡 Parcial | Mismo router `operacion.py`; tabla `salidas` presente en el modelo. UI no confirmada |
| **IT-5** — Facturación (cloud-first + sync-back) | Facturación online/offline, despachador DIAN | 🟡 Parcial (backend avanzado) | `api/v1/facturacion.py`, `dian/cloud/{dispatcher.py,ubl_serializer.py,atomic_next_consecutivo.py,dian_providers/factus.py}`; reverso de pagos con índice único (`tests/unit/test_factura_pagos_reverse.py`). UI no confirmada |
| **IT-6** — Anulación de ingreso | Workflow `solicitada → aprobada → ejecutada` | 🟡 Parcial | Router `api/v1/workflows.py` cubre workflows genéricos (no se abrió el detalle de cada endpoint en esta pasada). UI no confirmada |
| **IT-7** — Alertas operacionales | Alertas por arqueo y por caída de sync | 🟡 Parcial | `api/v1/caja.py` + `api/v1/caja_sesion.py` (arqueo); tabla `alerta` `[L-W]` en el modelo. UI no confirmada |
| **IT-8** — Reclamos | Workflow `abierto → en_revision → resuelto/rechazado` | 🟡 Parcial | Cubierto presumiblemente por `api/v1/workflows.py`; no se abrió el detalle de endpoints. UI no confirmada |
| **IT-9** — Reimpresión de ticket | Workflow gateado por evento de sync-back | 🟡 Parcial | Ídem `workflows.py`. UI no confirmada |
| **IT-10** — Subscripciones + vehículos | CRUD clientes/subscripciones/vehículos | 🟡 Parcial | Backend: `api/v1/clientes.py`. Sin UI admin (no existe página de clientes en `web_admin`, solo `Login`/`Dashboard`) |
| **IT-11** — Reportes admin | Agregaciones cross-branch (diaria/semanal/mensual) | 🟡 Parcial | `api/v1/admin_views.py` expone un dashboard con métricas por sucursal (`ingresos_count`, `facturas_emitidas_count`, `open_alertas_count`, salud de sync), consumido por `Dashboard.tsx`. No se encontró un router `reportes` dedicado a agregaciones por período |
| **IT-12** — Verificador de cadena de hash + auditoría | Worker nocturno independiente + `AuditDashboard` | 🟡 Parcial | La verificación de cadena de hash existe pero como rutina dentro de `job_sync_cloud` (`hash_chain_verifier_loop`, `AGENTS.md`), no como worker independiente `workers/hash_chain_verifier` tal como lo describía el plan. No existe página `AuditDashboard` en `web_admin` |

## Trabajo relevante no contemplado en el plan original

### Reescritura del motor de sincronización (`sync-overhaul`)

El plan de iteraciones no anticipaba el nivel de rediseño que recibió el
motor de sync. Un cambio completo (`sync-overhaul`, archivado en
`openspec/changes/archive/2026-09-09-sync-overhaul/`, `design.md` +
`proposal.md`) reemplazó el motor original por uno **catalog-driven**:

- Catálogo declarativo de sincronización (`sync/catalog/`) y grafo de
  dependencias (`sync/catalog/dependency_graph.py`).
- `SyncMotor` genérico con ciclo de vida por hooks (identidad, suscripción,
  cascada de placa, compensación bi-temporal).
- Hooks de cadena de hash + `verify_chain` con bootstrap real de la fila
  génesis; resolución de conflictos; numeración DIAN local en sucursal.
- Triggers de catálogo en 18 tablas `[V]`; el canon ER se actualizó a
  **51/54** tablas en este mismo trabajo.
- Corte de ambos workers (`jobs/sync_cloud.py`, `jobs/sync_sucursal.py`) al
  nuevo motor, protocolo dual vía `GET /sync/hello`.
- Observabilidad (métricas, logs estructurados, redacción de PII, alertas
  Grafana), evaluador de stage-gates y script de reversión idempotente.
- Ejercicio end-to-end sobre las 46 tablas de catálogo (corrigió 6 bugs
  reales de sincronización y un flake de JWT) antes de archivar el cambio.

### Correcciones de integridad post-`sync-overhaul` (rama actual)

La rama activa al momento de este documento,
`feature/motor_sync_correcciones_integridad`, **todavía no está mergeada a
`dev`** y contiene 21 commits adicionales de corrección sobre el motor
recién reescrito: orden de la cadena de hash por `created_at`, parseo
ISO-8601 de `timestamp_evento`, `/sync/pull` genérico real (dejó de ser
stub), UUIDs determinísticos para catálogos (permisos, `tipo_persona`,
`empresa`), partición `DEFAULT` para `pairing_tokens`/`revoked_sync_jwts`,
extensión de la reconciliación de identidad a 20 tablas de catálogo más, y
—el commit más reciente— la aplicación deja de conectarse como
superusuario y pasa a un rol de mínimo privilegio real. Ver
[`changelog.md`](./changelog.md) para el detalle commit por commit.

## Huecos y "Por definir"

- **`web_sucursal` no existe**: toda funcionalidad operativa de sucursal
  (ingreso, salida, facturación, alertas propias, reclamos) depende de una
  app que aún no tiene código. Fuente: verificado con Glob sobre `apps/`.
- **`apps/ui-kit`** tiene el scaffold de cliente API (`src/api/{admin,branch}/generated/`)
  pero la generación aún no corrió (solo hay `.gitkeep`).
- **Router de reportes dedicado (IT-11)**: no se encontró un
  `api/v1/reportes.py` ni equivalente con agregaciones diaria/semanal/mensual;
  solo el dashboard de una sucursal a la vez en `admin_views.py`.
- **`AuditDashboard` (IT-12)**: sin evidencia de código en `web_admin`.
- **Detalle de `workflows.py`**: se confirmó la existencia del router, pero
  esta pasada no abrió su contenido completo para distinguir qué combinación
  exacta de `anulaciones` / `reclamos` / `alerta` / `reimpresion_ticket`
  (IT-6, IT-7 parcial, IT-8, IT-9) ya tiene endpoint propio. Queda pendiente
  una pasada más profunda si se necesita precisión endpoint por endpoint.
- **Cobertura de tests por iteración**: se verificó la existencia
  estructural de routers/páginas/tablas, no la ejecución de la suite de
  pruebas ni el cumplimiento de cada tarea RED de `iteration-plan.md` una
  por una. Ver [`../04-qa-testing/plan-pruebas.md`](../04-qa-testing/plan-pruebas.md)
  para el estado de testing.
- **Preguntas abiertas heredadas del plan original** (`iteration-plan.md`),
  aún vigentes salvo que `../02-arquitectura/decisiones-tecnicas.md` indique
  lo contrario: formato `PRE-<uuid-8>` para numeración preliminar; DIAN
  provider real más allá del stub/Factus; soporte multi-país (diferido);
  WebSocket vs. polling (se mantiene polling para todo el MVP).

## Metodología de verificación

Para cada iteración se buscó evidencia de código con
`mcp__codegraph__codegraph_explore` (routers de `api_admin`/`api_sucursal`,
páginas de `web_admin`, workers) y se confirmaron rutas puntuales con
`Glob` sobre `backend/packages/parkos_core/src/parkos_core/api/v1/*.py`,
`apps/web_admin/src/pages/*.tsx`, `backend/.../jobs/*.py` y
`backend/.../dian/**/*.py`. El historial de commits (`git log`, 82 commits)
se usó para fechar y agrupar el trabajo real por tema — ver
[`changelog.md`](./changelog.md). No se ejecutó la suite de pruebas ni se
levantó el stack con Docker como parte de esta verificación.
