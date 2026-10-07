/**
 * Tests for `<CotizacionPanel />` (HU-F7.1 T3 — pure presentational).
 *
 * Coverage:
 *   T1: rotación — render with full desglose (cobrar:true) + formatCOP
 *       values asserted as literal `"$ 48.790"` (es-CO, no decimals).
 *   T2: mensualidad — render with cobrar:false + motivo. No `<dl>`
 *       rendered; only the mensualidad banner.
 *   T3: countdown red-threshold — render with `secondsLeft={119}`;
 *       the countdown div has `role="alert"`, `<AlertTriangle />` icon,
 *       and `text-destructive` class.
 *   T4: click handlers — `onConfirmar` and `onRecalcular` fire on click.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import type { Cotizacion } from '../hooks/useCotizacion';
import { CotizacionPanel } from './CotizacionPanel';

const TARIFA_UUID = '00000000-0000-0000-0000-0000000000aa';

const cotizacionRotacion: Cotizacion = {
  cobrar: true,
  subtotal: 41000,
  iva: 7790,
  total: 48790,
  tiempo_minutos: 32.5,
  tarifa_uuid: TARIFA_UUID,
  vigente_hasta: '2026-09-19T11:00:00Z',
};

const cotizacionMensualidad: Cotizacion = {
  cobrar: false,
  motivo: 'mensualidad_vigente',
  // MIGRATION 0050 (operator directive 2026-09-24): full fiscal
  // breakdown + discount concept, now required even when cobrar=false.
  subtotal: 8100,
  iva: 1900,
  total: 10000,
  tiempo_minutos: 90,
  tarifa_uuid: TARIFA_UUID,
  vigente_hasta: '2026-09-19T11:00:00Z',
  uuid_subscripcion_cliente: '00000000-0000-0000-0000-0000000000ab',
  concepto_descuento: 'Plan Oro',
};

describe('<CotizacionPanel /> — pure presentational (REQ-OPS-143)', () => {
  it('T1: rotación renderiza <dl> con formatCOP para subtotal/iva/total', () => {
    render(
      <CotizacionPanel
        data={cotizacionRotacion}
        secondsLeft={900}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    const dl = screen.getByTestId('cotizacion-dl');
    expect(dl).toBeInTheDocument();
    // formatCOP(48790) → "$ 48.790" (es-CO, no decimals).
    expect(dl.textContent).toContain('48.790');
    expect(dl.textContent).toContain('41.000');
    expect(dl.textContent).toContain('7.790');
  });

  it('T1b: subtotal e IVA muestran centavos para que reconcilien con el total', () => {
    render(
      <CotizacionPanel
        data={{ ...cotizacionRotacion, subtotal: 1260.5, iva: 239.5, total: 1500 }}
        secondsLeft={900}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    const dl = screen.getByTestId('cotizacion-dl');
    expect(dl.textContent).toContain('1.260,50');
    expect(dl.textContent).toContain('239,50');
    // El total conserva el formato de pesos enteros del resto de la UI.
    expect(screen.getByTestId('cotizacion-total').textContent).toMatch(/1\.500$/);
  });

  it('T2: mensualidad renderiza banner sin <dl>', () => {
    render(
      <CotizacionPanel
        data={cotizacionMensualidad}
        secondsLeft={900}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    expect(screen.getByTestId('cotizacion-mensualidad-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('cotizacion-dl')).not.toBeInTheDocument();
  });

  it('T3: countdown red-threshold (secondsLeft<120) → role="alert" + AlertTriangle icon', () => {
    render(
      <CotizacionPanel
        data={cotizacionRotacion}
        secondsLeft={119}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    const countdown = screen.getByTestId('cotizacion-countdown');
    expect(countdown.getAttribute('role')).toBe('alert');
    // text-destructive is the shadcn semantic class.
    expect(countdown.className).toContain('text-destructive');
  });

  it('T4: onConfirmar y onRecalcular disparan al click', () => {
    const onConfirmar = vi.fn();
    const onRecalcular = vi.fn();
    render(
      <CotizacionPanel
        data={cotizacionRotacion}
        secondsLeft={900}
        onConfirmar={onConfirmar}
        onRecalcular={onRecalcular}
      />,
    );
    fireEvent.click(screen.getByTestId('cotizacion-confirmar'));
    expect(onConfirmar).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('cotizacion-recalcular'));
    expect(onRecalcular).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it('T5: HTTP 500 iva_no_configurado → banner no-bloqueante (REQ-OPS-148)', () => {
    const error = new ParkosHttpError(
      500,
      JSON.stringify({ error: 'iva_no_configurado' }),
      '/api/v1/operacion/cotizar',
    );
    render(
      <CotizacionPanel
        data={undefined}
        error={error}
        secondsLeft={900}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    // Banner present, no <dl>, no countdown UI for rotation.
    expect(screen.getByTestId('cotizacion-error-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('cotizacion-dl')).not.toBeInTheDocument();
    expect(screen.queryByTestId('cotizacion-mensualidad-banner')).not.toBeInTheDocument();
    // Localized message references IVA not configured.
    const banner = screen.getByTestId('cotizacion-error-banner');
    expect(banner.textContent).toMatch(/IVA/i);
  });
});

describe('<CotizacionPanel /> — placeholder con tarifa_uuid nil (L2)', () => {
  it('no consulta la tarifa y no muestra el uuid nil ni error', async () => {
    const getSpy = vi.fn();
    vi.resetModules();
    vi.doMock('../../catalogos/hooks/useTarifaByUuid', async (orig) => ({
      ...(await orig<typeof import('../../catalogos/hooks/useTarifaByUuid')>()),
      useTarifaByUuid: (uuid: string | null) => {
        getSpy(uuid);
        return { tarifa: null, isLoading: false, error: undefined, refresh: vi.fn() };
      },
    }));
    const { CotizacionPanel: Panel } = await import('./CotizacionPanel');
    render(
      <Panel
        data={{
          ...cotizacionRotacion,
          tarifa_uuid: '00000000-0000-0000-0000-000000000000',
        }}
        secondsLeft={900}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    expect(getSpy).toHaveBeenCalledWith(null);
    expect(screen.queryByText('00000000-0000-0000-0000-000000000000')).not.toBeInTheDocument();
    vi.doUnmock('../../catalogos/hooks/useTarifaByUuid');
  });
});

describe('<CotizacionPanel /> — unidad real de la tarifa (FC2)', () => {
  const HORA = '12e3886a-7059-47ee-bdb2-aa5fb1272bea';
  const FRACCION = 'c41b6602-f7b2-437d-bcfc-0462cd385eda';

  async function detalleCon(uuidTipoTarifa: string | null, valor: number): Promise<string> {
    vi.resetModules();
    vi.doMock('../../catalogos/hooks/useTarifaByUuid', async (orig) => ({
      ...(await orig<typeof import('../../catalogos/hooks/useTarifaByUuid')>()),
      useTarifaByUuid: () => ({
        tarifa: {
          uuid: TARIFA_UUID,
          uuid_sucursal: null,
          uuid_tipo_vehiculo: null,
          uuid_tipo_tarifa: uuidTipoTarifa,
          valor,
          valor_plena: null,
          vigente_desde: '2026-10-05T14:35:00',
          vigente_hasta: null,
          estado: 'activo',
          created_at: '2026-10-05T19:37:36',
          created_by: null,
          sync_status: null,
        },
        isLoading: false,
        error: undefined,
        refresh: vi.fn(),
      }),
    }));
    const { CotizacionPanel: Panel } = await import('./CotizacionPanel');
    render(
      <Panel
        data={cotizacionRotacion}
        secondsLeft={900}
        onConfirmar={vi.fn()}
        onRecalcular={vi.fn()}
      />,
    );
    const texto = screen.getByTestId('cotizacion-tarifa-detalle').textContent ?? '';
    vi.doUnmock('../../catalogos/hooks/useTarifaByUuid');
    return texto;
  }

  it('tarifa de modalidad hora → "/hora", no "/min"', async () => {
    cleanup();
    const texto = await detalleCon(HORA, 1500);
    expect(texto).toMatch(/1\.500\/hora/);
    expect(texto).not.toContain('/min');
  });

  it('tarifa de modalidad fracción → "/fracción"', async () => {
    cleanup();
    const texto = await detalleCon(FRACCION, 100);
    expect(texto).toMatch(/100\/fracción/);
  });

  it('modalidad desconocida → valor sin unidad inventada', async () => {
    cleanup();
    const texto = await detalleCon(null, 100);
    expect(texto).not.toContain('/min');
    expect(texto).not.toContain('/hora');
  });
});
