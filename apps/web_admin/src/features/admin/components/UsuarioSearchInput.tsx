/**
 * `UsuarioSearchInput.tsx` — free-text search box for the user list
 * filter bar (HU-F9, web_admin).
 *
 * Filters on `email`, `nombre`, and `apellido` client-side via the
 * pure helper in `usuariosListFilters.ts` -- the backend list endpoint
 * is bounded to 100 rows and takes no query params (see
 * `AdminUsuarioTable.tsx`'s docblock for the rationale), so a
 * server-side round-trip would be wasted bandwidth. The search is
 * case-insensitive and matches by `includes` on each field; "admin"
 * matches `admin@parkos.local` and `Admin Dev` alike.
 *
 * Visual pattern mirrors `SucursalFilterCombobox.tsx`: a hand-rolled
 * `<Input type="search">` with a leading `Search` icon from `lucide`.
 * Native `<label htmlFor>`, `aria-label`, and `<input type="search">`
 * keep mouse + keyboard + screen-reader basics working. We do NOT
 * expose the WAI-ARIA combobox pattern here because the matching is
 * implicit (no popup, no `aria-activedescendant`); a future iteration
 * could add an autocomplete popup if the directory grows past a few
 * dozen users.
 *
 * Contract:
 *   - `value` is the current query (caller-owned state).
 *   - `onChange(next)` fires once per keystroke.
 *   - `data-testid` on the input is the integration point for tests
 *     (the parent passes its own through `testId`).
 */
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface UsuarioSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  /** Placeholder inside the input. Defaults to the i18n key. */
  placeholder?: string;
  /** Accessible label when no `<label>` is rendered above. */
  ariaLabel?: string;
  /**
   * Disables the whole control. Mirrors the `disabled` behaviour of
   * the native `<input>` next to it.
   */
  disabled?: boolean;
  /** `data-testid` placed on the input. */
  testId?: string;
  className?: string;
}

export function UsuarioSearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  disabled = false,
  testId,
  className,
}: UsuarioSearchInputProps): JSX.Element {
  const { t } = useTranslation();
  const inputId = useId();

  const resolvedPlaceholder =
    placeholder ??
    t('gestionUsuarios.search.placeholder', 'Buscar por correo o nombre…');
  const resolvedAriaLabel =
    ariaLabel ??
    t('gestionUsuarios.search.placeholder', 'Buscar por correo o nombre…');

  return (
    <div className={cn('relative flex flex-col gap-1', className)}>
      <label
        htmlFor={inputId}
        className="text-xs text-muted-foreground"
        data-testid="usuario-search-label"
      >
        {t('gestionUsuarios.search.label', 'Buscar')}
      </label>
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          id={inputId}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={resolvedPlaceholder}
          aria-label={resolvedAriaLabel}
          autoComplete="off"
          disabled={disabled}
          data-testid={testId}
          className="pl-8 pr-2"
        />
      </div>
    </div>
  );
}
