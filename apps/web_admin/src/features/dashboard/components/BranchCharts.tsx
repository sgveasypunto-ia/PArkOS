/**
 * `BranchCharts.tsx` — the 1-chart block for the branch-scoped
 * `/dashboard` (post-split). Today: a single `ChartLine` driven by the
 * selected branch's reporteria operacional (ingresos 30 días). Lives
 * in its own file so `Dashboard.tsx` can `lazy()` it without dragging
 * the cross-branch heatmap/ChartBar/ChartPie into the branch bundle.
 *
 * Sister file: `CrossBranchCharts.tsx` is the complementary
 * `lazy()`-loaded chart set consumed by the global HQ at `/`.
 */
import { ChartLine } from '@/components/charts/ChartLine';
import type { ReporteOperacionalResponse } from '@/features/reporteria/api/reporteriaSchema';

export interface BranchChartsProps {
  operacional: ReporteOperacionalResponse | undefined;
}

export default function BranchCharts({ operacional }: BranchChartsProps): JSX.Element {
  const ingresosSerie = (operacional?.items ?? []).map((item) => ({
    fecha: item.fecha ?? '',
    monto_total: item.monto_facturado_total,
  }));

  return (
    <section
      className="grid grid-cols-1 gap-6"
      aria-label="Gráficas de la sucursal seleccionada"
      data-testid="branch-charts-section"
    >
      <div className="rounded-lg border bg-card p-4">
        <ChartLine data={ingresosSerie} title="Ingresos facturados (30 días)" />
      </div>
    </section>
  );
}
