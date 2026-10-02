/**
 * `<SuscripcionesCohorte />` — subscription cohort retention heatmap
 * (HU-F17.4, BR1).
 *
 * Visual pattern reused from `HeatmapOcupacion.tsx` (HU-F17.1/F17.2) per
 * this HU's explicit instruction: same SVG grid + table-view toggle +
 * tooltip shape. The **color semantics were re-checked against the
 * dataviz skill for this HU** (explicitly requested — a retention %
 * heatmap is not the same kind of magnitude as an activity-intensity
 * heatmap), with these conclusions:
 *
 * - Still a SEQUENTIAL encoding, one hue (`--chart-1`, the same
 *   validated ramp `HeatmapOcupacion` already uses). Retención is a
 *   bounded magnitude (0-100%), not a polarity and not a fixed status
 *   set, so a diverging pair or the status palette would be the wrong
 *   tool here — "Sequential = magnitude, one hue, light->dark" is
 *   exactly the right call, same as the original heatmap.
 * - The scale is FIXED at 0-100% (`porcentaje_retencion / 100`), NEVER
 *   relative to the max observed in the dataset — unlike the ocupación
 *   heatmap's `count / maxCount`, 100% here is a real, meaningful
 *   ceiling (every member of the cohort still covered), not "whatever
 *   the busiest cell happened to be". Using a relative scale would make
 *   a uniformly-bad cohort (everyone churned) look just as "dark"/
 *   alarming as a uniformly-great one, which is the opposite of useful.
 * - A measured 0% is a MEANINGFUL (bad) data point and must stay
 *   visible: the opacity floor (0.15, same floor the ocupación heatmap
 *   uses for "some data, low value") never drops to fully transparent
 *   for a cell that exists. A cell with NO rect at all means "not
 *   enough time has passed to measure this cohort at this offset yet"
 *   (the normal triangular cohort-table shape) — a state that must read
 *   as visually DISTINCT from "measured, and it's 0%". The table view
 *   spells this out in text (`—` vs `0%`) so the distinction never
 *   depends on color alone (dataviz skill check 6 — a table fallback is
 *   mandatory for a sequential/heatmap form; here it is also the
 *   no-data-vs-zero disambiguation channel).
 */
import { useId, useMemo, useState } from 'react';

import type { CohorteRetencionCell, CohorteSuscripcionItem } from '../api/reporteriaSchema';

export interface SuscripcionesCohorteProps {
  cohortes: CohorteSuscripcionItem[];
  data: CohorteRetencionCell[];
  maxOffsetMeses: number;
  title: string;
}

const CELL = 28;
const LABEL_WIDTH = 96;
/** Lowest visible opacity for a MEASURED cell (0% retention) — never 0. */
const MIN_OPACITY = 0.15;

function cellKey(mes: string, offset: number): string {
  return `${mes}:${offset}`;
}

function mesLabel(mesCohorte: string): string {
  // "YYYY-MM-DD" -> "YYYY-MM"; the cohort axis is month-granular.
  return mesCohorte.slice(0, 7);
}

export function SuscripcionesCohorte({
  cohortes,
  data,
  maxOffsetMeses,
  title,
}: SuscripcionesCohorteProps): JSX.Element {
  const titleId = useId();
  const [asTable, setAsTable] = useState(false);
  const [hover, setHover] = useState<{ mes: string; offset: number } | null>(null);

  const byKey = useMemo(() => {
    const m = new Map<string, CohorteRetencionCell>();
    for (const cell of data) {
      m.set(cellKey(cell.mes_cohorte, cell.mes_offset), cell);
    }
    return m;
  }, [data]);

  const offsets = useMemo(
    () => Array.from({ length: Math.max(0, maxOffsetMeses) + 1 }, (_, i) => i),
    [maxOffsetMeses],
  );

  if (cohortes.length === 0) {
    return (
      <div
        className="flex h-[120px] items-center justify-center text-sm text-muted-foreground"
        data-testid="suscripciones-cohorte-empty"
      >
        Sin suscripciones en el rango.
      </div>
    );
  }

  const width = LABEL_WIDTH + offsets.length * CELL;
  const height = cohortes.length * CELL + 20;

  return (
    <figure data-testid="suscripciones-cohorte">
      <div className="mb-1 flex items-center justify-between">
        <figcaption id={titleId} className="text-xs font-medium text-muted-foreground">
          {title}
        </figcaption>
        <button
          type="button"
          className="text-xs font-medium text-primary underline-offset-2 hover:underline"
          onClick={() => setAsTable((v) => !v)}
          data-testid="suscripciones-cohorte-toggle-table"
        >
          {asTable ? 'Ver como mapa de calor' : 'Ver como tabla'}
        </button>
      </div>

      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="suscripciones-cohorte-table">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col" className="p-1 text-left">
                  Cohorte (mes de alta)
                </th>
                <th scope="col" className="p-1 text-right">
                  N
                </th>
                {offsets.map((o) => (
                  <th key={o} scope="col" className="p-1 text-right tabular-nums">
                    M+{o}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cohortes.map((c) => (
                <tr key={c.mes_cohorte}>
                  <th scope="row" className="p-1 text-left font-normal">
                    {mesLabel(c.mes_cohorte)}
                  </th>
                  <td className="p-1 text-right tabular-nums">{c.cohorte_size}</td>
                  {offsets.map((o) => {
                    const cell = byKey.get(cellKey(c.mes_cohorte, o));
                    return (
                      <td
                        key={o}
                        className="p-1 text-right tabular-nums"
                        data-testid={`suscripciones-cohorte-table-cell-${c.mes_cohorte}-${o}`}
                      >
                        {cell ? `${cell.porcentaje_retencion.toFixed(0)}%` : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full"
            role="img"
            aria-labelledby={titleId}
          >
            {cohortes.map((c, row) => (
              <g key={c.mes_cohorte}>
                <text
                  x={LABEL_WIDTH - 6}
                  y={row * CELL + CELL / 2 + 4}
                  textAnchor="end"
                  className="fill-muted-foreground text-[10px]"
                >
                  {mesLabel(c.mes_cohorte)}
                </text>
                {offsets.map((o) => {
                  const cell = byKey.get(cellKey(c.mes_cohorte, o));
                  const isHovered = hover?.mes === c.mes_cohorte && hover.offset === o;

                  if (!cell) {
                    // No data yet (cohort too young to measure this
                    // offset) -- deliberately NOT the sequential hue, so
                    // it never reads as "measured 0%".
                    return (
                      <rect
                        key={o}
                        x={LABEL_WIDTH + o * CELL}
                        y={row * CELL}
                        width={CELL - 2}
                        height={CELL - 2}
                        rx={2}
                        className="fill-muted/30"
                        data-testid={`suscripciones-cohorte-cell-${c.mes_cohorte}-${o}-nodata`}
                      />
                    );
                  }

                  const opacity =
                    MIN_OPACITY + (1 - MIN_OPACITY) * (cell.porcentaje_retencion / 100);
                  return (
                    <rect
                      key={o}
                      x={LABEL_WIDTH + o * CELL}
                      y={row * CELL}
                      width={CELL - 2}
                      height={CELL - 2}
                      rx={2}
                      fill="var(--chart-1)"
                      fillOpacity={opacity}
                      stroke={isHovered ? 'hsl(var(--foreground))' : 'transparent'}
                      strokeWidth={1}
                      onMouseEnter={() => setHover({ mes: c.mes_cohorte, offset: o })}
                      onMouseLeave={() => setHover(null)}
                      data-testid={`suscripciones-cohorte-cell-${c.mes_cohorte}-${o}`}
                    />
                  );
                })}
              </g>
            ))}
          </svg>
          {hover && byKey.get(cellKey(hover.mes, hover.offset)) ? (
            <div
              role="tooltip"
              data-testid="suscripciones-cohorte-tooltip"
              className="pointer-events-none absolute rounded-md border bg-popover px-2 py-1 text-xs shadow-elevation-2"
              style={{
                left: `${((LABEL_WIDTH + hover.offset * CELL + CELL / 2) / width) * 100}%`,
                top: `${
                  ((cohortes.findIndex((c) => c.mes_cohorte === hover.mes) * CELL) / height) * 100
                }%`,
                transform: 'translate(-50%, -120%)',
              }}
            >
              {(() => {
                const cell = byKey.get(cellKey(hover.mes, hover.offset));
                if (!cell) return null;
                return `M+${cell.mes_offset}: ${cell.porcentaje_retencion.toFixed(0)}% (${cell.retenidos}/${cell.cohorte_size})`;
              })()}
            </div>
          ) : null}
          <p className="mt-1 text-[10px] text-muted-foreground">
            % de la cohorte que sigue vigente N meses después del alta — aproximación por
            antigüedad, no sigue al mismo cliente a través de renovaciones.
          </p>
        </div>
      )}
    </figure>
  );
}
