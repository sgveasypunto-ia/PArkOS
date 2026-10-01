/**
 * `ArqueosList.test.tsx` -- HU-F18.2 list rendering tests.
 *
 * Validates the table renderer + empty state + load-more trigger +
 * row-click callback. Mocks no SWR; the list is pure.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ArqueosList } from './ArqueosList';
import type { ArqueoRead } from '../api/arqueosSchema';

function makeRow(uuid: string, sucursal: string | null = 's1'): ArqueoRead {
  return {
    uuid,
    created_at: '2026-10-01T12:00:00',
    created_by: null,
    sync_status: 'sincronizado',
    sync_timestamp: null,
    sync_attempts: 0,
    fecha_retencion_hasta: '2026-10-01',
    uuid_sucursal: sucursal,
    uuid_tipo_arqueo: 't1',
    uuid_sesion: null,
    valor_efectivo_esperado: '100',
    valor_datafono_esperado: '50',
    valor_efectivo_reportado: '100',
    valor_datafono_reportado: '50',
  };
}

describe('ArqueosList', () => {
  it('renders empty state when items=[] and isLoading=false', () => {
    render(
      <ArqueosList
        items={[]}
        isLoading={false}
        hasMore={false}
        isLoadingMore={false}
        onLoadMore={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('arqueos-list-empty')).toBeInTheDocument();
  });

  it('renders one row per item', () => {
    const items = [makeRow('a1'), makeRow('a2')];
    render(
      <ArqueosList
        items={items}
        isLoading={false}
        hasMore={false}
        isLoadingMore={false}
        onLoadMore={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId('arqueos-list-row-a1')).toBeInTheDocument();
    expect(screen.getByTestId('arqueos-list-row-a2')).toBeInTheDocument();
  });

  it('opens detail on row click', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <ArqueosList
        items={[makeRow('a1')]}
        isLoading={false}
        hasMore={false}
        isLoadingMore={false}
        onLoadMore={vi.fn()}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByTestId('arqueos-list-row-open-a1'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]?.[0]?.uuid).toBe('a1');
  });

  it('renders the load-more button when hasMore=true', async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();
    render(
      <ArqueosList
        items={[makeRow('a1')]}
        isLoading={false}
        hasMore={true}
        isLoadingMore={false}
        onLoadMore={onLoadMore}
        onSelect={vi.fn()}
      />,
    );
    const btn = screen.getByTestId('arqueos-list-load-more');
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it('omits the load-more button when hasMore=false', () => {
    render(
      <ArqueosList
        items={[makeRow('a1')]}
        isLoading={false}
        hasMore={false}
        isLoadingMore={false}
        onLoadMore={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('arqueos-list-load-more')).not.toBeInTheDocument();
  });
});