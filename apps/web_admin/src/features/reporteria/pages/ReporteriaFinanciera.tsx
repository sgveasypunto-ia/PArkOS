/**
 * `<ReporteriaFinanciera />` — financial reports container (HU-F17.3,
 * web_admin).
 *
 * Three tabs, one per backend endpoint:
 *   - Facturas (`GET /admin/reporteria/facturas`) — branch-scoped, date
 *     range filter. Columns resolved against the REAL `facturas` schema
 *     (see `FacturasTable.tsx`): `numero_completo` (joined FE),
 *     `iva` (summed `factura_impuestos`), `estado` (derived
 *     vigente/anulada badge).
 *   - FE (`GET /admin/reporteria/fe`) — cross-branch (every branch the
 *     admin can see, same reasoning as the HU-F17.2 occupancy heatmap),
 *     optional `estado` (raw DIAN ack state) filter.
 *   - Pagos (`GET /admin/reporteria/pagos`) — branch-scoped, date range
 *     filter, netted (pago - reverso) and grouped by medio_pago/día (BR2).
 *
 * Reuses `<DateRangePicker />` from the operational reportería page for
 * Facturas/Pagos (both take `desde`/`hasta`, same field names the
 * backend query params use — no `fecha_desde`/`fecha_hasta` remap needed
 * here, unlike `/admin/reporteria/operacional`).
 *
 * Branch context comes from `useSucursal()`, same as `<Reporteria />`.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSucursal } from '@/lib/sucursal-context';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import {
  useReporteriaFacturas,
  useReporteriaFe,
  useReporteriaPagos,
} from '../hooks/useReporteria';
import { FacturasTable } from '../components/FacturasTable';
import { FeTable } from '../components/FeTable';
import { PagosTable } from '../components/PagosTable';
import { DateRangePicker, type DateRange } from '../components/DateRangePicker';
import { defaultRange } from '../components/dateRange';

const ESTADO_DIAN_OPTIONS = [
  'pendiente',
  'enviado',
  'ack',
  'error',
  'aceptado',
  'rechazado',
  'timeout',
  'en_proceso',
] as const;

export default function ReporteriaFinanciera() {
  const { t } = useTranslation();
  const { selected } = useSucursal();
  const [tab, setTab] = useState<'facturas' | 'fe' | 'pagos'>('facturas');
  const [range, setRange] = useState<DateRange>(() => defaultRange());
  const [estadoDian, setEstadoDian] = useState<string>('');

  const facturasQuery = useMemo(() => {
    if (!selected) return null;
    return {
      uuid_sucursal: selected,
      desde: range.fecha_desde,
      hasta: range.fecha_hasta,
      limit: 50,
    };
  }, [selected, range]);
  const facturas = useReporteriaFacturas(facturasQuery);

  const pagosQuery = useMemo(() => {
    if (!selected) return null;
    return { uuid_sucursal: selected, desde: range.fecha_desde, hasta: range.fecha_hasta };
  }, [selected, range]);
  const pagos = useReporteriaPagos(pagosQuery);

  // FE is cross-branch -- does not depend on `selected`.
  const feQuery = useMemo(
    () => ({ estado: estadoDian || undefined, limit: 50 }),
    [estadoDian],
  );
  const fe = useReporteriaFe(feQuery);

  const rangeInvalid =
    range.fecha_desde > range.fecha_hasta ||
    !/^\d{4}-\d{2}-\d{2}$/.test(range.fecha_desde) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(range.fecha_hasta);

  return (
    <main
      className="min-h-screen bg-background p-6"
      data-testid="page-reporteria-financiera"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="border-b pb-4">
          <h1 className="text-3xl font-bold tracking-tight">
            {t('reporteriaFinanciera.title', 'Reportería financiera')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t(
              'reporteriaFinanciera.subtitle',
              'Facturas, facturación electrónica (FE) y pagos.',
            )}
          </p>
        </header>

        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as 'facturas' | 'fe' | 'pagos')}
        >
          <TabsList aria-label={t('reporteriaFinanciera.tabsLabel', 'Sección de reporte')}>
            <TabsTrigger value="facturas" data-testid="reporteria-financiera-tab-facturas">
              {t('reporteriaFinanciera.tabs.facturas', 'Facturas')}
            </TabsTrigger>
            <TabsTrigger value="fe" data-testid="reporteria-financiera-tab-fe">
              {t('reporteriaFinanciera.tabs.fe', 'FE')}
            </TabsTrigger>
            <TabsTrigger value="pagos" data-testid="reporteria-financiera-tab-pagos">
              {t('reporteriaFinanciera.tabs.pagos', 'Pagos')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="facturas">
            {!selected ? (
              <p
                className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground"
                data-testid="reporteria-financiera-no-branch"
              >
                {t(
                  'reporteriaFinanciera.noBranch',
                  'Seleccioná una sucursal para ver las facturas.',
                )}
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                <DateRangePicker
                  value={range}
                  onChange={setRange}
                  disabled={facturas.isLoading && !facturas.data}
                />
                {!rangeInvalid ? (
                  <FacturasTable
                    items={facturas.data?.items ?? []}
                    isLoading={facturas.isLoading}
                    error={facturas.error}
                    caption={t('reporteriaFinanciera.facturas.caption', 'Facturas de la sucursal')}
                  />
                ) : null}
              </div>
            )}
          </TabsContent>

          <TabsContent value="fe">
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs">
                <span className="font-medium text-muted-foreground">
                  {t('reporteriaFinanciera.fe.estadoFilter', 'Filtrar por estado DIAN')}
                </span>
                <select
                  className="w-56 rounded-md border bg-background px-2 py-1 text-sm"
                  value={estadoDian}
                  onChange={(e) => setEstadoDian(e.target.value)}
                  data-testid="reporteria-financiera-fe-estado-filter"
                >
                  <option value="">
                    {t('reporteriaFinanciera.fe.estadoFilterAll', 'Todos')}
                  </option>
                  {ESTADO_DIAN_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <FeTable
                items={fe.data?.items ?? []}
                isLoading={fe.isLoading}
                error={fe.error}
                caption={t('reporteriaFinanciera.fe.caption', 'Facturación electrónica')}
              />
            </div>
          </TabsContent>

          <TabsContent value="pagos">
            {!selected ? (
              <p
                className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground"
                data-testid="reporteria-financiera-no-branch"
              >
                {t(
                  'reporteriaFinanciera.noBranch',
                  'Seleccioná una sucursal para ver los pagos.',
                )}
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                <DateRangePicker
                  value={range}
                  onChange={setRange}
                  disabled={pagos.isLoading && !pagos.data}
                />
                {!rangeInvalid ? (
                  <PagosTable
                    items={pagos.data?.items ?? []}
                    isLoading={pagos.isLoading}
                    error={pagos.error}
                    caption={t('reporteriaFinanciera.pagos.caption', 'Pagos de la sucursal')}
                  />
                ) : null}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}
