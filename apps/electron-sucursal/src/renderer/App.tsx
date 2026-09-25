import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from '../features/auth/pages/Login';
import { Dashboard } from '../features/caja/pages/Dashboard';
import { AbrirTurno } from '../features/caja/pages/AbrirTurno';
import { CierreDiario } from '../features/caja/pages/CierreDiario';
import { FacturaDetalle } from '../features/facturacion/pages/FacturaDetalle';
import { ReimprimirTiquete } from '../features/facturacion/pages/ReimprimirTiquete';
import { Venta } from '../features/suscripciones/pages/Venta';
import { Listado } from '../features/suscripciones/pages/Listado';
import { LocalApiDownBanner } from '../components/LocalApiDownBanner';

/**
 * App — F2.1 router + F2.3 StatusBar mount + F3.1 Login + F3.3 caja
 * routes + REQ-OPS-140 (PR-6 of operador-dashboard-hub): the global
 * `<OcupacionStrip />` mount at the old L48 has been removed; the
 * occupancy panel now lives ONLY inside `<Dashboard />` so it does
 * not poll the API on `/caja/abrir-turno` and `/caja/cerrar-turno`
 * (F4.3 "TEMPORAL" comment honoured).
 *
 * F11.1 mount order (AD-5 + REQ-OPS-174):
 *   1. `<StatusBar />` — F2.3 API health chip (kept).
 *   2. `<LocalApiDownBanner />` — sticky hard-fault banner, mounts
 *      only when selectApiStatusDown(state) === true.
 *
 * F11.1 realineado (REQ-OPS-171, AD-3/AD-4/AD-5, 2026-09-24): el
 * antiguo `<SyncBanner />` global (franja arriba de toda la app,
 * incluido por encima del navbar del Dashboard) fue retirado por
 * directiva del operador — la funcionalidad de sync-to-cloud ahora
 * vive como `<SyncStatusBadge />` dentro del header del propio
 * `<Dashboard />` (color real + tooltip), no como un banner global.
 *
 * F11.2 note: `<AlertasPanel />` (REQ-OPS-178) was previously mounted
 * here at the App root but is now SCOPED to `<Dashboard />` only --
 * focused routes (caja/facturacion/suscripciones) don't need the
 * alerts surface while the operator is performing one task. Dashboard
 * keeps the panel in `sr-only` for back-compat with `dashboard-section-
 * alertas` test ids. The pre-auth gate (`!uuid_sucursal`) is also no
 * longer needed at the App level since the panel is unreachable from
 * /login anyway (Dashboard is not mounted on /login).
 *

 * Layout: full-bleed (no centered max-width) so the 6-section dashboard
 * uses the whole viewport without scroll at 1080p.
 *
 * The persistent turno indicator (chip + expandable details) lives inside
 * `<Dashboard />` as `<TurnoActivoToggle />` — see F3.3 + REQ-OPS-027.
 *
 * The root renders a semantic `<main>` with one `<h1>` so axe-core's
 * WCAG 2.1 AA audit (RNF-022) is satisfied from day one.
 */
export default function App(): JSX.Element {
  const { t } = useTranslation('common');

  return (
    // 2026-09-25 (rediseño visual + pedido operador "evitar el scroll de
    // página"): antes `<main>` usaba su propio `min-h-[calc(100vh-2rem)]`
    // (una ADIVINANZA del alto de `<StatusBar/>`, desalineada — StatusBar
    // es 2rem real, acá se restaba distinto) mientras `<Dashboard/>`
    // (adentro) hacía SU PROPIA cuenta separada `min-h-[calc(100dvh-2.5rem)]`
    // — dos `min-height` basados en viewport, anidados, sin relación real
    // entre sí. Cualquier crecimiento de contenido (ej. el logo del header,
    // ahora más grande) rompía la cuenta y hacía scrollear la PÁGINA
    // entera en vez de solo el `<main>` interno de `<Dashboard/>` (que ya
    // tiene su propio `overflow-y-auto` pensado para eso). Fix real: este
    // wrapper fija el alto exacto del viewport (`h-dvh`) en un flex-column;
    // `<main>` pasa a `flex-1 min-h-0` (alto real y acotado, no una
    // adivinanza) — así `<Dashboard/>` puede simplemente `h-full` y su
    // `grid-rows-[auto_1fr_auto]` + `overflow-y-auto` interno funcionan
    // de verdad, sin que la página nunca necesite scroll propio.
    <div className="flex h-dvh flex-col overflow-hidden">
      <StatusBar />
      <LocalApiDownBanner />
      <main
        lang="es-CO"
        className="w-full flex-1 min-h-0 overflow-y-auto bg-muted/40 px-4 py-3"
      >
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/caja/abrir-turno"
            element={
              <ProtectedRoute>
                <AbrirTurno />
              </ProtectedRoute>
            }
          />
          <Route
            path="/caja/cierre-diario"
            element={
              <ProtectedRoute>
                <CierreDiario />
              </ProtectedRoute>
            }
          />
          <Route
            path="/factura-electronica/:uuid"
            element={
              <ProtectedRoute>
                <FacturaDetalle />
              </ProtectedRoute>
            }
          />
          <Route
            path="/facturacion/reimprimir"
            element={
              <ProtectedRoute>
                <ReimprimirTiquete />
              </ProtectedRoute>
            }
          />
          <Route
            path="/suscripciones/venta"
            element={
              <ProtectedRoute>
                <Venta />
              </ProtectedRoute>
            }
          />
          <Route
            path="/suscripciones"
            element={
              <ProtectedRoute>
                <Listado />
              </ProtectedRoute>
            }
          />
          <Route
            path="*"
            element={
              <p role="status">{t('error', { defaultValue: '404' })}</p>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
