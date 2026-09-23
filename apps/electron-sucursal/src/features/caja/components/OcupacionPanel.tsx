/**
 * `<OcupacionPanel />` — in-dashboard inventory section (HU-F4.3,
 * F4.4 relocate, plus the "elegant" per-tipo rendering added by the
 * 2026-09-17 dashboard-hub iteration).
 *
 * Layout (one compact row per admin-configured tipo):
 *
 *   [●]  carro  1/0   ━━━━━━━━━━   100%  (red dot when full)
 *   [●]  moto   0/10  ────────────    0%
 *   [●]  bici   2/5   ━━━━━         40%
 *
 * Each row communicates at a glance:
 *   - Dot color = current occupancy status (green < 66%, amber 66-90%, red > 90%)
 *   - count `activos / cupo_maximo`
 *   - thin progress bar showing the occupancy ratio (only when cupo_maximo > 0)
 *
 * The parent card already says "INVENTARIO"; per UX feedback we dropped
 * the redundant "Ocupación en vivo" header label. Stale state is
 * surfaced by a tiny amber AlertCircle icon to the left of the list
 * (with a tooltip explaining the legend).
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

// Dot color (left of each row) — semantic by occupancy ratio.
const DOT_BG: Record<ColorLevel, string> = {
  green: 'bg-emerald-500',
  yellow: 'bg-amber-500',
  red: 'bg-red-500',
};
const PROGRESS_BG: Record<ColorLevel, string> = {
  green: 'bg-emerald-500',
  yellow: 'bg-amber-500',
  red: 'bg-red-500',
};
const TEXT_MUTED: Record<ColorLevel, string> = {
  green: 'text-emerald-700 dark:text-emerald-300',
  yellow: 'text-amber-700 dark:text-amber-300',
  red: 'text-red-700 dark:text-red-300',
};

function legendKeyFor(color: ColorLevel, cupoMaximo: number): string {
  // KD-6: when admin hasn't configured a cupo, the surface text is
  // "cupo no configurado" instead of a generic colored legend.
  if (cupoMaximo === 0) return 'cupo_no_configurado';
  if (color === 'green') return 'ocupacion_legend_green';
  if (color === 'yellow') return 'ocupacion_legend_yellow';
  return 'ocupacion_legend_red';
}

function progressPct(activos: number, cupo: number): number {
  if (cupo <= 0) return 0;
  return Math.max(0, Math.min(100, (activos / cupo) * 100));
}

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
      <ul
        role="status"
        data-testid="ocupacion-panel"
        data-stale={isStale ? 'true' : 'false'}
        className="flex flex-col gap-2 text-sm px-1"
      >
        {isStale ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <AlertCircle
                className="h-4 w-4 self-end text-amber-500"
                aria-hidden="true"
                data-testid="ocupacion-panel-stale-icon"
              />
            </TooltipTrigger>
            <TooltipContent>{t('ocupacion_legend_stale')}</TooltipContent>
          </Tooltip>
        ) : null}

        {items.length === 0 ? (
          <li
            className="text-muted-foreground"
            data-testid="ocupacion-panel-empty"
          >
            —
          </li>
        ) : (
          items.map((item) => {
            const color = classForPorcentaje(
              item.cupo_maximo === 0 ? Number.POSITIVE_INFINITY : item.activos / item.cupo_maximo,
            );
            const legendKey = legendKeyFor(color, item.cupo_maximo);
            const pct = progressPct(item.activos, item.cupo_maximo);
            return (
              <Tooltip key={item.uuid_tipo_vehiculo}>
                <TooltipTrigger asChild>
                  <li
                    data-testid={`ocupacion-panel-row-${item.tipo}`}
                    data-color={color}
                    aria-live="polite"
                    aria-atomic="false"
                    className="flex items-center gap-3 py-0.5"
                  >
                    {/* status dot */}
                    <span
                      aria-hidden
                      className={`inline-block h-2 w-2 shrink-0 rounded-full ring-2 ring-background ${DOT_BG[color]}`}
                    />
                    {/* tipo label, fixed width via uppercase tracking */}
                    <span className="w-16 shrink-0 truncate text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground/80">
                      {item.tipo}
                    </span>
                    {/* X / Y count */}
                    <span
                      className={`w-14 shrink-0 text-right text-sm font-mono font-medium tabular-nums ${TEXT_MUTED[color]}`}
                    >
                      {item.activos}
                      <span className="mx-0.5 text-muted-foreground">/</span>
                      {item.cupo_maximo}
                    </span>
                    {/* progress bar (only when admin configured a cupo) */}
                    {item.cupo_maximo > 0 ? (
                      <span
                        aria-hidden
                        className="relative inline-block h-1 flex-1 overflow-hidden rounded-full bg-muted/60"
                      >
                        <span
                          className={`absolute left-0 top-0 h-full rounded-full transition-[width] duration-500 ease-out ${PROGRESS_BG[color]}`}
                          style={{ width: `${pct}%` }}
                        />
                      </span>
                    ) : (
                      <span
                        aria-hidden
                        className="h-1 flex-1 rounded-full bg-muted/40"
                      />
                    )}
                  </li>
                </TooltipTrigger>
                <TooltipContent>{t(legendKey)}</TooltipContent>
              </Tooltip>
            );
          })
        )}
      </ul>
    </TooltipProvider>
  );
}