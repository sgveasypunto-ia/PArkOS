/**
 * `<DrawerHost />` — singleton drawer slot driven by
 * `useDashboardDrawerStore` (REQ-OPS-138).
 *
 * Renders ONE drawer at a time, gated by `openDrawer === <kind>`. Each
 * drawer branch owns its own focus-restore in its `onOpenChange(false)`
 * effect (REQ-OPS-138 §Esc).
 *
 * Drawer kinds mounted:
 *   - `'pago'`           → `<PagoSheet />` (PR-3, F8.1)
 *   - `'reimpresion'`    → `<ReimprimirTiqueteSheet />`
 *   - `'arqueo'`         → `<ArqueoSheet />`
 *   - `'cierre-diario'`  → `<CierreDiarioDialog />`
 *   - `'ingreso'`        → `<IngresoSheet />` (F6.1 — wires the
 *                          dashboard's PlacaInputHero to the ingreso flow)
 *   - `'salida'`         → `<SalidaSheet />` (F7.1 — same for salida)
 *   - `'suscripciones'`  → `<SuscripcionesSheet />` (F9.2 — list +
 *                          "Nueva venta" CTA into the existing
 *                          4-step `<Venta />` wizard at
 *                          /suscripciones/venta)
 *
 * Kinds still future: `'inventario'` (F5 — drawer TBD), `'fe-retry'`
 * (PR-4 — drawer TBD). The single-drawer invariant holds because
 * the store guarantees only ONE kind is active at a time and the
 * un-wired branches return `null`.
 */
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { PagoSheet } from '../../facturacion/components/PagoSheet';
import { ReimprimirTiqueteSheet } from '../../reimpresion/components/ReimprimirTiqueteSheet';
import { ArqueoSheet } from '../components/ArqueoSheet';
import { CerrarTurnoSheet } from '../components/CerrarTurnoSheet';
import { CierreDiarioDialog } from '../../caja/components/CierreDiarioDialog';
import { IngresoSheet } from '../../operacion/components/IngresoSheet';
import { SalidaSheet } from '../../operacion/components/SalidaSheet';
import { SuscripcionesSheet } from '../../suscripciones/components/SuscripcionesSheet';

export function DrawerHost(): JSX.Element | null {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const pagoContext = useDashboardDrawerStore((s) => s.pagoContext);

  if (!openDrawer) return null;

  // Single-drawer invariant (REQ-OPS-138): only ONE branch mounts.
  if (openDrawer === 'pago') {
    // F8.1 (HU-F8.1 — PagoModal) — read the live pagoContext the
    // `<SalidaPanel>` pushed via `open('pago', anchorId, null, ctx)`
    // and forward it to `<PagoSheet>` so the form can build the
    // `POST /facturacion/factura` body. When the context is absent
    // (e.g. a hotkey-driven `open('pago', ...)`), we fall back to
    // placeholders so the sheet still mounts but the submit is
    // blocked by `uuid_ingreso === null` (defense in depth — the
    // submit button is disabled when `uuid_ingreso` is null per
    // `<PagoModal>` `disabled={!uuid_ingreso || ...}`).
    //
    // F8.1-b (2026-09-23): also forward `uuid_salida` so `<PagoSheet>`
    // can auto-annul the salida on any close-without-pay path
    // (Cancelar / X / overlay click / Escape). Without this, the
    // ingreso would stay `cerrado` (the matching `prod.salidas`
    // row is already inserted) and the operator could never recover
    // the cobro — `prod.salidas` is `[A]` (append-only).
    //
    // `<PagoSheet>` owns its own `onSubmit` (wired to
    // `useRegistrarPago` + post-pago print triggers per DEC-SUC-27)
    // and its own close-without-pay annulment via
    // `useAnularSalidaNoPagada`.
    // `<DrawerHost>` is a pure shell — no callback forwarding needed.
    const uuidIngreso = pagoContext?.uuid_ingreso ?? null;
    const uuidSalida = pagoContext?.uuid_salida ?? null;
    const totalCop = pagoContext?.total_cop ?? 0;
    return (
      <PagoSheet
        uuid_ingreso={uuidIngreso}
        uuid_salida={uuidSalida}
        total_cop={totalCop}
      />
    );
  }
  if (openDrawer === 'reimpresion') {
    return <ReimprimirTiqueteSheet />;
  }
  if (openDrawer === 'arqueo') {
    // HU-F10.1 (REQ-OPS-153, AD-1 / AD-4) -- F11.3 follow-up:
    // The arqueo flow lives INSIDE the dashboard's right-side drawer,
    // matching PagoSheet / IngresoSheet / SuscripcionesSheet / etc.
    // pattern. The legacy ArqueoSheet stub (mounted with
    // uuid_sesion={null}) silently no-op'd the submit guard; the new
    // ArqueoSheet wraps the ArqueoParcial form body inside a real
    // <Sheet> chrome so the drawer portal-escapes the dashboard's
    // CSS grid (the page rendered inline below the layout when the
    // form body was mounted directly without <SheetContent>). The
    // form body itself (pages/ArqueoParcial.tsx) owns the sesion
    // fetch + live diferencia + POST /caja/arqueo submit logic.
    return <ArqueoSheet />;
  }
  if (openDrawer === 'cerrar-turno') {
    // HU-F3.3 + HU-F10.2 -- F11.3 follow-up: turn-closing flow lives
    // in the dashboard's right-side drawer (same pattern as Arqueo).
    // The legacy routed page `/caja/cerrar-turno` is retired; the
    // F10.2 `<CerrarTurno />` page is mounted by CerrarTurnoSheet
    // inside <SheetContent side="right">. The page handles the
    // F3.3 logout-on-success trifecta (useAuthStore.clear() +
    // parkos:auth:cleared event + navigate('/login?closed=true'))
    // which implicitly unmounts the drawer via the route change.
    return <CerrarTurnoSheet />;
  }
  if (openDrawer === 'cierre-diario') {
    return <CierreDiarioDialog uuid_sucursal={null} uuid_sesion={null} />;
  }
  if (openDrawer === 'ingreso') {
    return <IngresoSheet />;
  }
  if (openDrawer === 'salida') {
    return <SalidaSheet />;
  }
  if (openDrawer === 'suscripciones') {
    // HU-F9.2 sheet — list + "Nueva venta" CTA. CTA closes the
    // drawer and routes to /suscripciones/venta (the F9.1 wizard).
    return <SuscripcionesSheet />;
  }

  // For kinds not yet wired (inventario, fe-retry), render nothing
  // — single-drawer invariant preserved.
  return null;
}