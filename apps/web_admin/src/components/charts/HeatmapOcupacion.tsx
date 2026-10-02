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
 * Bundled (with its 3 sibling charts) inside `ChartsSection.tsx`, which
 * `Dashboard.tsx` loads via `React.lazy` (dynamic import) -- see that
 * file for why all 4 charts share one lazy boundary.
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
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const CELL = 18;
const LABEL_WIDTH = 120;

export function HeatmapOcupacion({
  data,
  sucursales,
  title,
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
        Sin sucursales en el rango.
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
                  <th scope="row" className="p-1 text-left font-normal">
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
                  className="fill-muted-foreground text-[10px]"
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
              {hover.hora}h: {byKey.get(`${hover.uuid}:${hover.hora}`) ?? 0} ingresos
            </div>
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">
            Intensidad de actividad (ingresos por hora, UTC) -- no es ocupación concurrente real.
          </p>
        </div>
      )}
    </figure>
  );
}
