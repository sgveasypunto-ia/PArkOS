/**
 * SucursalPicker — full-page grid of cards for the initial branch
 * selection (gate after login, replacement when the operator clicks the
 * chrome badge to switch).
 *
 * Renders one accessible card per permitted branch. Each card is a real
 * `<button type="button">` so the entire tile is the activation target
 * (no nested click targets, no `<div role="button">`); WCAG 2.1 AA
 * `aria-label` describes the branch by `nombre` and `uuid`.
 *
 * Search filters in-memory by `nombre` or `prefijo_nombre` (case
 * insensitive). When the list is empty AFTER filtering, a polite empty
 * state appears (no false "no branches" message that confuses the
 * operator about whether the system actually has branches).
 *
 * The picker never fetches: the parent (`SeleccionarSucursal`) loads the
 * list and passes it as a prop. This keeps the picker pure and unit
 * testable without SWR or fetch mocks.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Building2, Search } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface SucursalPickerOption {
  uuid: string;
  nombre: string | null;
  prefijo_nombre?: string | null;
}

interface SucursalPickerProps {
  options: SucursalPickerOption[];
  isLoading: boolean;
  onSelect: (uuid: string) => void;
}

export function SucursalPicker({
  options,
  isLoading,
  onSelect,
}: SucursalPickerProps): JSX.Element {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => {
      const name = (o.nombre ?? '').toLowerCase();
      const prefix = (o.prefijo_nombre ?? '').toLowerCase();
      return name.includes(q) || prefix.includes(q) || o.uuid.includes(q);
    });
  }, [options, query]);

  return (
    <section
      aria-labelledby="sucursal-picker-title"
      className="mx-auto w-full max-w-4xl px-4 py-10"
      data-testid="sucursal-picker"
    >
      <header className="mb-6 flex flex-col gap-1">
        <h1
          id="sucursal-picker-title"
          className="text-2xl font-semibold tracking-tight"
        >
          {t('sucursalPicker.title', 'Elegí una sucursal para empezar')}
        </h1>
        <p className="text-muted-foreground text-sm">
          {t(
            'sucursalPicker.subtitle',
            'Todas las métricas y configuraciones se filtran por la sucursal que elijas acá.',
          )}
        </p>
      </header>

      <div className="relative mb-4">
        <Search
          className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('sucursalPicker.search', 'Buscar por nombre o prefijo…')}
          aria-label={t('sucursalPicker.search', 'Buscar por nombre o prefijo…')}
          data-testid="sucursal-picker-search"
          className="pl-9"
          autoComplete="off"
        />
      </div>

      {isLoading ? (
        <p
          role="status"
          aria-live="polite"
          className="text-muted-foreground text-sm"
          data-testid="sucursal-picker-loading"
        >
          {t('sucursalPicker.loading', 'Cargando sucursales…')}
        </p>
      ) : options.length === 0 ? (
        <p
          role="status"
          className="text-muted-foreground text-sm"
          data-testid="sucursal-picker-empty-system"
        >
          {t(
            'sucursalPicker.emptySystem',
            'No tenés sucursales autorizadas. Contactá al administrador.',
          )}
        </p>
      ) : filtered.length === 0 ? (
        <p
          role="status"
          className="text-muted-foreground text-sm"
          data-testid="sucursal-picker-empty-filter"
        >
          {t('sucursalPicker.emptyFilter', 'Ningún resultado para esa búsqueda.')}
        </p>
      ) : (
        <ul
          className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          data-testid="sucursal-picker-grid"
        >
          {filtered.map((opt) => {
            const label = opt.nombre ?? opt.uuid;
            return (
              <li key={opt.uuid}>
                <button
                  type="button"
                  onClick={() => onSelect(opt.uuid)}
                  aria-label={`${label} (${opt.prefijo_nombre ?? opt.uuid})`}
                  data-testid={`sucursal-picker-option-${opt.uuid}`}
                  className={cn(
                    'focus-ring group flex w-full items-start gap-3 rounded-xl border border-input bg-background p-4 text-left shadow-sm transition-shadow duration-base ease-macos',
                    'hover:shadow-elevation-2 hover:border-accent',
                  )}
                >
                  <span
                    aria-hidden="true"
                    className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-lg"
                  >
                    <Building2 className="size-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-base font-medium tracking-tight">
                      {label}
                    </span>
                    {opt.prefijo_nombre && (
                      <span className="text-muted-foreground mt-0.5 block font-mono text-xs uppercase">
                        {opt.prefijo_nombre}
                      </span>
                    )}
                    <span className="text-muted-foreground mt-1 block font-mono text-[11px]">
                      {opt.uuid}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
