# HU-F15.2 — Empresa: card + página con tabs — proposal

## Why

Empresa es un singleton tenant-global (no se filtra por sucursal) que ya tiene
endpoint funcional `GET/POST/PUT /api/v1/empresa/empresa` pero **cero UI**.
Las columnas editables — `nombre`, `nit`, `mensaje_bienvenida`,
`mensaje_salida`, `regimen` (`modelo_datos_er.mmd:291-312`) — se editan hoy
solo por SQL. Sin superficie en el admin, un cambio de NIT o de mensaje de
ticket requiere un deploy.

`plan.md:3537-3569` ya enuncia HU-F15.2 con el mismo alcance. Esta propuesta
lo aterriza con la decisión de ubicación cerrada en `exploration.md`
(HomeHub card) y con un detalle de implementación ajustada a la convención
real del repo (`features/empresa/`, no `features/parametrizacion/` como dice
el plan).

## What changes

1. **Card Empresa en HomeHub** al lado de Sucursales y Catálogos.
2. **Nueva ruta `/empresa`** en el grupo global (auth required, no branch
   required) → `<EmpresaPage>` con tabs `Datos · Mensajes · Bitácora`.
3. **Feature folder `features/empresa/`** con `pages/`, `api/`, `hooks/`,
   `components/`, `schemas/` siguiendo el molde de `features/sucursales/`.
4. **NIT validator módulo 11** (`src/lib/validation/nit.ts`) — mismo
   algoritmo que el backend, para no aceptar en cliente lo que el server va a
   rechazar (BR1 de HU-F15.2).
5. **HashChainStatus** badge verde/rojo (`src/components/`) — reutilizado
   también por Fase 20 según `plan.md:3552`.
6. **i18n keys nuevos** en `es-CO.json` + tests.

## Archivos a tocar

### Nuevos
- `apps/web_admin/src/features/empresa/pages/EmpresaPage.tsx` — el contenedor
  con `<Tabs>` (3 tabs).
- `apps/web_admin/src/features/empresa/pages/EmpresaPage.test.tsx`.
- `apps/web_admin/src/features/empresa/components/EmpresaDatosTab.tsx` —
  form: nombre, nit (con validación módulo 11 inline), regimen.
- `apps/web_admin/src/features/empresa/components/EmpresaMensajesTab.tsx` —
  textareas para `mensaje_bienvenida`, `mensaje_salida` + preview de ticket.
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.tsx` —
  lista de cambios con `HashChainStatus`.
- `apps/web_admin/src/features/empresa/api/empresaApi.ts` — GET (singleton,
  sin uuid), PUT close+insert.
- `apps/web_admin/src/features/empresa/api/empresaSchema.ts` — Zod
  `EmpresaUpdate` (solo campos editables).
- `apps/web_admin/src/features/empresa/hooks/useEmpresa.ts` — SWR singleton.
- `apps/web_admin/src/lib/validation/nit.ts` + `.test.ts` — módulo 11.
- `apps/web_admin/src/components/HashChainStatus.tsx` + `.test.tsx`.
- `apps/web_admin/e2e/empresa.spec.ts` — 2 escenarios (happy + NIT inválido).

### Modificados
- `apps/web_admin/src/pages/HomeHub.tsx:34-51` — agregar 3ª entry `empresa`
  (`/empresa`, ícono `Building`/`Briefcase`).
- `apps/web_admin/src/pages/HomeHub.test.tsx:52-67` — H2 → 3 cards; H3
  parametrizar para que no haya que tocar al agregar la próxima.
- `apps/web_admin/src/App.tsx:89-92` — agregar `<Route path="/empresa">` en
  el grupo global (auth, no branch).
- `apps/web_admin/src/i18n/locales/es-CO.json` — namespace `empresa` (title,
  subtitle, tabs labels, validation messages) + `homeHub.empresa.*` + `nit.*`.

### NO se tocan
- `apps/web_admin/src/lib/admin-sections.ts` (Empresa NO va al sidebar).
- `apps/web_admin/src/components/chrome/AdminChrome.tsx`.
- `apps/web_admin/src/pages/Dashboard.tsx` (métricas branch-scoped, no aplica).

## Orden de tareas (1 PR; ~230 LOC alineado con `plan.md`)

1. **T1** — `src/lib/validation/nit.ts` con tests unitarios (algoritmo módulo
   11, casos borde: NIT con/sin DV, formato `XXXXXXXXX-Y`). Sin acoplamiento
   a React.
2. **T2** — `features/empresa/api/empresaApi.ts` + `empresaSchema.ts` +
   `hooks/useEmpresa.ts` (GET singleton con SWR key estable, PUT que pasa por
   el close+insert del backend). Sin UI todavía.
3. **T3** — `features/empresa/pages/EmpresaPage.tsx` skeleton + los 3 tab
   containers vacíos con `<Tabs>` del UI kit + tests de render (testids
   `empresa-tab-{datos,mensajes,bitacora}`).
4. **T4** — `EmpresaDatosTab` con el form real (nombre, nit, regimen),
   integración con `useEmpresa` + `empresaApi.put`. Validación NIT inline.
   `EmpresaMensajesTab` con los textareas + preview de ticket (placeholder,
   no toca `web_sucursal`).
5. **T5** — `EmpresaBitacoraTab` + `HashChainStatus` (consulta
   `log_transaccional` filtrado por `tabla='empresa'`).
6. **T6** — Card en `HomeHub.tsx` + actualizar `HomeHub.test.tsx` H2/H3.
   Ruta en `App.tsx`. i18n keys.
7. **T7** — `e2e/empresa.spec.ts` (2 escenarios: editar y guardar; NIT
   inválido → error inline con detalle del DV).

## Decisión abierta (cerrada en exploration.md §9)

Card en **HomeHub**, no en sidebar. Razón corta: Empresa es tenant-global
igual que Catálogos y la card debe estar visible apenas el admin aterriza
post-login; `AdminChrome` solo monta dentro de `<RequireSucursal>`, así que
meterla ahí la escondería antes de elegir sucursal.

## Tradeoffs

- **HomeHub vs sidebar**: cerramos HomeHub (exploración §9). El tradeoff
  residual: si el operador entra a `/dashboard` no ve Empresa en la nav — la
  descubre por la card en `/`. Aceptable porque HomeHub es la landing
  post-login obligatoria y cualquier operador vuelve a `/` con un click en el
  brand.
- **Tabs en EmpresaPage vs sub-rutas** (`/empresa/datos`, `/empresa/mensajes`,
  `/empresa/bitacora`): elegimos tabs porque Empresa es singleton (no hay
  deep-link a "un elemento" como pasa con Catálogos/Sucursales). El estado de
  tab activo vive solo en memoria; si más adelante hace falta URL state se
  migra a `useSearchParams` sin romper el contrato. Costo: un deep-link a
  `/empresa` siempre abre "Datos" (default tab).
- **NIT validator en cliente**: duplica lógica con el backend (BR1).
  Justificación: UX (feedback inmediato sin round-trip) + el server
  re-valida igual (defense in depth). El test pinning de `nit.ts` evita que
  la copia local diverja del backend.
- **HashChainStatus como componente compartido**: el plan dice
  "reutilizado también en Fase 20". Lo creamos en `src/components/` (no en
  `features/`) desde el día 1 para que la Fase 20 lo importe directo.
- **`features/empresa/` vs `features/parametrizacion/` del plan**: divergencia
  con `plan.md:3566`. Decidimos `features/empresa/` por consistencia con la
  convención del repo (`features/<recurso>/`). Nota en
  `openspec/specs/spec.md` (o un changelog del plan) al cerrar.

## Out of scope (de HU-F15.2 o cercano, NO en esta propuesta)

- Resolución DIAN por sucursal → HU-F15.3 (`plan.md:3573`).
- Documentos (logo, póliza RC) → HU-F15.4 (`plan.md:3609`).
- Cualquier cambio en `web_sucursal` (reimpresión de ticket con nuevos
  mensajes → fase posterior, no acá).

## Acceptance criteria

- `pnpm -C apps/web_admin test` pasa con la nueva cobertura.
- `pnpm -C apps/web_admin typecheck` pasa.
- `pnpm -C apps/web_admin build` pasa.
- `pnpm -C apps/web_admin lint` pasa.
- e2e `empresa.spec.ts` corre en CI.
- axe-core WCAG 2.1 AA gate verde (la nav es `<Link>` y los tabs son
  Radix — accesibilidad ya cubierta).
- `python openspec/scripts/check_schema_match.py` sigue verde (no tocamos DB).
