/**
 * `<CobradoEnTurno />` — dinero cobrado en efectivo durante el turno
 * (`total_cobrado_efectivo_cop` de `GET /operacion/mi-turno`), de sólo
 * lectura. Lo comparten el popover del encabezado (`TurnoActivoToggle`)
 * y `MiTurnoPanel`, para que la regla viva en un solo lugar.
 *
 * Reglas:
 *   - Sólo se pinta un monto cuando el hook trae datos reales
 *     (`isLoaded`); si no, `—` (un cero de relleno no es un cobro).
 *   - Error sin datos previos: `—` + mensaje `role="alert"`. Con datos
 *     previos, un refresco fallido conserva el último valor (SWR) y no
 *     alerta.
 *   - El datáfono NO se muestra: el BE lo fija en 0 (F12.1.1 /
 *     REQ-OPS-197) y un cero ahí sería un dato falso.
 */
import { useTranslation } from 'react-i18next';

import { formatCOP } from '../../caja/lib/format';
import type { UseMiTurnoReturn } from '../hooks/useMiTurno';

export type CobradoEnTurnoProps = Pick<UseMiTurnoReturn, 'data' | 'error' | 'isLoaded'> & {
  className?: string;
};

export function CobradoEnTurno({
  data,
  error,
  isLoaded,
  className,
}: CobradoEnTurnoProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const efectivo = isLoaded && data ? formatCOP(data.total_cobrado_efectivo_cop) : '—';
  const conError = !isLoaded && error !== undefined;

  return (
    <section
      role="region"
      aria-label={t('miTurno.cobrado.regionLabel')}
      data-testid="mi-turno-cobrado"
      className={className}
    >
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-sm">
          {t('miTurno.cobrado.efectivo')}
        </span>
        <span
          className="font-mono text-xl font-semibold tabular-nums tracking-tight text-foreground"
          data-testid="mi-turno-cobrado-efectivo-value"
        >
          {efectivo}
        </span>
      </div>
      {conError && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {t('miTurno.cobrado.error')}
        </p>
      )}
    </section>
  );
}
