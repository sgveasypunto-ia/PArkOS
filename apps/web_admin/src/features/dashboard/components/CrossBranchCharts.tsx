/**
 * `CrossBranchCharts.tsx` — the 3-chart block for the global HQ at
 * `/` (post-split). All 3 charts sit in a single row on desktop
 * (`lg:grid-cols-3`) so the row stays under 250px tall and the page
 * fits a 1080p viewport without scrolling. On mobile/tablet the
 * charts stack vertically.
 *
 * Sister file: `BranchCharts.tsx` carries the branch-scoped chart
 * consumed by `/dashboard`. Each side `lazy()`-imports only its
 * relevant file so the bundle of one does not drag the other.
 */
import { ChartBar } from '@/components/charts/ChartBar';
import { ChartPie } from '@/components/charts/ChartPie';
import { HeatmapOcupacion } from '@/components/charts/HeatmapOcupacion';
import type { DashboardResumen } from '../api/dashboardSchema';

export interface CrossBranchChartsProps {
  resumen: DashboardResumen | undefined;
}

export default function CrossBranchCharts({ resumen }: CrossBranchChartsProps): JSX.Element {
  const sucursalesPorUuid = new Map(
    (resumen?.top_sucursales ?? []).map((s) => [s.uuid_sucursal, s.nombre]),
  );
  const heatmapBranches = [
    ...new Set((resumen?.ocupacion_horaria ?? []).map((c) => c.uuid_sucursal)),
  ].map((uuid) => ({ uuid, nombre: sucursalesPorUuid.get(uuid) ?? null }));

  return (
    <section
      className="grid grid-cols-1 gap-4 lg:grid-cols-3"
      aria-label="Gráficas del resumen ejecutivo multi-sucursal"
      data-testid="cross-branch-charts-section"
    >
      <div className="rounded-lg border bg-card p-3">
        <ChartBar
          data={resumen?.top_sucursales ?? []}
          title="Top 5 sucursales por ingresos (30 días)"
        />
      </div>
      <div className="rounded-lg border bg-card p-3">
        <ChartPie data={resumen?.estado_envio_fe_24h ?? []} title="Estado de envío FE (24h)" />
      </div>
      <div className="rounded-lg border bg-card p-3">
        <HeatmapOcupacion
          data={resumen?.ocupacion_horaria ?? []}
          sucursales={heatmapBranches}
          title="Actividad por hora (24h)"
        />
      </div>
    </section>
  );
}
