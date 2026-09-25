/**
 * `<CierreDiarioSheet />` — right-side drawer wrapping the HU-F10.3
 * multi-session cierre diario page (ajuste 2026-09-25, directiva del
 * operador: "cierre diario no debe estar en una ruta aparte, debe
 * estar en un sheet dentro de / como todas las demás funcionalidades").
 *
 * Thin shell, mismo patrón que `<CerrarTurnoSheet />` / `<ArqueoSheet />`:
 * el shell resuelve open/close/focus-restore vía `useDashboardDrawerStore`;
 * `pages/CierreDiario.tsx` (el form real: resumen por sesión, totales
 * agregados, gates de rol, `runCierreDiarioChain`) no sabe que está
 * dentro de un Sheet — salvo por una excepción puntual: a diferencia
 * de `<CerrarTurno />` (que al terminar navega a `/login`, una ruta
 * DISTINTA, y el desmontaje del árbol cierra el drawer implícitamente),
 * `<CierreDiario />` navega a `/` — la MISMA ruta donde ya vive el
 * Dashboard que contiene este drawer — así que ese `navigate('/')` no
 * desmonta nada. Por eso `CierreDiario.tsx` llama explícitamente a
 * `useDashboardDrawerStore.getState().close()` en sus dos salidas
 * (cancelar y éxito) antes de navegar; ver el comentario puntual ahí.
 *
 * Unificación (2026-09-25, directiva del operador): existía un kind
 * viejo `'cierre-diario'` (hotkey F6, `<CierreDiarioDialog />`) — cierre
 * RÁPIDO de la sesión propia del operador — que quedó CONFIRMADO como
 * código muerto (`<DrawerHost />` lo montaba con
 * `uuid_sucursal={null} uuid_sesion={null}` siempre, su `handleSubmit`
 * nunca enviaba nada). Era la implementación VIEJA de este mismo cierre
 * diario. Se retiró por completo (`CierreDiarioDialog.tsx` borrado) y
 * el hotkey F6 ahora abre este mismo Sheet (`'cierre-diario-multi'`).
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
import { CierreDiario } from './CierreDiario';

export function CierreDiarioSheet(): JSX.Element {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'cierre-diario-multi';

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
      {/* Ancho/centrado 2026-09-25 (directiva del operador): mismo
          criterio que `<CerrarTurnoSheet />`/`<ArqueoSheet />`/
          `<ReimprimirTiqueteSheet />` — 50% de ancho por defecto
          (`md:w-1/2` de `sheetVariants`, sin cap de `max-w`), con el
          contenido centrado en un ancho de lectura cómodo más abajo. */}
      <SheetContent
        side="right"
        className="flex h-full w-full flex-col overflow-hidden p-4 sm:p-6"
        data-testid="cierre-diario-sheet"
      >
        <SheetHeader>
          <SheetTitle>Cierre diario</SheetTitle>
          <SheetDescription>
            Cierre de todas las sesiones abiertas del día — supervisor /
            multi-sucursal.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-1 flex-col overflow-y-auto">
          <div className="mx-auto w-full max-w-xl">
            <CierreDiario />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
