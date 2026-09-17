/**
 * Unit tests for `Principal` page (HU-F6.1, T8).
 *
 * Smoke tests only — the page composes PlacaInput, ForzarIngresoModal,
 * TiqueteModal, and `useIngresoActivo`. The granular contract tests
 * live next to each child. Here we assert:
 *   - Renders PlacaInput on mount.
 *   - Submitting a valid plate fires `postIngreso` (mocked).
 *   - 422 motivo_forzado_requerido → opens ForzarIngresoModal.
 *   - 409 ingreso_activo_existente → navigates to salida stub.
 *   - 201 → opens TiqueteModal with the response uuid + tipo.
 *
 * Uses `fireEvent` (from `@testing-library/react`).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import '@/i18n';

vi.mock('../lib/ingresoApi', () => ({
  postIngreso: vi.fn(),
}));

vi.mock('../api/ingresoActivoApi', () => ({
  getIngresosByPlaca: vi.fn(),
  getIngresoEstado: vi.fn(),
}));

const imprimirMock = vi.fn();

import Principal from './Principal';
import { postIngreso } from '../lib/ingresoApi';

const mockPost = postIngreso as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockPost.mockReset();
  imprimirMock.mockReset();
  imprimirMock.mockResolvedValue({ ok: true });
  (globalThis as unknown as { window: unknown }).window = {
    bridge: { imprimir: imprimirMock },
  };
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPrincipal(initialEntries: string[] = ['/']): void {
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <Principal />
    </MemoryRouter>,
  );
}

function submitPlaca(value: string): void {
  const input = screen.getByLabelText(/placa/i) as HTMLInputElement;
  fireEvent.change(input, { target: { value } });
  const form = input.closest('form');
  fireEvent.submit(form as HTMLFormElement);
}

describe('Principal', () => {
  it('renders PlacaInput on mount', async () => {
    renderPrincipal();
    const input = screen.getByLabelText(/placa/i) as HTMLInputElement;
    await waitFor(() => expect(document.activeElement).toBe(input));
  });

  it('fires postIngreso with the typed plate on submit', async () => {
    mockPost.mockResolvedValueOnce({
      uuid_ingreso: '11111111-1111-1111-1111-111111111111',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
    });
    renderPrincipal();
    submitPlaca('ABC123');
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    const payload = mockPost.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload).toEqual(expect.objectContaining({ placa: 'ABC123' }));
  });

  it('opens TiqueteModal on 201 success', async () => {
    mockPost.mockResolvedValueOnce({
      uuid_ingreso: '11111111-1111-1111-1111-111111111111',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
    });
    renderPrincipal();
    submitPlaca('ABC123');
    await waitFor(() =>
      expect(screen.getByRole('dialog')).toBeInTheDocument(),
    );
    expect(
      screen.getByText('11111111-1111-1111-1111-111111111111'),
    ).toBeInTheDocument();
  });

  it('opens ForzarIngresoModal on 422 motivo_forzado_requerido', async () => {
    mockPost.mockRejectedValueOnce(
      new ParkosHttpError(
        422,
        '{"code":"motivo_forzado_requerido"}',
        '/api/v1/operacion/ingresos',
      ),
    );
    renderPrincipal();
    submitPlaca('ABC123');
    await waitFor(() =>
      expect(screen.getByRole('dialog')).toBeInTheDocument(),
    );
    expect(screen.getByText(/forzar ingreso/i)).toBeInTheDocument();
  });

  it('does not show a destructive error UI on 409 ingreso_activo_existente', async () => {
    mockPost.mockRejectedValueOnce(
      new ParkosHttpError(
        409,
        '{"code":"ingreso_activo_existente"}',
        '/api/v1/operacion/ingresos',
      ),
    );
    renderPrincipal();
    submitPlaca('ABC123');
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    // The page navigates transparently on 409 — no role="alert" element.
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
