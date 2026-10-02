import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DianQueueTable } from './DianQueueTable';
import { canRetryEnvioDian } from '../lib/canRetryEnvioDian';
import type { EnvioDianRead } from '../api/envioDianSchema';

function envio(overrides: Partial<EnvioDianRead> = {}): EnvioDianRead {
  return {
    uuid: '11111111-1111-1111-1111-111111111111',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_factura_electronica: '33333333-3333-3333-3333-333333333333',
    uuid_resolucion_facturacion: null,
    payload: null,
    respuesta_proveedor: null,
    cufe: null,
    uuid_envio_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'pendiente',
    ...overrides,
  };
}

describe('canRetryEnvioDian', () => {
  it('is true only for a rechazado envio with a known factura electronica', () => {
    expect(canRetryEnvioDian(envio({ estado: 'rechazado' }))).toBe(true);
    expect(canRetryEnvioDian(envio({ estado: 'pendiente' }))).toBe(false);
    expect(canRetryEnvioDian(envio({ estado: 'aceptado' }))).toBe(false);
    expect(
      canRetryEnvioDian(envio({ estado: 'rechazado', uuid_factura_electronica: null })),
    ).toBe(false);
  });
});

describe('DianQueueTable', () => {
  it('renders the empty state when there are no items', () => {
    render(
      <DianQueueTable
        items={[]}
        isLoading={false}
        hasMore={false}
        onLoadMore={() => {}}
        onOpen={() => {}}
        onRetry={() => {}}
        isRetrying={() => false}
      />,
    );
    expect(screen.getByTestId('dian-empty')).toBeInTheDocument();
  });

  it('disables the retry button for a non-rechazado row', () => {
    const item = envio({ estado: 'pendiente' });
    render(
      <DianQueueTable
        items={[item]}
        isLoading={false}
        hasMore={false}
        onLoadMore={() => {}}
        onOpen={() => {}}
        onRetry={() => {}}
        isRetrying={() => false}
      />,
    );
    expect(screen.getByTestId(`dian-row-retry-${item.uuid}`)).toBeDisabled();
  });

  it('enables the retry button for a rechazado row and disables it synchronously on click', async () => {
    const user = userEvent.setup();
    const item = envio({ estado: 'rechazado' });
    const onRetry = vi.fn();
    const retrying = new Set<string>();

    const { rerender } = render(
      <DianQueueTable
        items={[item]}
        isLoading={false}
        hasMore={false}
        onLoadMore={() => {}}
        onOpen={() => {}}
        onRetry={(envioRow) => {
          onRetry(envioRow);
          // Mirrors `useRetryEnvioDian.trigger`: mark BEFORE any await
          // resolves, then force a re-render with the updated predicate.
          retrying.add(envioRow.uuid_factura_electronica as string);
          rerender(
            <DianQueueTable
              items={[item]}
              isLoading={false}
              hasMore={false}
              onLoadMore={() => {}}
              onOpen={() => {}}
              onRetry={onRetry}
              isRetrying={(uuid) => retrying.has(uuid)}
            />,
          );
        }}
        isRetrying={(uuid) => retrying.has(uuid)}
      />,
    );

    const button = screen.getByTestId(`dian-row-retry-${item.uuid}`);
    expect(button).toBeEnabled();

    await user.click(button);

    expect(onRetry).toHaveBeenCalledWith(item);
    expect(screen.getByTestId(`dian-row-retry-${item.uuid}`)).toBeDisabled();
    expect(screen.getByTestId(`dian-row-retry-${item.uuid}`)).toHaveTextContent('Reintentando');
  });

  it('calls onLoadMore when "Cargar más" is clicked', async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();
    render(
      <DianQueueTable
        items={[envio()]}
        isLoading={false}
        hasMore
        onLoadMore={onLoadMore}
        onOpen={() => {}}
        onRetry={() => {}}
        isRetrying={() => false}
      />,
    );
    await user.click(screen.getByTestId('dian-load-more'));
    expect(onLoadMore).toHaveBeenCalledOnce();
  });
});
