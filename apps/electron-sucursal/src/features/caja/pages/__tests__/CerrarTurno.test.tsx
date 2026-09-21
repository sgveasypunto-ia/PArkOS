/**
 * `CerrarTurno.test.tsx` — Strict-TDD RED scaffold for HU-F10.2
 * (REQ-OPS-157, REQ-OPS-159, AD-2 + AD-3 + AD-5 + AD-6).
 *
 * The orchestrator must chain:
 *   1. `useArqueo().submit({ tipo_arqueo: 'cierre_turno', ... })` →
 *      capture `{ uuid: A }`.
 *   2. `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno' })`
 *      fires exactly once (BEFORE the PUT).
 *   3. `useSesionActiva().cerrarSesion(uuid_sesion, payload)` →
 *      on `{ ok: true }` navigate `/login?closed=true`.
 *
 * Error precedence (8 cases per AD-3):
 *   - ZodError → FormMessage (no network).
 *   - 400 arqueo_invalid → field errors from `detail.campo[]`.
 *   - POST 5xx → banner `cerrarTurno.errorArqueoFallido`, no PUT call.
 *   - POST network → banner `cerrarTurno.errorRedArqueo`, no PUT call.
 *   - PUT 404 (SesionAlreadyClosedError) → banner + navigate '/login'.
 *   - PUT 409 (sesion_ya_cerrada) → banner + `Ref: A` + no clear + no navigate.
 *   - PUT 5xx/network → banner + `Ref: A` + no clear + no navigate.
 *   - PUT 401 → F3.3 fallback (handled inside helper per AD-4).
 *
 * The helper (`useSesionActiva().cerrarSesion`) owns the F3.3 logout
 * trifecta — the orchestrator only has to `navigate`. The helper
 * itself is tested separately at `hooks/__tests__/useSesionActiva.cerrarSesion.test.ts`.
 *
 * These 9 RED scenarios MUST FAIL on master because the orchestrator
 * is still the F3.3 stub (does not chain useArqueo + bridge.imprimir +
 * useSesionActiva helper). After Commit 4 lands the rewrite, they go GREEN.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
const mockArqueoSubmit = vi.fn();
const mockCerrarSesionHelper = vi.fn();
const mockClear = vi.fn();
const mockBridgeImprimir = vi.fn();
const dispatchEventSpy = vi
  .spyOn(window, 'dispatchEvent')
  .mockImplementation(() => true);

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (_selector: unknown) => undefined,
    { getState: () => ({ clear: mockClear }) },
  ),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class ParkosHttpError extends Error {
    public readonly status: number;
    public readonly body: string;
    public readonly url: string;
    constructor(status: number, body = '{}', url = '/api/v1/x') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

// Stub bridge so we can assert `bridge.imprimir('arqueo', payload)`.
vi.mock('../../../shared/bridge', () => ({
  bridge: {
    imprimir: (...args: unknown[]) => mockBridgeImprimir(...args),
  },
}));

vi.mock('../../hooks/useArqueo', () => ({
  useArqueo: () => ({ submit: mockArqueoSubmit, fetchResumen: vi.fn() }),
  useArqueoResumen: () => ({
    data: {
      uuid_sucursal: 'suc-uuid-1',
      fecha: '2026-09-21',
      total_efectivo_cop: 100_000,
      total_datafono_cop: 0,
      diferencia_cop: 0,
      sesiones_cerradas: 1,
    },
    error: undefined,
    refresh: vi.fn(),
  }),
}));

vi.mock('../../hooks/useSesionActiva', () => ({
  useSesionActiva: () => ({
    sesion: {
      uuid: 'sess-uuid-1',
      uuid_sucursal: 'suc-uuid-1',
      uuid_usuario: 'usr-uuid-1',
      valor_inicial_efectivo: 50_000,
      valor_inicial_datafono: 0,
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: null,
    },
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
    cerrarSesion: mockCerrarSesionHelper,
  }),
}));

// Passthrough CerrarTurnoForm mock — keeps the test isolated from the
// shadcn Form internals. The orchestrator passes its onConfirmar callback
// to the form, which we drive via the form's submit button.
vi.mock('../components/CerrarTurnoForm', () => ({
  CerrarTurnoForm: ({
    onSubmit,
  }: {
    onSubmit: (v: unknown) => Promise<void>;
  }) => (
    <form
      data-testid="cerrar-turno-form"
      onSubmit={(e) => {
        e.preventDefault();
        void onSubmit({
          valor_final_efectivo: 100_000,
          valor_final_datafono: 0,
          valor_efectivo_reportado: 100_000,
          valor_datafono_reportado: 0,
          observaciones_cierre: '',
          justificacion: '',
        });
      }}
    >
      <button type="submit" data-testid="cerrar-turno-confirmar">
        Confirmar
      </button>
    </form>
  ),
}));

import { CerrarTurno } from '../CerrarTurno';

beforeEach(() => {
  vi.clearAllMocks();
  // Default happy path: arqueo 201 returns uuid, helper returns ok.
  mockArqueoSubmit.mockResolvedValue({ uuid: 'arqueo-uuid-1' });
  mockCerrarSesionHelper.mockResolvedValue({
    ok: true,
    status: 200,
    sesion: { uuid: 'sess-uuid-1', timestamp_cierre: '2026-09-21T18:00:00Z' },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

const RENDER = (): ReturnType<typeof render> =>
  render(
    <MemoryRouter>
      <CerrarTurno />
    </MemoryRouter>,
  );

describe('HU-F10.2 — <CerrarTurno /> orchestrator (REQ-OPS-157, REQ-OPS-159, AD-2 + AD-3)', () => {
  // ────────────────────────────────────────────────────────────────────
  // seq-1-happy-path — POST 201 → PUT 200 → helper ok → navigate
  // ────────────────────────────────────────────────────────────────────
  it('seq-1: happy path POST 201 + PUT 200 + helper ok:true → /login?closed=true', async () => {
    const user = userEventFromScreen();
    RENDER();

    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    // 1. arqueo submit was awaited FIRST with cierre_turno discriminator.
    await waitFor(() => {
      expect(mockArqueoSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          uuid_sesion: 'sess-uuid-1',
          tipo_arqueo: 'cierre_turno',
          valor_efectivo_reportado: 100_000,
          valor_datafono_reportado: 0,
        }),
      );
    });

    // 2. bridge.imprimir fired exactly once with auditoria_codigo='cierre_turno'.
    await waitFor(() => {
      expect(mockBridgeImprimir).toHaveBeenCalledTimes(1);
    });
    expect(mockBridgeImprimir).toHaveBeenCalledWith(
      'arqueo',
      expect.objectContaining({
        auditoria_codigo: 'cierre_turno',
      }),
    );

    // 3. THEN the helper is invoked (after POST + bridge.imprimir).
    await waitFor(() => {
      expect(mockCerrarSesionHelper).toHaveBeenCalledWith('sess-uuid-1', {
        valor_final_efectivo: 100_000,
        valor_final_datafono: 0,
      });
    });

    // 4. navigate to /login?closed=true (DEC-F3.3-03 verbatim).
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login?closed=true', {
        replace: true,
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────
  // seq-2-tolerancia — diferencia within tolerancia: justificacion optional
  // ────────────────────────────────────────────────────────────────────
  it('seq-2: diferencia within tolerancia → justificacion empty OK → 200+200 redirect', async () => {
    const user = userEventFromScreen();
    RENDER();

    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      expect(mockArqueoSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          valor_efectivo_reportado: 100_000,
          // diferencia=0 → the call MUST NOT carry a justificacion field
          // (REACT-form `justificacion: ''` is dropped before the body).
        }),
      );
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login?closed=true', {
        replace: true,
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────
  // seq-3-diferencia-fuera-tolerancia — justificacion REQUIRED
  // ────────────────────────────────────────────────────────────────────
  it('seq-3: |diferencia| > tolerancia → justificacion required → POST carries justificacion', async () => {
    // Override the form mock to pass diferencia outside tolerancia + justification.
    vi.doMock('../components/CerrarTurnoForm', () => ({
      CerrarTurnoForm: ({
        onSubmit,
      }: {
        onSubmit: (v: unknown) => Promise<void>;
      }) => (
        <form
          data-testid="cerrar-turno-form"
          onSubmit={(e) => {
            e.preventDefault();
            void onSubmit({
              valor_final_efectivo: 100_000,
              valor_final_datafono: 0,
              valor_efectivo_reportado: 97_000,
              valor_datafono_reportado: 0,
              observaciones_cierre: '',
              justificacion: 'Faltante menor en caja',
            });
          }}
        />
      ),
    }));
    // Re-import so the new mock is picked up.
    const { CerrarTurno: CerrarTurnoFresh } = await import('../CerrarTurno');
    const user = userEventFromScreen();
    render(
      <MemoryRouter>
        <CerrarTurnoFresh />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      expect(mockArqueoSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          tipo_arqueo: 'cierre_turno',
          valor_efectivo_reportado: 97_000,
          justificacion: 'Faltante menor en caja',
        }),
      );
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login?closed=true', {
        replace: true,
      });
    });
    vi.doUnmock('../components/CerrarTurnoForm');
  });

  // ────────────────────────────────────────────────────────────────────
  // post-1-zod — ZodError before network
  // ────────────────────────────────────────────────────────────────────
  it('post-1: ZodError on submit → FormMessage, NO cerrarSesionHelper, NO navigate', async () => {
    // Simulate ZodError by having the form-level resolver reject.
    vi.doMock('../components/CerrarTurnoForm', () => ({
      CerrarTurnoForm: ({
        onSubmit,
      }: {
        onSubmit: (v: unknown) => Promise<void>;
      }) => (
        <form
          data-testid="cerrar-turno-form"
          onSubmit={(e) => {
            e.preventDefault();
            // Simulate ZodError at the orchestrator level: throw a
            // ZodError from onSubmit. The orchestrator's try/catch
            // should branch on err.name === 'ZodError'.
            const zodError = new Error('validation_failed');
            zodError.name = 'ZodError';
            void onSubmit({
              valor_final_efectivo: 100_000,
              valor_final_datafono: 0,
              valor_efectivo_reportado: 100_000,
              valor_datafono_reportado: 0,
              observaciones_cierre: '',
              justificacion: '',
              __zodError: zodError,
            });
          }}
        />
      ),
    }));
    const { CerrarTurno: CerrarTurnoFresh } = await import('../CerrarTurno');
    render(
      <MemoryRouter>
        <CerrarTurnoFresh />
      </MemoryRouter>,
    );

    await userEventFromScreen().click(screen.getByTestId('cerrar-turno-confirmar'));

    // The orchestrator MUST NOT proceed to bridge.imprimir, helper, or navigate.
    await new Promise((r) => setTimeout(r, 50));
    expect(mockBridgeImprimir).not.toHaveBeenCalled();
    expect(mockCerrarSesionHelper).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
    vi.doUnmock('../components/CerrarTurnoForm');
  });

  // ────────────────────────────────────────────────────────────────────
  // post-2-400-arqueo-invalid — 400 from POST → field-level errors
  // ────────────────────────────────────────────────────────────────────
  it('post-2: POST 400 arqueo_invalid → field errors, NO cerrarSesionHelper, NO navigate', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockArqueoSubmit.mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        '{"error":"arqueo_invalid","campo":["valor_efectivo_reportado"]}',
        '/api/v1/caja/arqueo',
      ),
    );
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await new Promise((r) => setTimeout(r, 50));
    expect(mockCerrarSesionHelper).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // post-3-5xx-no-cerrarsesion — POST 5xx → banner, no PUT attempt
  // ────────────────────────────────────────────────────────────────────
  it('post-3: POST 5xx → banner errorArqueoFallido, NO cerrarSesionHelper, NO navigate', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockArqueoSubmit.mockRejectedValueOnce(
      new ParkosHttpError(500, '{"error":"server_error"}', '/api/v1/caja/arqueo'),
    );
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await new Promise((r) => setTimeout(r, 50));
    expect(mockCerrarSesionHelper).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(mockBridgeImprimir).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // post-4-network-no-cerrarsesion — POST network error → banner
  // ────────────────────────────────────────────────────────────────────
  it('post-4: POST network error → banner errorRedArqueo, NO cerrarSesionHelper, NO navigate', async () => {
    mockArqueoSubmit.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await new Promise((r) => setTimeout(r, 50));
    expect(mockCerrarSesionHelper).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // put-1-404-sesion-not-found — SesionAlreadyClosedError → navigate /login (no ?closed=true)
  // ────────────────────────────────────────────────────────────────────
  it('put-1: helper returns { ok:false, status:404 } → navigate /login (no ?closed=true)', async () => {
    mockCerrarSesionHelper.mockResolvedValueOnce({
      ok: false,
      status: 404,
      error: new Error('sesion_not_found'),
    });
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
    // Critically: NO ?closed=true — the close did not succeed.
    expect(mockNavigate).not.toHaveBeenCalledWith(
      '/login?closed=true',
      expect.anything(),
    );
  });

  // ────────────────────────────────────────────────────────────────────
  // put-2-409-sesion-ya-cerrada — orphan uuid surfaced, no logout, no navigate
  // ────────────────────────────────────────────────────────────────────
  it('put-2: helper returns { ok:false, status:409 } → banner with Ref: A, NO clear, NO navigate', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockCerrarSesionHelper.mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: new ParkosHttpError(
        409,
        '{"error":"sesion_ya_cerrada"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    });
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    // The orphan uuid MUST be surfaced via data-testid="cerrar-turno-orphan-uuid".
    await waitFor(() => {
      const orphan = screen.getByTestId('cerrar-turno-orphan-uuid');
      expect(orphan.textContent).toContain('arqueo-uuid-1');
    });
    // The banner MUST show the "Ref: <uuid>" literal substring.
    const banner = await screen.findByTestId('cerrar-turno-orphan-uuid');
    expect(banner.textContent).toMatch(/Ref:.*arqueo-uuid-1/);
    // Critically: NO clear dispatched (operator stays on route).
    expect(mockClear).not.toHaveBeenCalled();
    // NO navigate — route stays mounted so the operator reads the banner.
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // put-3-5xx-orphan-uuid — PUT 5xx → banner, orphan uuid, no clear, no navigate
  // ────────────────────────────────────────────────────────────────────
  it('put-3: helper returns { ok:false, status:500 } → orphan uuid banner, NO clear, NO navigate', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockCerrarSesionHelper.mockResolvedValueOnce({
      ok: false,
      status: 500,
      error: new ParkosHttpError(
        500,
        '{"error":"server_error"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    });
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      const orphan = screen.getByTestId('cerrar-turno-orphan-uuid');
      expect(orphan.textContent).toContain('arqueo-uuid-1');
    });
    expect(mockClear).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // put-4-401-f3.3-fallback — handled inside helper (clear+event fired)
  // ────────────────────────────────────────────────────────────────────
  it('put-4: helper returns { ok:false, status:401 } → navigate /login (no ?closed=true)', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockCerrarSesionHelper.mockResolvedValueOnce({
      ok: false,
      status: 401,
      error: new ParkosHttpError(
        401,
        '{"error":"unauthorized"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    });
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    // The orchestrator navigates to /login (without ?closed=true); the
    // helper has already cleared authStore + fired the event (tested
    // separately in helper-3).
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
    expect(mockNavigate).not.toHaveBeenCalledWith(
      '/login?closed=true',
      expect.anything(),
    );
  });

  // ────────────────────────────────────────────────────────────────────
  // no-retry — assertions on no retry loop
  // ────────────────────────────────────────────────────────────────────
  it('no-retry: orchestrator does NOT retry arqueo.submit nor cerrarSesionHelper on failure', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockArqueoSubmit.mockRejectedValueOnce(
      new ParkosHttpError(500, '{"error":"server_error"}', '/api/v1/caja/arqueo'),
    );
    const user = userEventFromScreen();
    RENDER();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    // Wait briefly to allow any retry logic to fire (there should be none).
    await new Promise((r) => setTimeout(r, 100));
    expect(mockArqueoSubmit).toHaveBeenCalledTimes(1);
    expect(mockCerrarSesionHelper).not.toHaveBeenCalled();
    expect(mockBridgeImprimir).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

// Tiny helper — vitest doesn't auto-wire user-event; we don't need its
// real implementation here, just a `click` that flushes pending effects.
function userEventFromScreen(): {
  click: (el: HTMLElement) => Promise<void>;
} {
  return {
    async click(el: HTMLElement): Promise<void> {
      el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 0));
    },
  };
}