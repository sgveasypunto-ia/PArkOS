/**
 * `<ArqueoSheet />` — F10.1 / F11.3 right-side drawer for the partial
 * arqueo (auditoría del turno, sin cierre).
 *
 * The sheet is a THIN SHELL after the F10.1 ArqueoSheet → ArqueoParcial
 * split. The actual form lives in `pages/ArqueoParcial.tsx` (it fetches
 * the current sesion via `useSesionActiva()`, computes live diferencia,
 * and POSTs to `/api/v1/caja/arqueo`). This file owns ONLY the
 * drawer concerns:
 *   - Mounts `<ArqueoParcial />` inside the right-side `<SheetContent />`
 *     (REQ-OPS-138 single-drawer invariant + REQ-OPS-139 lazy-mount).
 *   - Wires `useDashboardDrawerStore` so the sheet opens when
 *     `openDrawer === 'arqueo'` and closes on Esc / onOpenChange=false.
 *   - Manages focus restore on close (REQ-OPS-138 §Esc) -- the trigger
 *     button that opened the drawer (sidebar nav, F4 hotkey chip,
 *     F4 global hotkey, or MiTurnoPanel "Hacer arqueo" button) gets
 *     focus back when the sheet closes.
 *
 * Side: right (matches PagoSheet, ReimprimirTiqueteSheet, IngresoSheet,
 * SalidaSheet, SuscripcionesSheet -- the dashboard's right-side
 * drawer pattern).
 */
import { useEffect } from 'react';

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { ArqueoParcial } from '../pages/ArqueoParcial';

export function ArqueoSheet(): JSX.Element {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'arqueo';

  // Focus restore per REQ-OPS-138 §Esc. The anchor id was set by the
  // triggering call to `open('arqueo', anchorId)` -- either the F4
  // global hotkey (anchorId=''), the F4 hotkey chip
  // (anchorId='hotkey-chip-arqu...'), the left-sidebar nav button
  // (F11.3 retired; the right-sidebar MiTurnoPanel button is the
  // canonical per-turn action surface, anchorId='mi-turno-arqueo-button').
  useEffect(() => {
    if (!open && lastAnchorId) {
      const anchor = document.getElementById(lastAnchorId);
      anchor?.focus();
    }
  }, [open, lastAnchorId]);

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent
        side="right"
        // F31.3 rediseño: el ancho default del Sheet (`w-full md:w-1/2`,
        // primitiva compartida) llega a 1920px en 3840/ultrawide — un
        // form de arqueo no necesita ese ancho y queda ilegible. El cap
        // `sm:max-w-md md:max-w-lg` mantiene el drawer a un ancho de
        // formulario razonable en cualquier viewport de la tabla de
        // breakpoints sin tocar la primitiva compartida. Padding fluido
        // (`p-4 sm:p-6`) recupera espacio útil en 320px.
        className="flex h-full w-full flex-col overflow-hidden p-4 sm:max-w-md sm:p-6 md:max-w-lg"
        data-testid="arqueo-sheet"
      >
        <SheetHeader>
          <SheetTitle>Arqueo parcial (auditoría)</SheetTitle>
          <SheetDescription>
            Contá la caja sin cerrar el turno. La diferencia es solo
            advertencia si es chica.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-1 flex-col overflow-y-auto">
          <ArqueoParcial />
        </div>
      </SheetContent>
    </Sheet>
  );
}
