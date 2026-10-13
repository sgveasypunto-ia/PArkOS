/**
 * `BranchPickerInline.tsx` — inline branch selector for the
 * branch-scoped reporteria pages (HU-X.8).
 *
 * Visual pattern: a Button trigger ("Sucursal: BOG-CEN ▾") that opens
 * a Popover containing the existing `<SucursalPicker />` — the same
 * search input + cards UI the operator sees at the initial branch
 * selection. Reusing `SucursalPicker` keeps the search experience
 * consistent (same fuzzy match on `nombre` / `prefijo` / `uuid`).
 *
 * Difference from `<BranchSelector />`:
 *   - `BranchSelector` is the topbar Radix Select (no search input,
 *     designed for compact chrome placement).
 *   - `BranchPickerInline` is a page-level Popover with search (designed
 *     for users who want to switch from within the page without going
 *     to the topbar).
 *
 * Controlled: parent owns the active `value` via `useSucursal()` and
 * the page's `setSelected`. The Popover just notifies via `onSelect`.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Building2, ChevronDown, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Popover } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

import { SucursalPicker, type SucursalPickerOption } from './SucursalPicker';

export interface BranchPickerInlineProps {
  /** Label to show in the trigger (typically `branch.nombre`). */
  valueLabel: string | null;
  /** Permitted branches the admin can pick from. */
  options: SucursalPickerOption[];
  /** Called when the user picks a branch. */
  onSelect: (uuid: string) => void;
  /** Whether the option list is loading (disables the trigger). */
  isLoading?: boolean;
}

export function BranchPickerInline({
  valueLabel,
  options,
  onSelect,
  isLoading = false,
}: BranchPickerInlineProps): JSX.Element {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const label = valueLabel
    ?? t('branchPickerInline.placeholder', 'Seleccionar sucursal');

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      testId="branch-picker-inline-popover"
      align="start"
      className="w-[28rem] max-w-[90vw] p-0"
      trigger={
        <Button
          type="button"
          variant="outline"
          disabled={isLoading}
          aria-label={t('branchPickerInline.aria', 'Cambiar sucursal')}
          data-testid="branch-picker-inline-trigger"
          className="min-w-[12rem] justify-between"
        >
          <span className="flex items-center gap-2 truncate">
            <Building2 className="h-4 w-4 shrink-0" aria-hidden />
            <span className="truncate" data-testid="branch-picker-inline-label">
              {label}
            </span>
          </span>
          <ChevronDown
            className={cn(
              'h-4 w-4 shrink-0 opacity-60 transition-transform',
              open && 'rotate-180',
            )}
            aria-hidden
          />
        </Button>
      }
    >
      <div className="flex items-center justify-between border-b px-4 py-2">
        <p className="text-xs font-medium uppercase text-muted-foreground">
          {t('branchPickerInline.popoverTitle', 'Cambiar de sucursal')}
        </p>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label={t('branchPickerInline.close', 'Cerrar')}
          data-testid="branch-picker-inline-close"
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <SucursalPicker
        options={options}
        isLoading={isLoading}
        onSelect={(uuid) => {
          onSelect(uuid);
          setOpen(false);
        }}
      />
    </Popover>
  );
}
