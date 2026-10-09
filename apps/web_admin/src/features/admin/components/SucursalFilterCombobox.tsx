/**
 * `SucursalFilterCombobox.tsx` — searchable single-select for the
 * branch (`sucursal`) picker. Replaces the native `<select>` in the
 * `/usuarios` filter bar and in the "Agregar sucursal" row of
 * `AdminUsuarioSucursalesManager` so the admin can find a branch by
 * `nombre`, `prefijo_nombre`, or `uuid` once the directory grows past
 * a handful of rows.
 *
 * Visual only: a hand-rolled `<Input type="search">` + filterable list
 * of `<button>` options, mirroring the layout of
 * `components/branch-selector/SucursalPicker.tsx` (which the operator
 * already knows from the branch-selection gate). The component does
 * NOT expose the WAI-ARIA "combobox with listbox autocomplete" pattern
 * (no `role="combobox"`, no `aria-activedescendant`, no active-descendant
 * keyboard cycle) — that is the next iteration if accessibility review
 * asks for it. Native `<label htmlFor>`, `aria-label` on the input, and
 * `<button>` options (so Enter/Space/click activate without JS wiring)
 * still keep mouse + keyboard + screen-reader basics working.
 *
 * Contract preserved from the replaced `<select>`:
 *   - `value` is the branch `uuid` or `""` ("Todas"/"Sin selección").
 *   - `onChange(uuid)` fires once per selection.
 *   - The `data-testid` on the input is the integration point for tests
 *     (kept on the `testId` prop so each call site can pass its own).
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Search } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface SucursalFilterComboboxOption {
  uuid: string;
  nombre: string | null;
  prefijo_nombre?: string | null;
}

export interface SucursalFilterComboboxProps {
  options: SucursalFilterComboboxOption[];
  value: string;
  onChange: (uuid: string) => void;
  /**
   * If `true`, the popup is permanently open (no click-to-toggle). Used
   * by the `/usuarios` filter bar so the popup is always visible next
   * to the search input — the same shape `<SucursalPicker />` renders.
   */
  alwaysOpen?: boolean;
  /** Label rendered above the input. Also drives the `<label htmlFor>`. */
  label: string;
  /** Placeholder inside the search input. */
  placeholder?: string;
  /** Label for the "Todas / no selection" pseudo-option (`value=""`). */
  allLabel?: string;
  /**
   * Disables the whole control (input + buttons). Mirrors the
   * `disabled` behaviour of the replaced native `<select>`.
   */
  disabled?: boolean;
  /**
   * `data-testid` placed on the search input — keeps the existing
   * `admin-filter-sucursal` / `admin-sucursales-add-select` ids so the
   * smoke tests and `getByTestId` lookups keep working.
   */
  testId?: string;
  className?: string;
}

export function SucursalFilterCombobox({
  options,
  value,
  onChange,
  alwaysOpen = false,
  label,
  placeholder,
  allLabel,
  disabled = false,
  testId,
  className,
}: SucursalFilterComboboxProps): JSX.Element {
  const { t } = useTranslation();
  const inputId = useId();
  const listId = `${inputId}-list`;

  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  /**
   * `inputRef.current.focus()` fires the `focus` event SYNCHRONOUSLY,
   * which would re-trigger our `onFocus` -> `setOpen(true)` in the same
   * tick as the `setOpen(false)` we just queued from a selection,
   * letting the popup reopen right after a click. This ref is set right
   * before the programmatic refocus and consumed by `onFocus` to swallow
   * that one event.
   */
  const suppressNextFocusRef = useRef<boolean>(false);

  const selected = useMemo(
    () => options.find((o) => o.uuid === value) ?? null,
    [options, value],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q === '') return options;
    return options.filter((o) => {
      const name = (o.nombre ?? '').toLowerCase();
      const prefix = (o.prefijo_nombre ?? '').toLowerCase();
      return name.includes(q) || prefix.includes(q) || o.uuid.includes(q);
    });
  }, [options, query]);

  useEffect(() => {
    if (alwaysOpen) return;
    if (!open) return;
    function onMouseDown(event: MouseEvent): void {
      const target = event.target as Node | null;
      if (!target) return;
      if (containerRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setOpen(false);
        inputRef.current?.focus();
      }
    }
    document.addEventListener('mousedown', onMouseDown, true);
    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('mousedown', onMouseDown, true);
      document.removeEventListener('keydown', onKeyDown, true);
    };
  }, [alwaysOpen, open]);

  const showPopup = alwaysOpen || open;
  const noResults = filtered.length === 0;

  function handleSelect(uuid: string): void {
    onChange(uuid);
    if (!alwaysOpen) {
      suppressNextFocusRef.current = true;
      setOpen(false);
      inputRef.current?.focus();
    }
    const opt = options.find((o) => o.uuid === uuid);
    setQuery(opt?.nombre ?? '');
  }

  return (
    <div ref={containerRef} className={cn('relative flex flex-col gap-1', className)}>
      <label
        htmlFor={inputId}
        className="text-xs text-muted-foreground"
      >
        {label}
      </label>

      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          ref={inputRef}
          id={inputId}
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!alwaysOpen) setOpen(true);
          }}
          onFocus={() => {
            if (suppressNextFocusRef.current) {
              suppressNextFocusRef.current = false;
              return;
            }
            if (!alwaysOpen) setOpen(true);
          }}
          placeholder={
            placeholder ??
            t(
              'gestionUsuarios.filtros.sucursalCombobox.search',
              'Buscar por nombre, prefijo o UUID…',
            )
          }
          aria-label={
            placeholder ??
            t(
              'gestionUsuarios.filtros.sucursalCombobox.search',
              'Buscar por nombre, prefijo o UUID…',
            )
          }
          aria-controls={showPopup ? listId : undefined}
          autoComplete="off"
          disabled={disabled}
          data-testid={testId}
          className="pl-8 pr-2"
        />
      </div>

      {selected !== null && !alwaysOpen && query === '' && (
        <p
          className="text-muted-foreground text-xs"
          data-testid={`${testId ?? 'sucursal-combobox'}-selected`}
        >
          {t('gestionUsuarios.filtros.sucursalCombobox.currentPrefix', 'Actual:')}{' '}
          <span className="font-medium text-foreground">
            {selected.nombre ?? selected.uuid}
          </span>
        </p>
      )}

      {showPopup && (
        <ul
          id={listId}
          data-testid={testId ? `${testId}-list` : 'sucursal-combobox-list'}
          className={cn(
            'z-50 max-h-64 overflow-y-auto rounded-md border border-input bg-popover p-1 text-popover-foreground shadow-elevation-2',
            alwaysOpen ? 'mt-1' : 'absolute top-full mt-1 w-full',
          )}
        >
          {options.length === 0 ? (
            <li
              className="text-muted-foreground px-2 py-2 text-sm"
              data-testid="sucursal-combobox-none"
            >
              {t(
                'gestionUsuarios.filtros.sucursalCombobox.none',
                'No hay sucursales disponibles.',
              )}
            </li>
          ) : noResults ? (
            <li
              className="text-muted-foreground px-2 py-2 text-sm"
              data-testid="sucursal-combobox-empty-filter"
            >
              {t(
                'gestionUsuarios.filtros.sucursalCombobox.empty',
                'Sin resultados para la búsqueda.',
              )}
            </li>
          ) : (
            <>
              {allLabel !== undefined && (
                <li>
                  <button
                    type="button"
                    onClick={() => handleSelect('')}
                    data-testid={
                      testId
                        ? `${testId}-option-all`
                        : 'sucursal-combobox-option-all'
                    }
                    className={cn(
                      'flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-sm',
                      'hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none',
                      value === '' && 'bg-accent/40',
                    )}
                  >
                    <span className="truncate">{allLabel}</span>
                    {value === '' && (
                      <Check
                        className="size-4 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                </li>
              )}
              {filtered.map((opt) => {
                const isSelected = opt.uuid === value;
                const label = opt.nombre ?? opt.uuid;
                return (
                  <li key={opt.uuid}>
                    <button
                      type="button"
                      onClick={() => handleSelect(opt.uuid)}
                      data-testid={
                        testId
                          ? `${testId}-option-${opt.uuid}`
                          : `sucursal-combobox-option-${opt.uuid}`
                      }
                      className={cn(
                        'flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-sm',
                        'hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none',
                        isSelected && 'bg-accent/40',
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        <span className="block truncate">{label}</span>
                        {opt.prefijo_nombre && (
                          <span className="text-muted-foreground block font-mono text-[11px] uppercase">
                            {opt.prefijo_nombre}
                          </span>
                        )}
                      </span>
                      {isSelected && (
                        <Check
                          className="text-primary size-4 shrink-0"
                          aria-hidden="true"
                        />
                      )}
                    </button>
                  </li>
                );
              })}
            </>
          )}
        </ul>
      )}
    </div>
  );
}
