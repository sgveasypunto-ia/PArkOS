/**
 * Tests for `<FacturaDetalle />` routed page (HU-F8.2, REQ-OPS-167/168/170).
 *
 * The page is a thin container over `useFacturaElectronica` +
 * `useReintentarFE`. It reads `uuid` from the URL (`useParams`), renders
 * the localized `estado`, surfaces CUFE only when `aceptado`, exposes
 * the "Reintentar" button only when `rechazado` (disabled while
 * `isMutating`), and surfaces the `NumeracionAgotadaError` banner with
 * `role="alert"` (WCAG 2.1 AA).
 *
 * Coverage:
 *   T1: estado='pendiente' → "Pendiente" label visible, NO CUFE, NO
 *       "Reintentar" button.
 *   T2: estado='aceptado' → "Aceptado" label visible + CUFE visible.
 *   T3: estado='rechazado' → "Rechazado" label visible + "Reintentar"
 *       button visible.
 *   T4: click "Reintentar" → `useReintentarFE.trigger` invoked with
 *       the UUID from the URL.
 *   T5: `useReintentarFE.trigger` throws `NumeracionAgotadaError` →
 *       banner with `role="alert"` and the localized copy.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

const mockUseFacturaElectronica = vi.fn();
const mockUseReintentarFE = vi.fn();

vi.mock('../hooks/useFacturaElectronica', () => ({
  useFacturaElectronica: (uuid: string | null) => mockUseFacturaElectronica(uuid),
}));

vi.mock('../hooks/useReintentarFE', () => ({
  useReintentarFE: () => mockUseReintentarFE(),
  NumeracionAgotadaError: class extends Error {
    public readonly status = 409;
    public readonly code = 'numeracion_agotada';
    constructor() {
      super('numeracion_agotada');
      this.name = 'NumeracionAgotadaError';
    }
  },
}));

import { FacturaDetalle } from './FacturaDetalle';
import { NumeracionAgotadaError } from '../hooks/useReintentarFE';

const UUID_FE = '00000000-0000-0000-0000-0000000000fe';
const UUID_ENVIO = '00000000-0000-0000-0000-0000000000a1';
const UUID_ENVIO_PADRE = '00000000-0000-0000-0000-0000000000a0';
const CUFE = 'cufe-test-abcdef0123456789';

function buildHookDefaults(overrides?: {
  triggerResult?: unknown;
  triggerError?: unknown;
}): { trigger: ReturnType<typeof vi.fn>; isMutating: boolean } {
  const trigger = vi.fn().mockImplementation(async () => {
    if (overrides?.triggerError) {
      throw overrides.triggerError;
    }
    return (
      overrides?.triggerResult ?? {
        uuid_envio: UUID_ENVIO,
        estado: 'pendiente' as const,
        uuid_envio_padre: UUID_ENVIO_PADRE,
      }
    );
  });
  return { trigger, isMutating: false };
}

function renderAt(uuid: string): void {
  render(
    <MemoryRouter initialEntries={[`/factura-electronica/${uuid}`]}>
      <Routes>
        <Route path="/factura-electronica/:uuid" element={<FacturaDetalle />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockUseFacturaElectronica.mockReset();
  mockUseReintentarFE.mockReset();
});

describe('<FacturaDetalle /> — REQ-OPS-167/168/170 FE routed page', () => {
  it('T1: estado=pendiente → "Pendiente" label, no CUFE, no Reintentar button', () => {
    mockUseFacturaElectronica.mockReturnValue({
      data: {
        uuid_factura_electronica: UUID_FE,
        uuid_factura: '00000000-0000-0000-0000-000000000fff',
        estado_dian: 'pendiente',
        respuesta_proveedor: null,
        actualizado_en: '2026-09-19T10:00:00Z',
      },
      error: undefined,
    });
    mockUseReintentarFE.mockReturnValue(buildHookDefaults());

    renderAt(UUID_FE);

    expect(screen.getByTestId('fe-estado')).toHaveTextContent(/Pendiente/i);
    expect(screen.queryByTestId('fe-cufe')).toBeNull();
    expect(screen.queryByTestId('fe-reintentar')).toBeNull();
    expect(screen.queryByTestId('fe-banner-numeracion-agotada')).toBeNull();
  });

  it('T2: estado=aceptado → "Aceptado" label + CUFE visible, no Reintentar button', () => {
    mockUseFacturaElectronica.mockReturnValue({
      data: {
        uuid_factura_electronica: UUID_FE,
        uuid_factura: '00000000-0000-0000-0000-000000000fff',
        estado_dian: 'aceptado',
        respuesta_proveedor: { cufe: CUFE, motivo: null, reportado_en: '2026-09-19T10:01:00Z' },
        actualizado_en: '2026-09-19T10:01:00Z',
      },
      error: undefined,
    });
    mockUseReintentarFE.mockReturnValue(buildHookDefaults());

    renderAt(UUID_FE);

    expect(screen.getByTestId('fe-estado')).toHaveTextContent(/Aceptado/i);
    expect(screen.getByTestId('fe-cufe')).toHaveTextContent(CUFE);
    expect(screen.queryByTestId('fe-reintentar')).toBeNull();
  });

  it('T3: estado=rechazado → "Rechazado" label + "Reintentar" button visible', () => {
    mockUseFacturaElectronica.mockReturnValue({
      data: {
        uuid_factura_electronica: UUID_FE,
        uuid_factura: '00000000-0000-0000-0000-000000000fff',
        estado_dian: 'rechazado',
        respuesta_proveedor: { cufe: null, motivo: 'range_exhausted', reportado_en: null },
        actualizado_en: '2026-09-19T10:02:00Z',
      },
      error: undefined,
    });
    mockUseReintentarFE.mockReturnValue(buildHookDefaults());

    renderAt(UUID_FE);

    expect(screen.getByTestId('fe-estado')).toHaveTextContent(/Rechazado/i);
    const btn = screen.getByTestId('fe-reintentar');
    expect(btn).toBeInTheDocument();
    expect(btn).not.toBeDisabled();
  });

  it('T4: click "Reintentar" → useReintentarFE.trigger called with uuid from URL', async () => {
    mockUseFacturaElectronica.mockReturnValue({
      data: {
        uuid_factura_electronica: UUID_FE,
        uuid_factura: '00000000-0000-0000-0000-000000000fff',
        estado_dian: 'rechazado',
        respuesta_proveedor: null,
        actualizado_en: '2026-09-19T10:02:00Z',
      },
      error: undefined,
    });
    const { trigger } = buildHookDefaults();
    mockUseReintentarFE.mockReturnValue({ trigger, isMutating: false });

    renderAt(UUID_FE);

    const btn = screen.getByTestId('fe-reintentar');
    await act(async () => {
      fireEvent.click(btn);
    });

    expect(trigger).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveBeenCalledWith(UUID_FE);
    expect(screen.queryByTestId('fe-banner-numeracion-agotada')).toBeNull();
  });

  it('T5: trigger throws NumeracionAgotadaError → banner role="alert" with localized copy', async () => {
    mockUseFacturaElectronica.mockReturnValue({
      data: {
        uuid_factura_electronica: UUID_FE,
        uuid_factura: '00000000-0000-0000-0000-000000000fff',
        estado_dian: 'rechazado',
        respuesta_proveedor: null,
        actualizado_en: '2026-09-19T10:02:00Z',
      },
      error: undefined,
    });
    mockUseReintentarFE.mockReturnValue(
      buildHookDefaults({ triggerError: new NumeracionAgotadaError() }),
    );

    renderAt(UUID_FE);

    const btn = screen.getByTestId('fe-reintentar');
    await act(async () => {
      fireEvent.click(btn);
    });

    const banner = screen.getByTestId('fe-banner-numeracion-agotada');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner.textContent).toMatch(/Numeración agotada/i);
  });
});
