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
});
