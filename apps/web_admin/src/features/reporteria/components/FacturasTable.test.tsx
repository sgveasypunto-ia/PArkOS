/**
 * `<FacturasTable />` — unit tests (HU-F17.3, reportería financiera).
 *
 * The backend serializes `created_at` as naive UTC (no trailing "Z",
 * e.g. "2026-10-02T23:26:30"). This guards against the same bug already
 * fixed for reportería operacional (`afaa7cd`/`4accc61`): rendering that
 * string without timezone-aware parsing shifts it ~10h forward instead
 * of showing the correct LOCAL wall-clock time
 * (`formatBackendTimestampLocal`, see `./dateRange`).
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FacturasTable } from './FacturasTable';
import type { ReporteFacturaItem } from '../api/reporteriaSchema';

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

const ITEM: ReporteFacturaItem = {
  uuid: '00000000-0000-0000-0000-000000000001',
  uuid_sucursal: '00000000-0000-0000-0000-000000000002',
  created_at: '2026-10-02T23:26:30',
  numero_completo: 'FE-001',
  subtotal: 1000,
  descuento: 0,
  iva: 190,
  total: 1190,
  estado: 'vigente',
};

describe('FacturasTable', () => {
  it('renders the naive-UTC created_at as the correct LOCAL time, not shifted ~10h', () => {
    render(
      <FacturasTable items={[ITEM]} isLoading={false} error={undefined} caption="Facturas" />,
    );
    const row = screen.getByText('FE-001').closest('tr');
    expect(row).toHaveTextContent('2026-10-02 18:26:30');
    // Old buggy `new Date(value).toISOString()` pattern double-shifted
    // this exact instant to the next day.
    expect(row).not.toHaveTextContent('2026-10-03 04:26:30');
  });
});
