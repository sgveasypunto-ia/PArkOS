/**
 * `ClienteFacturasTab.test.tsx` — cross-branch read-only facturas view
 * (HU-F20.1), mocked at `fetchReporteriaFacturas`.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { UUID_CLIENTE, UUID_FACTURA } = vi.hoisted(() => ({
  UUID_CLIENTE: '11111111-1111-1111-1111-111111111111',
  UUID_FACTURA: '22222222-2222-2222-2222-222222222222',
}));

vi.mock('@/features/reporteria/api/reporteriaApi', () => ({
  fetchReporteriaFacturas: vi.fn().mockResolvedValue({
    uuid_sucursal: null,
    desde: '2026-01-01',
    hasta: '2026-01-31',
    items: [
      {
        uuid: UUID_FACTURA,
        uuid_sucursal: 'suc-norte',
        created_at: '2026-01-15T00:00:00Z',
        numero_completo: 'FV-001',
        subtotal: 100,
        descuento: 0,
        iva: 19,
        total: 119,
        estado: 'vigente',
      },
    ],
    next_cursor: null,
    generado_en: '2026-01-31T00:00:00Z',
  }),
}));

import { fetchReporteriaFacturas } from '@/features/reporteria/api/reporteriaApi';
import { ClienteFacturasTab } from './ClienteFacturasTab';

describe('<ClienteFacturasTab />', () => {
  it('calls fetchReporteriaFacturas with uuid_cliente only (no uuid_sucursal)', async () => {
    render(<ClienteFacturasTab uuidCliente={UUID_CLIENTE} />);

    await waitFor(() => {
      expect(screen.getByTestId(`cliente-factura-row-${UUID_FACTURA}`)).toBeInTheDocument();
    });

    expect(fetchReporteriaFacturas).toHaveBeenCalledWith(
      expect.objectContaining({ uuid_cliente: UUID_CLIENTE }),
    );
    const callArgs = vi.mocked(fetchReporteriaFacturas).mock.calls[0]?.[0];
    expect(callArgs).not.toHaveProperty('uuid_sucursal');
  });

  it('renders the per-row uuid_sucursal column since rows can span branches', async () => {
    render(<ClienteFacturasTab uuidCliente={UUID_CLIENTE} />);

    await waitFor(() => {
      expect(screen.getByText('suc-norte')).toBeInTheDocument();
    });
  });
});
