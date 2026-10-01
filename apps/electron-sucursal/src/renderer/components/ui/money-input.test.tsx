/**
 * `money-input.test.tsx` — React Testing Library coverage for
 * `<MoneyInput />`, the COP money-input wrapper around the shadcn
 * `<Input>` base (`components/ui/input.tsx`).
 *
 * Covers: empty/placeholder render, typing, deleting, pasting,
 * external value resync while unfocused vs. focused, `disabled`
 * passthrough, and the decorative `$` being hidden from AT.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { MoneyInput } from './money-input';

describe('<MoneyInput />', () => {
  it('renders empty with the placeholder visible when value is undefined', () => {
    render(
      <MoneyInput
        value={undefined}
        onChange={vi.fn()}
        placeholder="Ingrese el valor"
        inputTestId="money-input"
      />,
    );
    const input = screen.getByTestId('money-input') as HTMLInputElement;
    expect(input.value).toBe('');
    expect(input.placeholder).toBe('Ingrese el valor');
  });

  it('typing "50000" shows "50.000" and calls onChange with the raw digits "50000"', () => {
    const onChange = vi.fn();
    render(<MoneyInput value={undefined} onChange={onChange} inputTestId="money-input" />);
    const input = screen.getByTestId('money-input') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '50000' } });

    expect(input.value).toBe('50.000');
    expect(onChange).toHaveBeenCalledWith('50000');
  });

  it('deleting everything clears the input and calls onChange with ""', () => {
    const onChange = vi.fn();
    render(<MoneyInput value={50000} onChange={onChange} inputTestId="money-input" />);
    const input = screen.getByTestId('money-input') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '' } });

    expect(input.value).toBe('');
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('pasting "$1.500.000" sanitizes and formats to "1.500.000", onChange receives "1500000"', () => {
    const onChange = vi.fn();
    render(<MoneyInput value={undefined} onChange={onChange} inputTestId="money-input" />);
    const input = screen.getByTestId('money-input') as HTMLInputElement;

    fireEvent.change(input, { target: { value: '$1.500.000' } });

    expect(input.value).toBe('1.500.000');
    expect(onChange).toHaveBeenCalledWith('1500000');
  });

  it('resyncs the display when the value prop changes externally while NOT focused', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <MoneyInput value={10000} onChange={onChange} inputTestId="money-input" />,
    );
    const input = screen.getByTestId('money-input') as HTMLInputElement;
    expect(input.value).toBe('10.000');

    rerender(<MoneyInput value={20000} onChange={onChange} inputTestId="money-input" />);
    expect(input.value).toBe('20.000');
  });

  it('does NOT overwrite the display when the value prop changes externally while focused', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <MoneyInput value={10000} onChange={onChange} inputTestId="money-input" />,
    );
    const input = screen.getByTestId('money-input') as HTMLInputElement;
    fireEvent.focus(input);

    rerender(<MoneyInput value={20000} onChange={onChange} inputTestId="money-input" />);

    expect(input.value).toBe('10.000');
  });

  it('propagates disabled to the underlying input', () => {
    render(
      <MoneyInput value={undefined} onChange={vi.fn()} disabled inputTestId="money-input" />,
    );
    const input = screen.getByTestId('money-input') as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it('hides the decorative "$" from assistive technology via aria-hidden', () => {
    render(<MoneyInput value={undefined} onChange={vi.fn()} inputTestId="money-input" />);
    const dollarSign = screen.getByText('$');
    expect(dollarSign.getAttribute('aria-hidden')).toBe('true');
  });
});
