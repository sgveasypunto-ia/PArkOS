/**
 * `ChartLine.tsx` — "ingresos 30 días" line chart (HU-F17.1, T5).
 *
 * Hand-rolled SVG (no charting dependency exists in this repo yet --
 * verified via `pnpm-lock.yaml`/package.json before writing this; see the
 * `dataviz` skill invocation in the apply report for the palette/marks
 * this follows). Single series -> no legend box needed (the chart title
 * names it, per `references/marks-and-anatomy.md`). 2px line, filled
 * circular data-ends, a crosshair + tooltip hover layer (mandatory for a
 * line/area form), recessive gridlines, muted axis ink.
 */
import { useId, useMemo, useState } from 'react';

export interface ChartLinePoint {
  fecha: string;
  monto_total: number;
}

export interface ChartLineProps {
  data: ChartLinePoint[];
  title: string;
  height?: number;
}

const MARGIN = { top: 12, right: 12, bottom: 24, left: 8 };
const WIDTH = 480;

export function ChartLine({ data, title, height = 200 }: ChartLineProps): JSX.Element {
  const gradientId = useId();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;

  const maxValue = useMemo(
    () => Math.max(1, ...data.map((d) => d.monto_total)),
    [data],
  );

  const points = useMemo(
    () =>
      data.map((d, i) => {
        const x =
          data.length > 1 ? MARGIN.left + (i / (data.length - 1)) * innerW : MARGIN.left;
        const y = MARGIN.top + innerH - (d.monto_total / maxValue) * innerH;
        return { x, y, ...d };
      }),
    [data, innerH, innerW, maxValue],
  );

  if (data.length === 0) {
    return (
      <div
        className="flex h-[200px] items-center justify-center text-sm text-muted-foreground"
        data-testid="chart-line-empty"
      >
        Sin datos en el rango.
      </div>
    );
  }

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`)
    .join(' ');
  const areaD = `${pathD} L${points[points.length - 1]?.x.toFixed(2)},${MARGIN.top + innerH} L${points[0]?.x.toFixed(2)},${MARGIN.top + innerH} Z`;

  const hovered = hoverIndex !== null ? points[hoverIndex] : undefined;

  return (
    <figure data-testid="chart-line" className="relative">
      <figcaption className="mb-1 text-xs font-medium text-muted-foreground">{title}</figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="w-full"
        role="img"
        aria-label={title}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Recessive gridlines (3 horizontal bands). */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={MARGIN.left}
            x2={WIDTH - MARGIN.right}
            y1={MARGIN.top + innerH * (1 - f)}
            y2={MARGIN.top + innerH * (1 - f)}
            stroke="hsl(var(--border))"
            strokeWidth={1}
          />
        ))}
        <path d={areaD} fill={`url(#${gradientId})`} stroke="none" />
        <path d={pathD} fill="none" stroke="var(--chart-1)" strokeWidth={2} strokeLinecap="round" />
        {points.map((p, i) => (
          <circle
            key={p.fecha}
            cx={p.x}
            cy={p.y}
            r={i === hoverIndex ? 5 : 3}
            fill="var(--chart-1)"
            data-testid={`chart-line-point-${i}`}
          />
        ))}
        {/* Hover hit targets, one per point, bigger than the mark itself. */}
        {points.map((p, i) => (
          <rect
            key={`hit-${p.fecha}`}
            x={p.x - innerW / Math.max(points.length, 1) / 2}
            y={MARGIN.top}
            width={innerW / Math.max(points.length, 1)}
            height={innerH}
            fill="transparent"
            onMouseEnter={() => setHoverIndex(i)}
            data-testid={`chart-line-hit-${i}`}
          />
        ))}
        {hovered && (
          <line
            x1={hovered.x}
            x2={hovered.x}
            y1={MARGIN.top}
            y2={MARGIN.top + innerH}
            stroke="hsl(var(--muted-foreground))"
            strokeWidth={1}
            strokeDasharray="2,2"
          />
        )}
      </svg>
      {hovered && (
        <div
          role="tooltip"
          data-testid="chart-line-tooltip"
          className="pointer-events-none absolute rounded-md border bg-popover px-2 py-1 text-xs shadow-elevation-2"
          style={{
            left: `${(hovered.x / WIDTH) * 100}%`,
            top: `${(hovered.y / height) * 100}%`,
            transform: 'translate(-50%, -120%)',
          }}
        >
          <strong>{hovered.fecha}</strong>: ${hovered.monto_total.toLocaleString('es-CO')}
        </div>
      )}
    </figure>
  );
}
