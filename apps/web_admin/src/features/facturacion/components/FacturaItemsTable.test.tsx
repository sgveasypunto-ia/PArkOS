/**
 * `FacturaItemsTable.test.tsx` — HU-X.1b defense in depth (Bug #1 of
 * the 2026-10-13 E2E report).
 *
 * Verifies the client-side filter: even if the server misbehaves and
 * returns detalle rows for OTHER facturas in the same response, the
 * table only renders rows whose `uuid_factura` matches the prop.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FacturaItemsTable } from './FacturaItemsTable';
import type { FacturaDetalleItem } from '../api/facturacionAdminApi';

const UUID_FACTURA = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const UUID_OTRA = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

function row(uuid: string, uuid_factura: string, concepto: string): FacturaDetalleItem {
  return {
    uuid,
    uuid_sucursal: null,
    uuid_factura,
    tipo: 'servicio',
    concepto,
    cantidad: 1,
    valor_unitario: 1000,
    subtotal: 1000,
  };
}

describe('FacturaItemsTable — X.1b client-side filter', () => {
  it('renders only rows whose uuid_factura matches the prop', () => {
    render(
      <FacturaItemsTable
        items={[
          row('row-1', UUID_FACTURA, 'Estadia 16 min carro ABC123'),
          row('row-2', UUID_OTRA, 'Estadia 3 min MNO34B (NO DEBE APARECER)'),
          row('row-3', UUID_FACTURA, 'Recargo nocturno'),
        ]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    // Two rows of THIS factura, both rendered.
    expect(screen.getByTestId('factura-item-row-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('factura-item-row-row-3')).toBeInTheDocument();
    expect(screen.queryByTestId('factura-item-row-row-2')).not.toBeInTheDocument();
    // The concept string of the foreign row is NOT in the document.
    expect(screen.queryByText(/NO DEBE APARECER/)).not.toBeInTheDocument();
  });

  it('renders the empty state when no rows match the prop', () => {
    render(
      <FacturaItemsTable
        items={[
          row('row-1', UUID_OTRA, 'Foreign row'),
          row('row-2', UUID_OTRA, 'Another foreign row'),
        ]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    expect(screen.getByTestId('factura-items-empty')).toBeInTheDocument();
    expect(screen.queryByTestId(/factura-item-row-/)).not.toBeInTheDocument();
  });

  it('passes through when items is already correctly filtered by the server', () => {
    // Backward-compat: if the server is doing its job (X.1b) the
    // client-side filter is a no-op and the rows render as-is.
    render(
      <FacturaItemsTable
        items={[row('row-1', UUID_FACTURA, 'Estadia')]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    expect(screen.getByTestId('factura-item-row-row-1')).toBeInTheDocument();
  });

  it('matches string-typed uuid_factura (the API may return a uuid.UUID object)', () => {
    // The contract: `String(row.uuid_factura) === uuidFactura`. Use a
    // string `uuid_factura` field on the row to confirm the coercion
    // path; the production response from pydantic serialises UUIDs
    // as strings but defense matters if a future refactor changes
    // that.
    const rowAsObj: FacturaDetalleItem = {
      uuid: 'row-1',
      uuid_sucursal: null,
      uuid_factura: UUID_FACTURA,
      tipo: 'servicio',
      concepto: 'Estadia',
      cantidad: 1,
      valor_unitario: 1000,
      subtotal: 1000,
    };
    render(
      <FacturaItemsTable
        items={[rowAsObj]}
        isLoading={false}
        error={null}
        onRetry={vi.fn()}
        uuidFactura={UUID_FACTURA}
      />,
    );

    expect(screen.getByTestId('factura-item-row-row-1')).toBeInTheDocument();
  });
});
