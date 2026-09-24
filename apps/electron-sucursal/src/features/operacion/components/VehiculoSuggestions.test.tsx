/**
 * Unit tests for `<VehiculoSuggestions />` (HU-F7.1, T5 — búsqueda sin
 * placa). Shared accessible dropdown consumed by the dashboard
 * `PlacaInputHero` AND `<SalidaPanel />`'s own `salida-placa` field.
 *
 * WCAG 2.1 AA — WAI-ARIA "combobox with listbox autocomplete" pattern:
 * the owning `<input>` carries `role="combobox"` + `aria-expanded` +
 * `aria-controls` + `aria-activedescendant` (wired at each integration
 * point, NOT by this component); this component renders the
 * `role="listbox"` + `role="option"` popup only.
 *
 * Coverage:
 *   V1: candidates=[] → renders nothing (no listbox in the DOM).
 *   V2: renders one `role="option"` per candidate, with the placa (or
 *       consecutivo) as the visible label.
 *   V3: the option at `activeIndex` has `aria-selected="true"`; the rest
 *       have `aria-selected="false"`.
 *   V4: clicking an option calls `onSelect` with that candidate.
 *   V5: the listbox `id` matches the `listboxId` prop (so the caller's
 *       `aria-controls` can reference it).
 *   V6: option ids follow `vehiculoSuggestionOptionId(listboxId, index)`.
 *
 * `vehiculoSuggestionOptionId` and `getNextSuggestionIndex` are pure
 * helpers colocated in `vehiculoMatch.ts` (not here — a plain function
 * export alongside a component trips `react-refresh/only-export-components`);
 * their own dedicated coverage lives in `vehiculoMatch.test.ts`.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { VehiculoSuggestions } from './VehiculoSuggestions';
import { vehiculoSuggestionOptionId, type VehiculoMatch } from '../lib/vehiculoMatch';
import type { IngresoActivo } from '../hooks/useIngresosActivos';

function makeIngreso(overrides: Partial<IngresoActivo> & { uuid: string }): IngresoActivo {
  return {
    placa: null,
    fecha_ingreso: '2026-09-19T10:00:00Z',
    consecutivo: null,
    created_at: '2026-09-19T10:00:00Z',
    uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
    uuid_sucursal: '00000000-0000-0000-0000-000000000def',
    ...overrides,
  };
}

const CANDIDATE_ABC123: VehiculoMatch = {
  ingreso: makeIngreso({ uuid: 'uuid-abc123', placa: 'ABC123' }),
  matchedOn: 'placa',
};
const CANDIDATE_PATINETA: VehiculoMatch = {
  ingreso: makeIngreso({ uuid: 'uuid-patineta', consecutivo: 'PATINETA-000003-34a24bae' }),
  matchedOn: 'consecutivo',
};

describe('<VehiculoSuggestions /> — HU-F7.1 shared accessible dropdown', () => {
  it('V1: candidates=[] → renders nothing', () => {
    const { container } = render(
      <VehiculoSuggestions
        listboxId="lb-1"
        candidates={[]}
        activeIndex={-1}
        onSelect={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('V2: renders one role="option" per candidate with the visible label', () => {
    render(
      <VehiculoSuggestions
        listboxId="lb-1"
        candidates={[CANDIDATE_ABC123, CANDIDATE_PATINETA]}
        activeIndex={-1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('ABC123');
    expect(options[1]).toHaveTextContent('PATINETA-000003-34a24bae');
  });

  it('V3: aria-selected reflects activeIndex', () => {
    render(
      <VehiculoSuggestions
        listboxId="lb-1"
        candidates={[CANDIDATE_ABC123, CANDIDATE_PATINETA]}
        activeIndex={1}
        onSelect={vi.fn()}
      />,
    );
    const options = screen.getAllByRole('option');
    expect(options[0]).toHaveAttribute('aria-selected', 'false');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
  });

  it('V4: clicking an option calls onSelect with that candidate', async () => {
    const onSelect = vi.fn();
    render(
      <VehiculoSuggestions
        listboxId="lb-1"
        candidates={[CANDIDATE_ABC123, CANDIDATE_PATINETA]}
        activeIndex={-1}
        onSelect={onSelect}
      />,
    );
    await userEvent.click(screen.getAllByRole('option')[1]!);
    expect(onSelect).toHaveBeenCalledWith(CANDIDATE_PATINETA);
  });

  it('V5: listbox id matches the listboxId prop', () => {
    render(
      <VehiculoSuggestions
        listboxId="salida-placa-suggestions"
        candidates={[CANDIDATE_ABC123]}
        activeIndex={-1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole('listbox')).toHaveAttribute('id', 'salida-placa-suggestions');
  });

  it('V6: option ids follow vehiculoSuggestionOptionId(listboxId, index)', () => {
    render(
      <VehiculoSuggestions
        listboxId="lb-1"
        candidates={[CANDIDATE_ABC123, CANDIDATE_PATINETA]}
        activeIndex={-1}
        onSelect={vi.fn()}
      />,
    );
    const options = screen.getAllByRole('option');
    expect(options[0]).toHaveAttribute('id', vehiculoSuggestionOptionId('lb-1', 0));
    expect(options[1]).toHaveAttribute('id', vehiculoSuggestionOptionId('lb-1', 1));
  });
});
