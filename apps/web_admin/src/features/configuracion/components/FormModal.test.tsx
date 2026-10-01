/**
 * FormModal — unit tests.
 *
 * Pins the shell responsibilities only: title wiring, description,
 * error slot, children passthrough, open/close.
 *
 * The caller-owned form is tested at the feature level (TarifaForm /
 * CupoForm). FormModal does not own the form, the submit button, or
 * the cancel button — that lives in the caller.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FormModal } from './FormModal';

function setup(
  over: Partial<Omit<React.ComponentProps<typeof FormModal>, 'children'>> = {},
) {
  const onOpenChange = vi.fn();
  const props: React.ComponentProps<typeof FormModal> = {
    open: true,
    onOpenChange,
    title: 'Nueva tarifa',
    description: 'Cargá la tarifa de la sucursal',
    children: <input data-testid="child-input" />,
    ...over,
  };
  const result = render(<FormModal {...props} />);
  return { ...result, onOpenChange };
}

describe('FormModal', () => {
  it('FM1: renders title + description + children when open', () => {
    setup();
    expect(screen.getByText('Nueva tarifa')).toBeInTheDocument();
    expect(screen.getByText('Cargá la tarifa de la sucursal')).toBeInTheDocument();
    expect(screen.getByTestId('child-input')).toBeInTheDocument();
  });

  it('FM2: hidden when closed', () => {
    setup({ open: false });
    expect(screen.queryByText('Nueva tarifa')).not.toBeInTheDocument();
  });

  it('FM3: error slot renders with role="alert" when error is set', () => {
    setup({ error: 'La ventana se solapa con la tarifa X' });
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('La ventana se solapa con la tarifa X');
  });

  it('FM4: error slot absent when error is null/undefined', () => {
    setup({ error: null });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('FM5: backdrop click fires onOpenChange(false)', async () => {
    const user = userEvent.setup();
    const { onOpenChange, container } = setup();
    // The Dialog renders a fixed-position backdrop; click on it (not
    // on a child) dispatches the close.
    const backdrop = container.querySelector('[role="dialog"]')?.parentElement;
    if (backdrop !== null && backdrop !== undefined) {
      await user.click(backdrop);
      expect(onOpenChange).toHaveBeenCalledWith(false);
    } else {
      throw new Error('backdrop not found');
    }
  });
});

