/**
 * `<IngresoSheet />` — right-side drawer wrapping `<IngresoPanel />`
 * (F6.1, REQ-OPS-138 single-drawer invariant).
 *
 * Opens via `useDashboardDrawerStore.open('ingreso', anchorId, placa?)`.
 * When the dashboard's PlacaInputHero provides a plate, that plate is
 * passed to the panel as `initialPlaca` so the operator only has to
 * press Enter / click "Registrar" once.
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
import { IngresoPanel } from './IngresoPanel';

export function IngresoSheet(): JSX.Element | null {
  const { t } = useTranslation('operacion');
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const initialPlaca = useDashboardDrawerStore((s) => s.initialPlaca);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);

  const open = openDrawer === 'ingreso';

  // Focus restore per REQ-OPS-138 §Esc — when the sheet closes, return
  // focus to the trigger that opened it. Mirrors ArqueoSheet.tsx:66-70.
  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  if (openDrawer !== 'ingreso') return null;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent
        side="right"
        // F31.3 rediseño: padding por pasos (p-4 en mobile/tablet chico,
        // p-6 desde sm) — a 320px el p-6 fijo del primitivo shadcn
        // (sheetVariants) deja muy poco ancho útil para el formulario.
        // `twMerge` (vía `cn()` en sheet.tsx) resuelve el conflicto con
        // el p-6 default a favor de esta clase.
        className="flex h-full flex-col overflow-hidden p-4 sm:p-6"
        data-testid="ingreso-sheet"
      >
        <SheetHeader>
          <SheetTitle>{t('ingreso', { defaultValue: 'Ingreso' })}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-1 flex-col overflow-y-auto">
          {/* max-w-xl: el Sheet llega a `md:w-1/2` del viewport — en
              1920/2560/3840/ultrawide eso sigue siendo muy ancho para un
              formulario de un solo campo. Se cappea el contenido sin
              tocar el ancho del propio drawer (primitivo compartido,
              fuera de este lote). */}
          <div className="m-auto w-full max-w-xl">
            <IngresoPanel initialPlaca={initialPlaca} />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default IngresoSheet;
