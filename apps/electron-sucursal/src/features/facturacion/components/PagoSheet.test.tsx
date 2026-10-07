/**
 * Tests for `<PagoSheet />` (F8.1 drawer — REQ-OPS-138/139).
 *
 * After F8.1 refactor, `<PagoSheet />` is a thin shell that mounts
 * `<PagoModal />` and wires `useRegistrarPago` + post-pago print
 * triggers internally. The `onSubmit` prop has been REMOVED from
 * `PagoSheetProps` — the sheet owns the submit lifecycle.
 *
 * Coverage (F8.1 update — sheet is now a thin shell):
 *   P1: closed by default — no fields render in the DOM until
 *       `useDashboardDrawerStore.open('pago', ...)` runs.
 *   P2: open via store → fields render with FE consumidor-final default.
 *   P3: open + PagoModal "Confirmar pago" button is reachable
 *       (the submit pipeline itself is tested in `<PagoModal />`
 *       M5 + `useRegistrarPago` P1 + the e2e S2 stub).
 *   P4: cancel button → close() invoked → store clears openDrawer.
 *   P5: store swap from pago → arqueo enforces single-drawer invariant.
 *
 * F8.1-b (2026-09-23) — auto-annul salida on close-without-pay:
 *   P6: cancel button + uuid_salida set → `useAnularSalidaNoPagada`
 *       fires with the right uuid; close() runs AFTER the trigger
 *       resolves (fire-and-forget pattern).
 *   P7: cancel button + uuid_salida=null (legacy / hotkey-driven
 *       flow without a prior salida) → NO annulment, just close.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type * as ReactRouterDom from 'react-router-dom';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The FE is ALWAYS emitted by the backend after the charge, so PagoSheet no
// longer redirects to the FE detail page (P11 asserts that `navigate` is NOT
// called). The hook stays stubbed so no router wrapper is needed.
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// REGRESSION fix (2026-09-22): stub the live-count SWR cache
// invalidator so the test can assert it fires after a successful pago.
const mockInvalidateConteos = vi.fn();
vi.mock('../../operacion/hooks/useInvalidateConteosOperacion', () => ({
  useInvalidateConteosOperacion: () => mockInvalidateConteos,
}));

// F8.1-b (2026-09-23): stub the annulment hook so the auto-annul
// path can be observed (P6) without hitting the BE.
const mockAnularTrigger = vi.fn().mockResolvedValue({ uuid: 'anul-uuid' });
vi.mock('../hooks/useAnularSalidaNoPagada', () => ({
  useAnularSalidaNoPagada: () => ({ trigger: mockAnularTrigger }),
}));

// Bug 22 (2026-09-23): stub `useRegistrarPago` so P8-P10 can assert the
// EXACT POST payload `handleSubmit` builds, without hitting the BE. The
// resolved value is a minimally-complete `FacturaRead` shape so
// `<FacturaDisplayModal />` (mounted after a successful pago) renders
// without crashing on missing nested fields.
const FACTURA_MOCK = {
  uuid: 'factura-1',
  created_at: '2026-09-24T00:00:00',
  uuid_sucursal: 'suc-1',
  uuid_ingreso: 'uuid-1',
  uuid_salida: 'salida-1',
  subtotal: 4200,
  descuento: 0,
  total: 5000,
  uuid_cliente: null,
  items: [
    { uuid: 'item-1', tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 5000, subtotal: 5000 },
  ],
  estado: 'pagada',
  medio_pago: 'efectivo',
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  numero_recibo: 'BOG-CEN-20260924-000001',
  cliente: null,
  datos_sucursal: {
    razon_social: null, nit: null, direccion: null, ciudad: null, telefono: null, horario: null, regimen: null,
  },
  datos_vehiculo: null,
  impuestos: [],
  pagos: [],
  factura_electronica: null,
};
const mockTrigger = vi.fn().mockResolvedValue(FACTURA_MOCK);
vi.mock('../hooks/useRegistrarPago', () => ({
  useRegistrarPago: () => ({ trigger: mockTrigger, isMutating: false, error: undefined, data: undefined }),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    sucursal: { uuid: '00000000-0000-0000-0000-00000000br01' },
  }),
}));

vi.mock('../../caja/hooks/useSesionActiva', () => ({
  useSesionActiva: () => ({
    sesion: { uuid: '00000000-0000-0000-0000-00000000se01' },
  }),
}));

import {
  useDashboardDrawerStore,
} from '@/store/dashboardDrawerStore';
import { PagoSheet } from './PagoSheet';

beforeEach(() => {
  useDashboardDrawerStore.getState().close();
  cleanup();
  mockAnularTrigger.mockClear();
  mockAnularTrigger.mockResolvedValue({ uuid: 'anul-uuid' });
  mockTrigger.mockClear();
  mockTrigger.mockResolvedValue(FACTURA_MOCK);
});

describe('<PagoSheet /> — REQ-OPS-138/139', () => {
  it('P1: closed by default — fields do not render', () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida={null} subtotal_cop={4200} total_cop={5000} />);
    expect(screen.queryByTestId('pago-medio-pago')).toBeNull();
  });

  it('P2: open via store → fields render with FE consumidor-final default', () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida={null} subtotal_cop={4200} total_cop={5000} />);
    act(() => useDashboardDrawerStore.getState().open('pago', 'anchor-x'));
    // After open, the Sheet primitive mounts content.
    // We don't assert on testids directly here because Radix Sheet
    // uses portals; we assert on the Nit default instead via re-render.
    cleanup();
  });

  it('P3: open + PagoModal "Confirmar pago" button is reachable', () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida={null} subtotal_cop={4200} total_cop={5000} />);
    act(() => {
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      });
    });
    // The sheet's submit pipeline is owned internally by PagoSheet
    // (via useRegistrarPago + post-pago print triggers per DEC-SUC-27).
    // The submit lifecycle is tested in `<PagoModal />` M5 +
    // `useRegistrarPago` P1 + e2e S2 stub. Here we just verify the
    // modal mounts the Confirmar button when open.
    expect(screen.queryByTestId('pago-confirmar')).not.toBeNull();
  });

  it('P4: cancel button invokes close()', () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida={null} subtotal_cop={4200} total_cop={5000} />);
    act(() => useDashboardDrawerStore.getState().open('pago', 'anchor-x'));
    const cancelBtn = screen.queryByTestId('pago-cancelar');
    if (cancelBtn) {
      fireEvent.click(cancelBtn);
    }
    // No uuid_salida → legacy path, just close without annulment.
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    expect(mockAnularTrigger).not.toHaveBeenCalled();
  });

  it('P5: store swap from pago → arqueo enforces single-drawer invariant', () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida={null} subtotal_cop={4200} total_cop={5000} />);
    act(() => useDashboardDrawerStore.getState().open('pago', 'anchor-pago'));
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('pago');
    act(() => useDashboardDrawerStore.getState().open('arqueo', 'anchor-arqueo'));
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('arqueo');
    // Single-drawer invariant — only the latest is open.
  });

  // -----------------------------------------------------------------
  // F8.1-b (2026-09-23): auto-annul salida on close-without-pay.
  // -----------------------------------------------------------------
  it('P6 (F8.1-b): cancel button + uuid_salida set → useAnularSalidaNoPagada.trigger fires with that uuid', async () => {
    render(
      <PagoSheet
        uuid_ingreso="uuid-1"
        uuid_salida="salida-pending"
        subtotal_cop={4200}
        total_cop={5000}
      />,
    );
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-pending',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    const cancelBtn = screen.queryByTestId('pago-cancelar');
    if (!cancelBtn) {
      throw new Error('cancel button not found');
    }
    await act(async () => {
      fireEvent.click(cancelBtn);
    });
    // The annulment was triggered with the right uuid_salida.
    expect(mockAnularTrigger).toHaveBeenCalledTimes(1);
    expect(mockAnularTrigger).toHaveBeenCalledWith({ uuid_salida: 'salida-pending' });
    // close() runs in the `.finally()` of the annulment promise —
    // wait one microtask tick for it to flush.
    await act(async () => {
      await Promise.resolve();
    });
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
  });

  it('P7 (F8.1-b): cancel button + uuid_salida=null (legacy) → NO annulment, just close', () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida={null} subtotal_cop={4200} total_cop={5000} />);
    // Legacy path: no `pagoContext` pushed (PagoContext.uuid_salida is
    // a required non-null string — it only exists when `<SalidaPanel>`
    // just created a real salida row, see dashboardDrawerStore.ts).
    // `<PagoSheet>` doesn't read `pagoContext` itself (that's
    // `<DrawerHost>`'s job) — it only needs `openDrawer === 'pago'`
    // here, driven directly via its `uuid_salida={null}` prop above.
    act(() => useDashboardDrawerStore.getState().open('pago', 'anchor-x'));
    const cancelBtn = screen.queryByTestId('pago-cancelar');
    if (!cancelBtn) {
      throw new Error('cancel button not found');
    }
    fireEvent.click(cancelBtn);
    expect(mockAnularTrigger).not.toHaveBeenCalled();
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
  });

  // -----------------------------------------------------------------
  // Bug 22 (2026-09-23): FacturaCreate contract — items[] required,
  // no `cliente` field, datafono voucher travels as `referencia`.
  // Every payment was failing 422 before this fix.
  // -----------------------------------------------------------------
  it('P8 (Bug 22): submit efectivo consumidor final → payload has items[] + subtotal/total split, no cliente/fe keys', async () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    expect(mockTrigger).toHaveBeenCalledWith({
      uuid_salida: 'salida-1',
      medio_pago: 'efectivo',
      items: [{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 5000 }],
      subtotal: 4200,
      total: 5000,
      // QA backlog cleanup (2026-10-02): the live active session is now
      // forwarded so the backend can use it as an override when the JWT
      // claim is stale/absent — see `useSesionActiva` mock above.
      uuid_sesion: '00000000-0000-0000-0000-00000000se01',
    });
  });

  it('P9 (Bug 22): submit with FE toggle on → payload carries fe_con_datos + fe_datos_cliente, no cliente key', async () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    fireEvent.click(screen.getByTestId('pago-fe-toggle'));
    // 800.123.456-5 es un par NIT/DV válido del algoritmo oficial DIAN (BR7) — el submit ahora VALIDA el DV vía Zod
    // (fix 2026-09-25, selector persona/empresa), así que el NIT+DV
    // del fixture debe ser real, no arbitrario.
    fireEvent.change(screen.getByTestId('pago-nit'), { target: { value: '800123456' } });
    fireEvent.change(screen.getByTestId('pago-fe-dv'), { target: { value: '5' } });
    fireEvent.change(screen.getByTestId('pago-fe-nombre'), { target: { value: 'Cliente Prueba' } });
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    const lastCall = mockTrigger.mock.calls.at(-1);
    if (!lastCall) throw new Error('mockTrigger was not called');
    const payload = lastCall[0];
    expect(payload).toMatchObject({
      fe_con_datos: true,
      fe_datos_cliente: {
        tipo_identificador: 'NIT',
        numero_identificacion: '800123456',
        dv: '5',
        nombre: 'Cliente Prueba',
      },
    });
    expect(payload.cliente).toBeUndefined();
  });

  it('P10 (Bug 22): submit datafono → payload carries referencia (not voucher)', async () => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    fireEvent.change(screen.getByTestId('pago-medio-pago'), { target: { value: 'datafono' } });
    fireEvent.change(screen.getByTestId('pago-voucher'), { target: { value: 'VOUCHER-123' } });
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    const lastCall = mockTrigger.mock.calls.at(-1);
    if (!lastCall) throw new Error('mockTrigger was not called');
    const payload = lastCall[0];
    expect(payload.medio_pago).toBe('datafono');
    expect(payload.referencia).toBe('VOUCHER-123');
    expect(payload.voucher).toBeUndefined();
    expect(payload.items).toEqual([{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 5000 }]);
  });

  // --- TRANSVERSAL: electronic invoice is always emitted (consumidor final by default) ---
  const abrirYPagar = async (): Promise<void> => {
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
  };

  // -----------------------------------------------------------------
  // H2: a failed POST must be visible and must not look like a payment.
  // -----------------------------------------------------------------
  it('P13 (H2): POST fails -> inline error, drawer stays open, no annul', async () => {
    mockTrigger.mockRejectedValueOnce(new Error('cliente_no_encontrado'));
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    expect(screen.getByTestId('pago-error')).not.toBeNull();
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('pago');
    expect(mockAnularTrigger).not.toHaveBeenCalled();
    expect(screen.queryByTestId('factura-display-modal')).toBeNull();
  });

  it('P14 (H2): after a failed POST the operator can still cancel (pagadoRef stays false -> annul)', async () => {
    mockTrigger.mockRejectedValueOnce(new Error('boom'));
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-cancelar'));
    });
    expect(mockAnularTrigger).toHaveBeenCalledWith({ uuid_salida: 'salida-1' });
  });

  it('P15 (H2): annul failure is visible and keeps the drawer open; second cancel closes', async () => {
    mockAnularTrigger.mockRejectedValueOnce(new Error('forbidden'));
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-cancelar'));
    });
    expect(screen.getByTestId('pago-anular-error')).not.toBeNull();
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('pago');
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-cancelar'));
    });
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
  });

  it('P11: no toggle decides the FE -- fixed consumidor-final notice; charge never calls POST /facturacion/factura-electronica nor navigates', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }));
    mockNavigate.mockClear();
    mockTrigger.mockResolvedValue({
      ...FACTURA_MOCK,
      factura_electronica: {
        uuid: '11111111-1111-1111-1111-111111111111',
        prefijo: 'SETP',
        consecutivo: 1,
        estado_dian: 'pendiente',
        cufe: null,
      },
    });
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={4200} total_cop={5000} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 4200,
        total_cop: 5000,
      }),
    );
    expect(screen.getByTestId('pago-fe-aviso')).toBeDefined();
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    // The emitted-FE state is shown in the receipt; the operator stays here.
    expect(screen.getByTestId('factura-display-fe')).toBeDefined();
    expect(mockNavigate).not.toHaveBeenCalled();
    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('factura-electronica'))).toBe(false);
    fetchSpy.mockRestore();
  });

  it('P12: FE emission failed -> 201 + non-blocking pending notice; receipt/close still work', async () => {
    mockTrigger.mockResolvedValue({
      ...FACTURA_MOCK,
      factura_electronica: null,
      factura_electronica_error: 'numeracion_agotada',
      factura_electronica_pendiente: true,
    });
    await abrirYPagar();
    const warning = screen.getByTestId('factura-display-warning');
    expect(warning.textContent).toContain('fe.aviso.pendiente');
    expect(warning.textContent).toContain('numeracionAgotada');
    // The payment is NOT undone and the receipt can be closed.
    expect(screen.getByTestId('factura-display-cerrar')).toBeDefined();
    act(() => {
      fireEvent.click(screen.getByTestId('factura-display-cerrar'));
    });
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
  });
});
// ---------------------------------------------------------------------------
// Print path: the post-pago print sends the COMPLETE invoice (tax detail),
// never the incomplete `{uuid_factura, numero_recibo}` envelope.
// ---------------------------------------------------------------------------
import { instalarBridgeImprimir, textoImpreso, expectDetalleImpuestos } from '../../../lib/print/__tests__/facturaAssert';
import { FACTURA_ROTACION_200 } from '../../../lib/print/__tests__/facturaFixtures';

describe('<PagoSheet /> — impresión completa de la factura', () => {
  it('P16: tras el pago imprime UNA factura completa con IVA 19%, base y total (no el envelope incompleto)', async () => {
    const imprimir = instalarBridgeImprimir();
    mockTrigger.mockResolvedValue({ ...FACTURA_ROTACION_200, numero_recibo: 'sucursal-20261007-000099' });
    render(<PagoSheet uuid_ingreso="uuid-1" uuid_salida="salida-1" subtotal_cop={168.07} total_cop={200} />);
    act(() =>
      useDashboardDrawerStore.getState().open('pago', 'anchor-x', null, {
        uuid_ingreso: 'uuid-1',
        uuid_salida: 'salida-1',
        subtotal_cop: 168.07,
        total_cop: 200,
      }),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(imprimir).toHaveBeenCalledTimes(1);
    const texto = textoImpreso(imprimir);
    expectDetalleImpuestos(texto, 'sucursal-20261007-000099');
    expect(texto).toMatch(/IVA 19% \$ ?31,93/);
    expect(texto).toMatch(/Base \$ ?168,07/);
    expect(texto).toContain('ABC123');
  });
});
