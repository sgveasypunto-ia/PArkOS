/**
 * `ChartsSection.tsx` — the 4-chart block of the executive dashboard
 * (HU-F17.1, T5): `ChartLine` (ingresos 30 días), `ChartBar` (top-5
 * sucursales), `ChartPie` (estado FE 24h), `HeatmapOcupacion` (24h x N
 * sucursales).
 *
 * This is the module `Dashboard.tsx` dynamic-imports via `React.lazy` --
 * one lazy boundary for all 4 charts rather than 4 separate ones. plan.md
 * ties "dynamic import" to the heaviest chart (the heatmap), but every
 * chart here is pure from-scratch SVG (no charting library exists in this
 * repo -- verified against package.json/pnpm-lock.yaml before writing
 * any of it), so all 4 add to the initial-bundle cost the HU is trying to
 * avoid. One `import()` boundary is also simpler to reason about than 4
 * independent `Suspense` fences for what is visually one section.
 */
import { ChartBar } from '@/components/charts/ChartBar';
import { ChartLine } from '@/components/charts/ChartLine';
import { ChartPie } from '@/components/charts/ChartPie';
import { HeatmapOcupacion } from '@/components/charts/HeatmapOcupacion';
import type { ReporteOperacionalResponse } from '@/features/reporteria/api/reporteriaSchema';

import type { DashboardResumen } from '../api/dashboardSchema';

export interface ChartsSectionProps {
  operacional: ReporteOperacionalResponse | undefined;
  resumen: DashboardResumen | undefined;
}

export default function ChartsSection({ operacional, resumen }: ChartsSectionProps): JSX.Element {
  const ingresosSerie = (operacional?.items ?? []).map((item) => ({
    fecha: item.fecha ?? '',
    monto_total: item.monto_facturado_total,
  }));

  const sucursalesPorUuid = new Map(
    (resumen?.top_sucursales ?? []).map((s) => [s.uuid_sucursal, s.nombre]),
  );
  const heatmapBranches = [...new Set((resumen?.ocupacion_horaria ?? []).map((c) => c.uuid_sucursal))].map(
    (uuid) => ({ uuid, nombre: sucursalesPorUuid.get(uuid) ?? null }),
  );

  return (
    <section
      className="grid grid-cols-1 gap-6 lg:grid-cols-2"
      aria-label="Gráficas del dashboard ejecutivo"
      data-testid="dashboard-charts-section"
    >
      <div className="rounded-lg border bg-card p-4">
        <ChartLine data={ingresosSerie} title="Ingresos facturados (30 días)" />
      </div>
      <div className="rounded-lg border bg-card p-4">
        <ChartBar data={resumen?.top_sucursales ?? []} title="Top 5 sucursales por ingresos (30 días)" />
      </div>
      <div className="rounded-lg border bg-card p-4">
        <ChartPie data={resumen?.estado_envio_fe_24h ?? []} title="Estado de envío FE (24h)" />
      </div>
      <div className="rounded-lg border bg-card p-4">
        <HeatmapOcupacion
          data={resumen?.ocupacion_horaria ?? []}
          sucursales={heatmapBranches}
          title="Actividad por hora (24h)"
        />
      </div>
    </section>
  );
}
