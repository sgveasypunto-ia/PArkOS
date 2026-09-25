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
        className="flex h-full flex-col overflow-hidden"
        data-testid="ingreso-sheet"
      >
        <SheetHeader>
          <SheetTitle>{t('ingreso', { defaultValue: 'Ingreso' })}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-1 flex-col overflow-y-auto">
          <div className="m-auto w-full">
            <IngresoPanel initialPlaca={initialPlaca} />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default IngresoSheet;
