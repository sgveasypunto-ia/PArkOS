/**
 * `<VehiculoSuggestions />` — shared accessible autocomplete dropdown
 * for the HU-F7.1 (búsqueda sin placa) vehicle search. Consumed by BOTH
 * the dashboard `PlacaInputHero` (`Dashboard.tsx`) and `<SalidaPanel />`'s
 * own `salida-placa` field.
 *
 * WCAG 2.1 AA — WAI-ARIA "combobox with listbox autocomplete" pattern
 * (https://www.w3.org/WAI/ARIA/apg/patterns/combobox/). This component
 * owns ONLY the popup: `role="listbox"` + one `role="option"` per
 * candidate, each with a stable `id`. The OWNING `<input>` at each
 * integration point is responsible for `role="combobox"`,
 * `aria-expanded`, `aria-controls={listboxId}`, and
 * `aria-activedescendant={vehiculoSuggestionOptionId(listboxId, activeIndex)}`
 * — this component has no opinion on focus/keyboard-event wiring
 * because the input is what owns focus.
 *
 * There is no combobox/listbox primitive already installed in this
 * repo (no `cmdk`, no shadcn `Combobox`) — this is a hand-built
 * dropdown over the existing `cn()` + Tailwind semantic-token
 * conventions (no new dependency, no hex-hardcoded colors).
 *
 * Deliberately NOT hero-sized: the hero input is `text-6xl`, but the
 * suggestion list always renders at normal/legible body text size in
 * BOTH integration points.
 */
import { cn } from '@/lib/utils';

import { vehiculoSuggestionOptionId, type VehiculoMatch } from '../lib/vehiculoMatch';

export interface VehiculoSuggestionsProps {
  /**
   * `id` of the rendered `<ul role="listbox">`. The owning `<input>`
   * must reference this SAME id via `aria-controls`.
   */
  listboxId: string;
  candidates: readonly VehiculoMatch[];
  /** Index of the highlighted option, or `-1` when none is highlighted. */
  activeIndex: number;
  onSelect: (candidate: VehiculoMatch) => void;
  /** `data-testid` prefix — lets each integration point assert render without id collisions. */
  testIdPrefix?: string;
  className?: string;
}

export function VehiculoSuggestions({
  listboxId,
  candidates,
  activeIndex,
  onSelect,
  testIdPrefix = 'vehiculo-suggestions',
  className,
}: VehiculoSuggestionsProps): JSX.Element | null {
  if (candidates.length === 0) return null;

  return (
    <ul
      id={listboxId}
      role="listbox"
      data-testid={testIdPrefix}
      className={cn(
        'absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-popover text-popover-foreground shadow-apple-sm',
        className,
      )}
    >
      {candidates.map((candidate, index) => {
        const label =
          candidate.ingreso.placa ??
          candidate.ingreso.consecutivo ??
          candidate.ingreso.uuid.slice(0, 8);
        const isActive = index === activeIndex;
        return (
          <li
            key={candidate.ingreso.uuid}
            id={vehiculoSuggestionOptionId(listboxId, index)}
            role="option"
            aria-selected={isActive}
            data-testid={`${testIdPrefix}-option-${index}`}
            className={cn(
              'cursor-pointer truncate px-3 py-2 font-mono text-sm',
              isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/60',
            )}
            // `onMouseDown` (not `onClick`) + `preventDefault` so the
            // input never blurs before `onSelect` fires — the standard
            // combobox-option pattern.
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(candidate);
            }}
          >
            {label}
          </li>
        );
      })}
    </ul>
  );
}
