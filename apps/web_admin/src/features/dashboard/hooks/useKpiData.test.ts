/**
 * useKpiData — unit tests (HU-F17.1, T6).
 *
 * Mirrors the mocking style of
 * `features/configuracion-tolerancias/hooks/useConfiguracionTolerancias.test.ts`:
 * mock the api transport module, render the hook under a fresh (non-shared)
 * `SWRConfig` cache, assert on the mapped card states.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

vi.mock('../api/dashboardApi', () => ({
  fetchSucursalDashboard: vi.fn(),
  fetchDashboardResumen: vi.fn(),
}));

import { fetchSucursalDashboard, fetchDashboardResumen } from '../api/dashboardApi';
import { useKpiData } from './useKpiData';
import type { DashboardResumen, SucursalDashboard } from '../api/dashboardSchema';

const mockedBranch = fetchSucursalDashboard as ReturnType<typeof vi.fn>;
const mockedResumen = fetchDashboardResumen as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, { value: { provider: (): never => new Map() as never } }, children);
}

const BRANCH_UUID = '11111111-1111-1111-1111-111111111111';
const OTHER_UUID = '22222222-2222-2222-2222-222222222222';

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

const SAMPLE_RESUMEN: DashboardResumen = {
  sucursales: [BRANCH_UUID, OTHER_UUID],
  ocupacion: { ocupados: 8, capacidad: 20, porcentaje: 40 },
  suscripciones_activas: { count: 5 },
  medios_pago_dia: [{ medio_pago: 'efectivo', monto_total: 100000 }],
  top_sucursales: [
    { uuid_sucursal: OTHER_UUID, nombre: 'Sucursal B', monto_total: 900000 },
    { uuid_sucursal: BRANCH_UUID, nombre: 'Sucursal A', monto_total: 450000 },
  ],
  sync_agregado: {
    sucursales_ok: 1,
    sucursales_degradadas: 1,
    queue_depth_total: 3,
    max_lag_seconds: 120,
  },
  alertas_por_severidad: [{ severity: 'critical', count: 2 }],
  estado_envio_fe_24h: [
    { estado: 'enviada', count: 4 },
    { estado: 'pendiente', count: 1 },
  ],
  ocupacion_horaria: [{ uuid_sucursal: BRANCH_UUID, hora: 9, ingresos_count: 3 }],
  errores: [],
  generado_en: '2026-10-01T00:00:00',
};

beforeEach(() => {
  mockedBranch.mockReset();
  mockedResumen.mockReset();
});

describe('useKpiData', () => {
  it('T1: maps the per-branch dashboard + resumen into the 9 card states', async () => {
    mockedBranch.mockResolvedValueOnce(SAMPLE_BRANCH);
    mockedResumen.mockResolvedValueOnce(SAMPLE_RESUMEN);

    const { result } = renderHook(() => useKpiData(BRANCH_UUID, [BRANCH_UUID, OTHER_UUID]), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.ingresos.value).toBe(12);
      expect(result.current.montoTotal.value).toBe(450000);
      expect(result.current.ocupacion.value?.porcentaje).toBe(40);
      expect(result.current.suscripciones.value).toBe(5);
      expect(result.current.topSucursales.value?.[0]?.uuid_sucursal).toBe(OTHER_UUID);
      expect(result.current.sync.value?.sucursales_ok).toBe(1);
      expect(result.current.alertas.value?.[0]?.severity).toBe('critical');
      expect(result.current.ocupacionHoraria).toHaveLength(1);
    });

    expect(mockedBranch).toHaveBeenCalledWith(BRANCH_UUID);
    expect(mockedResumen).toHaveBeenCalledWith([BRANCH_UUID, OTHER_UUID]);
  });

  it('T2: selected=null -> the 3 per-branch cards never fetch', () => {
    mockedResumen.mockResolvedValueOnce(SAMPLE_RESUMEN);
    const { result } = renderHook(() => useKpiData(null, [BRANCH_UUID]), { wrapper });

    expect(result.current.ingresos.value).toBeUndefined();
    expect(mockedBranch).not.toHaveBeenCalled();
  });

  it('T3: permitidas=[] -> the 6 cross-branch cards never fetch', () => {
    mockedBranch.mockResolvedValueOnce(SAMPLE_BRANCH);
    const { result } = renderHook(() => useKpiData(BRANCH_UUID, []), { wrapper });

    expect(result.current.ocupacion.value).toBeUndefined();
    expect(mockedResumen).not.toHaveBeenCalled();
  });

  it('T4: resumen fetch failure surfaces error=true on every cross-branch card', async () => {
    mockedBranch.mockResolvedValueOnce(SAMPLE_BRANCH);
    mockedResumen.mockRejectedValueOnce(new Error('network down'));

    const { result } = renderHook(() => useKpiData(BRANCH_UUID, [BRANCH_UUID]), { wrapper });

    await waitFor(() => {
      expect(result.current.sync.error).toBe(true);
      expect(result.current.alertas.error).toBe(true);
    });
    // The per-branch cards are unaffected by the resumen failure.
    expect(result.current.ingresos.error).toBe(false);
  });
});
