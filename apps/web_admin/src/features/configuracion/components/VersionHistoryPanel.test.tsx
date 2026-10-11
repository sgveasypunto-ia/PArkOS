/**
 * VersionHistoryPanel — unit tests.
 *
 * Pins:
 *   1. Renders one row per version, DESC order preserved.
 *   2. The current version (vigente_hasta === null && estado === 'activo')
 *      gets the "vigente" badge.
 *   3. Closed versions render "abierta" in the vigente_hasta column.
 *   4. Empty versions list renders the empty state.
 *   5. Toggle button collapses and expands the table.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { VersionHistoryPanel, type VersionHistoryItem } from './VersionHistoryPanel';

const SAMPLE: VersionHistoryItem[] = [
  {
    uuid: '11111111-1111-1111-1111-111111111111',
    display: '3000.0000',
    vigente_desde: '2026-09-15T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
  },
  {
    uuid: '22222222-2222-2222-2222-222222222222',
    display: '1500.0000',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: '2026-09-15T00:00:00',
    estado: 'inactivo',
  },
];

describe('VersionHistoryPanel', () => {
  it('VP1: renders one row per version, DESC order preserved', () => {
    render(<VersionHistoryPanel versions={SAMPLE} displayLabel="Valor" />);
    const rows = screen.getAllByTestId(/^version-history-row-/);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('3000.0000');
    expect(rows[1]).toHaveTextContent('1500.0000');
  });

  it('VP2: current version gets the "vigente" badge', () => {
    render(<VersionHistoryPanel versions={SAMPLE} displayLabel="Valor" />);
    expect(screen.getByTestId('version-history-current')).toBeInTheDocument();
  });

  it('VP3: closed versions render "abierta" label (Spanish, no date)', () => {
    render(<VersionHistoryPanel versions={SAMPLE} displayLabel="Valor" />);
    // The second row (closed) has vigente_hasta !== null → not "abierta".
    // The "abierta" label only appears in the open row's last cell.
    const openRow = screen.getByTestId('version-history-row-0');
    expect(openRow.textContent).toContain('abierta');
  });

  it('VP4: empty versions list renders the empty state', () => {
    render(<VersionHistoryPanel versions={[]} displayLabel="Valor" />);
    expect(screen.getByText('Sin versiones registradas.')).toBeInTheDocument();
  });

  it('VP5: toggle button collapses and expands the table', async () => {
    const user = userEvent.setup();
    render(<VersionHistoryPanel versions={SAMPLE} displayLabel="Valor" />);
    const toggle = screen.getByTestId('version-history-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByTestId(/^version-history-row-/)).toHaveLength(2);

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryAllByTestId(/^version-history-row-/)).toHaveLength(0);

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByTestId(/^version-history-row-/)).toHaveLength(2);
  });

  it('VP6: with displayLabel on every item -- the "Modalidad" column appears', () => {
    // The tarifa path passes displayLabel on every item (Hora /
    // Fracción / Plena / Nocturna). The panel must render the column
    // so the operator can see which dimension changed at each version
    // (operator feedback 2026-10-11).
    const SAMPLE_WITH_LABEL: VersionHistoryItem[] = [
      {
        uuid: '11111111-1111-1111-1111-111111111111',
        display: '3.000',
        displayLabel: 'Hora',
        vigente_desde: '2026-09-15T00:00:00',
        vigente_hasta: null,
        estado: 'activo',
      },
      {
        uuid: '22222222-2222-2222-2222-222222222222',
        display: '1.500',
        displayLabel: 'Fracción',
        vigente_desde: '2026-01-01T00:00:00',
        vigente_hasta: '2026-09-15T00:00:00',
        estado: 'inactivo',
      },
    ];
    render(<VersionHistoryPanel versions={SAMPLE_WITH_LABEL} displayLabel="Valor" />);
    // The header is present.
    expect(screen.getByTestId('version-history-modalidad-header')).toHaveTextContent(
      'Modalidad',
    );
    // Each row has its own modalidad cell with the per-row label.
    expect(screen.getByTestId('version-history-modalidad-0')).toHaveTextContent('Hora');
    expect(screen.getByTestId('version-history-modalidad-1')).toHaveTextContent(
      'Fracción',
    );
    // The existing "Valor" column still works.
    expect(screen.getByText('3.000')).toBeInTheDocument();
  });

  it('VP7: backward-compat without displayLabel (cupos) -- the "Modalidad" column is hidden', () => {
    // Cupos' history items do not set displayLabel. The panel must keep
    // the legacy 4-column layout (no "Modalidad" column) so the cupos
    // page doesn't break.
    render(<VersionHistoryPanel versions={SAMPLE} displayLabel="Cantidad" />);
    expect(screen.queryByTestId('version-history-modalidad-header')).not.toBeInTheDocument();
    expect(screen.queryByTestId('version-history-modalidad-0')).not.toBeInTheDocument();
  });

  it('VP8: mixed array (some items with displayLabel, some without) -- column still appears, missing items show "—"', () => {
    // Defensive: an item can carry displayLabel undefined while others
    // carry it (e.g. tarifa row with modalidad null). The column
    // appears because AT LEAST ONE item has it; the missing one
    // shows "—" rather than crashing.
    const MIXED: VersionHistoryItem[] = [
      {
        uuid: '33333333-3333-3333-3333-333333333333',
        display: '3.000',
        displayLabel: 'Hora',
        vigente_desde: '2026-09-15T00:00:00',
        vigente_hasta: null,
        estado: 'activo',
      },
      {
        uuid: '44444444-4444-4444-4444-444444444444',
        display: '—',
        vigente_desde: '2026-01-01T00:00:00',
        vigente_hasta: '2026-09-15T00:00:00',
        estado: 'inactivo',
        // displayLabel intentionally omitted
      },
    ];
    render(<VersionHistoryPanel versions={MIXED} displayLabel="Valor" />);
    expect(screen.getByTestId('version-history-modalidad-header')).toBeInTheDocument();
    expect(screen.getByTestId('version-history-modalidad-0')).toHaveTextContent('Hora');
    expect(screen.getByTestId('version-history-modalidad-1')).toHaveTextContent('—');
  });
});
