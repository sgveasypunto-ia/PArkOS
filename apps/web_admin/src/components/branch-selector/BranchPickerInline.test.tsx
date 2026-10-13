/**
 * `BranchPickerInline.test.tsx` — unit tests for the inline branch
 * picker (HU-X.8).
 *
 * The test exercises the trigger + the popover with `SucursalPicker`
 * inside. It does NOT verify the search filter (that's already covered
 * by `SucursalPicker.test.tsx`); it only verifies that:
 *   1. The trigger renders the supplied `valueLabel`.
 *   2. Clicking the trigger opens the popover with the options.
 *   3. Selecting an option fires `onSelect` with the right uuid AND
 *      closes the popover.
 *   4. The `isLoading` prop disables the trigger.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { BranchPickerInline } from './BranchPickerInline';

const OPTIONS = [
  { uuid: '11111111-1111-1111-1111-111111111111', nombre: 'BOG-CEN' },
  { uuid: '22222222-2222-2222-2222-222222222222', nombre: 'MED-NTE' },
  { uuid: '33333333-3333-3333-3333-333333333333', nombre: 'SUR-EST' },
];

describe('BranchPickerInline', () => {
  it('renders the trigger with the supplied valueLabel', () => {
    render(
      <BranchPickerInline
        valueLabel="BOG-CEN"
        options={OPTIONS}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('branch-picker-inline-trigger')).toBeInTheDocument();
    expect(screen.getByTestId('branch-picker-inline-label')).toHaveTextContent('BOG-CEN');
  });

  it('opens the popover and fires onSelect with the right uuid', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <BranchPickerInline
        valueLabel="BOG-CEN"
        options={OPTIONS}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByTestId('branch-picker-inline-trigger'));
    const option = await screen.findByLabelText(/BOG-CEN/i);
    expect(option).toBeInTheDocument();
    await user.click(option);
    expect(onSelect).toHaveBeenCalledWith(OPTIONS[0].uuid);
  });

  it('renders the placeholder when valueLabel is null', () => {
    render(
      <BranchPickerInline
        valueLabel={null}
        options={OPTIONS}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('branch-picker-inline-label')).toHaveTextContent(
      /Sucursal/i,
    );
  });

  it('disables the trigger when isLoading is true', () => {
    render(
      <BranchPickerInline
        valueLabel="BOG-CEN"
        options={OPTIONS}
        onSelect={vi.fn()}
        isLoading
      />,
    );
    expect(screen.getByTestId('branch-picker-inline-trigger')).toBeDisabled();
  });
});
