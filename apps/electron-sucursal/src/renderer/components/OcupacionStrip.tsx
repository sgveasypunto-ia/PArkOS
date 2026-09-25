/**
 * `<OcupacionStrip />` — shared occupancy organismo (HU-F4.3).
 *
 * Polls `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` every 10s via
 * `useOcupacion()` and renders one chip per `tipo` with a color derived
 * from `classForPorcentaje(activos / cupo_maximo)`. Cross-feature location
 * (precedent `<StatusBar />` F2.3) — F4.4 dashboard, F6.x ingreso and
 * F7.x salida all consume this same organismo.
 *
 * Accessibility:
 *   - Root `role="status"` + `data-testid="ocupacion-strip"`.
 *   - Per chip `aria-live="polite"` + `aria-atomic="false"` so screen
 *     readers announce only the changed cell, not the whole strip.
 *   - Each chip carries a tooltip (`ocupacion_legend_green/yellow/red`)
 *     explaining the threshold. Stale state shows `ocupacion_legend_stale`
 *     on the root.
 *
 * Degraded state:
 *   - When the most recent poll failed but a previous one succeeded, SWR
 *     keeps `data` populated. We set `data-stale="true"` on the root and
 *     render `<AlertCircle />` next to the title so the operator keeps
 *     situational awareness (plan.md:1433 verbatim — "el strip conserva
 *     el último valor conocido con indicador visual sutil").
 *
 * AbortController cleanup:
 *   - On `uuid_sucursal` change OR unmount we cancel the in-flight fetch.
 *     SWR handles its own fetcher abort per render via the `AbortSignal`
 *     passed to `parkosFetch`; this effect guarantees that any
 *     pre-computation or derived state in this componente tied to the
 *     previous branch is dropped before fresh data lands.
 */
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle } from 'lucide-react';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import { useOcupacion } from '../../features/operacion/hooks/useOcupacion';
import { classForPorcentaje } from '../../features/operacion/occupancyThresholds';

export interface OcupacionStripProps {
  uuid_sucursal: string | null;
}

type ColorLevel = ReturnType<typeof classForPorcentaje>;

const COLOR_CLASS: Record<ColorLevel, string> = {
  green: 'bg-green-500 text-white',
  yellow: 'bg-amber-500 text-white',
  red: 'bg-destructive text-destructive-foreground',
};

function legendKeyFor(
  color: ColorLevel,
  cupoMaximo: number,
): string {
  // KD-6: cuando el admin no configuró cupo, el chip surface es "cupo no
  // configurado" en lugar del legend genérico por color.
  if (cupoMaximo === 0) return 'cupo_no_configurado';
  if (color === 'green') return 'ocupacion_legend_green';
  if (color === 'yellow') return 'ocupacion_legend_yellow';
  return 'ocupacion_legend_red';
}

export function OcupacionStrip({ uuid_sucursal }: OcupacionStripProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const { data, isStale } = useOcupacion(uuid_sucursal);

  /**
   * AbortController cleanup on `uuid_sucursal` change / unmount.
   *
   * SWR already cancels in-flight fetches when its key changes (its
   * internal fetcher passes `AbortSignal` to `parkosFetch`). This effect
   * is the belt-and-braces layer for any work the componente itself may
   * schedule off the `uuid_sucursal` prop (none today, but the pattern
   * is documented here so F4.4 / F6.x consumers do not regress it).
   *
   * Returns a cleanup function that aborts the in-flight controller when
   * the effect re-runs (uuid_sucursal changed) or when the componente
   * unmounts. React guarantees the cleanup runs before the next effect
   * and on unmount.
   */
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    return () => {
      controller.abort();
      controllerRef.current = null;
    };
  }, [uuid_sucursal]);

  const items = data?.items ?? [];

  return (
    <TooltipProvider delayDuration={150}>
      <div
        role="status"
        data-testid="ocupacion-strip"
        data-stale={isStale ? 'true' : 'false'}
        className="flex min-w-0 flex-wrap items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm"
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className="flex shrink-0 items-center gap-1 font-medium text-foreground"
              data-testid="ocupacion-strip-title"
            >
              {t('ocupacion_titulo')}
              {isStale ? (
                <AlertCircle
                  className="h-4 w-4 text-amber-500"
                  aria-hidden="true"
                  data-testid="ocupacion-strip-stale-icon"
                />
              ) : null}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {t(isStale ? 'ocupacion_legend_stale' : 'ocupacion_titulo')}
          </TooltipContent>
        </Tooltip>

        {items.length === 0 ? (
          <span className="text-muted-foreground" data-testid="ocupacion-strip-empty">
            —
          </span>
        ) : (
          items.map((item) => {
            const color = classForPorcentaje(
              item.cupo_maximo === 0 ? Number.POSITIVE_INFINITY : item.activos / item.cupo_maximo,
            );
            const legendKey = legendKeyFor(color, item.cupo_maximo);
            return (
              <Tooltip key={item.uuid_tipo_vehiculo}>
                <TooltipTrigger asChild>
                  <span
                    data-testid={`ocupacion-chip-${item.tipo}`}
                    data-color={color}
                    aria-live="polite"
                    aria-atomic="false"
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${COLOR_CLASS[color]}`}
                  >
                    {item.tipo}: {item.activos}/{item.cupo_maximo}
                  </span>
                </TooltipTrigger>
                <TooltipContent>{t(legendKey)}</TooltipContent>
              </Tooltip>
            );
          })
        )}
      </div>
    </TooltipProvider>
  );
}