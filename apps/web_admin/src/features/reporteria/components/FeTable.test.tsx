/**
 * `<FeTable />` — unit tests (HU-F17.3, reportería financiera / FE).
 *
 * The backend serializes `timestamp_evento` as naive UTC (no trailing
 * "Z", e.g. "2026-10-02T23:26:30"). This guards against the same bug
 * already fixed for reportería operacional (`afaa7cd`/`4accc61`):
 * rendering that string without timezone-aware parsing shifts it ~10h
 * forward instead of showing the correct LOCAL wall-clock time
 * (`formatBackendTimestampLocal`, see `./dateRange`).
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FeTable } from './FeTable';
import type { ReporteFeItem } from '../api/reporteriaSchema';

const ORIGINAL_TZ = process.env.TZ;

beforeAll(() => {
  // Pin a non-UTC offset (America/Bogota, UTC-5, no DST) so the
  // regression reproduces deterministically regardless of the host's
  // own local timezone.
  process.env.TZ = 'America/Bogota';
});

afterAll(() => {
  process.env.TZ = ORIGINAL_TZ;
});

const ITEM: ReporteFeItem = {
  uuid: '00000000-0000-0000-0000-000000000001',
  uuid_sucursal: '00000000-0000-0000-0000-000000000002',
  uuid_factura: '00000000-0000-0000-0000-000000000003',
  numero_completo: 'FE-001',
  cufe: 'cufe-123',
  estado_dian: 'aceptado',
  timestamp_evento: '2026-10-02T23:26:30',
};

describe('FeTable', () => {
  it('renders the naive-UTC timestamp_evento as the correct LOCAL time, not shifted ~10h', () => {
    render(<FeTable items={[ITEM]} isLoading={false} error={undefined} caption="FE" />);
    const row = screen.getByText('FE-001').closest('tr');
    expect(row).toHaveTextContent('2026-10-02 18:26:30');
    // Old buggy `new Date(value).toISOString()` pattern double-shifted
    // this exact instant to the next day.
    expect(row).not.toHaveTextContent('2026-10-03 04:26:30');
  });

  it('renders "—" when timestamp_evento is null', () => {
    render(
      <FeTable
        items={[{ ...ITEM, timestamp_evento: null }]}
        isLoading={false}
        error={undefined}
        caption="FE"
      />,
    );
    const row = screen.getByText('FE-001').closest('tr');
    expect(row).toHaveTextContent('—');
  });
});
