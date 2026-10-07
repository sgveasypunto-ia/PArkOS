/**
 * Tests for `<RenovarSuscripcionPanel />` (PT-3 renewal flow + PT-1 back).
 *
 *   P1: summary shown, NO plate inputs, default medio = efectivo (no referencia).
 *   P2: confirm -> trigger payload + receipt (FacturaDisplayModal) + onRenovada on close.
 *   P3: datafono requires the voucher; sent as `referencia`.
 *   P4: renovacion_fuera_de_ventana -> clear Spanish message, lists refreshed
 *       (`onStale`) and a NEW attempt id on the next click.
 *   P5: a non-definitive failure keeps the SAME attempt id (safe retry).
 *   P6: "Volver" -> onBack, disabled while the payment is in flight.
 *   P7: pending FE shows the non-blocking notice inside the receipt.
 *   P8: receipt printing never blocks closing (bridge failure swallowed).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string; defaultValue_one?: string; defaultValue_other?: string }) =>
      opts?.defaultValue ?? opts?.defaultValue_other ?? _key,
  }),
}));

const mockTrigger = vi.fn();
const mockIsMutating = vi.fn(() => false);
vi.mock('../hooks/useRenovarSuscripcion', () => ({
  useRenovarSuscripcion: () => ({
    trigger: mockTrigger,
    isMutating: mockIsMutating(),
    error: undefined,
    data: undefined,
    reset: vi.fn(),
  }),
}));

import { instalarBridgeImprimir, textoImpreso, expectDetalleImpuestos } from '../../../lib/print/__tests__/facturaAssert';
import { FACTURA_SUSCRIPCION_120000 } from '../../../lib/print/__tests__/facturaFixtures';
import { RenovacionError } from '../hooks/renovacionErrors';
import { RenovarSuscripcionPanel } from './RenovarSuscripcionPanel';

const TARGET = {
  uuid: '00000000-0000-0000-0000-0000000000a1',
  cliente_nombre: 'Cliente Renovable',
  plan_nombre: 'MENSUAL_AUTO',
  fecha_vencimiento: '2026-10-08',
  dias_restantes: 3,
  placas: ['ABC123', 'DEF456'],
};

const FACTURA = {
  uuid: 'f0000000-0000-0000-0000-000000000001',
  created_at: '2026-10-06T10:00:00.000Z',
  uuid_sucursal: '00000000-0000-0000-0000-0000000000f1',
  uuid_ingreso: null,
  uuid_salida: null,
  numero_recibo: 'suc-20261006-000001',
  subtotal: 800000,
  descuento: 0,
  total: 952000,
  uuid_cliente: null,
  items: [],
  estado: 'pagada' as const,
  medio_pago: 'efectivo' as const,
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  cliente: null,
  datos_sucursal: {
    razon_social: 'Sede Test',
    nit: null,
    direccion: null,
    ciudad: null,
    telefono: null,
    horario: null,
    regimen: null,
  },
  datos_vehiculo: null,
  impuestos: [],
  pagos: [],
  factura_electronica: null,
};

const RESULT = {
  uuid_subscripcion_anterior: TARGET.uuid,
  uuid_subscripcion: '00000000-0000-0000-0000-0000000000b2',
  uuid_cliente: null,
  uuid_sucursal: FACTURA.uuid_sucursal,
  uuid_tipo_subscripcion: '00000000-0000-0000-0000-0000000000c3',
  uuid_vehiculos: [],
  placas: ['ABC123'],
  fecha_inicio_cobertura: '2026-10-08',
  fecha_vencimiento: '2026-11-07',
  dias_restantes: 32,
  renovacion_anticipada: true,
  ventana_renovacion_dias: 10,
  valor_total_plan: 800000,
  total_con_iva: 952000,
  uuid_factura: FACTURA.uuid,
  uuid_factura_electronica: null,
  factura_electronica_error: null,
  factura_electronica_pendiente: false,
  factura: FACTURA,
};

const setup = (over: Partial<Parameters<typeof RenovarSuscripcionPanel>[0]> = {}) => {
  const onBack = vi.fn();
  const onRenovada = vi.fn();
  const onStale = vi.fn();
  render(
    <RenovarSuscripcionPanel
      target={TARGET}
      onBack={onBack}
      onRenovada={onRenovada}
      onStale={onStale}
      {...over}
    />,
  );
  return { onBack, onRenovada, onStale };
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockIsMutating.mockReturnValue(false);
  mockTrigger.mockResolvedValue(RESULT);
});

describe('<RenovarSuscripcionPanel /> — PT-3', () => {
  it('P1: shows the summary, asks for NO plates and defaults to efectivo', () => {
    setup();
    expect(screen.getByTestId('renovar-resumen')).toHaveTextContent('Cliente Renovable');
    expect(screen.getByTestId('renovar-placas')).toHaveTextContent('ABC123 · DEF456');
    expect(screen.getByTestId('renovar-nota')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('ABC123')).not.toBeInTheDocument();
    expect((screen.getByTestId('renovar-medio-pago') as HTMLSelectElement).value).toBe('efectivo');
    expect(screen.queryByTestId('renovar-referencia')).not.toBeInTheDocument();
  });

  it('P2: confirm -> trigger payload, receipt, and onRenovada after closing it', async () => {
    const { onRenovada } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-confirmar'));

    expect(mockTrigger).toHaveBeenCalledTimes(1);
    expect(mockTrigger).toHaveBeenCalledWith(
      expect.objectContaining({
        uuid_subscripcion: TARGET.uuid,
        medio_pago: 'efectivo',
        referencia: null,
        intentoId: expect.any(String),
      }),
    );
    // Receipt (reuses FacturaDisplayModal with `factura`).
    await waitFor(() => expect(screen.getByTestId('factura-display-modal')).toBeInTheDocument());
    expect(screen.getByTestId('factura-display-total')).toHaveTextContent('952.000');
    // No "Volver" once charged.
    expect(screen.queryByTestId('renovar-volver')).not.toBeInTheDocument();
    expect(onRenovada).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('factura-display-cerrar'));
    expect(onRenovada).toHaveBeenCalledTimes(1);
  });

  it('P3: datafono requires the voucher and sends it as referencia', async () => {
    setup();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByTestId('renovar-medio-pago'), 'datafono');
    await user.click(screen.getByTestId('renovar-confirmar'));
    expect(mockTrigger).not.toHaveBeenCalled();
    expect(screen.getByTestId('renovar-error')).toHaveTextContent('voucher');

    await user.type(screen.getByTestId('renovar-referencia'), 'V-778899');
    await user.click(screen.getByTestId('renovar-confirmar'));
    expect(mockTrigger).toHaveBeenCalledWith(
      expect.objectContaining({ medio_pago: 'datafono', referencia: 'V-778899' }),
    );
  });

  it('P4: renovacion_fuera_de_ventana -> clear message, onStale, and a NEW attempt id afterwards', async () => {
    mockTrigger.mockRejectedValueOnce(
      new RenovacionError(409, 'renovacion_fuera_de_ventana', { dias_restantes: 25, ventana_dias: 10 }),
    );
    const { onStale } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-confirmar'));

    expect(screen.getByTestId('renovar-error')).toHaveTextContent('25');
    expect(onStale).toHaveBeenCalledTimes(1);

    await user.click(screen.getByTestId('renovar-confirmar'));
    const first = (mockTrigger.mock.calls[0]?.[0] as { intentoId: string }).intentoId;
    const second = (mockTrigger.mock.calls[1]?.[0] as { intentoId: string }).intentoId;
    expect(second).not.toBe(first);
  });

  it('P5: a non-definitive failure keeps the SAME attempt id (retry replays, never double-charges)', async () => {
    mockTrigger.mockRejectedValueOnce(new Error('network down'));
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-confirmar'));
    expect(screen.getByTestId('renovar-error')).toBeInTheDocument();
    await user.click(screen.getByTestId('renovar-confirmar'));
    const first = (mockTrigger.mock.calls[0]?.[0] as { intentoId: string }).intentoId;
    const second = (mockTrigger.mock.calls[1]?.[0] as { intentoId: string }).intentoId;
    expect(second).toBe(first);
  });

  it('P6: "Volver" calls onBack; it is disabled while the payment is in flight', async () => {
    const { onBack } = setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-volver'));
    expect(onBack).toHaveBeenCalledTimes(1);

    cleanup();
    mockIsMutating.mockReturnValue(true);
    setup();
    expect(screen.getByTestId('renovar-volver')).toBeDisabled();
    expect(screen.getByTestId('renovar-confirmar')).toBeDisabled();
  });

  it('P7: pending FE -> non-blocking "se reintenta sola" notice inside the receipt', async () => {
    mockTrigger.mockResolvedValueOnce({
      ...RESULT,
      factura_electronica_error: 'numeracion_agotada',
      factura_electronica_pendiente: true,
      factura: {
        ...FACTURA,
        factura_electronica_error: 'numeracion_agotada',
        factura_electronica_pendiente: true,
      },
    });
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-confirmar'));
    const warning = await screen.findByTestId('factura-display-warning');
    expect(warning).toHaveTextContent('se reintenta sola');
    expect(warning).toHaveTextContent('numeración');
    // The receipt can still be closed (reprint/close never blocked).
    expect(screen.getByTestId('factura-display-cerrar')).toBeEnabled();
  });

  it('P8: a failing print bridge never blocks closing the receipt', async () => {
    const imprimirFactura = vi.fn(() => {
      throw new Error('printer offline');
    });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { onRenovada } = setup({ imprimirFactura });
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-confirmar'));
    await screen.findByTestId('factura-display-modal');
    await act(async () => {
      fireEvent.click(screen.getByTestId('factura-display-cerrar'));
      await Promise.resolve();
    });
    expect(imprimirFactura).toHaveBeenCalledWith(
      expect.objectContaining({ numero_recibo: FACTURA.numero_recibo }),
    );
    expect(onRenovada).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it('P9: al cerrar el recibo imprime la factura COMPLETA (IVA 19%, base, total), no el envelope incompleto', async () => {
    const imprimir = instalarBridgeImprimir();
    mockTrigger.mockResolvedValue({
      ...RESULT,
      factura: {
        ...FACTURA,
        subtotal: FACTURA_SUSCRIPCION_120000.subtotal,
        total: FACTURA_SUSCRIPCION_120000.total,
        impuestos: FACTURA_SUSCRIPCION_120000.impuestos,
      },
    });
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('renovar-confirmar'));
    await screen.findByTestId('factura-display-modal');
    expect(imprimir).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByTestId('factura-display-cerrar'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(imprimir).toHaveBeenCalledTimes(1);
    const texto = textoImpreso(imprimir);
    expectDetalleImpuestos(texto, FACTURA.numero_recibo);
    expect(texto).toMatch(/IVA 19% \$ ?19\.159,66/);
    expect(texto).toMatch(/Base \$ ?100\.840,34/);
    expect(texto).toMatch(/TOTAL \$ ?120\.000/);
  });
});
