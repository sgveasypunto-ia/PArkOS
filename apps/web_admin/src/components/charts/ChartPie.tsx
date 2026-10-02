/**
 * `ChartPie.tsx` — "estado FE 24h" donut chart (HU-F17.1, T5).
 *
 * Only 2 states exist in the real data (`enviada` / `pendiente` -- see
 * `DashboardEstadoFEItem`'s docstring in `admin_views.py` for why there is
 * no DIAN accepted/rejected enum on the real schema). This is a STATUS
 * encoding, not a categorical one, so it reuses this design system's own
 * AA-validated `--success` / `--warning` tokens rather than the chart-N
 * categorical ramp (dataviz skill: "status colors are reserved, never
 * reused for 'series N'"). Direct percentage labels + a legend (a pie
 * always needs one, even at 2 slices).
 */
const SIZE = 160;
const STROKE = 28;
const RADIUS = (SIZE - STROKE) / 2;
const CENTER = SIZE / 2;

export interface ChartPieItem {
  estado: string;
  count: number;
}

export interface ChartPieProps {
  data: ChartPieItem[];
  title: string;
}

const COLOR_BY_ESTADO: Record<string, string> = {
  enviada: 'hsl(var(--success))',
  pendiente: 'hsl(var(--warning))',
};
const LABEL_BY_ESTADO: Record<string, string> = {
  enviada: 'Enviada',
  pendiente: 'Pendiente',
};

export function ChartPie({ data, title }: ChartPieProps): JSX.Element {
  const total = data.reduce((acc, d) => acc + d.count, 0);

  if (total === 0) {
    return (
      <div
        className="flex h-[160px] items-center justify-center text-sm text-muted-foreground"
        data-testid="chart-pie-empty"
      >
        Sin facturas electrónicas en 24h.
      </div>
    );
  }

  const circumference = 2 * Math.PI * RADIUS;
  let offsetSoFar = 0;

  return (
    <figure data-testid="chart-pie" className="flex items-center gap-4">
      <figcaption className="sr-only">{title}</figcaption>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE}
        height={SIZE}
        role="img"
        aria-label={title}
      >
        <circle
          cx={CENTER}
          cy={CENTER}
          r={RADIUS}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={STROKE}
        />
        {data.map((d) => {
          const fraction = d.count / total;
          const dash = fraction * circumference;
          const gap = circumference - dash;
          const el = (
            <circle
              key={d.estado}
              cx={CENTER}
              cy={CENTER}
              r={RADIUS}
              fill="none"
              stroke={COLOR_BY_ESTADO[d.estado] ?? 'hsl(var(--muted-foreground))'}
              strokeWidth={STROKE}
              strokeDasharray={`${dash} ${gap}`}
              strokeDashoffset={-offsetSoFar}
              transform={`rotate(-90 ${CENTER} ${CENTER})`}
              data-testid={`chart-pie-slice-${d.estado}`}
            />
          );
          offsetSoFar += dash;
          return el;
        })}
        <text
          x={CENTER}
          y={CENTER}
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-foreground text-sm font-semibold tabular-nums"
        >
          {total}
        </text>
      </svg>
      <ul className="flex flex-col gap-1 text-xs" aria-label={`Leyenda: ${title}`}>
        {data.map((d) => (
          <li key={d.estado} className="flex items-center gap-2" data-testid={`chart-pie-legend-${d.estado}`}>
            <span
              className="inline-block size-2.5 rounded-full"
              style={{ backgroundColor: COLOR_BY_ESTADO[d.estado] ?? 'hsl(var(--muted-foreground))' }}
              aria-hidden="true"
            />
            <span className="text-foreground">{LABEL_BY_ESTADO[d.estado] ?? d.estado}</span>
            <span className="tabular-nums text-muted-foreground">
              {d.count} ({Math.round((d.count / total) * 100)}%)
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
