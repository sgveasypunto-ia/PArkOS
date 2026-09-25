/**
 * `<CerrarTurnoSheet />` — F11.3 right-side drawer for the turn-closing
 * flow (HU-F3.3 + HU-F10.2).
 *
 * Thin shell that mirrors the pattern from `<ArqueoSheet />`:
 *   - Mounts the F10.2 `<CerrarTurno />` page inside a right-side
 *     <SheetContent />. The page owns the 3-step chain (arqueo +
 *     sesion-close + logout-on-success); the sheet owns the drawer
 *     concerns (open/close, focus-restore on Esc).
 *
 * F11.3 UX direction: the operator's per-turn action surface is the
 * RIGHT sidebar (MiTurnoPanel + header). The turn-closing flow used
 * to be a left-sidebar nav button + routed page
 * (`/caja/cerrar-turno`); both were retired in F11.3 in favor of this
 * drawer. The F10.2 page itself is unchanged -- the F3.3
 * logout-on-success trifecta (`useAuthStore.clear()` + the
 * `parkos:auth:cleared` event + `navigate('/login?closed=true')`)
 * is preserved verbatim per Engram #1899; the page already calls
 * `navigate` so the drawer's store close happens implicitly when
 * the page unmounts via the route change.
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
import { CerrarTurno } from '../pages/CerrarTurno';

export function CerrarTurnoSheet(): JSX.Element {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'cerrar-turno';

  // Focus restore per REQ-OPS-138 §Esc. The anchor id was set by the
  // triggering call to `open('cerrar-turno', anchorId)` — the canonical
  // header "Cerrar turno" button (anchorId='dashboard-cerrar-turno').
  // The legacy left-sidebar nav button (F11.3 retired) and the
  // MiTurnoPanel duplicate (removed — the header is the single
  // source of truth for the turn-closing entry-point) are gone; the
  // drawer is now opened only from the header.
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
        // F31.3 rediseño + ajuste 2026-09-25 (directiva del operador):
        // el form (resumen + 6 campos + banners) necesita más ancho que
        // el cap `max-w-lg` que tenía antes (mismo tratamiento que
        // `<ArqueoSheet />`) — se saca el cap y queda en el 50% de
        // ancho (`md:w-1/2`) que ya trae `sheetVariants` por defecto,
        // en vez de un límite fijo en px. Padding fluido en 320px +
        // chrome flex/overflow se mantienen para que el form scrollee
        // dentro del drawer en vez de desbordar el viewport en alturas
        // chicas.
        className="flex h-full w-full flex-col overflow-hidden p-4 sm:p-6"
        data-testid="cerrar-turno-sheet"
      >
        <SheetHeader>
          <SheetTitle>Cerrar turno</SheetTitle>
          <SheetDescription>
            Conteo final de caja + cierre de la sesión activa. Después
            de confirmar el arqueo la sesión queda cerrada y la app
            vuelve al login.
          </SheetDescription>
        </SheetHeader>
        {/* Ajuste 2026-09-25 (directiva del operador): el sheet pasó a
            50% de ancho (`md:w-1/2`, ver className de arriba), pero el
            form no debe estirarse a rellenar todo ese ancho -- los
            campos angostos (efectivo/datáfono contado) quedaban como
            barras larguísimas, dando sensación de "toca el borde".
            Se centra el contenido en un ancho de lectura cómodo dentro
            del sheet más ancho. */}
        <div className="flex flex-1 flex-col overflow-y-auto">
          <div className="mx-auto w-full max-w-xl">
            <CerrarTurno />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
