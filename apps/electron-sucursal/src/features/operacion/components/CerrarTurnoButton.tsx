/**
 * `<CerrarTurnoButton />` — navigation-only entry-point to the
 * `/caja/cerrar-turno` page (HU-F12.1, REQ-OPS-187, DA-F12.1-5).
 *
 * The button does NOT call `useSesionActiva().cerrarSesion` — that
 * belongs to F10.2 (`<CerrarTurno>` page). F12.1 owns the *navigation
 * trigger* only; the close logic is the F10.2 routed page's job.
 *
 * Renders as a shadcn `<Button variant="outline">` with the operator's
 * i18n key `miTurno.cerrarTurno`. When `uuid_sesion` is `null` (no
 * active turno) the button is disabled — clicking would be a no-op
 * (the routed page would 404 sesion_not_found anyway).
 */
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

export interface CerrarTurnoButtonProps {
  /**
   * Active operator turno UUID. When `null`, the button is disabled
   * because navigating to `/caja/cerrar-turno` without an active
   * sesion would 404 sesion_not_found on the BE side.
   */
  uuid_sesion: string | null;
}

export function CerrarTurnoButton({ uuid_sesion }: CerrarTurnoButtonProps): JSX.Element {
  const navigate = useNavigate();
  const { t } = useTranslation('operacion');

  function handleClick(): void {
    navigate('/caja/cerrar-turno');
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