/**
 * `AlertasBadge.test.tsx` -- HU-F19.5 nav counter.
 *
 *  - T1: unauthenticated -> renders nothing (no fetch attempted).
 *  - T2: sums `abierta` + `en_revision` pages, scoped to the actor's
 *    permitted sucursales (a row outside that set is NOT counted).
 *  - T3: a non-null `next_cursor` on either page renders "N+" (honest
 *    undercount), not a fabricated exact total.
 *  - T4: count 0 -> renders nothing (no empty badge clutter).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';

const useAdminAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAdminAuthMock(),
}));

vi.mock('@/features/alertas/api/alertasApi', () => ({
  fetchAlertas: vi.fn(),
}));

import { fetchAlertas } from '@/features/alertas/api/alertasApi';
import { AlertasBadge } from './AlertasBadge';

const mockedFetch = fetchAlertas as ReturnType<typeof vi.fn>;

const SUC_A = '22222222-2222-2222-2222-222222222222';
const SUC_B = '33333333-3333-3333-3333-333333333333';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    createElement(MemoryRouter, null, children),
  );
}

function page(items: Array<{ uuid_sucursal: string | null }>, nextCursor: string | null = null) {
  return { items, next_cursor: nextCursor };
}

describe('AlertasBadge', () => {
  it('T1: unauthenticated renders nothing and never fetches', () => {
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [], isAuthenticated: false });
    render(<AlertasBadge />, { wrapper });
    expect(screen.queryByTestId('alertas-badge')).not.toBeInTheDocument();
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it('T2: sums abierta + en_revision scoped to permitted sucursales', async () => {
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [SUC_A], isAuthenticated: true });
    mockedFetch.mockImplementation(async (query: { estado: string }) => {
      if (query.estado === 'abierta') {
        return page([{ uuid_sucursal: SUC_A }, { uuid_sucursal: SUC_B }]); // SUC_B is NOT permitted
      }
      return page([{ uuid_sucursal: SUC_A }]);
    });

    render(<AlertasBadge />, { wrapper });

    expect(await screen.findByTestId('alertas-badge')).toHaveTextContent('2');
  });

  it('T3: a non-null next_cursor renders "N+"', async () => {
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [SUC_A], isAuthenticated: true });
    mockedFetch.mockImplementation(async (query: { estado: string }) => {
      if (query.estado === 'abierta') return page([{ uuid_sucursal: SUC_A }], 'opaque-cursor');
      return page([]);
    });

    render(<AlertasBadge />, { wrapper });

    expect(await screen.findByTestId('alertas-badge')).toHaveTextContent('1+');
  });

  it('T4: count 0 renders nothing', async () => {
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [SUC_A], isAuthenticated: true });
    mockedFetch.mockResolvedValue(page([]));

    render(<AlertasBadge />, { wrapper });

    await waitFor(() => expect(mockedFetch).toHaveBeenCalled());
    expect(screen.queryByTestId('alertas-badge')).not.toBeInTheDocument();
  });
});
