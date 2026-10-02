/**
 * `GenerarPairingTokenModal.test.tsx` -- HU-F19.3 token issuance modal.
 *
 * Covers:
 *  - submitting a valid ttl reveals the plaintext token + Copiar button
 *    and calls `onIssued`.
 *  - BR1: Close is disabled and every dismiss path (button click,
 *    Escape) no-ops until Copiar succeeds; once copied, Close works.
 *  - a mocked 429 shows the static rate-limit message (no fabricated
 *    countdown), staying on step 1 so the admin can retry.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as PairingApiModule from '../api/pairingApi';

vi.mock('../api/pairingApi', async () => {
  const actual = await vi.importActual<typeof PairingApiModule>('../api/pairingApi');
  return {
    ...actual,
    issuePairingToken: vi.fn(),
  };
});

import { issuePairingToken, PairingTokenRateLimitedError } from '../api/pairingApi';
import { GenerarPairingTokenModal } from './GenerarPairingTokenModal';

const mockedIssue = issuePairingToken as ReturnType<typeof vi.fn>;

const SUCURSAL_UUID = '22222222-2222-2222-2222-222222222222';

const RESP = {
  token: 'plaintext-pairing-token-once',
  pairing_token_uuid: '11111111-1111-1111-1111-111111111111',
  pairing_token_hash: 'sha256:deadbeef',
  expires_at: '2026-09-02T00:00:00',
  uuid_sucursal: SUCURSAL_UUID,
  ttl_hours: 24,
};

beforeEach(() => {
  mockedIssue.mockReset();
  Object.defineProperty(window.navigator, 'clipboard', {
    configurable: true,
    writable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('GenerarPairingTokenModal', () => {
  it('submits a valid ttl, reveals the plaintext token + Copiar button, and calls onIssued', async () => {
    mockedIssue.mockResolvedValue(RESP);
    const user = userEvent.setup();
    const onIssued = vi.fn();
    render(
      <GenerarPairingTokenModal
        sucursalUuid={SUCURSAL_UUID}
        open
        onClose={vi.fn()}
        onIssued={onIssued}
      />,
    );

    await user.click(screen.getByTestId('generar-pairing-token-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('pairing-token-value')).toBeInTheDocument();
    });
    expect(screen.getByTestId('pairing-token-value').textContent).toBe(RESP.token);
    expect(screen.getByTestId('generar-pairing-token-copy')).toBeInTheDocument();
    expect(onIssued).toHaveBeenCalledWith(RESP);
    expect(mockedIssue).toHaveBeenCalledWith({ uuidSucursal: SUCURSAL_UUID, ttlHours: 24 });
  });

  it('BR1: Close is disabled and no-ops (click + Escape) until Copiar succeeds, then closes', async () => {
    mockedIssue.mockResolvedValue(RESP);
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <GenerarPairingTokenModal
        sucursalUuid={SUCURSAL_UUID}
        open
        onClose={onClose}
        onIssued={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId('generar-pairing-token-submit'));
    await waitFor(() => screen.getByTestId('pairing-token-value'));

    const closeBtn = screen.getByTestId('generar-pairing-token-close') as HTMLButtonElement;
    expect(closeBtn).toBeDisabled();

    await user.click(closeBtn);
    expect(onClose).not.toHaveBeenCalled();

    await user.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('generar-pairing-token-copy'));
    await waitFor(() => expect(closeBtn).not.toBeDisabled());

    await user.click(screen.getByTestId('generar-pairing-token-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows the static rate-limit message on a 429, with no fabricated countdown, and stays on step 1', async () => {
    mockedIssue.mockRejectedValue(new PairingTokenRateLimitedError());
    const user = userEvent.setup();
    render(
      <GenerarPairingTokenModal
        sucursalUuid={SUCURSAL_UUID}
        open
        onClose={vi.fn()}
        onIssued={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId('generar-pairing-token-submit'));

    const alert = await screen.findByTestId('generar-pairing-token-error');
    expect(alert.textContent).toMatch(/l[íi]mite de 5 tokens/i);
    expect(alert.textContent).not.toMatch(/\d{1,2}:\d{2}/);
    expect(screen.getByTestId('generar-pairing-token-form')).toBeInTheDocument();
    expect(screen.queryByTestId('pairing-token-value')).not.toBeInTheDocument();
  });
});
