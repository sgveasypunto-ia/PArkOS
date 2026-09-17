/**
 * Unit tests for `PlacaInput` (HU-F6.1, T5).
 *
 * Spec scenarios from `specs/operacion-ingreso.md`:
 *   - Plate normalized to uppercase + auto-focused
 *   - Submit by Enter key
 *   - Invalid format → inline error from `placa_formato_invalido`
 *
 * Uses `fireEvent` (from `@testing-library/react`) instead of the
 * `user-event` package — that dependency is not in package.json on
 * this branch (F3.3's AbrirTurno test references it but the import
 * is never resolved at test time).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import '@/i18n';

import { PlacaInput } from './PlacaInput';

describe('PlacaInput', () => {
  it('auto-focuses the input on mount', async () => {
    render(<PlacaInput onValidSubmit={vi.fn()} />);
    const input = screen.getByLabelText(/placa/i) as HTMLInputElement;
    await waitFor(() => expect(document.activeElement).toBe(input));
  });

  it('normalizes typed input to uppercase + strips whitespace', () => {
    render(<PlacaInput onValidSubmit={vi.fn()} />);
    const input = screen.getByLabelText(/placa/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'abc 12d' } });
    expect(input.value).toBe('ABC12D');
  });

  it('calls onValidSubmit with the normalized plate on Enter key', async () => {
    const onValidSubmit = vi.fn();
    render(<PlacaInput onValidSubmit={onValidSubmit} />);
    const input = screen.getByLabelText(/placa/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'ABC123' } });
    const form = input.closest('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    await waitFor(() =>
      expect(onValidSubmit).toHaveBeenCalledWith('ABC123'),
    );
  });

  it('shows the placa_formato_invalido inline error on invalid format', async () => {
    const onValidSubmit = vi.fn();
    render(<PlacaInput onValidSubmit={onValidSubmit} />);
    const input = screen.getByLabelText(/placa/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'XX' } });
    const form = input.closest('form');
    fireEvent.submit(form as HTMLFormElement);
    await waitFor(() =>
      expect(
        screen.getByText(/placa no coincide con ningún formato conocido/i),
      ).toBeInTheDocument(),
    );
    expect(onValidSubmit).not.toHaveBeenCalled();
  });

  it('accepts both Auto (ABC123) and Moto (ABC12E) shapes', async () => {
    const onValidSubmit = vi.fn();
    const { rerender } = render(
      <PlacaInput onValidSubmit={onValidSubmit} />,
    );
    const input1 = screen.getByLabelText(/placa/i) as HTMLInputElement;
    fireEvent.change(input1, { target: { value: 'ABC123' } });
    fireEvent.submit(input1.closest('form') as HTMLFormElement);
    await waitFor(() =>
      expect(onValidSubmit).toHaveBeenLastCalledWith('ABC123'),
    );
    rerender(<PlacaInput onValidSubmit={onValidSubmit} />);
    const input2 = screen.getByLabelText(/placa/i) as HTMLInputElement;
    fireEvent.change(input2, { target: { value: 'ABC12E' } });
    fireEvent.submit(input2.closest('form') as HTMLFormElement);
    await waitFor(() =>
      expect(onValidSubmit).toHaveBeenLastCalledWith('ABC12E'),
    );
  });
});
