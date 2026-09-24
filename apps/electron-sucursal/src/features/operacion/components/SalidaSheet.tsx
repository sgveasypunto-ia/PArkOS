/**
 * `<SalidaSheet />` — right-side drawer wrapping `<SalidaPanel />`
 * (F7.1, REQ-OPS-138 single-drawer invariant).
 *
 * Opens via `useDashboardDrawerStore.open('salida', anchorId, placa?, pagoContext?, initialUuidIngreso?)`.
 * When the dashboard's PlacaInputHero provides a plate that already
 * has an active ingreso in this branch, the panel opens with the
 * plate pre-filled so the operator only has to press Enter to cotizar.
 * HU-F7.1 (búsqueda sin placa): when the operator instead selects a
 * NO-placa suggestion (identified by `consecutivo`), the hero resolves
 * the `uuid_ingreso` directly and threads it through
 * `initialUuidIngreso` instead of `initialPlaca`.
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
 *   - HU-F7.1 bugfix: while `<SalidaPanel />`'s own suggestion listbox
 *     is open, Escape must close ONLY that listbox, not this whole
 *     Sheet (WAI-ARIA APG combobox pattern: Escape closes the popup
 *     first). Radix's Escape-to-close listener runs on `document`
 *     with `capture: true`, firing before the panel's field-level
 *     `onKeyDown` — so we intercept it here via `onEscapeKeyDown`,
 *     the hook Radix exposes for exactly this override.
 */
import { useEffect, useRef } from 'react';
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
  const initialUuidIngreso = useDashboardDrawerStore((s) => s.initialUuidIngreso);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);

  const open = openDrawer === 'salida';

  // HU-F7.1 bugfix — ref (not state) because `onEscapeKeyDown` fires
  // from a native Radix document listener outside React's render
  // cycle; a ref gives it the latest value without a subscription.
  const suggestionsOpenRef = useRef(false);

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
      <SheetContent
        side="right"
        className="overflow-y-auto"
        data-testid="salida-sheet"
        onEscapeKeyDown={(e) => {
          if (suggestionsOpenRef.current) {
            e.preventDefault();
          }
        }}
      >
        <SheetHeader>
          <SheetTitle>{t('salida', { defaultValue: 'Salida' })}</SheetTitle>
        </SheetHeader>
        <SalidaPanel
          uuid_ingreso={null}
          initialPlaca={initialPlaca}
          initialUuidIngreso={initialUuidIngreso}
          onSuggestionsOpenChange={(next) => {
            suggestionsOpenRef.current = next;
          }}
        />
      </SheetContent>
    </Sheet>
  );
}

export default SalidaSheet;
