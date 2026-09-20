# Proposal: HU-F9.2 — Listado, consulta y alerta de vencimiento próximo

## Intent

Hoy el operador del parqueadero no tiene una vista dedicada para revisar las suscripciones
vigentes de su sede, ni un aviso proactivo cuando una está por vencer. Cuando el cliente
llega a renovar, el operador tiene que cruzar mentalmente fechas y placas. Este gap se
cierra con tres entregables mínimos y verificables:

1. **Una página `/suscripciones`** con DataTable + búsqueda cliente-side, donde el
   operador puede buscar por placa o cliente sin recargar y ver fecha de vencimiento
   y días restantes de cada suscripción vigente.
2. **Un banner amarillo inline en la pantalla principal** (`<Dashboard />` — F6.x hub)
   con el texto literal del canon de plan.md:
   *"Suscripción de esta placa vence en X días (fecha). Considere renovación."*
3. **Un panel "Suscripciones por vencer"** que muestra el conteo total y el top 5,
   ordenadas por `fecha_vencimiento` ascendente.

El corte por `dias_para_vencer < 0` (vencidas) queda explícito: las vencidas NO
disparan el banner ni entran al top 5, pero SÍ aparecen en el listado general
marcadas como "vencida".

## Scope

### In Scope

- **T1** — Página `<Listado />` en `apps/electron-sucursal/src/features/suscripciones/pages/Listado.tsx`
  con DataTable + búsqueda cliente-side (Path A — sin reload de página).
- **T2** — Hook `useSuscripcionesProximasVencer()` en
  `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.ts`
  que calcula `dias_para_vencer = floor((fecha_vencimiento - NOW()).days)` y excluye
  las vencidas (`dias < 0`).
- **T3** — Integración del banner amarillo literal en `<Dashboard />` (F6.x) más
  el panel "Suscripciones por vencer" con conteo + top 5.
- **I1** — 2 escenarios e2e stub en `e2e/suscripciones-lista.spec.ts`
  (lista visible; banner aparece cuando hay suscripciones próximas a vencer).
- Constante global `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` en
  `apps/electron-sucursal/src/features/suscripciones/lib/constants.ts`.

### Out of Scope (deferred)

- **ABIERTO-05** — Override por suscripción individual de `dias_alerta_pre_vencimiento`
  (CU-06 BR4). El ER no tiene columna en `subscripciones_cliente`; el override per-row
  queda como follow-up explícito. F9.2 ships **default global only**.
- Nuevos endpoints backend. Path A reusa el listado paginado estándar de
  `subscripciones_cliente`; el banner usa `GET /api/v1/suscripciones-cliente/proximas-vencer`
  (read-only, sin schema change).
- Impresión / notificación push. El banner es solo visual.

## Capabilities

### Modified Capabilities

- `operaciones/suscripciones`: el feature `operacion` agrega al namespace `suscripciones`
  la lectura de "vencimiento próximo" y un listado dedicado. Modifica REQ-OPS-176 (F9.1
  wizard) porque ahora `/suscripciones` (la ruta sin `/venta`) está registrada.

### New Capabilities

- `operaciones/suscripciones-listado`: vista de tabla + búsqueda cliente-side de
  suscripciones vigentes con cálculo de días restantes.
- `operaciones/suscripciones-alerta-vencimiento`: banner literal amarillo con
  interpolación `X días (fecha)` y panel top-5 por vencer.

## Approach

Estrategia técnica de tres capas (mínima, sin servidor nuevo):

1. **Hook polling (`useSuscripcionesProximasVencer`)** — sigue el precedent
   F3.3 `useSesionActiva` + F6.1 `useIngresoActivo`: SWR key gated por
   `accessToken + uuid_sucursal`, `refreshInterval: 60_000`, 401 →
   `useAuthStore.clear()` + `parkos:auth:cleared` (F3.1 invariant preservado).
   Endpoint: `GET /api/v1/suscripciones-cliente/proximas-vencer?uuid_sucursal=X`.
   Filtro y sort se aplican **client-side** sobre el array que devuelve el backend
   (el endpoint no necesita cambios si devuelve todas las vigentes de la sede; el
   filtro excluye `dias < 0` y ordena por `fecha_vencimiento` ASC).

2. **Página `<Listado />`** — componente presentacional sobre el endpoint de
   lectura estándar `GET /api/v1/suscripciones-cliente?uuid_sucursal=X&cursor=…`
   (paginado por cursor). Búsqueda cliente-side (case-insensitive `includes`
   sobre `placa` o `cliente_nombre`), estado (`activa` / `vencida` /
   `suspendida`) mostrado con badge, columna `dias_restantes` calculada en
   render al momento del mount del componente (no se recalcula en cada
   keystroke — `useMemo` con `Date.now()` snapshot).

3. **Banner en `<Dashboard />`** — el `<Dashboard />` ya existente
   (`apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx`) gana dos
   bloques condicionales renderizados cuando
   `useSuscripcionesProximasVencer().data?.length > 0`:
   - Inline banner amarillo `role="alert"` con la cadena literal del canon,
     interpolada del **primer** item del array (recordando que el hook ya
     ordena por `fecha_vencimiento` ASC).
   - Panel "Suscripciones por vencer" en el sidebar derecho mostrando
     `{count_total}` + los primeros 5 items del array con su placa y días.

Constante única: `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` (un solo source of
truth en `lib/constants.ts`). El drift guard contra el override per-row
(`git grep -nE "dias_alerta_pre_vencimiento_override"`) es **mandatory pre-commit**.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `apps/electron-sucursal/src/features/suscripciones/lib/constants.ts` | New | `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.ts` | New | SWR polling 60s + filter exclude-vencidas + sort ASC |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.test.ts` | New | 3 hook tests (filter, sort, empty) |
| `apps/electron-sucursal/src/features/suscripciones/pages/Listado.tsx` | New | DataTable + búsqueda cliente-side |
| `apps/electron-sucursal/src/features/suscripciones/pages/Listado.test.tsx` | New | 3 component tests (render, search, sort) |
| `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` | Modified | Banner literal + panel top-5 |
| `apps/electron-sucursal/src/renderer/App.tsx` | Modified | Route `/suscripciones` |
| `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` | Modified | +8 keys |
| `apps/electron-sucursal/e2e/suscripciones-lista.spec.ts` | New | 2 stub scenarios (STUB gated) |
| `apps/electron-sucursal/vitest.config.ts` | Modified | +2 per-file thresholds |

LOC forecast: ~300 LOC total, well below 800 line PR budget.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Banner dispara en cold-mount con `data=undefined` antes del primer poll | Med | Guard `data && data.length > 0` (treat `undefined` as empty, no flash of banner); already F6.x pattern |
| Drift guard pass: `dias_alerta_pre_vencimiento_override` aparece en algún archivo | Low | Guard pre-commit (`git grep -nE "..." apps/electron-sucursal/src` MUST return 0); constant is single source of truth in `lib/constants.ts` |
| Conteo del panel "por vencer" se desincroniza del banner cuando backend agrega items entre polls | Low | Both read from same hook return; SWR revalidate on focus; re-render on each tick |
| Búsqueda cliente-side se siente lenta con >100 filas | Low | Tabla con `max-h` + scroll interno; search es `String.prototype.includes` O(n) con n esperado ≈ docenas por sede |
| Path A endpoint shape distinto del asumido por el hook (F9.1 schema) | Med | Zod schema en el hook parsea con `safeParse` y degrada a `[]` si difiere; backend contract ratified in F9.1 archive |
| Principal.tsx no existe en dev — integración debe ir a Dashboard.tsx | Low | Disclosed in apply-progress; the F6.x hub IS Dashboard.tsx on dev |

## Rollback Plan

Una sola rama + merge squash a `dev`. Rollback = `git revert` del merge commit
en `dev` (no requiere migración: el hook y la página son archivos nuevos, el
banner se quita removiendo dos bloques en `Dashboard.tsx`). El drift guard es la
red de seguridad contra reintroducir el override per-row por error.

## Dependencies

- **F9.1 (merged en `d25d081`)** — sienta el namespace `suscripciones:` en i18n
  y registra `/suscripciones/venta`. F9.2 monta su `<Listado />` en
  `/suscripciones` (parent route).
- **F3.3 `useSesionActiva`** + **F6.1 `useIngresoActivo`** — precedent SWR hook
  composition que F9.2 hook reusa verbatim.
- **F2.2 `useAuthStore`** + `parkos:auth:cleared` event — preserved 401-clear
  invariant.
- `<Dashboard />` debe tener `uuid_sucursal` disponible vía `useAuth()` (F3.x).

## Success Criteria

- [ ] `<Listado />` página accesible en `/suscripciones` con búsqueda cliente-side funcional
- [ ] Banner literal "Suscripción de esta placa vence en X días (fecha). Considere renovación." renderiza en `<Dashboard />` cuando hay items próximos
- [ ] Panel "Suscripciones por vencer" muestra `count_total` + top 5 ordenados por `fecha_vencimiento` ASC
- [ ] Vencidas (`dias < 0`) NO aparecen en el banner ni en el top 5
- [ ] Drift guard `git grep -nE "dias_alerta_pre_vencimiento_override" apps/electron-sucursal/src` retorna 0 matches
- [ ] `useSuscripcionesProximasVencer` con `refreshInterval: 60_000` validado por tests
- [ ] Tests 3+3 pasando (hook + componente)
- [ ] ESLint + tsc sin errores nuevos en archivos F9.2
- [ ] Diff total ≤ 800 LOC
