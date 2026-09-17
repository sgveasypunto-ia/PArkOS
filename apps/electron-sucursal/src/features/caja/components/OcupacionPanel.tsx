/**
 * `<OcupacionPanel />` — in-dashboard occupancy section (HU-F4.3, F4.4
 * relocate).
 *
 * Logic is intentionally a near-clone of `<OcupacionStrip />`
 * (`renderer/components/OcupacionStrip.tsx`) so the global mount at
 * `App.tsx:48` (F4.3 "TEMPORAL") can be deleted in PR-6 without any
 * behavioral change. The diff is structural only: this panel lives
 * inside the dashboard route (not at the SPA root) so the strip
 * disappears when the operator navigates to `/login`,
 * `/caja/abrir-turno`, or `/caja/cerrar-turno`. REQ-OPS-140 Scenario
 * "App.tsx global strip removed" verifies the swap.
 *
 * `data-testid="ocupacion-panel"` distinguishes this in-dashboard
 * variant from the soon-to-be-deleted global `<OcupacionStrip />`
 * (which kept `data-testid="ocupacion-strip"`).
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

import { useOcupacion } from '../../operacion/hooks/useOcupacion';
import { classForPorcentaje } from '../../operacion/occupancyThresholds';

export interface OcupacionPanelProps {
  uuid_sucursal: string | null;
}

type ColorLevel = ReturnType<typeof classForPorcentaje>;

const COLOR_CLASS: Record<ColorLevel, string> = {
  green: 'bg-green-500 text-white',
  yellow: 'bg-amber-500 text-white',
  red: 'bg-destructive text-destructive-foreground',
};

function legendKeyFor(color: ColorLevel, cupoMaximo: number): string {
  // KD-6: cuando el admin no configuró cupo, el chip surface es "cupo no
  // configurado" en lugar del legend genérico por color.
  if (cupoMaximo === 0) return 'cupo_no_configurado';
  if (color === 'green') return 'ocupacion_legend_green';
  if (color === 'yellow') return 'ocupacion_legend_yellow';
  return 'ocupacion_legend_red';
}

/**
 * In-dashboard occupancy section. Polls `GET /operacion/ocupacion` every
 * 10s via `useOcupacion` (REQ-OPS-132 fetcher-closure idiom — the
 * closure receives the bare UUID, NOT the SWR key).
 */
export function OcupacionPanel({ uuid_sucursal }: OcupacionPanelProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const { data, isStale } = useOcupacion(uuid_sucursal);

  // Belt-and-braces AbortController for the rare case the panel is
  // remounted with a different `uuid_sucursal` (admin branch switch).
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
        data-testid="ocupacion-panel"
        data-stale={isStale ? 'true' : 'false'}
        className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm"
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className="flex items-center gap-1 font-medium text-foreground"
              data-testid="ocupacion-panel-title"
            >
              {t('ocupacion_titulo')}
              {isStale ? (
                <AlertCircle
                  className="h-4 w-4 text-amber-500"
                  aria-hidden="true"
                  data-testid="ocupacion-panel-stale-icon"
                />
              ) : null}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {t(isStale ? 'ocupacion_legend_stale' : 'ocupacion_titulo')}
          </TooltipContent>
        </Tooltip>

        {items.length === 0 ? (
          <span className="text-muted-foreground" data-testid="ocupacion-panel-empty">
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
                    data-testid={`ocupacion-panel-chip-${item.tipo}`}
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