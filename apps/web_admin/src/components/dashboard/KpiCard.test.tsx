/**
 * KpiCard — unit tests (HU-F17.1, T6).
 */
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { KpiCard } from './KpiCard';

function renderCard(ui: ReactElement): ReturnType<typeof render> {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('KpiCard', () => {
  it('T1: loading renders a skeleton, not the value', () => {
    renderCard(<KpiCard label="Ingresos" value={42} loading error={false} />);
    expect(screen.getByTestId('kpi-card-ingresos-skeleton')).toBeInTheDocument();
    expect(screen.queryByTestId('kpi-card-ingresos-value')).not.toBeInTheDocument();
  });

  it('T2: error renders the error label instead of the value', () => {
    renderCard(<KpiCard label="Ingresos" value={42} loading={false} error />);
    expect(screen.getByTestId('kpi-card-ingresos-error')).toHaveTextContent('No disponible');
  });

  it('T3: loaded renders the numeric value', () => {
    renderCard(<KpiCard label="Ingresos" value={42} loading={false} error={false} />);
    expect(screen.getByTestId('kpi-card-ingresos-value')).toHaveTextContent('42');
  });

  it('T4: render prop takes over the body when provided', () => {
    renderCard(
      <KpiCard
        label="Ocupación"
        loading={false}
        error={false}
        render={() => <span>8/20</span>}
      />,
    );
    expect(screen.getByTestId('kpi-card-ocupación-content')).toHaveTextContent('8/20');
  });

  it('T5: `to` wraps the card in a Link with the linkHint visible', () => {
    renderCard(
      <KpiCard
        label="Cupos"
        value={3}
        loading={false}
        error={false}
        to="/cupos"
        linkHint="Ver cupos →"
      />,
    );
    const link = screen.getByTestId('kpi-card-cupos');
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', '/cupos');
    expect(screen.getByText('Ver cupos →')).toBeInTheDocument();
  });
});
