/**
 * ``ArqueosResumen`` -- container for the HU-F18.3 admin cross-branch
 * resumen por día tab.
 *
 * Includes:
 *   - Date input (defaults to today UTC).
 *   - One ``<ResumenSucursalCard />`` per branch.
 *   - Loading / error / empty-state banners.
 *
 * F18.3 wires this into ``<ArqueosPage />`` as a sibling tab to the
 * F18.2 listing tab (the page itself stays a single page; tabs separate
 * the "browse list" view from the "view summary" view).
 *
 * HU-F18.4 adds the "Exportar PDF firmado" action for the whole day's
 * cross-branch resumen (one row per sucursal, same fields
 * ``ResumenSucursalCard`` shows). BR2's logo header is scoped to the
 * GLOBALLY active sucursal (read via the non-React ``getSucursalHeader()``
 * -- the same ambient branch that scopes every other single-branch
 * concern in this app, e.g. ``documentosApi``'s ``X-Sucursal-Context``
 * header) -- this view is cross-branch by nature, so there's no single
 * "the" sucursal to brand the header with when no branch is globally
 * selected; in that case the PDF is generated without a logo header,
 * same as BR2's "no logo uploaded" case. Reading the ambient header
 * directly (instead of ``useSucursal()``) also means this component
 * doesn't require a ``<SucursalProvider>`` ancestor, matching its
 * existing tests, which render it standalone.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getSucursalHeader } from '@/lib/sucursal-context';
import { exportSignedPdf } from '@/lib/export/pdf';
import type { CsvColumn } from '@/lib/export/csv';

import { ResumenSucursalCard } from './ResumenSucursalCard';
import { useArqueosResumenAdmin } from '../hooks/useArqueosResumenAdmin';
import { fetchSucursalLogoDataUrl } from '../lib/sucursalLogo';
import type { ArqueoResumenAdminItem } from '../api/arqueosSchema';

function todayISO(): string {
  // Naive UTC date -- the BE's ``date_cls`` accepts YYYY-MM-DD, so we
  // don't need to time-zone adjust (the day boundary is at UTC midnight).
  return new Date().toISOString().slice(0, 10);
}

/** Mirrors `ResumenSucursalCard`'s `fmt` -- the exported table shows the
 * same values, formatted the same way, as what's on screen. */
function fmt(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

interface ResumenExportRow {
  sucursal: string;
  totalArqueos: number;
  esperadoEfectivo: string;
  reportadoEfectivo: string;
  diferenciaEfectivo: string;
  esperadoDatafono: string;
  reportadoDatafono: string;
  diferenciaDatafono: string;
}

const EXPORT_COLUMNS: CsvColumn<ResumenExportRow>[] = [
  { header: 'Sucursal', accessor: (r) => r.sucursal },
  { header: 'Total arqueos', accessor: (r) => r.totalArqueos },
  { header: 'Esperado efectivo', accessor: (r) => r.esperadoEfectivo },
  { header: 'Reportado efectivo', accessor: (r) => r.reportadoEfectivo },
  { header: 'Diferencia efectivo', accessor: (r) => r.diferenciaEfectivo },
  { header: 'Esperado datáfono', accessor: (r) => r.esperadoDatafono },
  { header: 'Reportado datáfono', accessor: (r) => r.reportadoDatafono },
  { header: 'Diferencia datáfono', accessor: (r) => r.diferenciaDatafono },
];

function buildExportRows(items: ArqueoResumenAdminItem[]): ResumenExportRow[] {
  return items.map((item) => ({
    sucursal: item.nombre ?? item.uuid_sucursal,
    totalArqueos: item.total_arqueos,
    esperadoEfectivo: fmt(item.esperado_efectivo),
    reportadoEfectivo: fmt(item.cierre_dia?.valor_efectivo_reportado),
    diferenciaEfectivo: fmt(item.cierre_dia?.diferencia_efectivo),
    esperadoDatafono: fmt(item.esperado_datafono),
    reportadoDatafono: fmt(item.cierre_dia?.valor_datafono_reportado),
    diferenciaDatafono: fmt(item.cierre_dia?.diferencia_datafono),
  }));
}

export interface ArqueosResumenProps {
  /**
   * Optional SWR cache-namespace suffix. Tests pass a unique value per
   * case to avoid SWR's global default provider handing a stale payload
   * from a previous case (the resumen endpoint's SWR key is the date,
   * which is the same across tests -- the salt breaks the cache slot).
   */
  swrSalt?: string;
}

export function ArqueosResumen({ swrSalt }: ArqueosResumenProps = {}): JSX.Element {
  const { t } = useTranslation();
  const [fecha, setFecha] = useState<string>(todayISO());
  const { resumen, isLoading, error } = useArqueosResumenAdmin(
    fecha,
    { swrSalt },
  );
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function handleExportPdf(): Promise<void> {
    if (!resumen || resumen.items.length === 0) return;
    setExportError(null);
    setIsExportingPdf(true);
    try {
      const sucursalActiva = getSucursalHeader()['X-Sucursal-Context'] ?? null;
      const logoDataUrl = await fetchSucursalLogoDataUrl(sucursalActiva);
      await exportSignedPdf(
        `arqueos-resumen-${fecha}.pdf`,
        EXPORT_COLUMNS,
        buildExportRows(resumen.items),
        {
          title: t('arqueos.resumen.title', 'Resumen admin por día'),
          subtitle: fecha,
          logoDataUrl,
        },
      );
    } catch (err) {
      setExportError(
        err instanceof Error
          ? err.message
          : t('arqueos.resumen.exportPdfError', 'No se pudo generar el PDF. Intenta de nuevo.'),
      );
    } finally {
      setIsExportingPdf(false);
    }
  }

  const totalCierreCount = useMemo(
    () =>
      resumen?.items.filter(
        (i) =>
          i.cierre_dia !== null &&
          (Number(i.cierre_dia.diferencia_efectivo) !== 0 ||
            Number(i.cierre_dia.diferencia_datafono) !== 0),
      ).length ?? 0,
    [resumen],
  );

  return (
    <section
      data-testid="arqueos-resumen"
      className="space-y-4"
      aria-label="Resumen admin cross-branch por día"
    >
      <header className="flex items-end gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('arqueos.resumen.dateLabel', 'Fecha')}
          </span>
          <Input
            data-testid="arqueos-resumen-date"
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
            className="w-fit"
          />
        </label>
        {resumen && (
          <span
            data-testid="arqueos-resumen-total-sucursales"
            className="ml-auto font-mono text-xs text-muted-foreground"
          >
            {t(
              'arqueos.resumen.totalSucursales',
              '{{ count }} sucursal(es)',
              { count: resumen.items.length },
            )}
          </span>
        )}
        {totalCierreCount > 0 && (
          <span
            data-testid="arqueos-resumen-total-descuadres"
            className="rounded-md bg-destructive/10 px-2 py-1 text-xs text-destructive"
          >
            {t(
              'arqueos.resumen.totalDescuadres',
              '{{ count }} descuadre(s)',
              { count: totalCierreCount },
            )}
          </span>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void handleExportPdf()}
          disabled={!resumen || resumen.items.length === 0 || isExportingPdf}
          data-testid="arqueos-resumen-export-pdf"
        >
          {isExportingPdf
            ? t('arqueos.resumen.exportingPdf', 'Generando…')
            : t('arqueos.resumen.exportPdf', 'Exportar PDF firmado')}
        </Button>
      </header>

      {exportError && (
        <p
          role="alert"
          data-testid="arqueos-resumen-export-pdf-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {exportError}
        </p>
      )}

      {isLoading && (
        <p
          role="status"
          data-testid="arqueos-resumen-loading"
          className="rounded-md border bg-muted/20 px-3 py-3 text-sm text-muted-foreground"
        >
          {t('common.loading', 'Cargando…')}
        </p>
      )}

      {error !== undefined && (
        <div
          role="alert"
          data-testid="arqueos-resumen-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-3 text-sm text-destructive"
        >
          {t('arqueos.errorLoading', 'No se pudo cargar el resumen.')}
        </div>
      )}

      {resumen && resumen.items.length === 0 && (
        <div
          role="status"
          data-testid="arqueos-resumen-empty"
          className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
        >
          {t(
            'arqueos.resumen.empty',
            'No hay sucursales con cierre del día registrado para esta fecha.',
          )}
        </div>
      )}

      {resumen && resumen.items.length > 0 && (
        <div
          data-testid="arqueos-resumen-list"
          className="grid grid-cols-1 gap-3 md:grid-cols-2"
        >
          {resumen.items.map((item) => (
            <ResumenSucursalCard key={item.uuid_sucursal} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}