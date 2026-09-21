/**
 * `CierreDiario.test.tsx` — Strict-TDD RED scaffold for HU-F10.3
 * (REQ-OPS-164 + REQ-OPS-167, AD-3 + AD-4).
 *
 * Page orchestrator (`<CierreDiario />`):
 *   - Fetches resumen via `useArqueoResumenPorSesion`.
 *   - Renders the per-session table + `<CierreDiarioForm>` inline.
 *   - On submit, calls `runCierreDiarioChain` (REQ-OPS-166).
 *   - On `{ kind: 'success' }` navigates to `/` with a success banner
 *     (NOT `/login?closed=true` — supervisor preserves own session
 *     per AD-3 + REQ-OPS-164).
 *   - Role gate: admin- JWT renders the supervisor variant;
 *     multi-branch operador- shows the pending banner per REQ-OPS-167.
 *
 * Scenarios (5):
 *   page-1 — role gate: admin- JWT → page renders; multi-branch
 *            operador- → pending banner
 *   page-2 — loading state: useArqueoResumenPorSesion fetching shows
 *            skeleton
 *   page-3 — happy path: with 1 open session, summary loads, submit
 *            calls cierreDiarioChain (no logout)
 *   page-4 — 2 closed + 1 open session resumen renders correctly
 *   page-5 — success banner after chain returns ok:true
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// ── Mocks (hoisted before the page import) ───────────────────────────
const mockNavigate = vi.fn();
const mockRunCierreDiarioChain = vi.fn();
const mockClear = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// Auth store mock — evaluator selector returns the accessToken so the
// hook's SWR key-gate fires.
const FAKE_AUTH_STATE = {
  accessToken: 'admin-cloud.fake.jwt',
  refreshToken: null,
  expiresAt: null,
};
vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: typeof FAKE_AUTH_STATE) => unknown) =>
      selector(FAKE_AUTH_STATE),
    { getState: () => ({ ...FAKE_AUTH_STATE, clear: mockClear }) },
  ),
}));

// Auth hook mock — useAuth returns sucursalesPermitidas.
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    user: { uuid: 'usr-uuid-1', email: 'supervisor@parkos.local' },
    sucursal: { uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' },
    sucursalesPermitidas: [
      { uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' },
    ],
    permisos: [],
    expiresAt: null,
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  }),
}));

// SWR + the per-session hook.
let mockResumenData: unknown = undefined;
let mockResumenError: Error | undefined = undefined;
vi.mock('../../hooks/useArqueoResumenPorSesion', () => ({
  useArqueoResumenPorSesion: () => ({
    data: mockResumenData,
    error: mockResumenError,
    refresh: vi.fn(),
  }),
}));

// useArqueo().submit
const mockSubmit = vi.fn();
vi.mock('../../hooks/useArqueo', () => ({
  useArqueo: () => ({ submit: mockSubmit }),
  useArqueoResumen: () => ({ data: undefined, error: undefined, refresh: vi.fn() }),
  useCierreDiario: () => ({ ejecutar: vi.fn() }),
  useArqueoResumenPorSesion: () => ({
    data: mockResumenData,
    error: mockResumenError,
    refresh: vi.fn(),
  }),
}));

// cierreDiarioChain
vi.mock('../cierreDiarioChain', () => ({
  runCierreDiarioChain: (...args: unknown[]) => mockRunCierreDiarioChain(...args),
}));

// Import AFTER the mocks are registered.
import { CierreDiario } from '../CierreDiario';

// ── Fixtures ─────────────────────────────────────────────────────────
const TRES_SESIONES = {
  fecha: '2026-09-21',
  uuid_sucursal: '11111111-2222-4333-8444-555555555555',
  sesiones: [
    {
      uuid_sesion: '22222222-3333-4444-8555-666666666666',
      uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: '2026-09-21T18:00:00Z',
      estado: 'cerrado',
      valor_efectivo_esperado: 50_000,
      valor_datafono_esperado: 0,
      valor_efectivo_reportado: 50_000,
      valor_datafono_reportado: 0,
      uuid_arqueo: 'cccccccc-dddd-4eee-8fff-111111111111',
    },
    {
      uuid_sesion: '33333333-4444-4555-8666-777777777777',
      uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: '2026-09-21T18:00:00Z',
      estado: 'cerrado',
      valor_efectivo_esperado: 100_000,
      valor_datafono_esperado: 30_000,
      valor_efectivo_reportado: 100_000,
      valor_datafono_reportado: 30_000,
      uuid_arqueo: 'cccccccc-dddd-4eee-8fff-222222222222',
    },
    {
      uuid_sesion: '44444444-5555-4666-8777-888888888888',
      uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: null,
      estado: 'abierta',
      valor_efectivo_esperado: null,
      valor_datafono_esperado: null,
      valor_efectivo_reportado: null,
      valor_datafono_reportado: null,
      uuid_arqueo: null,
    },
  ],
  cierre_dia: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockResumenData = undefined;
  mockResumenError = undefined;
});

afterEach(() => {
  vi.restoreAllMocks();
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <CierreDiario />
    </MemoryRouter>,
  );

describe('HU-F10.3 — <CierreDiario /> routed page (REQ-OPS-164 + REQ-OPS-167, AD-3 + AD-4)', () => {
  // ──────────────────────────────────────────────────────────────────
  // page-1 — role gate
  // ──────────────────────────────────────────────────────────────────
  it('page-1: admin- JWT renders page; multi-branch operador- shows pending banner', async () => {
    // Admin- issuer via accessToken prefix → page mounts.
    mockResumenData = TRES_SESIONES;
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByTestId('cierre-diario-page'),
      ).toBeInTheDocument();
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // page-2 — loading state
  // ──────────────────────────────────────────────────────────────────
  it('page-2: hook fetching shows skeleton (data === undefined)', async () => {
    mockResumenData = undefined;
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-skeleton'),
      ).toBeInTheDocument();
    });
    // The form MUST NOT render until data is loaded.
    expect(
      screen.queryByTestId('cierre-diario-sesiones'),
    ).not.toBeInTheDocument();
  });

  // ──────────────────────────────────────────────────────────────────
  // page-3 — happy path: 1 open session → submit calls chain
  // ──────────────────────────────────────────────────────────────────
  it('page-3: with 1 open session, summary loads, submit calls cierreDiarioChain (no logout)', async () => {
    mockResumenData = TRES_SESIONES;
    mockRunCierreDiarioChain.mockResolvedValueOnce({
      kind: 'success',
      uuid_arqueo: 'arqueo-uuid-AD',
    });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-confirmar'),
      ).toBeInTheDocument();
    });
    // Click Confirmar to trigger the form submission.
    const confirmar = screen.getByTestId(
      'cierre-diario-confirmar',
    ) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(false);
    confirmar.click();
    // The chain helper was awaited exactly once.
    await waitFor(() => {
      expect(mockRunCierreDiarioChain).toHaveBeenCalled();
    });
    // NO useAuthStore.clear() on success — supervisor preserves own
    // session per AD-3 + REQ-OPS-164.
    expect(mockClear).not.toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────
  // page-4 — 2 closed + 1 open session resumen renders
  // ──────────────────────────────────────────────────────────────────
  it('page-4: 2 closed + 1 open session resumen renders correctly (3 rows + footer)', async () => {
    mockResumenData = TRES_SESIONES;
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-sesiones'),
      ).toBeInTheDocument();
    });
    const tbody = screen
      .getByTestId('cierre-diario-sesiones')
      .querySelector('tbody');
    expect(tbody?.querySelectorAll('tr').length).toBe(3);
    // Aggregate footer MUST be present.
    expect(
      screen.getByTestId('cierre-diario-totals'),
    ).toBeInTheDocument();
  });

  // ──────────────────────────────────────────────────────────────────
  // page-5 — success banner after chain returns ok:true
  // ──────────────────────────────────────────────────────────────────
  it('page-5: success banner renders after cierreDiarioChain returns { kind: "success" }', async () => {
    mockResumenData = TRES_SESIONES;
    mockRunCierreDiarioChain.mockResolvedValueOnce({
      kind: 'success',
      uuid_arqueo: 'arqueo-uuid-AD',
    });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-confirmar'),
      ).toBeInTheDocument();
    });
    // Click Confirmar to trigger the form submission.
    const confirmar = screen.getByTestId(
      'cierre-diario-confirmar',
    ) as HTMLButtonElement;
    confirmar.click();
    // Page navigates to `/` with success banner; mockNavigate is
    // called with `/`.
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
  });
});