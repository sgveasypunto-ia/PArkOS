/**
 * `FacturaImpuestosTable.test.tsx` — HU-X.1b defense in depth (Bug #1
 * of the 2026-10-13 E2E report).
 *
 * Mirror of `FacturaItemsTable.test.tsx` for the tax-snapshot table.
 * Same client-side filter, same 4 scenarios.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FacturaImpuestosTable } from './FacturaImpuestosTable';
import type { FacturaImpuestoItem } from '../api/facturacionAdminApi';

const UUID_FACTURA = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const UUID_OTRA = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

function row(uuid: string, uuid_factura: string, valor: number): FacturaImpuestoItem {
  return {
    uuid,
    uuid_sucursal: null,
    uuid_factura,
    uuid_impuesto: '976ce0c8-8c1f-4f6d-af63-9d78a36b552d',
    base_calculo: 25210.08,
    porcentaje_aplicado: 0.19,
    valor,
  };
}

describe('FacturaImpuestosTable — X.1b client-side filter', () => {
  it('renders only rows whose uuid_factura matches the prop', () => {
    render(
      <FacturaImpuestosTable
        items={[
          row('imp-1', UUID_FACTURA, 4789.92),
          row('imp-2', UUID_OTRA, 99.99),
          row('imp-3', UUID_FACTURA, 100.0),
        ]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    expect(screen.getByTestId('factura-impuesto-row-imp-1')).toBeInTheDocument();
    expect(screen.getByTestId('factura-impuesto-row-imp-3')).toBeInTheDocument();
    expect(screen.queryByTestId('factura-impuesto-row-imp-2')).not.toBeInTheDocument();
  });

  it('renders the empty state when no rows match the prop', () => {
    render(
      <FacturaImpuestosTable
        items={[
          row('imp-1', UUID_OTRA, 99.99),
          row('imp-2', UUID_OTRA, 88.88),
        ]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    expect(screen.getByTestId('factura-impuestos-empty')).toBeInTheDocument();
    expect(screen.queryByTestId(/factura-impuesto-row-/)).not.toBeInTheDocument();
  });

  it('passes through when items is already correctly filtered by the server', () => {
    render(
      <FacturaImpuestosTable
        items={[row('imp-1', UUID_FACTURA, 4789.92)]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    expect(screen.getByTestId('factura-impuesto-row-imp-1')).toBeInTheDocument();
  });
});
