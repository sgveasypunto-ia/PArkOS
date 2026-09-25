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
        // Ajuste 2026-09-25 (directiva del operador): se saca el cap
        // `sm:max-w-md md:max-w-lg` — el sheet vuelve al 50% de ancho
        // por defecto (`md:w-1/2` de `sheetVariants`), igual que
        // `<CerrarTurnoSheet />`/`<ReimprimirTiqueteSheet />`. El
        // contenido se centra abajo en un ancho de lectura cómodo para
        // que el form no se estire edge-to-edge en el 50% más ancho.
        // Padding fluido (`p-4 sm:p-6`) se mantiene.
        className="flex h-full w-full flex-col overflow-hidden p-4 sm:p-6"
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
          <div className="mx-auto w-full max-w-xl">
            <ArqueoParcial />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
