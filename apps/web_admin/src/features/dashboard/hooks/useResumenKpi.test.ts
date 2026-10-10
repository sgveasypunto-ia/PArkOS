/**
 * `useResumenKpi` — unit tests for the cross-branch half of the
 * post-split dashboard data hooks. Sister file to
 * `useSucursalKpi.test.ts`.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

vi.mock('../api/dashboardApi', () => ({
  fetchSucursalDashboard: vi.fn(),
  fetchDashboardResumen: vi.fn(),
}));

import { fetchDashboardResumen } from '../api/dashboardApi';
import { useResumenKpi } from './useResumenKpi';
import type { DashboardResumen } from '../api/dashboardSchema';

const mockedResumen = fetchDashboardResumen as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, { value: { provider: (): never => new Map() as never } }, children);
}

const BRANCH_UUID = '11111111-1111-1111-1111-111111111111';
const OTHER_UUID = '22222222-2222-2222-2222-222222222222';

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
  mockedResumen.mockReset();
});

describe('useResumenKpi', () => {
  it('T1: maps the 6 cross-branch card states from /dashboard/resumen', async () => {
    mockedResumen.mockResolvedValueOnce(SAMPLE_RESUMEN);

    const { result } = renderHook(
      () => useResumenKpi([BRANCH_UUID, OTHER_UUID]),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.ocupacion.value?.porcentaje).toBe(40);
      expect(result.current.suscripciones.value).toBe(5);
      expect(result.current.mediosPago.value?.[0]?.monto_total).toBe(100000);
      expect(result.current.topSucursales.value?.[0]?.uuid_sucursal).toBe(OTHER_UUID);
      expect(result.current.sync.value?.sucursales_ok).toBe(1);
      expect(result.current.alertas.value?.[0]?.severity).toBe('critical');
      expect(result.current.ocupacionHoraria).toHaveLength(1);
      expect(result.current.resumen?.generado_en).toBe('2026-10-01T00:00:00');
    });

    expect(mockedResumen).toHaveBeenCalledWith([BRANCH_UUID, OTHER_UUID]);
  });

  it('T2: permitidas=[] -> no fetch, every card is undefined', () => {
    const { result } = renderHook(() => useResumenKpi([]), { wrapper });

    expect(result.current.ocupacion.value).toBeUndefined();
    expect(result.current.suscripciones.value).toBeUndefined();
    expect(result.current.topSucursales.value).toBeUndefined();
    expect(result.current.sync.value).toBeUndefined();
    expect(result.current.alertas.value).toBeUndefined();
    expect(result.current.resumen).toBeUndefined();
    expect(mockedResumen).not.toHaveBeenCalled();
  });

  it('T3: fetch failure surfaces error=true on every cross-branch card', async () => {
    mockedResumen.mockRejectedValueOnce(new Error('network down'));

    const { result } = renderHook(() => useResumenKpi([BRANCH_UUID]), { wrapper });

    await waitFor(() => {
      expect(result.current.ocupacion.error).toBe(true);
      expect(result.current.suscripciones.error).toBe(true);
      expect(result.current.topSucursales.error).toBe(true);
      expect(result.current.sync.error).toBe(true);
      expect(result.current.alertas.error).toBe(true);
    });
  });
});
