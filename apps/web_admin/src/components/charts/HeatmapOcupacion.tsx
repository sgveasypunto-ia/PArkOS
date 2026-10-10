/**
 * `HeatmapOcupacion.tsx` — 24h x N sucursales activity heatmap (HU-F17.1, T5).
 *
 * Sequential encoding: ONE hue (`--chart-1`), varying only opacity
 * light->dark per the dataviz skill's "sequential = one hue" rule --
 * this sidesteps needing a second, separately-validated dark-mode ramp
 * for a 2-dimensional grid (documented tradeoff in the apply report).
 * Cells are ``ingresos`` per UTC hour bucket, an activity-intensity
 * PROXY, not true concurrent occupancy (see
 * `DashboardOcupacionHorariaItem`'s backend docstring). A table-view
 * toggle is mandatory accessibility relief for a sequential/heatmap
 * form (dataviz skill, check 6) -- it is not optional chrome here.
 *
 * Bundled (with its 2 sibling charts) inside `CrossBranchCharts.tsx`, which
 * `Dashboard.tsx` loads via `React.lazy` (dynamic import) -- see that
 * file for why all 4 charts share one lazy boundary.
 *
 * HU-F19.2 generalization: this component is also reused by
 * `features/sync/pages/SyncDashboard.tsx` to render a 24h x N sucursales
 * sync-lag heatmap instead of an ingresos-activity one. The magnitude
 * field name (`ingresos_count`) is kept as-is for backward compatibility
 * (existing callers/tests pass it unchanged); four NEW optional props
 * let a caller override the unit label, the bottom disclaimer, the
 * empty-state copy, and add a row-click (drill-down) -- all default to
 * the exact original ingresos copy/behavior, so `CrossBranchCharts.tsx` and
 * `Reporteria.tsx` need no changes.
 */
import { useId, useMemo, useState } from 'react';

export interface HeatmapCell {
  uuid_sucursal: string;
  hora: number;
  ingresos_count: number;
}

export interface HeatmapBranch {
  uuid: string;
  nombre: string | null;
}

export interface HeatmapOcupacionProps {
  data: HeatmapCell[];
  sucursales: HeatmapBranch[];
  title: string;
  /** Unit label appended to the hover tooltip value (default: `'ingresos'`). */
  valueUnitLabel?: string;
  /** Bottom disclaimer under the SVG grid (default: the original ingresos-proxy caption). */
  footerNote?: string;
  /** Empty-state copy when `sucursales.length === 0` (default: the original ingresos copy). */
  emptyMessage?: string;
  /**
   * Optional drill-down: called with a branch's `uuid` when its row
   * label is activated (click or Enter/Space). Absent by default --
   * existing callers get no interactive row affordance, unchanged.
   */
  onRowClick?: (uuid: string) => void;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const CELL = 18;
const LABEL_WIDTH = 120;
const DEFAULT_VALUE_UNIT_LABEL = 'ingresos';
const DEFAULT_FOOTER_NOTE =
  'Intensidad de actividad (ingresos por hora, UTC) -- no es ocupación concurrente real.';
const DEFAULT_EMPTY_MESSAGE = 'Sin sucursales en el rango.';

export function HeatmapOcupacion({
  data,
  sucursales,
  title,
  valueUnitLabel = DEFAULT_VALUE_UNIT_LABEL,
  footerNote = DEFAULT_FOOTER_NOTE,
  emptyMessage = DEFAULT_EMPTY_MESSAGE,
  onRowClick,
}: HeatmapOcupacionProps): JSX.Element {
  const titleId = useId();
  const [asTable, setAsTable] = useState(false);
  const [hover, setHover] = useState<{ uuid: string; hora: number } | null>(null);

  const byKey = useMemo(() => {
    const m = new Map<string, number>();
    for (const cell of data) {
      m.set(`${cell.uuid_sucursal}:${cell.hora}`, cell.ingresos_count);
    }
    return m;
  }, [data]);

  const maxCount = useMemo(
    () => Math.max(1, ...data.map((d) => d.ingresos_count)),
    [data],
  );

  if (sucursales.length === 0) {
    return (
      <div
        className="flex h-[120px] items-center justify-center text-sm text-muted-foreground"
        data-testid="heatmap-ocupacion-empty"
      >
        {emptyMessage}
      </div>
    );
  }

  const width = LABEL_WIDTH + HOURS.length * CELL;
  const height = sucursales.length * CELL + 20;

  return (
    <figure data-testid="heatmap-ocupacion">
      <div className="mb-1 flex items-center justify-between">
        <figcaption id={titleId} className="text-xs font-medium text-muted-foreground">
          {title}
        </figcaption>
        <button
          type="button"
          className="text-xs font-medium text-primary underline-offset-2 hover:underline"
          onClick={() => setAsTable((v) => !v)}
          data-testid="heatmap-ocupacion-toggle-table"
        >
          {asTable ? 'Ver como mapa de calor' : 'Ver como tabla'}
        </button>
      </div>

      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="heatmap-ocupacion-table">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col" className="p-1 text-left">
                  Sucursal
                </th>
                {HOURS.map((h) => (
                  <th key={h} scope="col" className="p-1 text-right tabular-nums">
                    {h}h
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sucursales.map((s) => (
                <tr key={s.uuid}>
                  <th
                    scope="row"
                    className={
                      onRowClick
                        ? 'cursor-pointer p-1 text-left font-normal underline-offset-2 hover:underline'
                        : 'p-1 text-left font-normal'
                    }
                    tabIndex={onRowClick ? 0 : undefined}
                    role={onRowClick ? 'button' : undefined}
                    onClick={onRowClick ? () => onRowClick(s.uuid) : undefined}
                    onKeyDown={
                      onRowClick
                        ? (e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              onRowClick(s.uuid);
                            }
                          }
                        : undefined
                    }
                    data-testid={`heatmap-ocupacion-row-${s.uuid}`}
                  >
                    {s.nombre ?? s.uuid.slice(0, 8)}
                  </th>
                  {HOURS.map((h) => (
                    <td key={h} className="p-1 text-right tabular-nums">
                      {byKey.get(`${s.uuid}:${h}`) ?? 0}
                    </td>
                  ))}
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
            {sucursales.map((s, row) => (
              <g key={s.uuid}>
                <text
                  x={LABEL_WIDTH - 6}
                  y={row * CELL + CELL / 2 + 4}
                  textAnchor="end"
                  className={
                    onRowClick
                      ? 'cursor-pointer fill-muted-foreground text-[10px] underline-offset-2 hover:fill-foreground hover:underline'
                      : 'fill-muted-foreground text-[10px]'
                  }
                  onClick={onRowClick ? () => onRowClick(s.uuid) : undefined}
                  data-testid={`heatmap-ocupacion-row-${s.uuid}`}
                >
                  {s.nombre ?? s.uuid.slice(0, 8)}
                </text>
                {HOURS.map((h) => {
                  const count = byKey.get(`${s.uuid}:${h}`) ?? 0;
                  const opacity = count === 0 ? 0 : 0.15 + 0.85 * (count / maxCount);
                  const isHovered = hover?.uuid === s.uuid && hover.hora === h;
                  return (
                    <rect
                      key={h}
                      x={LABEL_WIDTH + h * CELL}
                      y={row * CELL}
                      width={CELL - 2}
                      height={CELL - 2}
                      rx={2}
                      fill="var(--chart-1)"
                      fillOpacity={opacity}
                      stroke={isHovered ? 'hsl(var(--foreground))' : 'transparent'}
                      strokeWidth={1}
                      onMouseEnter={() => setHover({ uuid: s.uuid, hora: h })}
                      onMouseLeave={() => setHover(null)}
                      data-testid={`heatmap-cell-${s.uuid}-${h}`}
                    />
                  );
                })}
              </g>
            ))}
          </svg>
          {hover && (
            <div
              role="tooltip"
              data-testid="heatmap-ocupacion-tooltip"
              className="pointer-events-none absolute rounded-md border bg-popover px-2 py-1 text-xs shadow-elevation-2"
              style={{
                left: `${((LABEL_WIDTH + hover.hora * CELL + CELL / 2) / width) * 100}%`,
                top: `${((sucursales.findIndex((s) => s.uuid === hover.uuid) * CELL) / height) * 100}%`,
                transform: 'translate(-50%, -120%)',
              }}
            >
              {hover.hora}h: {byKey.get(`${hover.uuid}:${hover.hora}`) ?? 0} {valueUnitLabel}
            </div>
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">{footerNote}</p>
        </div>
      )}
    </figure>
  );
}
