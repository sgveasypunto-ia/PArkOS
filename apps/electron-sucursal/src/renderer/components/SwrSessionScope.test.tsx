/**
 * UX1 — the SWR cache must not outlive the session of the operator.
 *
 * Repro (seen in the browser): Cerrar turno -> "Finalizar y salir" -> log in
 * again in the SAME tab -> the header still showed the CLOSED turno because
 * `useSesionActiva` served the stale `/caja-sesion/sesion/me` entry from the
 * SWR cache (and the 10 s dedupe window suppressed the revalidation). Real
 * SWR + real hook; only the HTTP layer and the auth store module are replaced.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { getSesionActivaMock } = vi.hoisted(() => ({ getSesionActivaMock: vi.fn() }));

vi.mock('@parkos/ui-kit/store', async () => {
  const { create } = await import('zustand');
  const useAuthStore = create<{
    accessToken: string | null;
    clear: () => void;
    setTokens: (t: string) => void;
  }>((set) => ({
    accessToken: null,
    clear: () => set({ accessToken: null }),
    setTokens: (t) => set({ accessToken: t }),
  }));
  return { useAuthStore };
});

vi.mock('@parkos/ui-kit/hooks', () => ({ REFRESH_INTERVAL_MS: 50 * 60 * 1000 }));

vi.mock('../../features/caja/api/sesionActivaApi', () => ({
  getSesionActiva: (...a: unknown[]) => getSesionActivaMock(...a),
  cerrarSesion: vi.fn(),
  SesionAlreadyClosedError: class extends Error {
    status = 409;
  },
}));

import { useAuthStore } from '@parkos/ui-kit/store';
import { useSesionActiva } from '../../features/caja/hooks/useSesionActiva';
import { SwrSessionScope } from './SwrSessionScope';

function Probe() {
  const { sesion } = useSesionActiva();
  return <span data-testid="sesion">{sesion ? (sesion as { uuid: string }).uuid : 'ninguna'}</span>;
}

const ui = (
  <SwrSessionScope>
    <Probe />
  </SwrSessionScope>
);

describe('SwrSessionScope (UX1)', () => {
  beforeEach(() => {
    getSesionActivaMock.mockReset();
    useAuthStore.setState({ accessToken: null });
  });

  it('after logout + login in the same tab the hook reads sesion/me again (no stale closed turno)', async () => {
    getSesionActivaMock.mockResolvedValueOnce({ uuid: 'sesion-cerrada' });
    act(() => useAuthStore.setState({ accessToken: 'tok-1' }));
    render(ui);
    await waitFor(() => expect(screen.getByTestId('sesion').textContent).toBe('sesion-cerrada'));
    expect(getSesionActivaMock).toHaveBeenCalledTimes(1);

    // "Finalizar y salir" (logoutAfterClose -> clear)
    act(() => useAuthStore.getState().clear());
    expect(screen.getByTestId('sesion').textContent).toBe('ninguna');

    // Log in again without reloading; backend now says: no active turno
    getSesionActivaMock.mockResolvedValueOnce(null);
    act(() => useAuthStore.setState({ accessToken: 'tok-2' }));

    await waitFor(() => expect(getSesionActivaMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId('sesion').textContent).toBe('ninguna'));
  });

  it('keeps the cache on a token refresh (non-null -> non-null)', async () => {
    getSesionActivaMock.mockResolvedValue({ uuid: 'sesion-1' });
    act(() => useAuthStore.setState({ accessToken: 'tok-1' }));
    render(ui);
    await waitFor(() => expect(screen.getByTestId('sesion').textContent).toBe('sesion-1'));

    act(() => useAuthStore.setState({ accessToken: 'tok-1-rotated' }));
    expect(screen.getByTestId('sesion').textContent).toBe('sesion-1');
  });
});
