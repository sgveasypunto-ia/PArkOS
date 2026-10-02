/**
 * `AlertasTable.test.tsx` -- HU-F19.5 BR3 + BR4 UI contract.
 *
 *  - T1: a unique tuple renders as a plain row, no group header.
 *  - T2 (BR3): a repeated `(tipo_alerta, uuid_sucursal, día)` tuple
 *    renders ONE collapsed-by-default group header with a count badge;
 *    its rows are not in the document until expanded, and expanding
 *    reveals every one of them -- none dropped.
 *  - T3 (BR4): `severity: null` renders "—", not an error.
 *  - T4: row click calls `onOpen` with that exact alerta.
 *  - T5: empty state renders when there are no items.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AlertasTable } from './AlertasTable';
import type { AlertaRead } from '../api/alertasSchema';

function alerta(overrides: Partial<AlertaRead>): AlertaRead {
  return {
    uuid: '11111111-1111-1111-1111-111111111111',
    fecha_retencion_hasta: '2027-09-01',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_usuario: null,
    uuid_arqueo: null,
    tipo_alerta: 'descuadre_critico',
    valor_diferencia_efectivo: '1500.00',
    valor_diferencia_datafono: null,
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'abierta',
    severity: 'critical',
    ...overrides,
  };
}

describe('AlertasTable', () => {
  it('T1: a unique tuple renders as a plain row (no group header)', () => {
    render(
      <AlertasTable
        items={[alerta({ uuid: 'a' })]}
        isLoading={false}
        hasMore={false}
        onLoadMore={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByTestId('alertas-row-a')).toBeInTheDocument();
    expect(screen.queryByText(/alertas-group-/)).not.toBeInTheDocument();
  });

  it('T2 (BR3): a repeated tuple groups under one collapsed header; expanding reveals every row', async () => {
    const user = userEvent.setup();
    const items = [alerta({ uuid: 'a' }), alerta({ uuid: 'b' }), alerta({ uuid: 'c' })];
    render(
      <AlertasTable items={items} isLoading={false} hasMore={false} onLoadMore={vi.fn()} onOpen={vi.fn()} />,
    );

    // Collapsed by default: individual rows not yet in the document.
    expect(screen.queryByTestId('alertas-row-a')).not.toBeInTheDocument();
    expect(screen.queryByTestId('alertas-row-b')).not.toBeInTheDocument();
    expect(screen.queryByTestId('alertas-row-c')).not.toBeInTheDocument();

    const groupKey = 'descuadre_critico|22222222-2222-2222-2222-222222222222|2026-09-01';
    const toggle = screen.getByTestId(`alertas-group-toggle-${groupKey}`);
    expect(screen.getByTestId(`alertas-group-count-${groupKey}`)).toHaveTextContent('3');

    await user.click(toggle);

    // Expanded: none of the 3 rows were dropped.
    expect(screen.getByTestId('alertas-row-a')).toBeInTheDocument();
    expect(screen.getByTestId('alertas-row-b')).toBeInTheDocument();
    expect(screen.getByTestId('alertas-row-c')).toBeInTheDocument();
  });

  it('T3 (BR4): severity: null renders "—"', () => {
    render(
      <AlertasTable
        items={[alerta({ uuid: 'a', severity: null })]}
        isLoading={false}
        hasMore={false}
        onLoadMore={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByTestId('severity-badge-none')).toHaveTextContent('—');
  });

  it('T4: clicking "Ver detalle" calls onOpen with that exact alerta', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const item = alerta({ uuid: 'a' });
    render(
      <AlertasTable items={[item]} isLoading={false} hasMore={false} onLoadMore={vi.fn()} onOpen={onOpen} />,
    );
    await user.click(screen.getByTestId('alertas-row-open-a'));
    expect(onOpen).toHaveBeenCalledWith(item);
  });

  it('T5: renders the empty state when there are no items', () => {
    render(
      <AlertasTable items={[]} isLoading={false} hasMore={false} onLoadMore={vi.fn()} onOpen={vi.fn()} />,
    );
    expect(screen.getByTestId('alertas-empty')).toBeInTheDocument();
  });
});
