/**
 * BranchSelector — topbar dropdown for the multi-tenant admin PWA.
 *
 * Renders a shadcn-style Select (Radix UI Select primitive) bound to the
 * list of branches the actor is permitted to see. The Dashboard page
 * feeds `options` from `GET /api/v1/sucursales` (T-PR10-01, REQ-X2) and
 * persists the selection through the `SucursalContext` provider (T-PR10-12).
 *
 * WCAG 2.1 AA: `aria-label` on the trigger, focus ring via `focus:ring-2
 * focus:ring-ring`, full keyboard navigation inherited from Radix Select
 * (Up/Down/Enter/Space, Home/End, typeahead).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import * as Select from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface BranchOption {
  uuid: string;
  nombre: string | null;
}

interface BranchSelectorProps {
  options: BranchOption[];
  value: string | null;
  onChange: (uuid: string) => void;
}

export function BranchSelector({ options, value, onChange }: BranchSelectorProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  if (options.length === 0) {
    return (
      <div
        className="text-sm text-muted-foreground"
        data-testid="branch-selector-empty"
      >
        {t('branchSelector.empty', 'No hay sucursales disponibles')}
      </div>
    );
  }

  const current = options.find((o) => o.uuid === value);
  const triggerLabel = current?.nombre
    ?? t('branchSelector.placeholder', 'Selecciona una sucursal');

  return (
    <Select.Root
      value={value ?? undefined}
      onValueChange={onChange}
      open={open}
      onOpenChange={setOpen}
    >
      <Select.Trigger
        aria-label={t('branchSelector.label', 'Seleccionar sucursal')}
        data-testid="branch-selector-trigger"
        className={cn(
          'inline-flex items-center gap-2 rounded-md border border-input bg-background px-3 py-1.5 text-sm',
          'hover:bg-accent hover:text-accent-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <Select.Value placeholder={triggerLabel}>{triggerLabel}</Select.Value>
        <Select.Icon>
          <ChevronDown className="h-4 w-4 opacity-60" aria-hidden="true" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="overflow-hidden rounded-md border border-input bg-popover text-popover-foreground shadow-md"
          position="popper"
          sideOffset={4}
        >
          <Select.Viewport className="p-1">
            {options.map((opt) => (
              <Select.Item
                key={opt.uuid}
                value={opt.uuid}
                data-testid={`branch-selector-option-${opt.uuid}`}
                className={cn(
                  'relative flex cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none',
                  'focus:bg-accent focus:text-accent-foreground',
                  'data-[state=checked]:bg-accent data-[state=checked]:text-accent-foreground',
                  'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
                )}
              >
                <Select.ItemIndicator className="absolute left-2 inline-flex items-center">
                  <Check className="h-4 w-4" aria-hidden="true" />
                </Select.ItemIndicator>
                <Select.ItemText>{opt.nombre ?? opt.uuid}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
