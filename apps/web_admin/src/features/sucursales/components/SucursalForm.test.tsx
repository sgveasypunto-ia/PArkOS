/**
 * `SucursalForm.test.tsx` -- unit tests for the presentational
 * `<SucursalForm />` (IT-2.7).
 *
 * Pattern (mirror of LoginForm.test.tsx): a Harness with real RHF +
 * zodResolver so the rendered tree exercises the same component path
 * as production. We don't mock the form -- mocking it is brittle.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SucursalFormHarness } from './SucursalForm';

describe('SucursalForm', () => {
  it('renders the required fields with the submit button', () => {
    render(<SucursalFormHarness onSubmit={vi.fn()} isSubmitting={false} />);
    expect(screen.getByTestId('sucursal-field-nombre')).toBeInTheDocument();
    expect(screen.getByTestId('sucursal-field-prefijo')).toBeInTheDocument();
    expect(screen.getByTestId('sucursal-submit')).toBeInTheDocument();
  });

  it('disables the submit button while submitting', () => {
    render(<SucursalFormHarness onSubmit={vi.fn()} isSubmitting />);
    expect((screen.getByTestId('sucursal-submit') as HTMLButtonElement).disabled).toBe(true);
  });

  it('blocks submit when nombre is empty (Zod)', async () => {
    const onSubmit = vi.fn();
    render(<SucursalFormHarness onSubmit={onSubmit} isSubmitting={false} />);
    const user = userEvent.setup();
    // Only prefijo_nombre is filled; nombre is missing.
    await user.type(screen.getByTestId('sucursal-field-prefijo'), 'BOG-CEN');
    await user.click(screen.getByTestId('sucursal-submit'));
    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it('blocks submit when prefijo_nombre is not uppercase 3-6 chars', async () => {
    const onSubmit = vi.fn();
    render(<SucursalFormHarness onSubmit={onSubmit} isSubmitting={false} />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId('sucursal-field-nombre'), 'Sucursal Centro');
    await user.type(screen.getByTestId('sucursal-field-prefijo'), 'bog-cen-very-long');
    await user.click(screen.getByTestId('sucursal-submit'));
    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it('submits valid input', async () => {
    const onSubmit = vi.fn();
    render(<SucursalFormHarness onSubmit={onSubmit} isSubmitting={false} />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId('sucursal-field-nombre'), 'Sucursal Centro');
    await user.type(screen.getByTestId('sucursal-field-prefijo'), 'BOG-CEN');
    await user.type(screen.getByTestId('sucursal-field-ciudad'), 'Bogota');
    await user.click(screen.getByTestId('sucursal-submit'));
    // Zod resolver is async; the onSubmit call lands after a microtask.
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled();
    });
    const firstCall = (onSubmit.mock.calls[0]?.[0] ?? {}) as Record<string, unknown>;
    expect(firstCall).toMatchObject({
      nombre: 'Sucursal Centro',
      prefijo_nombre: 'BOG-CEN',
      ciudad: 'Bogota',
    });
  });
});
