/**
 * `ClienteBitacoraTab.test.tsx` — HU-F20.1. Confirms the (documented,
 * intentional) fallback: `fetchAuditLog` is called with
 * `tabla_afectada: 'clientes'` only -- NOT filtered by `uuidCliente`,
 * since the backend has no way to do that today (see the component's
 * own docblock).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { UUID_CLIENTE, UUID_ROW } = vi.hoisted(() => ({
  UUID_CLIENTE: '11111111-1111-1111-1111-111111111111',
  UUID_ROW: '22222222-2222-2222-2222-222222222222',
}));

vi.mock('@/features/audit/api/auditApi', () => ({
  fetchAuditLog: vi.fn().mockResolvedValue({
    items: [
      {
        uuid: UUID_ROW,
        timestamp_evento: '2026-01-15T00:00:00Z',
        uuid_usuario: null,
        accion: 'actualizar',
        hash_anterior: 'a'.repeat(64),
        hash_actual: 'b'.repeat(64),
      },
    ],
    next_cursor: null,
  }),
}));

import { fetchAuditLog } from '@/features/audit/api/auditApi';
import { ClienteBitacoraTab } from './ClienteBitacoraTab';

describe('<ClienteBitacoraTab />', () => {
  it('fetches tabla_afectada=clientes unfiltered by uuidCliente', async () => {
    render(<ClienteBitacoraTab uuidCliente={UUID_CLIENTE} />);

    await waitFor(() => {
      expect(screen.getByTestId(`cliente-bitacora-row-${UUID_ROW}`)).toBeInTheDocument();
    });

    expect(fetchAuditLog).toHaveBeenCalledWith(
      expect.objectContaining({ tabla_afectada: 'clientes' }),
    );
    const callArgs = vi.mocked(fetchAuditLog).mock.calls[0]?.[0];
    expect(callArgs).not.toHaveProperty('uuid_cliente');
    expect(callArgs).not.toHaveProperty('uuid_sucursal');
  });

  it('shows the empty state when there are no rows', async () => {
    vi.mocked(fetchAuditLog).mockResolvedValueOnce({ items: [], next_cursor: null });
    render(<ClienteBitacoraTab uuidCliente="other-cliente-uuid" />);

    await waitFor(() => {
      expect(screen.getByTestId('cliente-bitacora-empty')).toBeInTheDocument();
    });
  });
});
