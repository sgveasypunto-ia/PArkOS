/**
 * `<AbrirTurnoAviso />` — presentational states of the open-shift screen.
 *
 * The operator is never asked for a value: the base de caja is a branch
 * parameter configured by administration. The container (`<AbrirTurno>`) opens
 * the shift on its own and drives `status`; on success it leaves this screen
 * for the dashboard, which shows the base notice (`<BaseCajaAviso>`).
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export type AbrirTurnoStatus =
  | 'cargando'
  | 'sin_base'
  | 'abriendo'
  | 'sesion_ya_abierta'
  | 'error';

export interface AbrirTurnoAvisoProps {
  status: AbrirTurnoStatus;
  onReintentar: () => void;
  onIrAlTurno: () => void;
}

export function AbrirTurnoAviso({
  status,
  onReintentar,
  onIrAlTurno,
}: AbrirTurnoAvisoProps): JSX.Element {
  const { t } = useTranslation(['caja', 'common']);

  return (
    <Card data-testid="abrir-turno-form" aria-labelledby="abrir-turno-title">
      <CardHeader>
        <CardTitle id="abrir-turno-title" asChild>
          <h1>{t('caja:abrirTurno')}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4" aria-live="polite">
        {(status === 'cargando' || status === 'abriendo') && (
          <p data-testid="abrir-turno-abriendo">
            {t('caja:abrirTurnoAbriendo', { defaultValue: 'Abriendo turno…' })}
          </p>
        )}

        {status === 'sin_base' && (
          <>
            <p role="alert" data-testid="abrir-turno-sin-base">
              {t('caja:abrirTurnoSinBase', {
                defaultValue:
                  'Esta sucursal no tiene una base de caja configurada, por eso no se puede abrir el turno. Contacta al supervisor o al administrador del sistema.',
              })}
            </p>
            <Button type="button" onClick={onReintentar} data-testid="abrir-turno-reintentar">
              {t('caja:abrirTurnoReintentar', { defaultValue: 'Reintentar' })}
            </Button>
          </>
        )}

        {status === 'sesion_ya_abierta' && (
          <>
            <p role="alert" data-testid="abrir-turno-error-sesion-ya-abierta">
              {t('caja:sesionYaAbierta')}
            </p>
            <Button type="button" onClick={onIrAlTurno} data-testid="abrir-turno-ir-al-turno">
              {t('caja:irAlTurno')}
            </Button>
          </>
        )}

        {status === 'error' && (
          <>
            <p role="alert" data-testid="abrir-turno-error-network">
              {t('common:error')}
            </p>
            <Button type="button" onClick={onReintentar} data-testid="abrir-turno-reintentar">
              {t('caja:abrirTurnoReintentar', { defaultValue: 'Reintentar' })}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
