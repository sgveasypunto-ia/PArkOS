/**
 * `LogTransaccionalFilters` -- presentational filter bar for the
 * HU-F20.4 bitácora listing. Mirrors
 * `alertas/components/AlertasFilters.tsx` / `arqueos/components/ArqueosFilters.tsx`
 * (fully controlled, the container owns state + re-fetches via SWR).
 *
 * Six controlled filters match the BE `LogTransaccionalListQueryParams`:
 *
 *   - `tabla` -- free-text. The bitácora spans every `[A]` catalog table
 *     (`ingreso`, `salida`, `arqueo`, `alerta`, ...), unlike `/verify-chain`'s
 *     `tabla` (closed to the two hash-chain-verifiable tables) -- no
 *     catalog endpoint exists to constrain this one to a dropdown.
 *   - `uuid_registro` / `uuid_usuario` -- free-text UUID filters (pasted
 *     by the admin, e.g. from a support ticket or `BuscarGlobal`).
 *   - `uuid_sucursal` -- branch dropdown, full directory (cross-branch
 *     admin surface, same as `SyncLog.tsx` / `ArqueosFilters.tsx` -- the
 *     BE already enforces 403/400 server-side, so the FE doesn't need its
 *     own client-side branch restriction here like `AlertasFilters.tsx`
 *     does).
 *   - `desde` / `hasta` -- inclusive date range.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export interface LogTransaccionalFiltersValue {
  tabla: string;
  uuid_registro: string;
  uuid_sucursal: string;
  uuid_usuario: string;
  desde: string;
  hasta: string;
}

export interface LogTransaccionalFiltersOptions {
  sucursalOptions: ReadonlyArray<{ uuid: string; nombre: string | null }>;
}

export interface LogTransaccionalFiltersProps {
  value: LogTransaccionalFiltersValue;
  onChange: (next: LogTransaccionalFiltersValue) => void;
  onReset: () => void;
  options: LogTransaccionalFiltersOptions;
}

export function LogTransaccionalFilters({
  value,
  onChange,
  onReset,
  options,
}: LogTransaccionalFiltersProps): JSX.Element {
  const { t } = useTranslation();
  const update = (patch: Partial<LogTransaccionalFiltersValue>): void => {
    onChange({ ...value, ...patch });
  };

  return (
    <div
      data-testid="log-transaccional-filters"
      className="grid grid-cols-1 gap-3 rounded-md border bg-muted/20 sm:grid-cols-2 md:grid-cols-6"
    >
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('auditoria.filters.tabla', 'Tabla')}
        </span>
        <Input
          data-testid="log-transaccional-filters-tabla"
          value={value.tabla}
          onChange={(e) => update({ tabla: e.target.value })}
          placeholder={t('auditoria.filters.tablaPlaceholder', 'ingreso')}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('auditoria.filters.uuidRegistro', 'UUID de registro')}
        </span>
        <Input
          data-testid="log-transaccional-filters-uuid-registro"
          value={value.uuid_registro}
          onChange={(e) => update({ uuid_registro: e.target.value })}
          placeholder="00000000-0000-0000-0000-000000000000"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('auditoria.filters.branch', 'Sucursal')}
        </span>
        <select
          data-testid="log-transaccional-filters-sucursal"
          value={value.uuid_sucursal}
          onChange={(e) => update({ uuid_sucursal: e.target.value })}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">{t('auditoria.filters.allBranches', 'Todas')}</option>
          {options.sucursalOptions.map((s) => (
            <option key={s.uuid} value={s.uuid}>
              {s.nombre ?? s.uuid}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('auditoria.filters.uuidUsuario', 'UUID de usuario')}
        </span>
        <Input
          data-testid="log-transaccional-filters-uuid-usuario"
          value={value.uuid_usuario}
          onChange={(e) => update({ uuid_usuario: e.target.value })}
          placeholder="00000000-0000-0000-0000-000000000000"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('auditoria.filters.dateFrom', 'Desde')}
        </span>
        <Input
          data-testid="log-transaccional-filters-date-desde"
          type="date"
          value={value.desde}
          onChange={(e) => update({ desde: e.target.value })}
        />
      </label>

      <div className="flex items-end gap-2">
        <label className="flex flex-1 flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('auditoria.filters.dateTo', 'Hasta')}
          </span>
          <Input
            data-testid="log-transaccional-filters-date-hasta"
            type="date"
            value={value.hasta}
            onChange={(e) => update({ hasta: e.target.value })}
          />
        </label>
        <Button
          data-testid="log-transaccional-filters-reset"
          type="button"
          variant="ghost"
          onClick={onReset}
        >
          {t('auditoria.filters.reset', 'Limpiar')}
        </Button>
      </div>
    </div>
  );
}
