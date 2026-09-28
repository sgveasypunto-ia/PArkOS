/**
 * FormModal — unit tests.
 *
 * Pins:
 *   1. Renders title + description + children when open.
 *   2. Hidden when closed.
 *   3. Renders the error slot with role="alert" when error is set.
 *   4. Submit fires the onSubmit handler; cancel button fires
 *      onOpenChange(false).
 *   5. Submit button shows submitting label and is disabled.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FormModal } from './FormModal';

function setup(over: Partial<React.ComponentProps<typeof FormModal>> = {}) {
  const onSubmit = vi.fn((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
  });
  const onOpenChange = vi.fn();
  const props: React.ComponentProps<typeof FormModal> = {
    open: true,
    onOpenChange,
    title: 'Nueva tarifa',
    description: 'Cargá la tarifa de la sucursal',
    submitLabel: 'Crear',
    submitting: false,
    onSubmit,
    children: <input data-testid="child-input" />,
    ...over,
  };
  const result = render(<FormModal {...props} />);
  return { ...result, onSubmit, onOpenChange };
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

  it('FM5: cancel fires onOpenChange(false)', async () => {
    const user = userEvent.setup();
    const { onOpenChange } = setup();
    await user.click(screen.getByTestId('form-modal-cancel'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('FM6: submit button has type="submit" and the submitLabel', () => {
    setup({ submitLabel: 'Actualizar' });
    const btn = screen.getByTestId('form-modal-submit');
    expect(btn).toHaveAttribute('type', 'submit');
    expect(btn).toHaveTextContent('Actualizar');
  });

  it('FM7: submitting=true disables both buttons and shows ellipsis', () => {
    setup({ submitting: true, submitLabel: 'Crear' });
    const submit = screen.getByTestId('form-modal-submit');
    const cancel = screen.getByTestId('form-modal-cancel');
    expect(submit).toBeDisabled();
    expect(cancel).toBeDisabled();
    expect(submit).toHaveTextContent('Crear…');
  });

  it('FM8: form submit fires onSubmit with the event', async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup();
    await user.click(screen.getByTestId('form-modal-submit'));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});
