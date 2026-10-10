/**
 * `useSucursalKpi` — unit tests for the branch-scoped half of the
 * post-split dashboard data hooks.
 *
 * Mirrors the mocking style of the original `useKpiData.test.ts` (now
 * retired): mock the api transport module, render the hook under a
 * fresh (non-shared) `SWRConfig` cache, assert on the mapped card
 * states. Cross-branch behavior lives in `useResumenKpi.test.ts`.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

vi.mock('../api/dashboardApi', () => ({
  fetchSucursalDashboard: vi.fn(),
  fetchDashboardResumen: vi.fn(),
}));

import { fetchSucursalDashboard } from '../api/dashboardApi';
import { useSucursalKpi } from './useSucursalKpi';
import type { SucursalDashboard } from '../api/dashboardSchema';

const mockedBranch = fetchSucursalDashboard as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, { value: { provider: (): never => new Map() as never } }, children);
}

const BRANCH_UUID = '11111111-1111-1111-1111-111111111111';

const SAMPLE_BRANCH: SucursalDashboard = {
  uuid_sucursal: BRANCH_UUID,
  fecha: '2026-10-01T00:00:00',
  ingresos_count: 12,
  ingresos_monto_total: 450000,
  facturas_emitidas_count: 10,
  facturas_electronicas_count: 10,
  open_alertas_count: 1,
  sync_health: { last_sync_at: null, lag_seconds: null, queue_depth: 0 },
};

beforeEach(() => {
  mockedBranch.mockReset();
});

describe('useSucursalKpi', () => {
  it('T1: selected -> maps the 3 per-branch card states from /sucursales/{uuid}/dashboard', async () => {
    mockedBranch.mockResolvedValueOnce(SAMPLE_BRANCH);

    const { result } = renderHook(() => useSucursalKpi(BRANCH_UUID), { wrapper });

    await waitFor(() => {
      expect(result.current.ingresos.value).toBe(12);
      expect(result.current.facturas.value).toBe(10);
      expect(result.current.montoTotal.value).toBe(450000);
      expect(result.current.raw?.uuid_sucursal).toBe(BRANCH_UUID);
    });

    expect(mockedBranch).toHaveBeenCalledWith(BRANCH_UUID);
  });

  it('T2: selected=null -> no fetch, every card state is undefined / not loading-error', () => {
    const { result } = renderHook(() => useSucursalKpi(null), { wrapper });

    expect(result.current.ingresos.value).toBeUndefined();
    expect(result.current.facturas.value).toBeUndefined();
    expect(result.current.montoTotal.value).toBeUndefined();
    expect(result.current.raw).toBeUndefined();
    expect(mockedBranch).not.toHaveBeenCalled();
  });

  it('T3: fetch failure surfaces error=true on every per-branch card', async () => {
    mockedBranch.mockRejectedValueOnce(new Error('network down'));

    const { result } = renderHook(() => useSucursalKpi(BRANCH_UUID), { wrapper });

    await waitFor(() => {
      expect(result.current.ingresos.error).toBe(true);
      expect(result.current.facturas.error).toBe(true);
      expect(result.current.montoTotal.error).toBe(true);
    });
  });
});
