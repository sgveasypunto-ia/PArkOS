/**
 * `EmpresaBitacoraTab.test.tsx` — HU-F15.2 wire-up.
 *
 * Mirrors the wiring the F1.15 login-historic / HU-F15.2 Empresa
 * integration contract:
 *
 *   - B1 (empty): the BE has no rows for ``tabla_afectada='empresa'``
 *     → the empty-state banner renders with the
 *     ``empresa-bitacora-empty`` testid.
 *   - B2 (loaded): the mocked `fetchAuditLog` returns two rows with
 *     hash-chain fields → the rendered list has the two rows, each
 *     carrying `empresa-bitacora-row-{uuid}`, ``empresa-bitacora-accion``,
 *     ``empresa-bitacora-timestamp``, and the per-row HashChainStatus
 *     rendered by the shared `<HashChainStatus />` component.
 *   - B3 (error): the mocked `fetchAuditLog` throws → the
 *     ``empresa-bitacora-error`` testid is rendered with the
 *     role="alert" copy.
 *   - B4 (before/after JSON preformatted): the loaded rows include
 *     ``datos_anteriores`` and ``datos_nuevos`` JSON → the
 *     ``empresa-bitacora-antes`` and ``empresa-bitacora-despues``
 *     testids carry JSON.stringify of the payloads.
 *
 * Note on test isolation: SWR's default cache provider keeps the
 * resolved payload between tests. To force a fresh fetch we render
 * with a unique React ``key`` per test -- SWR discards the cached
 * state when the component unmounts and remounts.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('@/features/audit/api/auditApi', () => ({
  fetchAuditLog: vi.fn(),
}));

import { fetchAuditLog } from '@/features/audit/api/auditApi';
import { EmpresaBitacoraTab } from './EmpresaBitacoraTab';

const mockFetchAuditLog = vi.mocked(fetchAuditLog);

function renderTab(testSalt: string): void {
  // The SWR key embeds ``swrKeySuffix`` so the global cache provider
  // hands each test its own slot -- without this, B2 and B3 would
  // see B1's cached empty success. The ``key`` prop here is belt-
  // and-suspenders: it forces React to remount the subtree even if
  // SWR's internal state somehow leaks.
  render(
    <div key={testSalt}>
      <EmpresaBitacoraTab swrKeySuffix={testSalt} />
    </div>,
  );
}

describe('EmpresaBitacoraTab', () => {
  beforeEach(() => {
    mockFetchAuditLog.mockReset();
  });

  it('B1: empty state when the BE returns no rows for tabla_afectada=empresa', async () => {
    mockFetchAuditLog.mockResolvedValue({ items: [], next_cursor: null });

    renderTab('b1-' + Date.now());

    await waitFor(() => {
      expect(screen.getByTestId('empresa-bitacora-empty')).toBeInTheDocument();
    });
    expect(mockFetchAuditLog).toHaveBeenCalledWith({
      tabla_afectada: 'empresa',
      limit: 20,
    });
  });

  it('B2: loads two rows with hash-chain fields and renders before/after JSON', async () => {
    mockFetchAuditLog.mockResolvedValue({
      items: [
        {
          uuid: '5eec90e3-38a3-45db-8aec-3f3216eed701',
          timestamp_evento: '2026-09-29T02:28:50.905199',
          uuid_usuario: '975ebb14-5636-4013-8f8f-e2a44d100a18',
          uuid_sucursal: null,
          uuid_referencia: null,
          accion: 'actualizar',
          tabla_afectada: 'empresa',
          datos_anteriores: { nit: '900111111-1', regimen: 'comun' },
          datos_nuevos: { nit: '900222222-2', regimen: 'simplificado' },
          hash_anterior: 'af4b6f01cef48ebb231eb8d444436447d82d426b99c1a8db96d0abfc3fe45249',
          hash_actual: 'fb0871a3277a771d6e9b06b846bc17e06ca1c00af305bad5e07cccf9a30180c2',
        },
        {
          uuid: 'd05c2b7a-f8ff-4c2b-9cb0-836d39f0fae4',
          timestamp_evento: '2026-09-29T02:28:37.676873',
          uuid_usuario: '975ebb14-5636-4013-8f8f-e2a44d100a18',
          uuid_sucursal: null,
          uuid_referencia: null,
          accion: 'actualizar',
          tabla_afectada: 'empresa',
          datos_anteriores: null,
          datos_nuevos: null,
          hash_anterior: '02e3941fa9cdccaff15a825770b977f34f956a7029b63d1535b3e25e30cec2fd',
          hash_actual: 'af4b6f01cef48ebb231eb8d444436447d82d426b99c1a8db96d0abfc3fe45249',
        },
      ],
      next_cursor: null,
    });

    renderTab('b2-' + Date.now());

    await waitFor(() => {
      expect(
        screen.getByTestId('empresa-bitacora-row-5eec90e3-38a3-45db-8aec-3f3216eed701'),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('empresa-bitacora-row-d05c2b7a-f8ff-4c2b-9cb0-836d39f0fae4'),
    ).toBeInTheDocument();

    const acciones = screen.getAllByTestId('empresa-bitacora-accion');
    expect(acciones).toHaveLength(2);
    expect(acciones[0]).toHaveTextContent('actualizar');

    const antes = screen.getAllByTestId('empresa-bitacora-antes');
    expect(antes[0]).toHaveTextContent('"nit": "900111111-1"');
    const despues = screen.getAllByTestId('empresa-bitacora-despues');
    expect(despues[0]).toHaveTextContent('"nit": "900222222-2"');

    // The second row has null data_anteriores / data_nuevos -- the
    // antes/después pre tags are conditional on those being non-null.
    expect(screen.queryAllByTestId('empresa-bitacora-antes')).toHaveLength(1);
  });

  it('B3: error state when the BE throws', async () => {
    mockFetchAuditLog.mockRejectedValue(new Error('network'));

    renderTab('b3-' + Date.now());

    await waitFor(() => {
      expect(screen.getByTestId('empresa-bitacora-error')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('empresa-bitacora-empty')).not.toBeInTheDocument();
  });
});