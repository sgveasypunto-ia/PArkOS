/**
 * `<EstanciaPanel />` — unit tests (HU-F17.2, BR1).
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { EstanciaPanel } from './EstanciaPanel';
import type { ReporteEstanciaItem } from '../api/reporteriaSchema';

describe('EstanciaPanel', () => {
  it('T1: loading with no items yet renders the loading status', () => {
    render(<EstanciaPanel items={[]} isLoading error={undefined} />);
    expect(screen.getByTestId('reporteria-estancia-loading')).toBeInTheDocument();
  });

  it('T2: error renders the error message instead of the table', () => {
    render(
      <EstanciaPanel items={[]} isLoading={false} error={new Error('fetch failed')} />,
    );
    expect(screen.getByTestId('reporteria-estancia-error')).toHaveTextContent('fetch failed');
  });

  it('T3: no completed stays in range renders the empty state', () => {
    render(<EstanciaPanel items={[]} isLoading={false} error={undefined} />);
    expect(screen.getByTestId('reporteria-estancia-empty')).toBeInTheDocument();
  });

  it('T4: one bucket renders the formatted duration (h/min)', () => {
    const items: ReporteEstanciaItem[] = [
      {
        fecha: '2026-09-15',
        muestras: 2,
        promedio_segundos: 5400, // 1h 30min
        maximo_segundos: 7200, // 2h 0min
        minimo_segundos: 1800, // 30min
      },
    ];
    render(<EstanciaPanel items={items} isLoading={false} error={undefined} />);
    const row = screen.getByTestId('reporteria-estancia-row-2026-09-15');
    expect(row).toHaveTextContent('2');
    expect(row).toHaveTextContent('1h 30min');
    expect(row).toHaveTextContent('2h 0min');
    expect(row).toHaveTextContent('30min');
  });
});
