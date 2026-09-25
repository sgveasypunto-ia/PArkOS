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
        // F31.3 rediseño: mismo tratamiento que IngresoSheet — padding
        // por pasos (p-4 en mobile/tablet chico, p-6 desde sm) y cap de
        // ancho del contenido interno para ultra-wide (ver wrapper
        // abajo). `twMerge` resuelve el conflicto con el p-6 default
        // del primitivo compartido a favor de esta clase.
        className="overflow-y-auto p-4 sm:p-6"
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
        {/* max-w-xl: el Sheet llega a `md:w-1/2` del viewport — en
            1920/2560/3840/ultrawide eso sigue siendo muy ancho para el
            flujo de cotización + pago. Se cappea el contenido sin tocar
            el ancho del propio drawer (primitivo compartido, fuera de
            este lote). */}
        <div className="mx-auto w-full max-w-xl">
          <SalidaPanel
            uuid_ingreso={null}
            initialPlaca={initialPlaca}
            initialUuidIngreso={initialUuidIngreso}
            onSuggestionsOpenChange={(next) => {
              suggestionsOpenRef.current = next;
            }}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default SalidaSheet;
