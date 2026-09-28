/**
 * `AuditDashboard.test.tsx` -- container tests for IT-12.
 *
 * Pattern (mirror of ``features/auth/pages/Login.test.tsx``):
 *   1. Import the real AuditDashboard.
 *   2. Import the mocked modules and grab the spy via ``vi.mocked``.
 *   3. Configure each test via ``vi.mocked(spy).mockReturnValue(...)``
 *      (persistent -- the default branch-selected setup lives in the
 *      factory above).
 *   4. Use ``beforeEach`` with ``mockClear`` to reset call history
 *      but NOT ``restoreAllMocks`` (that would unregister the
 *      ``vi.mock(...)`` factories and break subsequent tests).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import AuditDashboard from '../pages/AuditDashboard';
import * as auditApi from '../api/auditApi';
import * as sucursalCtx from '@/lib/sucursal-context';

// A unique branch per test so the SWR cache key changes between
// tests (the dashboard reads ``selected`` from the context to build
// the key). Without this, SWR caches test 2's success and test 3's
// ``mockRejectedValue`` is never consumed.
const branchForTest = (): string =>
  `00000000-0000-0000-0000-${Date.now().toString(16).padStart(12, '0')}`;

vi.mock('../api/auditApi', () => ({
  fetchAuditLog: vi.fn(),
}));
vi.mock('@/lib/sucursal-context', () => ({
  useSucursal: vi.fn(),
}));

const fetchAuditLog = vi.mocked(auditApi.fetchAuditLog);
const useSucursal = vi.mocked(sucursalCtx.useSucursal);

const MOCK_ITEM = {
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

beforeEach(() => {
  fetchAuditLog.mockReset();
  useSucursal.mockClear();
  // Re-establish the default branch-selected state -- ``mockReset``
  // wipes implementations on the spies, so the per-test override has
  // to be set explicitly. The default lives in the factory above.
  useSucursal.mockReturnValue({
    selected: branchForTest(),
    setSelected: vi.fn(),
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('AuditDashboard', () => {
  it('renders the no-branch hint when no branch is selected', () => {
    useSucursal.mockReturnValue({ selected: null, setSelected: vi.fn() });
    render(
      <MemoryRouter>
        <AuditDashboard />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('page-audit-no-branch')).toBeInTheDocument();
  });
  it('renders the rows when the API succeeds', async () => {
    fetchAuditLog.mockResolvedValue({
      items: [MOCK_ITEM],
      next_cursor: null,
    });
    render(
      <MemoryRouter>
        <AuditDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('audit-log-table')).toBeInTheDocument();
    });
    expect(screen.getByText('crear_factura')).toBeInTheDocument();
    expect(fetchAuditLog).toHaveBeenCalledTimes(1);
  });
  it('renders the empty placeholder when there are no rows', async () => {
    fetchAuditLog.mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    render(
      <MemoryRouter>
        <AuditDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('audit-log-empty')).toBeInTheDocument();
    });
  });

  it('renders the error state when the API throws', async () => {
    fetchAuditLog.mockRejectedValue(new Error('boom'));
    render(
      <MemoryRouter>
        <AuditDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('audit-log-error')).toBeInTheDocument();
    });
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('renders the load-more button when next_cursor is non-null and appends on click', async () => {
    fetchAuditLog
      .mockResolvedValueOnce({ items: [MOCK_ITEM], next_cursor: 'cursor-1' })
      .mockResolvedValueOnce({
        items: [{ ...MOCK_ITEM, uuid: '00000000-0000-0000-0000-000000000002' }],
        next_cursor: null,
      });
    render(
      <MemoryRouter>
        <AuditDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('audit-load-more')).toBeInTheDocument();
    });
    await userEvent.setup().click(screen.getByTestId('audit-load-more'));
    await waitFor(() => {
      expect(fetchAuditLog).toHaveBeenCalledTimes(2);
    });
    expect(fetchAuditLog).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ cursor: 'cursor-1' }),
    );
  });
});
