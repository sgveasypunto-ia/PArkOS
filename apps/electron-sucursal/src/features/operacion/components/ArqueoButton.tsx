/**
 * `<ArqueoButton />` — per-turn contextual trigger for HU-F10.1 partial
 * arqueo (auditoría del turno actual, sin cierre).
 *
 * El arqueo tiene dos superficies de trigger en el dashboard:
 *   1. Sidebar izquierdo (`data-testid="sidebar-arqueo"` en
 *      `Dashboard.tsx`) — nav primaria, accesible siempre que el
 *      sidebar esté montado (desktop ≥ lg, o mobile con hamburger).
 *      Cablea `openDrawer('arqueo', 'sidebar-arqueo')`.
 *   2. Este botón dentro de `<MiTurnoPanel />` (sidebar derecho) —
 *      atajo contextual del turno activo. El header del dashboard
 *      tiene un único "Cerrar turno" como single source of truth del
 *      turn-closing; MiTurnoPanel NO lo duplica.
 *
 * Cualquiera de los dos triggers desemboca en el mismo
 * `<ArqueoSheet />` montado por `<DrawerHost />` cuando
 * `useDashboardDrawerStore.openDrawer === 'arqueo'` (REQ-OPS-138
 * single-drawer invariant). El drawer-from-right pattern es
 * compartido con Suscripciones (Venta wizard dentro de
 * SuscripcionesSheet) y con Ingreso/Salida (IngresoSheet /
 * SalidaSheet envolviendo IngresoPanel / SalidaPanel).
 *
 * The button is disabled when no active sesion exists — opening the
 * arqueo drawer without a sesion would render the no-session fallback
 * inside `<ArqueoParcial />`, which is a confusing UX. Operators can
 * only arquear when they have an open turno.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

export interface ArqueoButtonProps {
  /**
   * Active operator turno UUID. When `null` (no active turno) the
   * button is disabled — opening the arqueo drawer without a sesion
   * would render the F3.3 "no active session" fallback and the
   * operator would have to open a turno first anyway.
   */
  uuid_sesion: string | null;
}

export function ArqueoButton({ uuid_sesion }: ArqueoButtonProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const openDrawer = useDashboardDrawerStore((s) => s.open);

  function handleClick(): void {
    // The anchor id ('mi-turno-arqueo-button') lets <DrawerHost />
    // restore focus on Esc close. Mirrors the F4 hotkey chip +
    // left-sidebar nav button conventions in Dashboard.tsx.
    openDrawer('arqueo', 'mi-turno-arqueo-button');
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      data-testid="mi-turno-arqueo-button"
      onClick={handleClick}
      disabled={uuid_sesion === null}
      aria-label={t('miTurno.hacerArqueo')}
    >
      {t('miTurno.hacerArqueo')}
    </Button>
  );
}
