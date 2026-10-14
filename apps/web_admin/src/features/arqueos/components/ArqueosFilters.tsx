/**
 * ``ArqueosFilters`` -- presentational filter bar for the admin
 * arqueo listing (HU-F18.2, T1).
 *
 * Four controlled filters match the BE ``ArqueoListQueryParams``:
 *
 *   - ``uuid_sucursal`` -- branch combobox (searchable single-select,
 *     `SucursalFilterCombobox`). Empty = all branches (admin sees
 *     cross-branch by default).
 *   - ``fecha_desde`` / ``fecha_hasta`` -- inclusive date range.
 *     Either alone is a one-sided range; both empty = unbounded.
 *   - ``uuid_tipo_arqueo`` -- dropdown of the two seed codes
 *     (``auditoria`` and ``cierre_turno``) loaded from the
 *     ``tipo_arqueo`` catalog endpoint. Empty = both.
 *
 * The component is fully controlled -- the container owns the
 * ``ArqueosListQuery`` state and re-fetches via SWR whenever any field
 * changes.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SucursalFilterCombobox } from '@/features/admin/components/SucursalFilterCombobox';

export interface ArqueosFiltersValue {
  uuid_sucursal: string;
  fecha_desde: string;
  fecha_hasta: string;
  uuid_tipo_arqueo: string;
}

export interface ArqueosFiltersOptions {
  sucursalOptions: ReadonlyArray<{
    uuid: string;
    nombre: string | null;
    prefijo_nombre?: string | null;
  }>;
  tipoOptions: ReadonlyArray<{ uuid: string; codigo: string | null }>;
}

export interface ArqueosFiltersProps {
  value: ArqueosFiltersValue;
  onChange: (next: ArqueosFiltersValue) => void;
  onReset: () => void;
  options: ArqueosFiltersOptions;
}

export function ArqueosFilters({
  value,
  onChange,
  onReset,
  options,
}: ArqueosFiltersProps): JSX.Element {
  const { t } = useTranslation();
  const update = (patch: Partial<ArqueosFiltersValue>): void => {
    onChange({ ...value, ...patch });
  };

  return (
    <div
      data-testid="arqueos-filters"
      className="grid grid-cols-1 gap-3 rounded-md border bg-muted/20 sm:grid-cols-2 md:grid-cols-5"
    >
      <SucursalFilterCombobox
        options={options.sucursalOptions.map((s) => ({
          uuid: s.uuid,
          nombre: s.nombre,
          prefijo_nombre: s.prefijo_nombre ?? null,
        }))}
        value={value.uuid_sucursal}
        onChange={(v) => update({ uuid_sucursal: v })}
        label={t('arqueos.filters.branch')}
        placeholder={t(
          'arqueos.filters.search',
          'Buscar por nombre, prefijo o UUID…',
        )}
        allLabel={t('arqueos.filters.allBranches')}
        testId="arqueos-filters-sucursal"
      />

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('arqueos.filters.dateFrom')}
        </span>
        <Input
          data-testid="arqueos-filters-date-desde"
          type="date"
          value={value.fecha_desde}
          onChange={(e) => update({ fecha_desde: e.target.value })}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('arqueos.filters.dateTo')}
        </span>
        <Input
          data-testid="arqueos-filters-date-hasta"
          type="date"
          value={value.fecha_hasta}
          onChange={(e) => update({ fecha_hasta: e.target.value })}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('arqueos.filters.type')}
        </span>
        <select
          data-testid="arqueos-filters-tipo"
          value={value.uuid_tipo_arqueo}
          onChange={(e) => update({ uuid_tipo_arqueo: e.target.value })}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">
            {t('arqueos.filters.allTypes')}
          </option>
          {options.tipoOptions.map((t_) => (
            <option key={t_.uuid} value={t_.uuid}>
              {t_.codigo ?? t_.uuid}
            </option>
          ))}
        </select>
      </label>

      <div className="flex items-end">
        <Button
          data-testid="arqueos-filters-reset"
          type="button"
          variant="ghost"
          size="sm"
          onClick={onReset}
          className="w-full"
        >
          {t('arqueos.filters.reset')}
        </Button>
      </div>
    </div>
  );
}