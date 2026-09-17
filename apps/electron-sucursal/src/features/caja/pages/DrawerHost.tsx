/**
 * `<DrawerHost />` — singleton drawer slot driven by
 * `useDashboardDrawerStore` (REQ-OPS-138).
 *
 * Renders ONE drawer at a time, gated by `openDrawer === <kind>`. Each
 * drawer branch owns its own focus-restore in its `onOpenChange(false)`
 * effect (REQ-OPS-138 §Esc).
 *
 * Drawer kinds mounted:
 *   - `'pago'`        → `<PagoSheet />` (PR-3, F8.1)
 *
 * Future PRs add: `'fe-retry'` (PR-4), `'reimpresion'` (PR-4),
 * `'arqueo'` (PR-5), `'cierre-diario'` (PR-5).
 */
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { PagoSheet } from '../../facturacion/components/PagoSheet';
import { ReimprimirTiqueteSheet } from '../../reimpresion/components/ReimprimirTiqueteSheet';
import { ArqueoSheet } from '../../caja/components/ArqueoSheet';
import { CierreDiarioDialog } from '../../caja/components/CierreDiarioDialog';

export function DrawerHost(): JSX.Element | null {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);

  if (!openDrawer) return null;

  // Single-drawer invariant (REQ-OPS-138): only ONE branch mounts.
  if (openDrawer === 'pago') {
    return (
      <PagoSheet
        uuid_ingreso={null}
        total_cop={0}
        onSubmit={async () => {
          /* PR-3 placeholder */
        }}
      />
    );
  }
  if (openDrawer === 'reimpresion') {
    return <ReimprimirTiqueteSheet />;
  }
  if (openDrawer === 'arqueo') {
    return <ArqueoSheet uuid_sesion={null} />;
  }
  if (openDrawer === 'cierre-diario') {
    return <CierreDiarioDialog uuid_sucursal={null} uuid_sesion={null} />;
  }

  // For kinds not yet wired (fe-retry), render nothing — single-drawer
  // invariant preserved.
  return null;
}