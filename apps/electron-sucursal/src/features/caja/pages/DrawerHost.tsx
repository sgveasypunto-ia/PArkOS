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

export function DrawerHost(): JSX.Element | null {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);

  if (!openDrawer) return null;

  // PR-3 mounts PagoSheet. PR-4 adds fe-retry/reimpresion; PR-5 adds
  // arqueo/cierre-diario. The single-drawer invariant is upheld
  // because only ONE branch mounts at a time.
  if (openDrawer === 'pago') {
    return (
      <PagoSheet
        uuid_ingreso={null}
        total_cop={0}
        onSubmit={async () => {
          /* PR-3 placeholder — the SalidaPanel wires its own onSubmit
             via prop drilling once the active flujo is in scope. */
        }}
      />
    );
  }

  // For kinds not yet wired, render nothing (consistent with the
  // pre-PR-3 placeholder behavior — DrawerHost is structural).
  return null;
}