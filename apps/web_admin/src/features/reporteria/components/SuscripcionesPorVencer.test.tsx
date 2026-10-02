/**
 * `<SuscripcionesPorVencer />` — unit tests (HU-F17.4).
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SuscripcionesPorVencer } from './SuscripcionesPorVencer';
import type { SuscripcionPorVencerItem } from '../api/reporteriaSchema';

describe('SuscripcionesPorVencer', () => {
  it('T1: loading with no items yet renders the loading status', () => {
    render(<SuscripcionesPorVencer items={[]} isLoading error={undefined} caption="c" />);
    expect(screen.getByTestId('suscripciones-por-vencer-loading')).toBeInTheDocument();
  });

  it('T2: error renders the error message instead of the table', () => {
    render(
      <SuscripcionesPorVencer
        items={[]}
        isLoading={false}
        error={new Error('fetch failed')}
        caption="c"
      />,
    );
    expect(screen.getByTestId('suscripciones-por-vencer-error')).toHaveTextContent(
      'fetch failed',
    );
  });

  it('T3: no items renders the empty state', () => {
    render(<SuscripcionesPorVencer items={[]} isLoading={false} error={undefined} caption="c" />);
    expect(screen.getByTestId('suscripciones-por-vencer-empty')).toBeInTheDocument();
  });

  it('T4: one row renders the días-restantes badge', () => {
    const items: SuscripcionPorVencerItem[] = [
      {
        uuid: '11111111-1111-1111-1111-111111111111',
        uuid_cliente: '22222222-2222-2222-2222-222222222222',
        uuid_sucursal: '33333333-3333-3333-3333-333333333333',
        fecha_vencimiento: '2026-10-05',
        dias_para_vencer: 4,
      },
    ];
    render(
      <SuscripcionesPorVencer items={items} isLoading={false} error={undefined} caption="c" />,
    );
    const badge = screen.getByTestId(
      'suscripciones-por-vencer-badge-11111111-1111-1111-1111-111111111111',
    );
    expect(badge).toHaveTextContent('4 días');
    expect(screen.getByText('2026-10-05')).toBeInTheDocument();
  });
});
