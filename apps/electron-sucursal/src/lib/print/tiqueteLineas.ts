/**
 * `tiqueteLineas.ts` — the ONE model of every operation ticket (entrada,
 * salida, salida con mensualidad, recibo de pago, reimpresion, arqueo parcial).
 *
 * Each constructor turns a validated payload into a channel-neutral list of
 * `FacturaLinea` — exactly like the invoice (`construirFactura`) and the cierre
 * de turno (`construirCierre`) — so the SAME lines feed ESC/POS (Electron
 * bridge) and HTML (browser mode → `window.print`) and the three families look
 * the same: 80 mm roll, 48 columns (576 dots), easypunto logo on top and at the
 * bottom. Pure: same payload, same lines; no DOM, no I/O.
 *
 * The printed content is the one each ticket always had (sucursal header,
 * empresa, operario, sello, tipo ROTACIÓN/MENSUALIDAD, folio, tarifa, fechas,
 * placa, horario, póliza, observaciones, montos with tax detail, resolución,
 * leyendas). Only the presentation changed.
 *
 * Reimpresión: the reprinted ticket is the ORIGINAL ticket's lines plus a
 * legend block right under the header (REIMPRESIÓN, its number, motivo and the
 * original folio); nothing of the original is dropped or duplicated.
 */
import type { FacturaLinea } from './facturaPrint';
import { MARCA_ENCABEZADO, MARCA_PIE } from './marcaTicket';
import { ajustarTexto, TICKET_COLUMNAS } from './ticketBase';
import {
  formatCOP,
  formatFecha,
  formatFechaCorta,
  formatHora,
  lineasMontos,
  type ArqueoPayload,
  type Empresa,
  type EntradaPayload,
  type ReciboPagoPayload,
  type ReimpresionPayload,
  type SalidaMensualidadPayload,
  type SalidaPayload,
} from './escposTemplates';

/** Legend block printed by a reimpresión right under the header. */
interface LeyendaReimpresion {
  motivo: string;
  folioOriginal: string;
  numero?: string | undefined;
}

type Opciones = { centro?: boolean; negrita?: boolean };

/** `Etiqueta: valor` whose value is ONE token (uuid, folio, code): label and value are split when the row overflows. */
const CAMPO_CON_TOKEN = /^([^:]{1,32}:) (\S+)$/;

/**
 * Builder of lines: keeps the constructors short and strips non-breaking spaces
 * (the printer has no glyph for them). Every `texto` is wrapped HERE to the 48
 * ticket columns, so the model itself never carries a row wider than the paper:
 * ESC/POS, HTML and the on-screen preview show the same rows. A long single-token
 * value (a 36-char uuid) goes on its own line under its label instead of being cut.
 */
class Lineas {
  readonly out: FacturaLinea[] = [];

  texto(t: string, o: Opciones = {}): this {
    const limpio = t.replace(/[\u00a0\u202f]/g, ' ');
    const campo = limpio.length > TICKET_COLUMNAS ? CAMPO_CON_TOKEN.exec(limpio) : null;
    const filas = campo
      ? [campo[1] as string, ...ajustarTexto(campo[2] as string, TICKET_COLUMNAS)]
      : ajustarTexto(limpio, TICKET_COLUMNAS);
    for (const fila of filas) this.out.push({ tipo: 'texto', texto: fila, ...o });
    return this;
  }

  sep(): this {
    this.out.push({ tipo: 'sep' });
    return this;
  }

  marca(l: FacturaLinea): this {
    this.out.push(l);
    return this;
  }
}

/** Sucursal header + empresa block, centred. */
function cabecera(l: Lineas, encabezado: string, empresa: Empresa): void {
  l.marca(MARCA_ENCABEZADO);
  l.texto(encabezado, { centro: true, negrita: true });
  l.texto(empresa.nombre, { centro: true });
  l.texto(empresa.direccion, { centro: true });
  l.texto(`NIT ${empresa.nit}`, { centro: true });
  l.texto(empresa.regimen, { centro: true });
  l.sep();
}

function leyendaReimpresion(l: Lineas, r: LeyendaReimpresion | undefined): void {
  if (r === undefined) return;
  l.texto('*** REIMPRESIÓN ***', { centro: true, negrita: true });
  if (r.numero !== undefined) l.texto(`Reimpresión No. ${r.numero}`, { centro: true, negrita: true });
  l.texto('--- COPIA AUTORIZADA ---', { centro: true });
  l.texto(`Motivo: ${r.motivo}`);
  l.texto(`Folio original: ${r.folioOriginal}`);
  l.sep();
}

function sello(l: Lineas, titulo: string, tipo: 'ROTACIÓN' | 'MENSUALIDAD'): void {
  l.texto(`*** ${titulo} ***`, { centro: true, negrita: true });
  l.texto(`Tipo: ${tipo}`, { centro: true, negrita: true });
  l.sep();
}

function pie(l: Lineas, leyenda: string): void {
  l.sep();
  l.texto(leyenda, { centro: true });
  l.marca(MARCA_PIE);
}

function montos(l: Lineas, p: SalidaPayload): void {
  const m = lineasMontos(p);
  l.sep();
  l.texto(m.subtotal);
  for (const linea of m.impuestos) l.texto(linea);
  l.texto(m.total, { negrita: true });
}

/** Tiquete de ingreso (CU-15E). */
export function construirEntrada(p: EntradaPayload, r?: LeyendaReimpresion): FacturaLinea[] {
  const l = new Lineas();
  cabecera(l, p.sucursal.encabezado, p.empresa);
  leyendaReimpresion(l, r);
  l.texto(`Operario: ${p.operario}`);
  sello(l, 'TIQUETE DE ENTRADA', p.esMensualidad === true ? 'MENSUALIDAD' : 'ROTACIÓN');
  l.texto(`Folio: ${p.folio}`);
  // The hourly tariff is informative; omitted when unknown (never print "$ 0").
  if (p.tarifaAplicada !== undefined) l.texto(`Tarifa: ${formatCOP(p.tarifaAplicada)}/hora`);
  l.texto(`Fecha: ${formatFecha(p.fechaEntrada)}`);
  l.texto(`Hora: ${formatHora(p.fechaEntrada)}`);
  if (p.variant === 'con-placa') l.texto(`Placa: ${p.placa}`, { negrita: true });
  else l.texto(`Identificación: ${p.consecutivo}`, { negrita: true });
  l.texto(`Horario: ${p.horarioAtencion}`);
  if (p.polizaRC) l.texto(`Poliza RC: ${p.polizaRC}`);
  if (p.observaciones) l.texto(`Observaciones: ${p.observaciones}`);
  pie(l, 'Conserve este tiquete para la salida.');
  return l.out;
}

/** Tiquete de salida con cobro (CU-15S). */
export function construirSalida(p: SalidaPayload, r?: LeyendaReimpresion): FacturaLinea[] {
  const l = new Lineas();
  cabecera(l, p.sucursal.encabezado, p.empresa);
  leyendaReimpresion(l, r);
  l.texto(`Operario: ${p.operario}`);
  sello(l, 'SALIDA', 'ROTACIÓN');
  l.texto(`Folio: ${p.folio}`);
  l.texto(`Tarifa: ${formatCOP(p.tarifaAplicada)}/hora`);
  l.texto(`Fecha: ${formatFecha(p.fechaEntrada)}`);
  l.texto(`Hora entrada: ${formatHora(p.fechaEntrada)}`);
  l.texto(`Hora salida: ${formatHora(p.fechaSalida)}`);
  l.texto(`Tiempo: ${p.tiempoTotal}`);
  montos(l, p);
  l.sep();
  l.texto(`Medio de pago: ${p.medioPago}`);
  l.texto(`Placa: ${p.placa}`, { negrita: true });
  l.texto(`Horario: ${p.horarioAtencion}`);
  if (p.polizaRC) l.texto(`Poliza RC: ${p.polizaRC}`);
  l.texto(`Resolucion FE: ${p.resolucionFE}`);
  if (p.observaciones) l.texto(`Observaciones: ${p.observaciones}`);
  pie(l, 'Gracias por su visita.');
  return l.out;
}

/** Tiquete de salida con mensualidad (CU-15SM): never carries money (DEC-SUC-23). */
export function construirSalidaMensualidad(
  p: SalidaMensualidadPayload,
  r?: LeyendaReimpresion,
): FacturaLinea[] {
  const l = new Lineas();
  cabecera(l, p.sucursal.encabezado, p.empresa);
  leyendaReimpresion(l, r);
  l.texto(`Operario: ${p.operario}`);
  sello(l, 'PAGO CON MENSUALIDAD', 'MENSUALIDAD');
  l.texto(`Folio: ${p.folio}`);
  l.texto(`Fecha: ${formatFecha(p.fechaEntrada)}`);
  l.texto(`Hora entrada: ${formatHora(p.fechaEntrada)}`);
  l.texto(`Hora salida: ${formatHora(p.fechaSalida)}`);
  l.texto(`Tiempo: ${p.tiempoTotal}`);
  l.texto(`Placa: ${p.placa}`, { negrita: true });
  l.texto(`Horario: ${p.horarioAtencion}`);
  if (p.polizaRC) l.texto(`Poliza RC: ${p.polizaRC}`);
  if (p.observaciones) l.texto(`Observaciones: ${p.observaciones}`);
  pie(l, 'Conserve este tiquete como soporte.');
  return l.out;
}

/** Recibo de pago (post-pago): the CU-15S fields plus `numero_recibo` and the typed `medio_pago`. */
export function construirRecibo(p: ReciboPagoPayload): FacturaLinea[] {
  const l = new Lineas();
  cabecera(l, p.sucursal.encabezado, p.empresa);
  l.texto(`Operario: ${p.operario}`);
  l.texto('*** RECIBO DE PAGO ***', { centro: true, negrita: true });
  l.sep();
  l.texto(`Numero de recibo: ${p.numero_recibo}`, { negrita: true });
  l.texto(`Folio: ${p.folio}`);
  l.texto(`Tarifa: ${formatCOP(p.tarifaAplicada)}/hora`);
  l.texto(`Fecha: ${formatFecha(p.fechaEntrada)}`);
  l.texto(`Hora entrada: ${formatHora(p.fechaEntrada)}`);
  l.texto(`Hora salida: ${formatHora(p.fechaSalida)}`);
  l.texto(`Tiempo: ${p.tiempoTotal}`);
  montos(l, p);
  l.sep();
  l.texto(`Medio de pago: ${p.medio_pago}`);
  l.texto(`Placa: ${p.placa}`, { negrita: true });
  l.texto(`Horario: ${p.horarioAtencion}`);
  if (p.polizaRC) l.texto(`Poliza RC: ${p.polizaRC}`);
  l.texto(`Resolucion FE: ${p.resolucionFE}`);
  if (p.observaciones) l.texto(`Observaciones: ${p.observaciones}`);
  pie(l, 'Gracias por su pago.');
  return l.out;
}

/** Reimpresión of an entrada / salida / salida con mensualidad: the original ticket plus the legend. */
export function construirReimpresion(p: ReimpresionPayload): FacturaLinea[] {
  const leyenda: LeyendaReimpresion = {
    motivo: p.motivo,
    folioOriginal: p.folioOriginal,
    numero: p.numeroReimpresion,
  };
  switch (p.originalTipo) {
    case 'entrada':
      return construirEntrada(p.payload, leyenda);
    case 'salida':
      return construirSalida(p.payload, leyenda);
    case 'salida-mensualidad':
      return construirSalidaMensualidad(p.payload, leyenda);
  }
}

function conSigno(n: number): string {
  return n < 0 ? `-${formatCOP(Math.abs(n))}` : `+${formatCOP(n)}`;
}

/** Comprobante de arqueo parcial (CU-10). */
export function construirArqueoParcial(p: ArqueoPayload): FacturaLinea[] {
  const l = new Lineas();
  l.marca(MARCA_ENCABEZADO);
  l.texto(`ARQUEO PARCIAL — ${p.sucursal.encabezado}`, { centro: true, negrita: true });
  l.sep();
  l.texto('*** ARQUEO PARCIAL ***', { centro: true, negrita: true });
  l.texto(`Codigo: ${p.auditoria_codigo}`);
  l.texto(`Fecha: ${formatFechaCorta(p.fecha)}`);
  l.texto(`Sesion: ${p.uuid_sesion_short}`);
  l.sep();
  l.texto(`Base: ${formatCOP(p.base_efectivo_cop)}`);
  l.texto(`Esperado efectivo: ${formatCOP(p.valor_esperado_efectivo)}`);
  l.texto(`Reportado efectivo: ${formatCOP(p.valor_reportado_efectivo)}`);
  l.texto(`Diferencia efectivo: ${conSigno(p.diferencia_efectivo)}`, { negrita: true });
  l.texto(`Tolerancia efectivo: ${formatCOP(p.tolerancia_efectivo)}`);
  // Legacy payloads only: the efectivo-only cuadre omits the datáfono block entirely.
  if (
    p.valor_esperado_datafono !== undefined &&
    p.valor_reportado_datafono !== undefined &&
    p.diferencia_datafono !== undefined &&
    p.tolerancia_datafono !== undefined
  ) {
    l.sep();
    l.texto(`Esperado datafono: ${formatCOP(p.valor_esperado_datafono)}`);
    l.texto(`Reportado datafono: ${formatCOP(p.valor_reportado_datafono)}`);
    l.texto(`Diferencia datafono: ${conSigno(p.diferencia_datafono)}`, { negrita: true });
    l.texto(`Tolerancia datafono: ${formatCOP(p.tolerancia_datafono)}`);
  }
  if (p.justificacion && p.justificacion.length > 0) {
    l.sep();
    l.texto(`Justificacion: ${p.justificacion}`);
  }
  l.sep();
  l.marca(MARCA_PIE);
  return l.out;
}
