/**
 * `<SalidaSheet />` — right-side drawer wrapping `<SalidaPanel />`
 * (F7.1, REQ-OPS-138 single-drawer invariant).
 *
 * Opens via `useDashboardDrawerStore.open('salida', anchorId, placa?)`.
 * When the dashboard's PlacaInputHero provides a plate that already
 * has an active ingreso in this branch, the panel opens with the
 * plate pre-filled so the operator only has to press Enter to cotizar.
 *
 * The panel's `onPagoSubmit` is wired to a no-op stub here — PR-3
 * (the pago flow) will thread the real `POST /facturacion/factura`
 * + `POST /facturacion/factura-pagos` call. For now the panel just
 * shows the cotizacion breakdown and lets the operator cancel.
 *
 * Follows the same pattern as `<PagoSheet />` / `<ArqueoSheet />`:
 *   - shadcn `Sheet` (Radix Dialog primitive) — portal + overlay.
 *   - Esc + overlay click → `onOpenChange(false)` → `close()`.
 *   - Focus restore: when the sheet closes, focus returns to the
 *     trigger that opened it (captured via `lastAnchorId`).
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SalidaPanel } from './SalidaPanel';

export function SalidaSheet(): JSX.Element | null {
  const { t } = useTranslation('operacion');
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const initialPlaca = useDashboardDrawerStore((s) => s.initialPlaca);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);

  const open = openDrawer === 'salida';

  // Focus restore per REQ-OPS-138 §Esc — when the sheet closes, return
  // focus to the trigger that opened it. Mirrors ArqueoSheet.tsx:66-70.
  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  if (openDrawer !== 'salida') return null;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent side="right" className="overflow-y-auto" data-testid="salida-sheet">
        <SheetHeader>
          <SheetTitle>{t('salida', { defaultValue: 'Salida' })}</SheetTitle>
        </SheetHeader>
        <SalidaPanel
          uuid_ingreso={null}
          onPagoSubmit={async () => {
            // TODO: PR-3 — wire to POST /facturacion/factura + pagos.
          }}
          initialPlaca={initialPlaca}
        />
      </SheetContent>
    </Sheet>
  );
}

export default SalidaSheet;
