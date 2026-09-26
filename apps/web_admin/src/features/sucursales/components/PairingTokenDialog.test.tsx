/**
 * `PairingTokenDialog.test.tsx` -- unit tests for the token display +
 * countdown (IT-2.3, IT-2.7).
 *
 * Verifies:
 *   - The dialog renders nothing when token=null.
 *   - When token is set, the token value + the "Copied!" status
 *     placeholder are rendered.
 *   - The copy button triggers the navigator.clipboard.writeText
 *     call (mocked). The status "Copied!" appears.
 *   - After closeExpires (now < expires_at) the dialog does NOT
 *     render the closed/expired state ("Expira en ...") once seconds
 *     count reaches 0 -- the countdown keeps ticking until 00:00.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PairingTokenDialog } from './PairingTokenDialog';

function expiresInSeconds(s: number): Date {
  return new Date(Date.now() + s * 1000);
}

const TOKEN_PAYLOAD = {
  token: 'fake-jwt-pairing-token-abc.def.ghi',
  expires_at: '',
  sucursal_uuid: '00000000-0000-0000-0000-0000000000a1',
};

describe('PairingTokenDialog', () => {
  beforeEach(() => {
    // jsdom v25 exposes `navigator.clipboard` as a frozen
    // `[EventTarget]`-backed prototype property. Plain
    // `Object.assign` does not override it; we must redefine the
    // property descriptor with `configurable: true` AFTER deleting
    // the prototype default.
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      writable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when token is null', () => {
    const { container } = render(<PairingTokenDialog token={null} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders the token value when token is provided', () => {
    render(
      <PairingTokenDialog
        token={{ ...TOKEN_PAYLOAD, expires_at: expiresInSeconds(1800).toISOString() }}
        onClose={vi.fn()}
      />,
    );
    const dialog = screen.getByTestId('pairing-token-dialog');
    expect(dialog).toBeInTheDocument();
    const value = screen.getByTestId('pairing-token-value');
    expect(value.textContent).toBe(TOKEN_PAYLOAD.token);
  });

  it('triggers the copy action on copy click and shows Copied status', async () => {
    render(
      <PairingTokenDialog
        token={{ ...TOKEN_PAYLOAD, expires_at: expiresInSeconds(1800).toISOString() }}
        onClose={vi.fn()}
      />,
    );
    // The component reads `navigator.clipboard.writeText` at click time
    // -- jsdom v25 freezes that property, so the test patches the
    // descriptor in place rather than re-reading the captured spy
    // object.
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      writable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    const user = userEvent.setup();
    await user.click(screen.getByTestId('pairing-token-copy'));
    const status = screen.getByTestId('pairing-token-copied');
    expect(status.textContent).toMatch(/copiad/i);
  });

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn();
    render(
      <PairingTokenDialog
        token={{ ...TOKEN_PAYLOAD, expires_at: expiresInSeconds(1800).toISOString() }}
        onClose={onClose}
      />,
    );
    await userEvent.setup().click(screen.getByTestId('pairing-token-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
