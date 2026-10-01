/**
 * `ArqueosFilters.test.tsx` -- HU-F18.2 T1 filter bar unit.
 *
 * Exercises the controlled-input contract: every dropdown / date
 * field calls ``onChange`` with the patched value; the reset button
 * calls ``onReset``. No network calls -- the dropdown options are
 * passed in directly by the container (which fetches them upstream).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ArqueosFilters, type ArqueosFiltersValue } from './ArqueosFilters';

const EMPTY: ArqueosFiltersValue = {
  uuid_sucursal: '',
  fecha_desde: '',
  fecha_hasta: '',
  uuid_tipo_arqueo: '',
};

const OPTIONS = {
  sucursalOptions: [
    { uuid: '00000000-0000-0000-0000-000000000001', nombre: 'Sucursal Norte' },
    { uuid: '00000000-0000-0000-0000-000000000002', nombre: 'Sucursal Sur' },
  ],
  tipoOptions: [
    { uuid: '00000000-0000-0000-0000-000000000010', codigo: 'auditoria' },
    { uuid: '00000000-0000-0000-0000-000000000011', codigo: 'cierre_turno' },
  ],
};

describe('ArqueosFilters', () => {
  it('renders the four controlled inputs + reset', () => {
    const onChange = vi.fn();
    const onReset = vi.fn();
    render(
      <ArqueosFilters
        value={EMPTY}
        onChange={onChange}
        onReset={onReset}
        options={OPTIONS}
      />,
    );
    expect(screen.getByTestId('arqueos-filters')).toBeInTheDocument();
    expect(screen.getByTestId('arqueos-filters-sucursal')).toBeInTheDocument();
    expect(screen.getByTestId('arqueos-filters-date-desde')).toBeInTheDocument();
    expect(screen.getByTestId('arqueos-filters-date-hasta')).toBeInTheDocument();
    expect(screen.getByTestId('arqueos-filters-tipo')).toBeInTheDocument();
    expect(screen.getByTestId('arqueos-filters-reset')).toBeInTheDocument();
  });

  it('calling onChange when the branch dropdown changes', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ArqueosFilters
        value={EMPTY}
        onChange={onChange}
        onReset={vi.fn()}
        options={OPTIONS}
      />,
    );
    await user.selectOptions(
      screen.getByTestId('arqueos-filters-sucursal'),
      '00000000-0000-0000-0000-000000000001',
    );
    expect(onChange).toHaveBeenCalledWith({
      ...EMPTY,
      uuid_sucursal: '00000000-0000-0000-0000-000000000001',
    });
  });

  it('calling onChange when the date inputs change', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ArqueosFilters
        value={EMPTY}
        onChange={onChange}
        onReset={vi.fn()}
        options={OPTIONS}
      />,
    );
    await user.type(
      screen.getByTestId('arqueos-filters-date-desde'),
      '2026-10-01',
    );
    expect(onChange).toHaveBeenLastCalledWith({
      ...EMPTY,
      fecha_desde: '2026-10-01',
    });
  });

  it('reset button calls onReset', async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(
      <ArqueosFilters
        value={EMPTY}
        onChange={vi.fn()}
        onReset={onReset}
        options={OPTIONS}
      />,
    );
    await user.click(screen.getByTestId('arqueos-filters-reset'));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});