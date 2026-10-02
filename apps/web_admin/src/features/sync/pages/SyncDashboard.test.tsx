/**
 * `SyncDashboard.test.tsx` — component tests for HU-F19.2 (web_admin),
 * covering the component-test equivalents of the plan.md e2e scenarios
 * (heatmap with data, click -> drill-down to log filtered by that
 * sucursal, viewing a conflict's diff) plus the empty-state and the
 * "never recompute BR1 thresholds client-side" regression guard.
 *
 * Convention note (apply report): `apps/web_admin/e2e/` (Playwright) has
 * had zero new specs since HU-F15.2 despite F16-F19 all shipping, so
 * this follows that established Vitest/RTL-only convention instead of
 * adding a new Playwright spec (plan.md's task table names one, but the
 * actual repo convention for recent HUs does not).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement } from 'react';
import { SWRConfig } from 'swr';

const fetchSyncEstadoMock = vi.fn();
const fetchSyncLogMock = vi.fn();
const fetchSyncConflictMock = vi.fn();

vi.mock('../api/syncApi', async () => {
  const actual = (await vi.importActual('../api/syncApi')) as Record<string, unknown>;
  return {
    ...actual,
    fetchSyncEstado: (...args: unknown[]) => fetchSyncEstadoMock(...args),
    fetchSyncLog: (...args: unknown[]) => fetchSyncLogMock(...args),
    fetchSyncConflict: (...args: unknown[]) => fetchSyncConflictMock(...args),
  };
});

vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => ({
    sucursales: [
      { uuid: '11111111-1111-1111-1111-111111111111', nombre: 'Suc A' },
      { uuid: '22222222-2222-2222-2222-222222222222', nombre: 'Suc B' },
    ],
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  }),
}));

import SyncDashboard from './SyncDashboard';
import { SyncMissingSucursalContextError } from '../api/syncApi';

const SUC_A = '11111111-1111-1111-1111-111111111111';
const SUC_B = '22222222-2222-2222-2222-222222222222';

function estadoResponse(
  items: Array<{ uuid_sucursal: string; nombre: string; estado: 'verde' | 'amarillo' | 'rojo' }>,
) {
  return {
    items: items.map((i) => ({
      ...i,
      last_sync_at: '2026-09-30T10:00:00',
      lag_seconds: 10,
      queue_depth: 0,
    })),
    generado_en: '2026-09-30T10:00:05',
  };
}

function emptyLogResponse() {
  return { items: [], next_cursor: null };
}

function emptyConflictResponse() {
  return { items: [], next_cursor: null };
}

/** Fresh isolated SWR cache per render -- same convention as
 *  `Pairing.test.tsx` / `AdminUsuarioTable.test.tsx` -- so one test's
 *  resolved `sync:estado` key never leaks into the next test. */
function renderDashboard() {
  return render(
    createElement(
      SWRConfig,
      { value: { provider: (): never => new Map() as never, dedupingInterval: 0 } },
      createElement(SyncDashboard),
    ),
  );
}

describe('SyncDashboard', () => {
  it('T1: heatmap renders with sequential-opacity lag cells', async () => {
    fetchSyncEstadoMock.mockResolvedValue(
      estadoResponse([{ uuid_sucursal: SUC_A, nombre: 'Suc A', estado: 'verde' }]),
    );
    fetchSyncLogMock.mockResolvedValue({
      items: [
        {
          uuid: 'aaaaaaaa-0000-0000-0000-000000000001',
          fecha_retencion_hasta: '2026-09-30',
          created_at: '2026-09-30T09:00:10',
          created_by: null,
          sync_status: null,
          sync_timestamp: null,
          sync_attempts: null,
          uuid_sucursal: SUC_A,
          timestamp_evento: '2026-09-30T09:00:00',
          operaciones_enviadas: 5,
          operaciones_exitosas: 5,
          operaciones_fallidas: 0,
          conflictos: 0,
          duracion_ms: 120,
        },
      ],
      next_cursor: null,
    });
    fetchSyncConflictMock.mockResolvedValue(emptyConflictResponse());

    renderDashboard();

    await waitFor(() => {
      const cell = screen.getByTestId(`heatmap-cell-${SUC_A}-9`);
      expect(Number(cell.getAttribute('fill-opacity'))).toBeGreaterThan(0);
    });
  });

  it('T2: clicking a heatmap branch row drills down to the Log tab filtered by that sucursal', async () => {
    fetchSyncEstadoMock.mockResolvedValue(
      estadoResponse([{ uuid_sucursal: SUC_A, nombre: 'Suc A', estado: 'verde' }]),
    );
    fetchSyncLogMock.mockResolvedValue(emptyLogResponse());
    fetchSyncConflictMock.mockResolvedValue(emptyConflictResponse());

    const user = userEvent.setup();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByTestId(`heatmap-ocupacion-row-${SUC_A}`)).toBeInTheDocument();
    });
    await user.click(screen.getByTestId(`heatmap-ocupacion-row-${SUC_A}`));

    await waitFor(() => {
      expect(screen.getByTestId('sync-log-tab')).toBeInTheDocument();
    });
    const select = screen.getByTestId('sync-log-filter-sucursal') as HTMLSelectElement;
    expect(select.value).toBe(SUC_A);
  });

  it('T3: viewing a conflict shows datos_local vs datos_cloud side by side', async () => {
    fetchSyncEstadoMock.mockResolvedValue(
      estadoResponse([{ uuid_sucursal: SUC_A, nombre: 'Suc A', estado: 'verde' }]),
    );
    fetchSyncLogMock.mockResolvedValue(emptyLogResponse());
    fetchSyncConflictMock.mockResolvedValue({
      items: [
        {
          uuid: 'cccccccc-0000-0000-0000-000000000001',
          created_at: '2026-09-30T09:00:00',
          created_by: null,
          sync_status: null,
          sync_timestamp: null,
          sync_attempts: null,
          fecha_retencion_hasta: '2026-09-30',
          uuid_sucursal: SUC_A,
          tabla: 'factura_pagos',
          uuid_registro: 'dddddddd-0000-0000-0000-000000000001',
          datos_local: { monto: 100 },
          datos_cloud: { monto: 200 },
          politica: 'last-write-wins',
          resolucion: 'cloud_wins',
          timestamp_evento: '2026-09-30T09:00:00',
        },
      ],
      next_cursor: null,
    });

    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByTestId('sync-tab-conflictos'));
    const row = await screen.findByTestId('sync-conflict-row-cccccccc-0000-0000-0000-000000000001');
    await user.click(
      within(row).getByTestId('sync-conflict-ver-diff-cccccccc-0000-0000-0000-000000000001'),
    );

    const diff = screen.getByTestId(
      'sync-conflict-diff-cccccccc-0000-0000-0000-000000000001',
    );
    expect(within(diff).getByText(/"monto": 100/)).toBeInTheDocument();
    expect(within(diff).getByText(/"monto": 200/)).toBeInTheDocument();
  });

  it('T4: empty state shows "Sin sucursales sincronizando aún" instead of the heatmap', async () => {
    fetchSyncEstadoMock.mockRejectedValue(new SyncMissingSucursalContextError());
    fetchSyncLogMock.mockResolvedValue(emptyLogResponse());
    fetchSyncConflictMock.mockResolvedValue(emptyConflictResponse());

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByTestId('sync-dashboard-empty')).toHaveTextContent(
        'Sin sucursales sincronizando aún',
      );
    });
    expect(screen.queryByTestId('sync-heatmap-section')).not.toBeInTheDocument();
  });

  it('T5: resumen counts render the server estado verbatim (no client-side BR1 recompute)', async () => {
    fetchSyncEstadoMock.mockResolvedValue(
      estadoResponse([
        { uuid_sucursal: SUC_A, nombre: 'Suc A', estado: 'verde' },
        { uuid_sucursal: SUC_B, nombre: 'Suc B', estado: 'rojo' },
      ]),
    );
    fetchSyncLogMock.mockResolvedValue(emptyLogResponse());
    fetchSyncConflictMock.mockResolvedValue(emptyConflictResponse());

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByTestId('sync-resumen-verde')).toHaveTextContent('1');
    });
    expect(screen.getByTestId('sync-resumen-amarillo')).toHaveTextContent('0');
    expect(screen.getByTestId('sync-resumen-rojo')).toHaveTextContent('1');
  });
});
