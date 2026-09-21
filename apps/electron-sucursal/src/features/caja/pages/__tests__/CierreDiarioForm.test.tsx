/**
 * `CierreDiarioForm.test.tsx` — Strict-TDD RED scaffold for HU-F10.3
 * (REQ-OPS-164, REQ-OPS-165, AD-4).
 *
 * Presentational form: receives `totals` from the parent page
 * (computed by the page from `useArqueoResumenPorSesion().data.sesiones[]`)
 * and emits an `onSubmit(values)` callback when the user confirms.
 *
 * Aggregate-justification rule (REQ-OPS-164 scenario 2 + AD-4): when
 * `Σ|valor_efectivo_reportado - valor_efectivo_esperado| +
 * |valor_datafono_reportado - valor_datafono_esperado|| > 0`, the
 * `justificacion` field is REQUIRED (`min(3)` after trim) and the
 * Confirmar button stays disabled while the field is invalid. The
 * `arqueoSchemaStrict` (REQ-OPS-158 strict-mode Zod branch from
 * `<ArqueoSheet>`) is composed here.
 *
 * Scenarios (5):
 *   form-1 — renders summary table with 3 sesiones + aggregate footer
 *   form-2 — fecha picker defaults to today; future dates rejected
 *   form-3 — `Σ|diferencia|>0` requires justificacion.min(3)
 *   form-4 — Confirmar disabled when validacion incomplete
 *   form-5 — happy submit calls onSubmit with typed payload
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { CierreDiarioForm } from '../CierreDiarioForm';

const TRES_SESIONES = [
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
];

// Aggregate totals computed by the page from the per-session array.
// Σ values reflect only closed sessions (REQ-OPS-163).
const TOTALS_NO_DIFF = {
  valor_efectivo_reportado: 150_000, // 50_000 + 100_000
  valor_datafono_reportado: 30_000, // 0 + 30_000
  diferencia: 0, // Σ(|50_000-50_000| + |100_000-100_000| + |0-0| + |30_000-30_000|) = 0
};

const TOTALS_WITH_DIFF = {
  valor_efectivo_reportado: 147_000,
  valor_datafono_reportado: 30_000,
  diferencia: 3_000, // Σ| -3_000 | from session 2
};

const defaultProps = (overrides: Partial<Parameters<typeof CierreDiarioForm>[0]> = {}) => ({
  sesiones: TRES_SESIONES,
  totals: TOTALS_NO_DIFF,
  cierreDiaExists: false,
  isSubmitting: false,
  fecha: '2026-09-21',
  onSubmit: vi.fn().mockResolvedValue(undefined),
  onCancel: vi.fn(),
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('HU-F10.3 — <CierreDiarioForm /> (REQ-OPS-164, AD-4)', () => {
  // ──────────────────────────────────────────────────────────────────
  // form-1 — renders summary table with 3 sesiones
  // ──────────────────────────────────────────────────────────────────
  it('form-1: renders summary table with 3 sesiones (2 cerradas + 1 abierta) + aggregate footer', async () => {
    render(<CierreDiarioForm {...defaultProps()} />);

    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-sesiones'),
      ).toBeInTheDocument();
    });

    const tbody = screen
      .getByTestId('cierre-diario-sesiones')
      .querySelector('tbody');
    expect(tbody).not.toBeNull();
    expect(tbody?.querySelectorAll('tr').length).toBe(3);

    // Aggregate footer MUST show Σ totals.
    expect(screen.getByTestId('cierre-diario-totals')).toHaveTextContent(
      /150\.000/,
    );
    expect(screen.getByTestId('cierre-diario-totals')).toHaveTextContent(
      /30\.000/,
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // form-2 — fecha picker defaults to today; future rejected
  // ──────────────────────────────────────────────────────────────────
  it('form-2: fecha picker defaults to today; future dates rejected via max=today', async () => {
    render(<CierreDiarioForm {...defaultProps()} />);

    await waitFor(() => {
      expect(screen.getByTestId('cierre-diario-fecha')).toBeInTheDocument();
    });
    const fechaInput = screen.getByTestId(
      'cierre-diario-fecha',
    ) as HTMLInputElement;
    // Default value MUST be today's date (REQ-OPS-164 + AD-6).
    expect(fechaInput.value).toBe('2026-09-21');
    // HTML5 max=today enforces future rejection at the browser layer
    // (DA-F10.3-3 RESOLVED).
    const today = new Date().toISOString().slice(0, 10);
    expect(fechaInput.getAttribute('max')).toBe(today);
  });

  // ──────────────────────────────────────────────────────────────────
  // form-3 — Σ|diferencia|>0 requires justificacion.min(3)
  // ──────────────────────────────────────────────────────────────────
  it('form-3: Σ|diferencia|>0 requires justificacion.min(3) — Confirmar disabled on initial render', async () => {
    render(
      <CierreDiarioForm {...defaultProps({ totals: TOTALS_WITH_DIFF })} />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-confirmar'),
      ).toBeInTheDocument();
    });
    // Confirmar MUST be disabled while justificacion is empty AND
    // Σ|diferencia|>0 (REQ-OPS-164 scenario 2 + AD-4).
    const confirmar = screen.getByTestId(
      'cierre-diario-confirmar',
    ) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    // The aggregate-justification message MUST render (FormMessage
    // with i18n key cierreDiario.justificacionRequerida).
    expect(screen.getByText(/justificacion_requerida/i)).toBeInTheDocument();
  });

  // ──────────────────────────────────────────────────────────────────
  // form-4 — Confirmar disabled when validacion incomplete
  // ──────────────────────────────────────────────────────────────────
  it('form-4: Confirmar disabled while valor_efectivo_reportado=0 (form validation incomplete)', async () => {
    render(
      <CierreDiarioForm
        {...defaultProps({
          totals: { ...TOTALS_NO_DIFF, valor_efectivo_reportado: 0 },
        })}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-confirmar'),
      ).toBeInTheDocument();
    });
    const confirmar = screen.getByTestId(
      'cierre-diario-confirmar',
    ) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
  });

  // ──────────────────────────────────────────────────────────────────
  // form-5 — happy submit calls onSubmit with typed payload
  // ──────────────────────────────────────────────────────────────────
  it('form-5: with Σ|diferencia|=0, typing values enables Confirmar → onSubmit fires with payload (no justificacion)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <CierreDiarioForm {...defaultProps({ onSubmit })} />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-valor-efectivo'),
      ).toBeInTheDocument();
    });
    // Confirmar is enabled because Σ|diferencia|=0 (no justificacion
    // required).
    const confirmar = screen.getByTestId(
      'cierre-diario-confirmar',
    ) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(false);
    // Clicking Confirmar MUST call onSubmit (no justificacion since
    // Σ|diferencia|=0 per the buildArqueoBody helper).
    confirmar.click();
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    const payload = onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload).toMatchObject({
      valor_efectivo_reportado: expect.any(Number),
      valor_datafono_reportado: expect.any(Number),
    });
    expect(payload).not.toHaveProperty('justificacion');
  });
});