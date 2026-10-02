/**
 * `AlertasFilters` -- presentational filter bar for the HU-F19.5 alertas
 * inbox. Mirrors `arqueos/components/ArqueosFilters.tsx` (fully
 * controlled, the container owns state + re-fetches via SWR).
 *
 *   - `uuid_sucursal` -- restricted to the actor's `sucursales
 *     permitidas` (`useAdminAuth().sucursalUuids`); the container passes
 *     only those as `options.sucursalOptions`. Empty = all permitted
 *     branches.
 *   - `tipo_alerta` -- free-text filter. No `GET /workflows/alert-types`
 *     catalog dropdown here on purpose: that endpoint's own schema
 *     docblock (`schemas/workflows.py::AlertTypeRead`) says it "was
 *     never mounted on the backend (404 in production)" as of this
 *     writing -- wiring a dropdown to a 404 would be worse than a text
 *     filter.
 *   - `estado` / `severidad` -- closed-enum dropdowns (FE-known
 *     vocabularies, `ALERTA_ESTADOS` / `ALERTA_SEVERITIES`).
 *   - `desde` / `hasta` -- inclusive date range.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { ALERTA_ESTADOS, ALERTA_SEVERITIES } from '../api/alertasSchema';
import type { AlertaEstado, AlertaSeverity } from '../api/alertasSchema';

export interface AlertasFiltersValue {
  uuid_sucursal: string;
  tipo_alerta: string;
  estado: AlertaEstado | '';
  severidad: AlertaSeverity | '';
  desde: string;
  hasta: string;
}

export interface AlertasFiltersOptions {
  sucursalOptions: ReadonlyArray<{ uuid: string; nombre: string | null }>;
}

export interface AlertasFiltersProps {
  value: AlertasFiltersValue;
  onChange: (next: AlertasFiltersValue) => void;
  onReset: () => void;
  options: AlertasFiltersOptions;
}

export function AlertasFilters({
  value,
  onChange,
  onReset,
  options,
}: AlertasFiltersProps): JSX.Element {
  const { t } = useTranslation();
  const update = (patch: Partial<AlertasFiltersValue>): void => {
    onChange({ ...value, ...patch });
  };

  return (
    <div
      data-testid="alertas-filters"
      className="grid grid-cols-1 gap-3 rounded-md border bg-muted/20 sm:grid-cols-2 md:grid-cols-6"
    >
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('alertas.filters.branch', 'Sucursal')}
        </span>
        <select
          data-testid="alertas-filters-sucursal"
          value={value.uuid_sucursal}
          onChange={(e) => update({ uuid_sucursal: e.target.value })}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">{t('alertas.filters.allBranches', 'Todas mis sucursales')}</option>
          {options.sucursalOptions.map((s) => (
            <option key={s.uuid} value={s.uuid}>
              {s.nombre ?? s.uuid}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('alertas.filters.tipo', 'Tipo de alerta')}
        </span>
        <Input
          data-testid="alertas-filters-tipo"
          value={value.tipo_alerta}
          onChange={(e) => update({ tipo_alerta: e.target.value })}
          placeholder={t('alertas.filters.tipoPlaceholder', 'descuadre_critico')}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('alertas.filters.estado', 'Estado')}
        </span>
        <select
          data-testid="alertas-filters-estado"
          value={value.estado}
          onChange={(e) => update({ estado: e.target.value as AlertaEstado | '' })}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">{t('alertas.filters.allEstados', 'Todos')}</option>
          {ALERTA_ESTADOS.map((estado) => (
            <option key={estado} value={estado}>
              {t(`alertas.estado.${estado === 'en_revision' ? 'enRevision' : estado}`, estado)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('alertas.filters.severidad', 'Severidad')}
        </span>
        <select
          data-testid="alertas-filters-severidad"
          value={value.severidad}
          onChange={(e) => update({ severidad: e.target.value as AlertaSeverity | '' })}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">{t('alertas.filters.allSeveridades', 'Todas')}</option>
          {ALERTA_SEVERITIES.map((sev) => (
            <option key={sev} value={sev}>
              {t(`alertas.severity.${sev}`, sev)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('alertas.filters.dateFrom', 'Desde')}
        </span>
        <Input
          data-testid="alertas-filters-date-desde"
          type="date"
          value={value.desde}
          onChange={(e) => update({ desde: e.target.value })}
        />
      </label>

      <div className="flex items-end gap-2">
        <label className="flex flex-1 flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('alertas.filters.dateTo', 'Hasta')}
          </span>
          <Input
            data-testid="alertas-filters-date-hasta"
            type="date"
            value={value.hasta}
            onChange={(e) => update({ hasta: e.target.value })}
          />
        </label>
        <Button
          data-testid="alertas-filters-reset"
          type="button"
          variant="ghost"
          onClick={onReset}
        >
          {t('alertas.filters.reset', 'Limpiar')}
        </Button>
      </div>
    </div>
  );
}
