# Proposal: HU-F4.3 — Ocupación en vivo (frontend)

## Intent

The operador necesita ver de un vistazo cuántos cupos quedan por tipo de vehículo en el strip superior de `web_sucursal`, con alerta visual cuando la sede se está llenando. Esta HU shippea **el primer organismo compartido de F4** (consumido por futuras pantallas — F4.4 dashboard, F6.x ingreso, F7.x salida — todas referencian al strip como single source of truth visible de la capacidad) sobre la fuente de verdad ya consolidada por HU-F1.5: la vista materializada `prod.mv_ocupacion_diaria` refrescada cada 10 s.

El cálculo de la ocupación es derivado, no mutable: la columna `disponible` de la respuesta es siempre `cupo_maximo - activos`, computada en backend por `repo/ocupacion.py::get_ocupacion_puros_activos()`. **Nunca** se persiste ni se transporta al cliente como estado mutable de columna (DEC-SUC-11 verbatim). El cliente solo lee y renderiza.

## Scope

### In Scope

- Organismo compartido `<OcupacionStrip />` en `apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx` (mismo path que `<StatusBar />` F2.3 — componente cross-feature, no dentro de `features/`).
- SWR polling `refreshInterval: 10_000` (DEC-SUC-11 verbatim, en sync con el `REFRESH MATERIALIZED VIEW CONCURRENTLY` que `RefreshMvOcupacionWorker` ejecuta cada 10 s).
- `AbortController` explícito por ciclo, cleanup en `useEffect` `unmount` (no leak de petición si el operador sale de la pantalla / cambia de ruta / cierra la app).
- Render por tipo (`Auto: 23/50`) con color por umbral — verde `<70%`, amarillo `70-90%`, rojo `>90%` — y `<Tooltip>` shadcn leyenda al pasar el mouse sobre cada chip.
- Degradación: si el polling falla, el strip conserva el último valor conocido con marca visual sutil de "desactualizado" (`data-stale="true"` + ícono `AlertCircle`), **no desaparece** (UX contract del plan.md:1433).
- `aria-live="polite"` + `aria-atomic="false"` por celda de tipo, para que el screen reader anuncie cambios transitorios sin interrumpir al operador (precedent F2.3 `<StatusBar>`).
- 4 unit tests RTL + 1 e2e Playwright + 1 axe-core smoke.

### Out of Scope

- WebSocket / SSE — explícitamente descartado (DEC-SUC-11 verbatim). La vista materializada se refresca en backend; polling de 10 s es el contrato. v2 puede evaluarlo.
- Puesto individual / mapa visual del patio — DEC-SUC-11 cierra ese alcance: el cupo es agregado por tipo, sin asignación de puesto individual.
- Mutación del modelo de datos (A-04 + DEC-SUC-11): **ninguna** columna nueva, **ningún** trigger, **ningún** `UPDATE` sobre `cantidad_vehiculos_sucursal`. El ER es 4NF canon y el plan ya descartó explícitamente la columna `disponible`.
- Cambio al backend — `GET /api/v1/operacion/ocupacion` ya existe y es estable (REQ-OPS-030, REQ-OPS-031; archive `2026-09-14-hu-f1-5-mv-ocupacion-diaria`). HU-F1.5 ya cerrado.
- Sincronización cloud del dato de ocupación — `mv_ocupacion_diaria` vive en el branch (cloud no la necesita; la reportería cloud recalcula con su propio query F17.2).
- i18n en otros locales — solo `es-CO` se modifica en este slice. Otros locales quedan con fallback `es-CO` (`fallbackLng: 'es-CO'` en `lib/i18n.ts`).

## Capabilities

### New Capabilities

- `operacion` (delta sobre `openspec/changes/fase-4-1-deteccion-tipo-vehiculo/specs/operacion/spec.md`): consumo frontend del endpoint `GET /api/v1/operacion/ocupacion` con polling 10 s, thresholds visuales por porcentaje, degradación con último valor conocido, accesibilidad WCAG 2.1 AA, e2e con Playwright + `_electron.launch`.

### Modified Capabilities

- None a nivel de spec canónico. `openspec/specs/operations/spec.md` REQ-OPS-030/031 (backend) ya cubre el contrato del endpoint; este delta describe **el consumidor frontend**, no el contrato del endpoint.

## Approach

Renderer pasivo sobre el endpoint existente. SWR como único *data fetcher* (DEC-SUC-05 verbatim — mismo SWR key string `/operacion/ocupacion?uuid_sucursal=X` que cualquier otro consumer futuro, deduping compartido). `refreshInterval: 10_000` alineado al `RefreshMvOcupacionWorker` del backend (mismo 10s). `dedupingInterval: 5_000` evita storm si múltiples componentes montan `<OcupacionStrip>` en la misma pantalla (futuro F4.4 dashboard). `AbortController` por fetch para que `unmount` corte la petición en vuelo — sin esto, React StrictMode + dev hot-reload dejan fugas silenciosas. Thresholds via constante exportada del mismo archivo (`THRESHOLD_YELLOW = 0.7`, `THRESHOLD_RED = 0.9`) — single source of truth, fácil de testear. Colores via tokens semánticos shadcn (`bg-green-500`/`bg-amber-500`/`bg-destructive` mapeados por tenant si el admin lo configura; el default cae al CSS variable `--destructive` de shadcn). Aria-live polite por celda con `aria-atomic="false"` para anunciar solo el delta.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx` | New | Organismo compartido. SWR + AbortController + thresholds + Tooltip leyenda. |
| `apps/electron-sucursal/src/renderer/components/OcupacionStrip.test.tsx` | New | 4 tests RTL: render inicial, cambio de color por umbral, `data-stale` tras error, aria-live correcto. |
| `apps/electron-sucursal/src/features/operacion/api/ocupacionApi.ts` | New | Wrapper `parkosFetch` sobre `GET /api/v1/operacion/ocupacion?uuid_sucursal=X`. Zod schema local + tipos. |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts` | New | SWR hook: key `/operacion/ocupacion?uuid_sucursal=X`, refresh 10s, dedupe 5s, error callback. |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.test.ts` | New | SWR config tests (refreshInterval=10_000, dedupingInterval=5_000, key null pre-auth). |
| `apps/electron-sucursal/src/features/operacion/occupancyThresholds.ts` | New | Constantes `THRESHOLD_YELLOW`, `THRESHOLD_RED`, función pura `classForPorcentaje(p: number): 'green'\|'yellow'\|'red'`. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modified | 6 keys: `ocupacion_titulo`, `ocupacion_legend_green/yellow/red`, `ocupacion_stale`, `ocupacion_legend_*`. |
| `apps/electron-sucursal/e2e/operacion/ocupacion.spec.ts` | New | 2 tests: render + valor cambia tras refresh simulado; axe-core WCAG 2.1 AA. |

> **Path note**: el prompt del orquestador menciona `src/components/OcupacionStrip.tsx`. El scaffold real usa `src/renderer/components/` (precedent F2.3 `<StatusBar />`, F2.1 `<ProtectedRoute />`). Se honra el path real del repo — el prompt es natural-language, no mandate.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Drift entre el `refreshInterval` del cliente (10s) y el `DEFAULT_REFRESH_INTERVAL_S` del `RefreshMvOcupacionWorker` (también 10s) | Low | Constante compartida documentada como `OPERACION_REFRESH_INTERVAL_MS` exportada de un único módulo `src/features/operacion/constants.ts` para que un cambio futuro rompa build en ambos lados. |
| Polling falla y operador ve dato viejo por minutos | Medium | Marcador visual `data-stale="true"` + ícono `AlertCircle` (lucide) + texto accesible "ocupación desactualizada" via `aria-live="polite"` separado. Nunca tira el último valor. |
| Memory leak por `AbortController` no cancelado en unmount | Medium | Cleanup explícito en `useEffect` (test unitario lo cubre) + lint rule que prohíbe `fetch` directo fuera de `parkosFetch`. |
| F4.4 dashboard u otros consumers montan múltiples `<OcupacionStrip>` y generan N polls paralelos | Low | `dedupingInterval: 5_000` cubre el caso; el key SWR es determinístico, idéntico al endpoint. |
| Endpoint `GET /api/v1/operacion/ocupacion` se rompe (regresión HU-F1.5) | Low | El test e2e mockea el endpoint via `page.route`; el contrato ya está congelado en REQ-OPS-030 (REQ-OPS-031 authz chain). Smoke test CI del backend ya cubre esto. |
| `useTiposVehiculo()` no se ha montado en `useOcupacion` para filtrar tipos sin cupo | Low | El endpoint ya devuelve `cupo_maximo: 0, disponibles: 0` para tipos sin configurar (REQ-OPS-030 S3 `cupo_no_configurado`). El strip los renderiza con `0/N` y umbral `rojo` — es la interpretación del cliente (KD-6 invariant). |

## Rollback Plan

Borrar los 8 archivos nuevos (`OcupacionStrip.tsx`, `OcupacionStrip.test.tsx`, `ocupacionApi.ts`, `useOcupacion.ts`, `useOcupacion.test.ts`, `occupancyThresholds.ts`, `ocupacion.spec.ts`, key removidas de `operacion.json`). No DB migration, no backend change, no consumer downstream todavía (F4.4/F6.x/F7.x dependen de este HU pero shippean más tarde — el rollback es local a esta HU). El branch sigue compilando y `vitest run` queda en cero tests asociados a este slice.

## Dependencies

- Backend endpoint `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` — **ya montado y archivado** (HU-F1.5 cerrado, archive `2026-09-14-hu-f1-5-mv-ocupacion-diaria`). Contrato REQ-OPS-030 + REQ-OPS-031 verificados en `backend/.../api/v1/operacion.py:808-...` y `backend/.../schemas/operacion.py:205-...`. **No es blocker**.
- `@parkos/ui-kit/fetch` `parkosFetch` + `ParkosHttpError` (F2.2 precedent, ya en uso en F3.3/F4.1).
- `useAuthStore` para gate de SWR key (precedent F3.3, F4.1 — `accessToken ? key : null`).
- `Tooltip` de shadcn (ya en `src/renderer/components/ui/tooltip.tsx`).
- `lucide-react` para íconos (`AlertCircle`, `Car` opcional).
- `Zod` schema local en `ocupacionApi.ts` para validar el shape `OcupacionResponse` antes de pasar a SWR.

## Success Criteria

- [ ] `npx vitest run src/renderer/components/OcupacionStrip.test.tsx src/features/operacion/hooks/useOcupacion.test.ts` exits 0.
- [ ] `npx playwright test e2e/operacion/ocupacion.spec.ts` corre en CI con `_electron.launch` y verifica render + cambio tras refresh + 0 violaciones axe-core WCAG 2.1 AA.
- [ ] Ningún archivo fuera de `openspec/changes/fase-4-3-ocupacion-en-vivo/` + los paths declarados en "Affected Areas" + Engram fue modificado.
- [ ] `data-stale` se activa cuando `parkosFetch` rechaza la petición con `NetworkError` o 5xx — preserva el último valor conocido (verificado por test RTL).
- [ ] El componente **no** agrega columna `disponible` ni ningún estado mutable nuevo — el cálculo es siempre derivado del response del endpoint.

## Non-Goals (explicit)

- **No websocket**, **no SSE** — DEC-SUC-11 cierra esto para esta versión.
- **No puesto individual** — DEC-SUC-11 + A-03 (cupo agregado por tipo).
- **No columna mutable `disponible`** — DEC-SUC-11 + A-04 (la vista materializada es la única fuente).
- **No nuevos permisos** — `operacion:read` ya existe en el catálogo sembrado por F1.2 (verificar en archive F1.2 antes de apply; si falta, abrir HU separada — no scope-creep aquí).
- **No multi-tenant theming del strip** — los umbrales son globales; si un tenant quiere customizarlos, abre HU futura.
