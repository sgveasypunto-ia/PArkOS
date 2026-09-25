/**
 * Tests for `<ReimprimirTiquete />` (HU-F8.3, REQ-OPS-171 + REQ-OPS-174).
 *
 * NO es una ruta — vive dentro de `<ReimprimirTiqueteSheet />` (drawer),
 * ver ese componente para el smoke test de open/close. Este archivo
 * prueba el form/logic component en aislamiento (sin Sheet ni Router,
 * ninguno de los dos hace falta).
 *
 * BUGFIX (2026-09-25, ajuste de alcance -- directiva del operador): la
 * reimpresión ahora dispara el flujo real de cobro (monto -> método de
 * pago vía `<PagoModal>` real, NO mockeado -> `POST /factura-servicio`
 * -> `POST /workflows/reimpresion-ticket` con `uuid_factura` real). El
 * viejo alertdialog "confirmar cobro" desapareció -- el paso de motivo
 * ahora abre el paso de cobro (`<PagoModal>`), que YA es la confirmación
 * (mismo patrón que `<PagoSheet>` para salida, sin dialog redundante).
 *
 * Coverage:
 *   T1: page mounts with the búsqueda form; motivo/pago NO están
 *       visibles todavía.
 *   T2: búsqueda resuelve 'found' → tarjeta de ingreso + motivo visible.
 *   T3: motivo <10 chars → inline error; el paso de cobro NUNCA se abre.
 *   T4: motivo ≥10 chars → "Continuar al cobro" → `<PagoModal>` real
 *       visible con el costo vigente.
 *   T5: costo NO configurado (costoServicio.costo === null) → banner de
 *       error, `<PagoModal>` NO se muestra.
 *   T6: submit de `<PagoModal>` → POST factura-servicio + POST
 *       reimpresión (CON uuid_factura real) → success card + imprime.
 *   T7: success card "Anular" click → alertdialog con motivo_anulacion.
 *   T8: búsqueda resuelve 'none' → mensaje de error visible.
 *   T9: búsqueda resuelve 'multiple' → lista de candidatos clickeable.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

const mockUseReimprimir = vi.fn();
const mockUseAnularReimpresion = vi.fn();
const mockUseRegistrarPagoServicio = vi.fn();
const mockUseCostoServicioVigente = vi.fn();
const mockUseIvaVigente = vi.fn();
const mockResolverIngresoReimpresion = vi.fn();
const mockUseIngresosActivos = vi.fn(() => []);
const mockUseAuth = vi.fn(() => ({ sucursal: { uuid: 'suc-1' } }));

vi.mock('../hooks/useReimprimir', () => ({
  useReimprimir: () => mockUseReimprimir(),
}));

vi.mock('../hooks/useAnularReimpresion', () => ({
  useAnularReimpresion: () => mockUseAnularReimpresion(),
}));

vi.mock('../hooks/useRegistrarPagoServicio', () => ({
  useRegistrarPagoServicio: () => mockUseRegistrarPagoServicio(),
}));

vi.mock('../hooks/useCostoServicioVigente', () => ({
  useCostoServicioVigente: () => mockUseCostoServicioVigente(),
}));

vi.mock('../hooks/useIvaVigente', () => ({
  useIvaVigente: () => mockUseIvaVigente(),
}));

vi.mock('../lib/resolverIngresoReimpresion', () => ({
  resolverIngresoReimpresion: (termino: string) =>
    mockResolverIngresoReimpresion(termino),
}));

vi.mock('../../operacion/hooks/useIngresosActivos', () => ({
  useIngresosActivos: () => mockUseIngresosActivos(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
}));

// window.bridge.imprimir stub (same pattern as IngresoPanel.test.tsx) —
// the page under test calls `window.bridge.imprimir(payload)` best-effort
// after a successful reimpresión.
const imprimirMock = vi.fn().mockResolvedValue({ ok: true });
(window as unknown as { bridge: { imprimir: typeof imprimirMock } }).bridge = {
  imprimir: imprimirMock,
};

import { ReimprimirTiquete } from './ReimprimirTiquete';
import type { Ingreso } from '../../operacion/api/ingresoActivoApi';
import type { FacturaRead } from '../api/facturaApi';

const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';
const UUID_REIMPRESION = '00000000-0000-0000-0000-0000000000aa';
const UUID_REIMPRESION_NEW = '00000000-0000-0000-0000-0000000000bb';
const UUID_FACTURA = '00000000-0000-0000-0000-0000000000cc';
const MOTIVO_VALIDO = 'Cliente solicita reimpresion por deterioro del original';
const COSTO_VIGENTE = 5000;

const INGRESO_CON_PLACA: Ingreso = {
  uuid: UUID_INGRESO,
  uuid_sucursal: 'suc-1',
  placa: 'ABC123',
  fecha_ingreso: '2026-09-17T10:00:00Z',
  uuid_subscripcion_cliente: null,
  consecutivo: null,
  uuid_tipo_vehiculo: null,
};

function buildFacturaRead(overrides?: Partial<FacturaRead>): FacturaRead {
  return {
    uuid: UUID_FACTURA,
    created_at: '2026-09-19T11:00:00Z',
    uuid_sucursal: 'suc-1',
    uuid_ingreso: UUID_INGRESO,
    uuid_salida: null,
    subtotal: COSTO_VIGENTE,
    descuento: 0,
    total: COSTO_VIGENTE,
    uuid_cliente: null,
    items: [
      {
        uuid: 'item-1',
        tipo: 'servicio',
        concepto: 'Reimpresión de tiquete',
        cantidad: 1,
        valor_unitario: COSTO_VIGENTE,
        subtotal: COSTO_VIGENTE,
      },
    ],
    estado: 'emitida',
    medio_pago: 'efectivo',
    monto_recibido_cents: null,
    vuelto_cents: null,
    voucher: null,
    numero_recibo: 'suc-20260919-000001',
    cliente: null,
    datos_sucursal: {
      razon_social: 'Parkos',
      nit: '900000000',
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
    ...overrides,
  };
}

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
        uuid_factura: UUID_FACTURA,
        costo_aplicado: COSTO_VIGENTE,
        motivo: MOTIVO_VALIDO,
        created_at: '2026-09-19T11:00:00Z',
      }
    );
  });
  return { trigger, isMutating: false };
}

function buildRegistrarPagoServicioHook(overrides?: {
  triggerResult?: unknown;
  triggerError?: unknown;
}): { trigger: ReturnType<typeof vi.fn>; isMutating: boolean } {
  const trigger = vi.fn().mockImplementation(async () => {
    if (overrides?.triggerError) {
      throw overrides.triggerError;
    }
    return overrides?.triggerResult ?? buildFacturaRead();
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
        uuid_factura: UUID_FACTURA,
        costo_aplicado: COSTO_VIGENTE,
        motivo: 'Original reimpresion authorized correctly',
        motivo_anulacion: 'Error operativo: reimprimir solicitada por error',
        created_at: '2026-09-19T12:00:00Z',
      }
    );
  });
  return { trigger, isMutating: false };
}

function renderAt(): void {
  // No es una ruta (directiva del operador 2026-09-25) — el componente
  // vive dentro de `<ReimprimirTiqueteSheet />` y no depende de Router.
  render(<ReimprimirTiquete />);
}

async function buscarYEncontrar(termino = 'ABC123'): Promise<void> {
  fireEvent.input(screen.getByTestId('reimprimir-termino'), {
    target: { value: termino },
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId('reimprimir-buscar-confirmar'));
  });
}

async function llegarAlPago(): Promise<void> {
  await buscarYEncontrar();
  fireEvent.input(screen.getByTestId('reimprimir-motivo'), {
    target: { value: MOTIVO_VALIDO },
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId('reimprimir-continuar'));
  });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockUseReimprimir.mockReset();
  mockUseAnularReimpresion.mockReset();
  mockUseRegistrarPagoServicio.mockReset();
  mockUseCostoServicioVigente.mockReset();
  mockUseIvaVigente.mockReset();
  mockResolverIngresoReimpresion.mockReset();
  mockUseIngresosActivos.mockReturnValue([]);
  mockUseAuth.mockReturnValue({ sucursal: { uuid: 'suc-1' } });
  mockUseCostoServicioVigente.mockReturnValue({
    costo: COSTO_VIGENTE,
    isLoading: false,
    error: undefined,
  });
  // BUGFIX (2026-09-25): el fix de subtotal/IVA agrega `useIvaVigente`
  // como segunda dependencia antes de montar `<PagoModal>` — default
  // 19% para no romper los tests existentes que no lo mencionan.
  mockUseIvaVigente.mockReturnValue({
    porcentaje: 0.19,
    isLoading: false,
    error: undefined,
  });
  imprimirMock.mockClear();
});

describe('<ReimprimirTiquete /> — HU-F8.3 búsqueda placa/cupo + cobro real + motivo Zod', () => {
  it('T1: page mounts with the búsqueda form; motivo/pago NOT visible yet', () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());

    renderAt();

    expect(screen.getByTestId('reimprimir-tiquete-page')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-termino')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-buscar-confirmar')).toBeInTheDocument();
    expect(screen.queryByTestId('reimprimir-motivo')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pago-confirmar')).not.toBeInTheDocument();
  });

  it('T2: búsqueda resuelve "found" → tarjeta de ingreso + motivo visibles', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'found',
      ingreso: INGRESO_CON_PLACA,
    });

    renderAt();
    await buscarYEncontrar();

    expect(mockResolverIngresoReimpresion).toHaveBeenCalledWith('ABC123');
    expect(screen.getByTestId('reimprimir-ingreso-encontrado')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-motivo')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-continuar')).toBeInTheDocument();
  });

  it('T3: motivo <10 chars → inline error; el paso de cobro NUNCA se abre', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'found',
      ingreso: INGRESO_CON_PLACA,
    });

    renderAt();
    await buscarYEncontrar();

    fireEvent.input(screen.getByTestId('reimprimir-motivo'), {
      target: { value: 'corto' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-continuar'));
    });

    expect(screen.getByText('motivo_muy_corto')).toBeInTheDocument();
    expect(screen.queryByTestId('reimprimir-cobro')).not.toBeInTheDocument();
  });

  it('T4: motivo ≥10 chars → "Continuar al cobro" → <PagoModal> real con el costo vigente', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'found',
      ingreso: INGRESO_CON_PLACA,
    });

    renderAt();
    await llegarAlPago();

    expect(screen.getByTestId('reimprimir-cobro')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-costo-vigente').textContent).toMatch(/5[.,]000/);
    expect(screen.getByTestId('pago-modal')).toBeInTheDocument();
    expect(screen.getByTestId('pago-confirmar')).toBeInTheDocument();
  });

  it('T5: costo NO configurado → banner de error, <PagoModal> NO se muestra', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    mockUseCostoServicioVigente.mockReturnValue({
      costo: null,
      isLoading: false,
      error: undefined,
    });
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'found',
      ingreso: INGRESO_CON_PLACA,
    });

    renderAt();
    await llegarAlPago();

    expect(screen.getByTestId('reimprimir-costo-no-configurado')).toBeInTheDocument();
    expect(screen.queryByTestId('pago-modal')).not.toBeInTheDocument();
  });

  it('T6: submit de <PagoModal> → POST factura-servicio + POST reimpresión con uuid_factura real → success + imprime', async () => {
    const reimprimirHook = buildReimprimirHook();
    const registrarPagoServicioHook = buildRegistrarPagoServicioHook();
    mockUseReimprimir.mockReturnValue(reimprimirHook);
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(registrarPagoServicioHook);
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'found',
      ingreso: INGRESO_CON_PLACA,
    });

    renderAt();
    await llegarAlPago();

    // <PagoModal> real (no mockeado): medio_pago default 'efectivo',
    // monto_recibido_cop default = total_cop (costo vigente) → el
    // submit no necesita tocar más campos.
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(registrarPagoServicioHook.trigger).toHaveBeenCalledWith(
      expect.objectContaining({
        uuid_ingreso: UUID_INGRESO,
        medio_pago: 'efectivo',
        items: [
          expect.objectContaining({
            tipo: 'servicio',
            concepto: 'Reimpresión de tiquete',
            cantidad: 1,
            valor_unitario: COSTO_VIGENTE,
          }),
        ],
        // BUGFIX (2026-09-25): COSTO_VIGENTE (5000) ya incluye IVA;
        // subtotal = total - round(total*0.19,2) = 5000-950 = 4050.
        subtotal: 4050,
        total: COSTO_VIGENTE,
      }),
    );
    expect(reimprimirHook.trigger).toHaveBeenCalledWith({
      uuid_ingreso: UUID_INGRESO,
      motivo: MOTIVO_VALIDO,
      uuid_factura: UUID_FACTURA,
    });
    expect(screen.getByTestId('reimprimir-success')).toBeInTheDocument();
    expect(screen.getByTestId('reimprimir-success-uuid').textContent).toBe(UUID_REIMPRESION);
    expect(screen.getByTestId('reimprimir-success-costo').textContent).toMatch(/5[.,]000/);
    expect(imprimirMock).toHaveBeenCalled();
  });

  it('T7: success card "Anular" click → alertdialog con motivo_anulacion', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'found',
      ingreso: INGRESO_CON_PLACA,
    });

    renderAt();
    await llegarAlPago();
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('reimprimir-anular'));
    });

    const anularDialog = screen.getByTestId('reimprimir-anular-dialog');
    expect(anularDialog).toBeInTheDocument();
    expect(anularDialog.getAttribute('role')).toBe('alertdialog');
    expect(screen.getByTestId('reimprimir-anular-motivo')).toBeInTheDocument();
  });

  it('T8: búsqueda resuelve "none" → mensaje de error visible', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'none',
      termino: 'NOEXISTE',
    });

    renderAt();
    await buscarYEncontrar('NOEXISTE');

    expect(screen.getByTestId('reimprimir-no-encontrado')).toBeInTheDocument();
    expect(screen.queryByTestId('reimprimir-motivo')).not.toBeInTheDocument();
  });

  it('T9: búsqueda resuelve "multiple" → lista de candidatos clickeable selecciona uno', async () => {
    mockUseReimprimir.mockReturnValue(buildReimprimirHook());
    mockUseAnularReimpresion.mockReturnValue(buildAnularHook());
    mockUseRegistrarPagoServicio.mockReturnValue(buildRegistrarPagoServicioHook());
    const otro: Ingreso = { ...INGRESO_CON_PLACA, uuid: 'uuid-otro', placa: 'XYZ999' };
    mockResolverIngresoReimpresion.mockResolvedValue({
      kind: 'multiple',
      candidatos: [INGRESO_CON_PLACA, otro],
    });

    renderAt();
    await buscarYEncontrar('AMBIGUO');

    expect(screen.getByTestId('reimprimir-candidatos')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId(`reimprimir-candidato-${UUID_INGRESO}`));
    });

    expect(screen.getByTestId('reimprimir-ingreso-encontrado')).toBeInTheDocument();
    expect(screen.queryByTestId('reimprimir-candidatos')).not.toBeInTheDocument();
  });
});
