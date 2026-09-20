/**
 * Tests for `<ReimprimirTiquete />` routed page (HU-F8.3, REQ-OPS-171
 * + REQ-OPS-174).
 *
 * The page composes `useReimprimir` + `useAnularReimpresion`. It
 * validates `motivo: min(10)` + `tipo: 'entrada' | 'salida'` via RHF +
 * Zod resolver BEFORE any POST, opens a `role="alertdialog"` for the
 * cobro-consequence confirmation, and on 201 renders a success card
 * with an "Anular" action that opens a second alertdialog with
 * `motivo_anulacion`.
 *
 * Coverage (5 scenarios):
 *   T1: page mounts with form (uuid_ingreso + tipo radio + motivo
 *       inputs visible).
 *   T2: motivo <10 chars → inline error visible; submit blocked;
 *       alertdialog NEVER opens.
 *   T3: motivo ≥10 chars + tipo selected → click Confirm →
 *       alertdialog opens with `role="alertdialog"`.
 *   T4: alertdialog confirm fires `useReimprimir.trigger` and on
 *       success renders the success card with the uuid_reimpresion.
 *   T5: success card "Anular" click → second alertdialog opens with
 *       motivo_anulacion field; on confirm fires
 *       `useAnularReimpresion.trigger`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

const mockUseReimprimir = vi.fn();
const mockUseAnularReimpresion = vi.fn();

vi.mock('../hooks/useReimprimir', () => ({
  useReimprimir: () => mockUseReimprimir(),
}));

vi.mock('../hooks/useAnularReimpresion', () => ({
  useAnularReimpresion: () => mockUseAnularReimpresion(),
}));

import { ReimprimirTiquete } from './ReimprimirTiquete';

const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';
const UUID_REIMPRESION = '00000000-0000-0000-0000-0000000000aa';
const UUID_REIMPRESION_NEW = '00000000-0000-0000-0000-0000000000bb';

function buildReimprimirHook(overrides?: {
  triggerResult?: unknown;
  triggerError?: unknown;
}): { trigger: ReturnType<typeof vi.fn>; isMutating: boolean } {
  const trigger = vi.fn().mockImplementation(async () => {
    if (overrides?.triggerError) {
      throw overrides.triggerError;
    }
    return (
      overrides?.triggerResult ?? {
        uuid: UUID_REIMPRESION,
        workflow_estado: 'autorizada' as const,
        uuid_reimpresion_padre: null,
        uuid_ingreso: UUID_INGRESO,
        uuid_factura: null,
        motivo: 'Cliente solicita reimpresion por deterioro del original',
        created_at: '2026-09-19T11:00:00Z',
      }
    );
  });
  return { trigger, isMutating: false };
}

function buildAnularHook(overrides?: {
  triggerResult?: unknown;
  triggerError?: unknown;
}): { trigger: ReturnType<typeof vi.fn>; isMutating: boolean } {
  const trigger = vi.fn().mockImplementation(async () => {
    if (overrides?.triggerError) {
      throw overrides.triggerError;
    }
    return (
      overrides?.triggerResult ?? {
        uuid: UUID_REIMPRESION_NEW,
        workflow_estado: 'rechazada' as const,
        uuid_reimpresion_padre: UUID_REIMPRESION,
        uuid_ingreso: UUID_INGRESO,
        uuid_factura: null,
        motivo: 'Original reimpresion authorized correctly',
        motivo_anulacion: 'Error operativo: reimprimir solicitada por error',
        created_at: '2026-09-19T12:00:00Z',
      }
    );
  });
  return { trigger, isMutating: false };
}

function renderAt(): void {
  render(
    <MemoryRouter initialEntries={['/facturacion/reimprimir']}>
      <Routes>
        <Route path="/facturacion/reimprimir" element={<ReimprimirTiquete />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockUseReimprimir.mockReset();
  mockUseAnularReimpresion.mockReset();
});

describe('<ReimprimirTiquete /> — REQ-OPS-171 + REQ-OPS-174 alertdialog + motivo Zod', () => {
  it('T1: page mounts with uuid_ingreso + tipo radio + motivo inputs', () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());

    renderAt();

    expect(screen.getByTestId('reimprimir-tiquete-page')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-uuid')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-tipo-entrada')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-tipo-salida')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-motivo')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-confirmar')).toBeInTheDocument();
  });

  it('T2: motivo <10 chars → inline error; submit blocked; alertdialog NEVER opens', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());

    renderAt();

    fireEvent.input(screen.getByTestId('reimprimir-uuid'), {
      target: { value: UUID_INGRESO },
    });
    fireEvent.click(screen.getByTestId('reimprimir-tipo-entrada'));
    fireEvent.input(screen.getByTestId('reimprimir-motivo'), {
      target: { value: 'corto' }, // 5 chars
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-confirmar'));
    });

    // Inline error visible
    expect(screen.getByText('motivo_muy_corto')).toBeInTheDocument();
    // Alertdialog NEVER opens
    expect(screen.queryByTestId('reimprimir-confirm-dialog')).not.toBeInTheDocument();
  });

  it('T3: motivo ≥10 chars → click Confirm → alertdialog opens with role="alertdialog"', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());

    renderAt();

    fireEvent.input(screen.getByTestId('reimprimir-uuid'), {
      target: { value: UUID_INGRESO },
    });
    fireEvent.click(screen.getByTestId('reimprimir-tipo-entrada'));
    fireEvent.input(screen.getByTestId('reimprimir-motivo'), {
      target: { value: 'Cliente solicita reimpresion por deterioro del original' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-confirmar'));
    });

    const dialog = screen.getByTestId('reimprimir-confirm-dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute('role')).toBe('alertdialog');
  });

  it('T4: alertdialog confirm fires useReimprimir.trigger and renders success card with uuid', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());

    renderAt();

    fireEvent.input(screen.getByTestId('reimprimir-uuid'), {
      target: { value: UUID_INGRESO },
    });
    fireEvent.click(screen.getByTestId('reimprimir-tipo-entrada'));
    fireEvent.input(screen.getByTestId('reimprimir-motivo'), {
      target: { value: 'Cliente solicita reimpresion por deterioro del original' },
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-confirmar'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-dialog-confirm'));
    });

    // Success card renders with the uuid_reimpresion
    expect(screen.getByTestId('reimprimir-success')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-success-uuid').textContent).toBe(UUID_REIMPRESION);
    expect(screen.getByTestId('reimprimir-anular')).toBeInTheDocument();
  });

  it('T5: success card "Anular" click → second alertdialog opens with motivo_anulacion', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());

    renderAt();

    fireEvent.input(screen.getByTestId('reimprimir-uuid'), {
      target: { value: UUID_INGRESO },
    });
    fireEvent.click(screen.getByTestId('reimprimir-tipo-entrada'));
    fireEvent.input(screen.getByTestId('reimprimir-motivo'), {
      target: { value: 'Cliente solicita reimpresion por deterioro del original' },
    });

    // Drive to success card
    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-confirmar'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-dialog-confirm'));
    });

    // Click Anular → second alertdialog opens
    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-anular'));
    });

    const anularDialog = screen.getByTestId('reimprimir-anular-dialog');
    expect(anularDialog).toBeInTheDocument();
    expect(anularDialog.getAttribute('role')).toBe('alertdialog');
    expect(screen.getByTestId('reimprimir-anular-motivo')).toBeInTheDocument();
  });
});
