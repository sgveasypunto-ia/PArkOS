/**
 * `LogTable.test.tsx` -- presentational tests for IT-12.
 *
 * Pattern: render with a controlled items prop and assert on the
 * rendered DOM. No SWR mocking -- this file is pure presentation.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LogTable } from './LogTable';

const ITEM = {
  uuid: '00000000-0000-0000-0000-000000000001',
  timestamp_evento: '2026-09-26T10:00:00',
  uuid_usuario: null,
  uuid_sucursal: '00000000-0000-0000-0000-000000000020',
  uuid_referencia: null,
  accion: 'crear_factura',
  tabla_afectada: 'factura',
  datos_anteriores: null,
  datos_nuevos: null,
  hash_anterior: 'abcdef01abcdef01abcdef01abcdef01abcdef01abcdef01abcdef01abcdef01',
  hash_actual: 'fedcba98fedcba98fedcba98fedcba98fedcba98fedcba98fedcba98fedcba98',
};

describe('LogTable', () => {
  it('renders the table with one row', () => {
    render(<LogTable items={[ITEM]} isLoading={false} error={null} />);
    const table = screen.getByTestId('audit-log-table');
    expect(table).toBeInTheDocument();
    // Accion and tabla are both present; assert each by exact-text match.
    expect(screen.getByText('crear_factura')).toBeInTheDocument();
    expect(screen.getByText('factura')).toBeInTheDocument();
  });

  it('abbreviates the hash chain badge (first 8 chars + ellipsis)', () => {
    render(<LogTable items={[ITEM]} isLoading={false} error={null} />);
    expect(screen.getByText(/abcdef01…/)).toBeInTheDocument();
    expect(screen.getByText(/fedcba98…/)).toBeInTheDocument();
  });

  it('shows the dash placeholder for null hashes', () => {
    const item = { ...ITEM, hash_anterior: null, hash_actual: null };
    render(<LogTable items={[item]} isLoading={false} error={null} />);
    // Two dashes present (one per hash field).
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
  });

  it('shows the loading state when isLoading and no items', () => {
    render(<LogTable items={[]} isLoading={true} error={null} />);
    expect(screen.getByTestId('audit-log-loading')).toBeInTheDocument();
  });

  it('shows the empty state when not loading and zero items', () => {
    render(<LogTable items={[]} isLoading={false} error={null} />);
    expect(screen.getByTestId('audit-log-empty')).toBeInTheDocument();
  });

  it('shows the error state when error is set', () => {
    render(<LogTable items={[]} isLoading={false} error={new Error('boom')} />);
    expect(screen.getByTestId('audit-log-error')).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
