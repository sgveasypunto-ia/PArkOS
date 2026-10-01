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
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Input } from '@/components/ui/input';

import { ResumenSucursalCard } from './ResumenSucursalCard';
import { useArqueosResumenAdmin } from '../hooks/useArqueosResumenAdmin';

function todayISO(): string {
  // Naive UTC date -- the BE's ``date_cls`` accepts YYYY-MM-DD, so we
  // don't need to time-zone adjust (the day boundary is at UTC midnight).
  return new Date().toISOString().slice(0, 10);
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
      </header>

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