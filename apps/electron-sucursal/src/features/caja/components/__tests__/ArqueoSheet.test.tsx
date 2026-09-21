/**
 * `ArqueoSheet.test.tsx` — Strict-TDD RED scaffold for HU-F10.2
 * (REQ-OPS-158, AD-1) — the new `requiredMode` prop on `<ArqueoSheet>`.
 *
 * The F10.1 `<ArqueoSheet>` (REQ-OPS-154) shipped with a single
 * `arqueoSchema` that uses `superRefine` to require
 * `justificacion.min(3)` ONLY when `|diferencia|>0` — the lenient
 * path. F10.2 cierre de turno needs a STRICT-MODE branch where
 * `justificacion` is required at the TOP level (not via
 * `superRefine`) and the submit button is DISABLED on initial render
 * while `justificacion.length < 3`.
 *
 * The `requiredMode?: 'parcial' | 'cierre_turno' | 'cierre_dia'`
 * prop discriminates:
 *   - `undefined` (default) → F10.1 lenient path, REGRESSION-CLEAN.
 *   - `'parcial'` → same as `undefined` (F10.1 ArqueoParcial page).
 *   - `'cierre_turno'` → strict-mode Zod variant + button disable.
 *   - `'cierre_dia'` → same as `'cierre_turno'` (F10.3 forward hook).
 *
 * These 2 RED scenarios MUST FAIL on master because the prop is not
 * yet declared. After Commit 2 lands the prop + Zod branch, they go
 * GREEN.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

// Mock the dashboard drawer store so the sheet renders (open=true).
vi.mock('@/store/dashboardDrawerStore', () => ({
  useDashboardDrawerStore: (
    selector: (s: {
      openDrawer: string | null;
      lastAnchorId: string | null;
      open: () => void;
      close: () => void;
    }) => unknown,
  ) =>
    selector({
      openDrawer: 'arqueo',
      lastAnchorId: null,
      open: vi.fn(),
      close: vi.fn(),
    }),
}));

// Mock useArqueo so submit() is observable.
const submitMock = vi.fn();
vi.mock('../hooks/useArqueo', () => ({
  useArqueo: () => ({ submit: submitMock }),
}));

// Mock react-i18next to return the key verbatim so assertions on
// placeholder text are stable across locales.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue ?? key,
  }),
}));

import { ArqueoSheet } from '../ArqueoSheet';

const RENDER_SHEET = (props: {
  requiredMode?: 'parcial' | 'cierre_turno' | 'cierre_dia';
  diferencia?: number;
}): ReturnType<typeof render> =>
  render(
    <ArqueoSheet
      uuid_sesion="sesion-uuid-1"
      requiredMode={props.requiredMode}
      expected={
        props.diferencia === undefined
          ? null
          : {
              valor_esperado_efectivo: 100_000,
              valor_esperado_datafono: 0,
              tolerancia_efectivo: 1_000,
              tolerancia_datafono: 500,
            }
      }
    />,
  );

beforeEach(() => {
  submitMock.mockReset();
  submitMock.mockResolvedValue({ uuid: 'arqueo-uuid-1' });
});

afterEach(() => {
  cleanup();
});

describe('HU-F10.2 — <ArqueoSheet requiredMode> prop (REQ-OPS-158, AD-1)', () => {
  // ────────────────────────────────────────────────────────────────────
  // strict-1 — requiredMode='cierre_turno' + empty justificacion
  //            blocks the submit button on initial render
  // ────────────────────────────────────────────────────────────────────
  it("strict-1: requiredMode='cierre_turno' with empty justificacion keeps the submit button disabled on initial render", () => {
    RENDER_SHEET({
      requiredMode: 'cierre_turno',
      diferencia: -3_000, // outside tolerance → strict-mode required
    });

    // Submit button MUST be disabled BEFORE any user interaction.
    const submitBtn = screen.getByTestId('arqueo-confirmar');
    expect(submitBtn).toBeInTheDocument();
    expect(submitBtn).toBeDisabled();

    // The strict-mode justificacion surface MUST be present
    // (data-testid per spec REQ-OPS-158 scenario 2).
    expect(
      screen.getByTestId('arqueo-required-justificacion'),
    ).toBeInTheDocument();
  });

  // ────────────────────────────────────────────────────────────────────
  // strict-2 — requiredMode='cierre_turno' + justificacion.min(3)
  //            re-enables the submit button
  // ────────────────────────────────────────────────────────────────────
  it("strict-2: requiredMode='cierre_turno' with justificacion.length >= 3 enables the submit button", () => {
    RENDER_SHEET({
      requiredMode: 'cierre_turno',
      diferencia: -3_000,
    });

    // Type a justificacion >= 3 chars → button re-enables.
    // In strict-mode the input's data-testid is `arqueo-required-justificacion`.
    const input = screen.getByTestId('arqueo-required-justificacion');
    input.focus();
    // jsdom-friendly setter so react-hook-form picks up the value.
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set;
    nativeSetter?.call(input, 'Faltante menor en caja');
    input.dispatchEvent(new Event('input', { bubbles: true }));

    const submitBtn = screen.getByTestId('arqueo-confirmar');
    expect(submitBtn).not.toBeDisabled();
  });
});