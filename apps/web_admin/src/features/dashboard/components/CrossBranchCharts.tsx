/**
 * `CrossBranchCharts.tsx` — the 3-chart block for the global HQ at
 * `/` (post-split): `ChartBar` (top-5 sucursales), `ChartPie` (estado
 * FE 24h), `HeatmapOcupacion` (24h x N sucursales). Driven entirely by
 * the cross-branch resumen payload.
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
      className="grid grid-cols-1 gap-6 lg:grid-cols-2"
      aria-label="Gráficas del resumen ejecutivo multi-sucursal"
      data-testid="cross-branch-charts-section"
    >
      <div className="rounded-lg border bg-card p-4">
        <ChartBar
          data={resumen?.top_sucursales ?? []}
          title="Top 5 sucursales por ingresos (30 días)"
        />
      </div>
      <div className="rounded-lg border bg-card p-4">
        <ChartPie data={resumen?.estado_envio_fe_24h ?? []} title="Estado de envío FE (24h)" />
      </div>
      <div className="rounded-lg border bg-card p-4 lg:col-span-2">
        <HeatmapOcupacion
          data={resumen?.ocupacion_horaria ?? []}
          sucursales={heatmapBranches}
          title="Actividad por hora (24h)"
        />
      </div>
    </section>
  );
}
