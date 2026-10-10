/**
 * Fixtures of the 80 mm thermal tickets (entrada, salida, salida con
 * mensualidad, recibo de pago, reimpresion, arqueo parcial). Shared by the
 * ticket tests and the development preview (`vistaPreviaTiquetes.ts`).
 *
 * Texts are deliberately long in places (empresa, observaciones, motivo) so the
 * 48-column wrapping is exercised.
 */
import type {
  ArqueoPayload,
  EntradaPayload,
  ReciboPagoPayload,
  ReimpresionPayload,
  SalidaMensualidadPayload,
  SalidaPayload,
} from '../escposTemplates';

export const FOLIO = '3f8a1b2c-0000-4000-8000-00000000a1b2';
export const NUMERO_REIMPRESION = '0A1B2C3D';

const EMPRESA = {
  nombre: 'Inversiones y Representaciones Internacionales del Caribe SAS',
  nit: '900123456-7',
  direccion: 'Carrera 43A No. 1 Sur - 31, Local 105, Centro Comercial',
  regimen: 'Responsable de IVA',
};

const SUCURSAL = { encabezado: 'Sede Centro' };

export function entradaConPlaca(over: Partial<EntradaPayload> = {}): EntradaPayload {
  return {
    variant: 'con-placa',
    placa: 'ABC123',
    fechaEntrada: '2026-10-07T21:07:00.000Z',
    empresa: EMPRESA,
    operario: 'Operador de prueba',
    tarifaAplicada: 5000,
    horarioAtencion: 'Lunes a domingo, 24 horas',
    polizaRC: 'POL-12345',
    folio: FOLIO,
    observaciones: 'Vehiculo con rayon en la puerta izquierda y espejo roto',
    esMensualidad: false,
    sucursal: SUCURSAL,
    ...over,
  } as EntradaPayload;
}

export function entradaSinPlaca(): EntradaPayload {
  return {
    variant: 'con-consecutivo',
    placa: null,
    consecutivo: 'BICI-000001-3f8a1b2c',
    fechaEntrada: '2026-10-07T21:07:00.000Z',
    empresa: EMPRESA,
    operario: 'Operador de prueba',
    horarioAtencion: '24h',
    folio: FOLIO,
    sucursal: SUCURSAL,
  };
}

export function salida(over: Partial<SalidaPayload> = {}): SalidaPayload {
  return {
    ...(entradaConPlaca() as Extract<EntradaPayload, { variant: 'con-placa' }>),
    fechaSalida: '2026-10-07T23:37:00.000Z',
    tiempoTotal: '2 h 30 min',
    subtotal: 10000,
    iva: 1900,
    total: 11900,
    impuestos: [{ nombre: 'IVA', porcentaje: 0.19, base: 10000, valor: 1900 }],
    medioPago: 'efectivo',
    resolucionFE: 'RES-18760000001 de 2026',
    ...over,
  } as SalidaPayload;
}

export function salidaMensualidad(): SalidaMensualidadPayload {
  return {
    placa: 'ABC123',
    fechaEntrada: '2026-10-07T21:07:00.000Z',
    fechaSalida: '2026-10-07T23:37:00.000Z',
    empresa: EMPRESA,
    operario: 'Operador de prueba',
    horarioAtencion: 'Lunes a domingo, 24 horas',
    polizaRC: 'POL-12345',
    folio: FOLIO,
    observaciones: 'Suscripcion vigente hasta el 31/10/2026',
    sucursal: SUCURSAL,
    tiempoTotal: '2 h 30 min',
    esMensualidad: true,
  };
}

export function recibo(): ReciboPagoPayload {
  return {
    ...salida(),
    numero_recibo: 'sucursal-20261007-000042',
    medio_pago: 'datafono',
  } as ReciboPagoPayload;
}

export function reimpresionEntrada(numero: string | null = NUMERO_REIMPRESION): ReimpresionPayload {
  return {
    originalTipo: 'entrada',
    motivo: 'Cliente perdio el tiquete original',
    empresa: EMPRESA,
    folioOriginal: FOLIO,
    ...(numero !== null ? { numeroReimpresion: numero } : {}),
    payload: entradaConPlaca(),
  };
}

export function reimpresionSalida(): ReimpresionPayload {
  return {
    originalTipo: 'salida',
    motivo: 'Copia solicitada por el cliente',
    empresa: EMPRESA,
    folioOriginal: FOLIO,
    numeroReimpresion: NUMERO_REIMPRESION,
    payload: salida() as SalidaPayload,
  };
}

export function reimpresionSalidaMensualidad(): ReimpresionPayload {
  return {
    originalTipo: 'salida-mensualidad',
    motivo: 'Copia solicitada por el cliente',
    empresa: EMPRESA,
    folioOriginal: FOLIO,
    numeroReimpresion: NUMERO_REIMPRESION,
    payload: salidaMensualidad(),
  };
}

export function arqueo(): ArqueoPayload {
  return {
    sucursal: SUCURSAL,
    uuid_sesion: '3f8a1b2c-0000-4000-8000-00000000c3d4',
    base_efectivo_cop: 100000,
    valor_esperado_efectivo: 350000,
    valor_reportado_efectivo: 345000,
    diferencia_efectivo: -5000,
    tolerancia_efectivo: 2000,
    justificacion: 'Billete falso detectado y retirado por el operador',
    auditoria_codigo: 'AUD-20261007-000007',
    fecha: '2026-10-07T23:37:00.000Z',
    uuid_sesion_short: '0000c3d4',
  };
}

export type TipoFixture =
  | 'entrada'
  | 'salida'
  | 'salida-mensualidad'
  | 'recibo_pago'
  | 'reimpresion'
  | 'arqueo';

/** Every ticket scenario: `[nombre, tipo, payload]`. */
export const ESCENARIOS_TIQUETE: ReadonlyArray<readonly [string, TipoFixture, unknown]> = [
  ['entrada con placa', 'entrada', entradaConPlaca()],
  ['entrada con mensualidad', 'entrada', entradaConPlaca({ esMensualidad: true })],
  ['entrada sin placa', 'entrada', entradaSinPlaca()],
  ['salida', 'salida', salida()],
  ['salida con mensualidad', 'salida-mensualidad', salidaMensualidad()],
  ['recibo de pago', 'recibo_pago', recibo()],
  ['reimpresion de entrada', 'reimpresion', reimpresionEntrada()],
  ['reimpresion de salida', 'reimpresion', reimpresionSalida()],
  ['reimpresion de salida con mensualidad', 'reimpresion', reimpresionSalidaMensualidad()],
  ['arqueo parcial', 'arqueo', arqueo()],
];
