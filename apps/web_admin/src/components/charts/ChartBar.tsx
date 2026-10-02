/**
 * `ChartBar.tsx` — "top-5 sucursales" horizontal bar chart (HU-F17.1, T5).
 *
 * Color follows the entity (one categorical slot per branch, in the
 * validated 5-slot order from `index.css --chart-1..5` -- see the
 * `dataviz` skill invocation in the apply report). The validator flagged
 * 3 of the 5 slots below 3:1 contrast on the surface (WARN), so the
 * "relief" rule applies here: every bar carries a direct value label,
 * never color alone. The branch-name axis labels double as the
 * identity legend (no separate legend box for a category axis).
 */
import { useState } from 'react';

import type { DashboardTopSucursalItem } from '@/features/dashboard/api/dashboardSchema';

export interface ChartBarProps {
  data: DashboardTopSucursalItem[];
  title: string;
}

const SLOT_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];

const WIDTH = 480;
const ROW_HEIGHT = 32;
const LABEL_WIDTH = 140;

export function ChartBar({ data, title }: ChartBarProps): JSX.Element {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (data.length === 0) {
    return (
      <div
        className="flex h-[160px] items-center justify-center text-sm text-muted-foreground"
        data-testid="chart-bar-empty"
      >
        Sin facturación en el rango.
      </div>
    );
  }

  const maxValue = Math.max(1, ...data.map((d) => d.monto_total));
  const plotWidth = WIDTH - LABEL_WIDTH - 72;
  const height = data.length * ROW_HEIGHT + 8;

  return (
    <figure data-testid="chart-bar">
      <figcaption className="mb-1 text-xs font-medium text-muted-foreground">{title}</figcaption>
      <svg viewBox={`0 0 ${WIDTH} ${height}`} className="w-full" role="img" aria-label={title}>
        {data.map((item, i) => {
          const barWidth = (item.monto_total / maxValue) * plotWidth;
          const y = i * ROW_HEIGHT + 4;
          const color = SLOT_COLORS[i % SLOT_COLORS.length] ?? SLOT_COLORS[0];
          return (
            <g
              key={item.uuid_sucursal}
              onMouseEnter={() => setHoverIndex(i)}
              onMouseLeave={() => setHoverIndex((cur) => (cur === i ? null : cur))}
              data-testid={`chart-bar-row-${i}`}
            >
              <text
                x={LABEL_WIDTH - 8}
                y={y + ROW_HEIGHT / 2 + 4}
                textAnchor="end"
                className="fill-foreground text-[11px]"
              >
                {item.nombre ?? item.uuid_sucursal.slice(0, 8)}
              </text>
              <rect
                x={LABEL_WIDTH}
                y={y}
                width={Math.max(barWidth, 2)}
                height={ROW_HEIGHT - 10}
                rx={4}
                fill={color}
                opacity={hoverIndex === null || hoverIndex === i ? 1 : 0.55}
              />
              <text
                x={LABEL_WIDTH + Math.max(barWidth, 2) + 6}
                y={y + (ROW_HEIGHT - 10) / 2 + 4}
                className="fill-muted-foreground text-[11px] tabular-nums"
              >
                ${item.monto_total.toLocaleString('es-CO')}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
