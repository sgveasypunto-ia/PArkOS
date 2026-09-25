/**
 * `<ReimprimirTiqueteSheet />` — HU-F8.3 right-side drawer for the
 * reimpresión con costo flow (directiva del operador 2026-09-25: todo
 * el flujo debe vivir dentro de un sheet, NO una ruta aparte del
 * dashboard).
 *
 * THIN SHELL, mismo patrón que `<ArqueoSheet />` (F10.1): la forma real
 * (búsqueda por placa/cupo, motivo, alertdialogs de cobro y anulación,
 * impresión) vive en `pages/ReimprimirTiquete.tsx`, que no sabe que
 * está dentro de un Sheet. Este archivo owns SOLO:
 *   - Wires `useDashboardDrawerStore` so the sheet opens when
 *     `openDrawer === 'reimpresion'` and closes on Esc / onOpenChange.
 *   - Focus restore on close (REQ-OPS-138 §Esc) — el trigger (botón
 *     "Facturas" del sidebar o el hotkey global F8) recupera el foco.
 *
 * Side: right (matches PagoSheet, ArqueoSheet, IngresoSheet, SalidaSheet,
 * SuscripcionesSheet — the dashboard's right-side drawer pattern).
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
import { ReimprimirTiquete } from '../pages/ReimprimirTiquete';

export function ReimprimirTiqueteSheet(): JSX.Element {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'reimpresion';

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
        // Ajuste 2026-09-25 (directiva del operador, mismo criterio que
        // `<CerrarTurnoSheet />`): 50% de ancho (`md:w-1/2` por defecto
        // de `sheetVariants`) en vez del cap `max-w-lg` — el contenido
        // interno se centra en un ancho de lectura cómodo más abajo,
        // así el sheet usa el 50% sin que el form se estire feo.
        className="flex h-full w-full flex-col overflow-y-auto p-4 sm:p-6"
        data-testid="reimprimir-sheet"
      >
        <SheetHeader>
          <SheetTitle>Reimprimir tiquete</SheetTitle>
          <SheetDescription>
            Buscá por placa o por cupo (vehículo sin placa) para reimprimir un
            tiquete de entrada cobrando el servicio vigente.
          </SheetDescription>
        </SheetHeader>
        <div className="mx-auto w-full max-w-xl">
          <ReimprimirTiquete />
        </div>
      </SheetContent>
    </Sheet>
  );
}
