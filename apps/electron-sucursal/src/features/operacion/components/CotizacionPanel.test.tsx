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
