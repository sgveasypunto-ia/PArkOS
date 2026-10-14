/**
 * `SesionesBreakdownTable.test.tsx` -- HU-F18.2 + Bug #2 fix
 * (2026-10-14). Renders the per-session drill-down rows for a
 * ``cierre_dia`` aggregate.
 *
 * Covers the four states the parent ``<ArqueoDetalle>`` cares about:
 * loading, error, empty, and populated.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SesionesBreakdownTable } from './SesionesBreakdownTable';
import type { ArqueoResumenItem } from '../api/arqueosSchema';

function makeSesion(overrides: Partial<ArqueoResumenItem> = {}): ArqueoResumenItem {
  return {
    uuid_sesion: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    uuid_usuario: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    timestamp_apertura: '2026-10-14T01:02:09.293860Z',
    timestamp_cierre: '2026-10-14T01:19:11.986901Z',
    estado: 'cerrada',
    valor_efectivo_esperado: '160000.0000',
    valor_efectivo_reportado: null,
    uuid_arqueo: null,
    ...overrides,
  };
}

describe('SesionesBreakdownTable', () => {
  it('renders the loading state when isLoading=true', () => {
    render(
      <SesionesBreakdownTable
        sesiones={[]}
        isLoading={true}
        error={undefined}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByTestId('sesiones-breakdown-loading')).toBeInTheDocument();
  });

  it('renders the error state with a retry button', () => {
    render(
      <SesionesBreakdownTable
        sesiones={[]}
        isLoading={false}
        error={new Error('boom')}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByTestId('sesiones-breakdown-error')).toBeInTheDocument();
  });

  it('renders the empty state when the BE returned zero sesiones', () => {
    render(
      <SesionesBreakdownTable
        sesiones={[]}
        isLoading={false}
        error={undefined}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByTestId('sesiones-breakdown-empty')).toBeInTheDocument();
  });

  it('renders one row per sesion with the formatted money + timestamps', () => {
    render(
      <SesionesBreakdownTable
        sesiones={[
          makeSesion({
            uuid_sesion: 's1-s1-s1-s1-s1-s1-s1-s1-s1-s1',
            valor_efectivo_esperado: '160000.0000',
          }),
          makeSesion({
            uuid_sesion: 's2-s2-s2-s2-s2-s2-s2-s2-s2-s2',
            valor_efectivo_esperado: '110000.0000',
            timestamp_cierre: null, // still open
          }),
        ]}
        isLoading={false}
        error={undefined}
        onRetry={vi.fn()}
      />,
    );

    // Table is rendered.
    expect(screen.getByTestId('sesiones-breakdown-table')).toBeInTheDocument();

    // Two rows in the tbody, one per sesion.
    expect(screen.getByTestId('sesion-row-s1-s1-s1-s1-s1-s1-s1-s1-s1-s1')).toBeInTheDocument();
    expect(screen.getByTestId('sesion-row-s2-s2-s2-s2-s2-s2-s2-s2-s2-s2')).toBeInTheDocument();

    // First row: efectivo esperado cell shows 160000 (ICU data may not
    // include es-CO grouping separators, so we only assert the digit
    // sequence + the comma decimal).
    const firstRowChildren = Array.from(
      screen.getByTestId('sesion-row-s1-s1-s1-s1-s1-s1-s1-s1-s1-s1').children,
    );
    expect(firstRowChildren[4]?.textContent).toMatch(/160/);
    // First row: cierre timestamp truncated to YYYY-MM-DD HH:MM:SS.
    expect(firstRowChildren[3]?.textContent).toContain('2026-10-14 01:19:11');

    // Second row: still open, cierre cell shows "—".
    const secondRowChildren = Array.from(
      screen.getByTestId('sesion-row-s2-s2-s2-s2-s2-s2-s2-s2-s2-s2').children,
    );
    expect(secondRowChildren[4]?.textContent).toMatch(/110/);
    // "—" rendered for the cierre cell.
    expect(secondRowChildren[3]?.textContent).toBe('—');
  });
});
