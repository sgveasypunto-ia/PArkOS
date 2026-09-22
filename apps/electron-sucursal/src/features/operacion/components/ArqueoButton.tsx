/**
 * `<ArqueoButton />` — right-side drawer trigger for HU-F10.1 partial
 * arqueo (auditoría del turno actual, sin cierre).
 *
 * Lives inside `<MiTurnoPanel />` in the dashboard's RIGHT sidebar
 * as the per-turn caja action. The "Cerrar turno" entry-point is the
 * dashboard header button (single source of truth); MiTurnoPanel does
 * NOT duplicate it. The arqueo screen itself is a drawer-embedded page
 * mounted by `<DrawerHost />` when the `useDashboardDrawerStore` state
 * is `openDrawer === 'arqueo'` (REQ-OPS-138 single-drawer invariant).
 *
 * F11.3 UX direction: the operator's per-turn action surface is
 * the RIGHT sidebar (MiTurnoPanel). The arqueo flow was previously
 * surfaced as a left-sidebar nav button + a separate routed page
 * (`/caja/arqueo-parcial`); both were removed. The drawer-from-right
 * pattern is shared with Suscripciones (Venta wizard inside
 * SuscripcionesSheet) and with Ingreso/Salida (IngresoSheet /
 * SalidaSheet wrapping IngresoPanel / SalidaPanel).
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
