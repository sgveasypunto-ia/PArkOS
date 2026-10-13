/**
 * `UsuarioSearchInput.test.tsx` — unit tests for the free-text user
 * search box (HU-F9).
 *
 * The component is intentionally minimal (a controlled `<input
 * type="search">` with a `Search` icon), so the tests pin:
 *   - the `value` / `onChange` contract,
 *   - the default + overridable placeholder / aria-label,
 *   - the `disabled` prop mirror,
 *   - the `data-testid` integration seam.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { UsuarioSearchInput } from './UsuarioSearchInput';

describe('<UsuarioSearchInput />', () => {
  it('renders the input with the i18n fallback placeholder and aria-label', () => {
    render(<UsuarioSearchInput value="" onChange={() => undefined} testId="search" />);
    const input = screen.getByTestId('search');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('type', 'search');
    expect(input).toHaveAttribute('placeholder', expect.stringMatching(/correo o nombre/i));
    expect(input).toHaveAttribute('aria-label', expect.stringMatching(/correo o nombre/i));
  });

  it('honors a custom placeholder and aria-label when provided', () => {
    render(
      <UsuarioSearchInput
        value=""
        onChange={() => undefined}
        placeholder="Buscar usuarios…"
        ariaLabel="Buscar usuarios por nombre o correo"
        testId="search"
      />,
    );
    const input = screen.getByTestId('search');
    expect(input).toHaveAttribute('placeholder', 'Buscar usuarios…');
    expect(input).toHaveAttribute('aria-label', 'Buscar usuarios por nombre o correo');
  });

  it('fires onChange on each keystroke and reflects the new value', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <UsuarioSearchInput value="" onChange={onChange} testId="search" />,
    );
    const input = screen.getByTestId('search') as HTMLInputElement;
    await user.type(input, 'a');
    expect(onChange).toHaveBeenCalled();
    // The component is controlled -- the rendered value follows the
    // caller's `value` prop, so we re-render with the new value to
    // assert the parent-driven update path.
    rerender(<UsuarioSearchInput value="a" onChange={onChange} testId="search" />);
    expect(input.value).toBe('a');
  });

  it('disables the input when disabled is true', () => {
    render(
      <UsuarioSearchInput
        value=""
        onChange={() => undefined}
        disabled={true}
        testId="search"
      />,
    );
    expect(screen.getByTestId('search')).toBeDisabled();
  });

  it('renders a <label> with the i18n fallback above the input', () => {
    render(<UsuarioSearchInput value="" onChange={() => undefined} testId="search" />);
    const label = screen.getByTestId('usuario-search-label');
    expect(label).toBeInTheDocument();
    expect(label.tagName).toBe('LABEL');
    expect(label).toHaveTextContent(/buscar/i);
  });
});
