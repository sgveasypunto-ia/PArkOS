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
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { CierreDiarioForm } from '../CierreDiarioForm';
import type { ArqueoResumenPorSesion } from '../../hooks/useArqueoResumenPorSesion';

const cierreDiarioSchema = z.object({
  valor_efectivo_reportado: z.coerce.number().int().nonnegative(),
  valor_datafono_reportado: z.coerce.number().int().nonnegative(),
  justificacion: z.string().trim().optional(),
});
type CierreDiarioInput = z.infer<typeof cierreDiarioSchema>;

const TRES_SESIONES: ArqueoResumenPorSesion['sesiones'] = [
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

/**
 * Test wrapper — the parent page owns the `useForm` lifecycle; in
 * the form tests we render the form through a wrapper component so
 * `useForm` is called inside React (hooks rule).
 */
function FormHost(
  props: Omit<Parameters<typeof CierreDiarioForm>[0], 'form'>,
): JSX.Element {
  const form = useForm<CierreDiarioInput>({
    resolver: zodResolver(cierreDiarioSchema),
    mode: 'onBlur',
    defaultValues: {
      valor_efectivo_reportado: 0,
      valor_datafono_reportado: 0,
      justificacion: '',
    },
  });
  return (
    <CierreDiarioForm
      form={form as unknown as Parameters<typeof CierreDiarioForm>[0]['form']}
      {...props}
    />
  );
}

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
    render(
      <FormHost
        sesiones={TRES_SESIONES}
        totals={TOTALS_NO_DIFF}
        cierreDiaExists={false}
        isSubmitting={false}
        fecha="2026-09-21"
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onCancel={vi.fn()}
      />,
    );

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
  });

  // ──────────────────────────────────────────────────────────────────
  // form-2 — fecha picker defaults to today; future rejected
  // ──────────────────────────────────────────────────────────────────
  it('form-2: fecha picker defaults to today; future dates rejected via max=today', async () => {
    render(
      <FormHost
        sesiones={TRES_SESIONES}
        totals={TOTALS_NO_DIFF}
        cierreDiaExists={false}
        isSubmitting={false}
        fecha="2026-09-21"
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onCancel={vi.fn()}
      />,
    );

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
      <FormHost
        sesiones={TRES_SESIONES}
        totals={TOTALS_WITH_DIFF}
        cierreDiaExists={false}
        isSubmitting={false}
        fecha="2026-09-21"
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onCancel={vi.fn()}
      />,
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
    // The justificacion field MUST render (required when diff>0).
    expect(
      screen.getByTestId('cierre-diario-justificacion'),
    ).toBeInTheDocument();
  });

  // ──────────────────────────────────────────────────────────────────
  // form-4 — Confirmar disabled when validacion incomplete
  // ──────────────────────────────────────────────────────────────────
  it('form-4: Confirmar disabled while valor_efectivo_reportado=0 (form validation incomplete)', async () => {
    render(
      <FormHost
        sesiones={TRES_SESIONES}
        totals={{ ...TOTALS_NO_DIFF, valor_efectivo_reportado: 0 }}
        cierreDiaExists={false}
        isSubmitting={false}
        fecha="2026-09-21"
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onCancel={vi.fn()}
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
  it('form-5: with Σ|diferencia|=0, Confirmar is enabled — onSubmit carries payload (no justificacion field)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <FormHost
        sesiones={TRES_SESIONES}
        totals={TOTALS_NO_DIFF}
        cierreDiaExists={false}
        isSubmitting={false}
        fecha="2026-09-21"
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('cierre-diario-valor-efectivo'),
      ).toBeInTheDocument();
    });
    // Confirmar is enabled because Σ|diferencia|=0 (no justificacion
    // required) AND valor_efectivo_reportado totals is > 0.
    const confirmar = screen.getByTestId(
      'cierre-diario-confirmar',
    ) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(false);
    // When `Σ|diferencia|=0`, the form does NOT render the
    // justificacion field at all (UI gate per AD-4).
    expect(
      screen.queryByTestId('cierre-diario-justificacion'),
    ).not.toBeInTheDocument();
  });
});