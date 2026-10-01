import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SucursalPicker, type SucursalPickerOption } from './SucursalPicker';

const OPTIONS: SucursalPickerOption[] = [
  {
    uuid: '11111111-1111-1111-1111-111111111111',
    nombre: 'Sucursal Norte',
    prefijo_nombre: 'BOG-NOR',
  },
  {
    uuid: '22222222-2222-2222-2222-222222222222',
    nombre: 'Sucursal Sur',
    prefijo_nombre: 'BOG-SUR',
  },
];

describe('SucursalPicker', () => {
  it('renders one card per option with accessible label', () => {
    render(<SucursalPicker options={OPTIONS} isLoading={false} onSelect={() => {}} />);

    expect(
      screen.getByRole('button', { name: /Sucursal Norte \(BOG-NOR\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Sucursal Sur \(BOG-SUR\)/ }),
    ).toBeInTheDocument();
  });

  it('invokes onSelect with the clicked UUID', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SucursalPicker options={OPTIONS} isLoading={false} onSelect={onSelect} />);

    await user.click(
      screen.getByRole('button', { name: /Sucursal Sur \(BOG-SUR\)/ }),
    );

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('22222222-2222-2222-2222-222222222222');
  });

  it('filters by name, prefix and uuid (case insensitive)', async () => {
    const user = userEvent.setup();
    render(<SucursalPicker options={OPTIONS} isLoading={false} onSelect={() => {}} />);

    const search = screen.getByTestId('sucursal-picker-search');
    await user.type(search, 'sur');

    expect(
      screen.getByRole('button', { name: /Sucursal Sur/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Sucursal Norte/ }),
    ).not.toBeInTheDocument();
  });

  it('shows a polite filter-empty state when no match', async () => {
    const user = userEvent.setup();
    render(<SucursalPicker options={OPTIONS} isLoading={false} onSelect={() => {}} />);

    await user.type(screen.getByTestId('sucursal-picker-search'), 'zzzzzz');

    expect(screen.getByTestId('sucursal-picker-empty-filter')).toBeInTheDocument();
  });

  it('shows a system-empty state when options is empty', () => {
    render(<SucursalPicker options={[]} isLoading={false} onSelect={() => {}} />);
    expect(screen.getByTestId('sucursal-picker-empty-system')).toBeInTheDocument();
  });

  it('shows a loading status while isLoading', () => {
    render(<SucursalPicker options={OPTIONS} isLoading={true} onSelect={() => {}} />);
    expect(screen.getByTestId('sucursal-picker-loading')).toBeInTheDocument();
  });

  it('falls back to uuid when nombre is null', () => {
    render(
      <SucursalPicker
        options={[
          { uuid: 'uuid-only', nombre: null, prefijo_nombre: null },
        ]}
        isLoading={false}
        onSelect={() => {}}
      />,
    );
    expect(
      screen.getByRole('button', { name: /uuid-only/ }),
    ).toBeInTheDocument();
  });
});
