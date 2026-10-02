/**
 * `RevocarPairingModal.test.tsx` -- HU-F19.3 revoke actions.
 *
 * Covers:
 *  - Section A (revoke token) is disabled with explanatory copy when
 *    `pairingTokenUuid` is `null`.
 *  - Confirming Section A calls `revokePairingToken` + `onRevoked`,
 *    then closes.
 *  - Section B (revoke sync, "avanzado") validates required fields
 *    and, once filled, calls `revokeSucursalSync` with the typed body.
 *  - A failure in one section does not disable the other.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as PairingApiModule from '../api/pairingApi';

vi.mock('../api/pairingApi', async () => {
  const actual = await vi.importActual<typeof PairingApiModule>('../api/pairingApi');
  return {
    ...actual,
    revokePairingToken: vi.fn(),
    revokeSucursalSync: vi.fn(),
  };
});

import { revokePairingToken, revokeSucursalSync } from '../api/pairingApi';
import { RevocarPairingModal } from './RevocarPairingModal';

const mockedRevokeToken = revokePairingToken as ReturnType<typeof vi.fn>;
const mockedRevokeSync = revokeSucursalSync as ReturnType<typeof vi.fn>;

const SUCURSAL_UUID = '33333333-3333-3333-3333-333333333333';
const TOKEN_UUID = '44444444-4444-4444-4444-444444444444';

beforeEach(() => {
  mockedRevokeToken.mockReset();
  mockedRevokeSync.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('RevocarPairingModal', () => {
  it('disables the revoke-token section with explanatory copy when pairingTokenUuid is null', () => {
    render(
      <RevocarPairingModal
        sucursalUuid={SUCURSAL_UUID}
        pairingTokenUuid={null}
        open
        onClose={vi.fn()}
        onRevoked={vi.fn()}
      />,
    );
    expect(screen.getByTestId('revocar-pairing-token-unknown')).toBeInTheDocument();
    expect(screen.getByTestId('revocar-pairing-token-confirm')).toBeDisabled();
  });

  it('confirming revoke-token calls revokePairingToken + onRevoked, then closes', async () => {
    mockedRevokeToken.mockResolvedValue(undefined);
    const user = userEvent.setup();
    const onRevoked = vi.fn();
    const onClose = vi.fn();
    render(
      <RevocarPairingModal
        sucursalUuid={SUCURSAL_UUID}
        pairingTokenUuid={TOKEN_UUID}
        open
        onClose={onClose}
        onRevoked={onRevoked}
      />,
    );
    expect(screen.getByTestId('revocar-pairing-token-confirm')).toBeEnabled();
    await user.click(screen.getByTestId('revocar-pairing-token-confirm'));
    await waitFor(() => expect(mockedRevokeToken).toHaveBeenCalledWith(TOKEN_UUID));
    expect(onRevoked).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('revoke-sync form validates required fields and does not submit when empty', async () => {
    const user = userEvent.setup();
    render(
      <RevocarPairingModal
        sucursalUuid={SUCURSAL_UUID}
        pairingTokenUuid={null}
        open
        onClose={vi.fn()}
        onRevoked={vi.fn()}
      />,
    );
    await user.click(screen.getByTestId('revocar-pairing-sync-submit'));
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
    expect(mockedRevokeSync).not.toHaveBeenCalled();
  });

  it('revoke-sync form submits the typed body and calls revokeSucursalSync + onRevoked', async () => {
    mockedRevokeSync.mockResolvedValue(undefined);
    const user = userEvent.setup();
    const onRevoked = vi.fn();
    const onClose = vi.fn();
    render(
      <RevocarPairingModal
        sucursalUuid={SUCURSAL_UUID}
        pairingTokenUuid={null}
        open
        onClose={onClose}
        onRevoked={onRevoked}
      />,
    );
    await user.type(screen.getByTestId('revocar-sync-jwt-kid'), 'kid-123');
    await user.type(screen.getByTestId('revocar-sync-jwt-uuid'), 'uuid-456');
    await user.click(screen.getByTestId('revocar-pairing-sync-submit'));
    await waitFor(() =>
      expect(mockedRevokeSync).toHaveBeenCalledWith(SUCURSAL_UUID, {
        jwtKid: 'kid-123',
        jwtUuid: 'uuid-456',
      }),
    );
    expect(onRevoked).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('a failure in one section does not disable the other', async () => {
    mockedRevokeToken.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(
      <RevocarPairingModal
        sucursalUuid={SUCURSAL_UUID}
        pairingTokenUuid={TOKEN_UUID}
        open
        onClose={vi.fn()}
        onRevoked={vi.fn()}
      />,
    );
    await user.click(screen.getByTestId('revocar-pairing-token-confirm'));
    await screen.findByTestId('revocar-pairing-token-error');
    expect(screen.getByTestId('revocar-sync-jwt-kid')).toBeEnabled();
    expect(screen.getByTestId('revocar-pairing-sync-submit')).toBeEnabled();
  });
});
