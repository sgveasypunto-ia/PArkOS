/**
 * `<CerrarTurnoButton />` — right-side drawer trigger for HU-F3.3 +
 * HU-F10.2 turn-closing flow (F11.3 follow-up).
 *
 * The button does NOT call `useSesionActiva().cerrarSesion` — that
 * belongs to F10.2 (`<CerrarTurno>` page mounted inside
 * `<CerrarTurnoSheet />`). The button only opens the right-side
 * drawer; the close logic is the F10.2 page's job.
 *
 * Renders as a shadcn `<Button variant="outline">` with the operator's
 * i18n key `miTurno.cerrarTurno`. When `uuid_sesion` is `null` (no
 * active turno) the button is disabled — opening the drawer without
 * a sesion would render the F10.2 page's "no active sesion" branch
 * (the page returns null without a sesion), which is confusing UX.
 *
 * Anchor id `mi-turno-cerrar-button` lets `<CerrarTurnoSheet />`
 * restore focus on Esc close (REQ-OPS-138 §Esc).
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

export interface CerrarTurnoButtonProps {
  /**
   * Active operator turno UUID. When `null`, the button is disabled
   * because opening the drawer without an active sesion would render
   * the F10.2 page's "no active sesion" branch.
   */
  uuid_sesion: string | null;
}

export function CerrarTurnoButton({ uuid_sesion }: CerrarTurnoButtonProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const openDrawer = useDashboardDrawerStore((s) => s.open);

  function handleClick(): void {
    openDrawer('cerrar-turno', 'mi-turno-cerrar-button');
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      data-testid="mi-turno-cerrar-button"
      onClick={handleClick}
      disabled={uuid_sesion === null}
      aria-label={t('miTurno.cerrarTurno')}
    >
      {t('miTurno.cerrarTurno')}
    </Button>
  );
}