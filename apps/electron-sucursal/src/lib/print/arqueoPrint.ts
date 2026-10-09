/**
 * `arqueoPrint.ts` — the ONE builder of the cierre de turno / cierre diario
 * slips (comprobante de arqueo de cierre).
 *
 * Replaces the retired `bridge.imprimir('arqueo', { uuid, auditoria_codigo })`
 * envelope (old (tipo, payload) signature: the IPC rejected it and nobody
 * checked the result, so the slip never printed). It follows the same shape as
 * `facturaPrint.ts`: a channel-neutral list of lines rendered to ESC/POS
 * (Electron) and HTML (browser mode → `window.print`), sent through the shared
 * `enviarAlBridge`.
 *
 * Content: sucursal, turno/sesión, operador, apertura/cierre, efectivo base,
 * esperado vs reportado vs diferencia, justificación (only if any). Datáfono
 * was removed from the operator flow: this builder never prints a datáfono
 * cuadre. 80 mm paper, 48 columns, easypunto logo on top and bottom, no QR.
 *
 * Cierre de TURNO reprint: when `secciones` is given (the rows the post-close
 * summary shows on screen) the body is exactly those rows plus the operator's
 * signature line; the legacy fields below it only feed the header.
 */
import type { BridgeSurface } from '../../../electron/bridge';
import {
  bridgeActual,
  dinero,
  enviarAlBridge,
  lineasAEscpos,
  lineasAHtml,
  marcaParaBridge,
  type FacturaLinea,
  type ResultadoImpresion,
} from './facturaPrint';
import { comoInstanteUtc as comoUtc, formatFechaCorta } from './escposTemplates';
import { MARCA_ENCABEZADO, MARCA_PIE, type MarcaRaster } from './marcaTicket';
import { TICKET_COLUMNAS } from './ticketBase';

/** One block of rows of the on-screen post-close summary (`ResumenCierrePdfSection`-compatible). */
export interface CierreSeccion {
  heading: string;
  rows: Array<{ label: string; value: string }>;
}

export interface CierreImpresion {
  tipo: 'cierre_turno' | 'cierre_dia';
  sucursal?: string | null;
  operador: string;
  /** Full sesión UUID (turno only). */
  uuidSesion?: string | null;
  aperturaIso?: string | null;
  /** Closing moment (sesión `timestamp_cierre`, or the close time for the day). */
  cierreIso?: string | null;
  baseEfectivo?: number | null;
  esperado?: number | null;
  reportado: number;
  /** reportado − esperado; computed when absent and `esperado` is known. */
  diferencia?: number | null;
  justificacion?: string | null;
  uuidArqueo?: string | null;
  /** Rows of the on-screen post-close summary (turno reprint). Replaces the cuadre block. */
  secciones?: CierreSeccion[];
  /** Footnote under the sections (e.g. electronic payments are informational). */
  nota?: string | null;
}

function conSigno(n: number): string {
  if (n === 0) return dinero(0);
  return n < 0 ? `-${dinero(Math.abs(n))}` : `+${dinero(n)}`;
}

function estadoDiferencia(n: number): string {
  if (n === 0) return 'Caja cuadrada';
  return n < 0 ? 'Faltante' : 'Sobrante';
}

/** Channel-neutral lines of the slip. */
export function construirCierre(d: CierreImpresion): FacturaLinea[] {
  const out: FacturaLinea[] = [];
  const texto = (t: string, o: { centro?: boolean; negrita?: boolean } = {}): void => {
    out.push({ tipo: 'texto', texto: t, ...o });
  };
  const fila = (izq: string, der: string, negrita = false): void => {
    out.push({ tipo: 'fila', izq, der, ...(negrita ? { negrita } : {}) });
  };
  const sep = (): void => {
    out.push({ tipo: 'sep' });
  };

  out.push(MARCA_ENCABEZADO);
  const titulo = d.tipo === 'cierre_turno' ? 'CIERRE DE TURNO' : 'CIERRE DIARIO';
  if (d.sucursal) texto(d.sucursal, { centro: true, negrita: true });
  texto(titulo, { centro: true, negrita: true });
  sep();
  texto(`Operador: ${d.operador}`);
  if (d.uuidSesion) texto(`Turno: ${d.uuidSesion.slice(-8)}`);
  const conSecciones = d.secciones !== undefined && d.secciones.length > 0;
  // With `secciones` the dates come from the on-screen summary (Bogotá time); not repeated here.
  if (d.aperturaIso && !conSecciones) texto(`Apertura: ${formatFechaCorta(comoUtc(d.aperturaIso))}`);
  if (d.cierreIso && !conSecciones) texto(`Cierre: ${formatFechaCorta(comoUtc(d.cierreIso))}`);
  if (d.uuidArqueo && !conSecciones) texto(`Arqueo: ${d.uuidArqueo.slice(-8)}`);
  sep();
  if (conSecciones) {
    cuerpoSecciones(out, d);
    return out;
  }
  if (d.baseEfectivo !== undefined && d.baseEfectivo !== null) {
    fila('Base efectivo', dinero(d.baseEfectivo));
  }
  if (d.esperado !== undefined && d.esperado !== null) {
    fila('Esperado efectivo', dinero(d.esperado));
  }
  fila('Reportado efectivo', dinero(d.reportado));
  const diferencia =
    d.diferencia ??
    (d.esperado !== undefined && d.esperado !== null ? d.reportado - d.esperado : null);
  if (diferencia !== null) {
    fila('Diferencia efectivo', conSigno(diferencia), true);
    texto(estadoDiferencia(diferencia), { negrita: true });
  }
  const just = d.justificacion?.trim();
  if (just) {
    sep();
    texto(`Justificación: ${just}`);
  }
  sep();
  texto('Comprobante de cierre de caja.', { centro: true });
  out.push(MARCA_PIE);
  return out;
}

const sinEspaciosDuros = (t: string): string => t.replace(/[\u00a0\u202f]/g, ' ');

/** Rows that fit next to their value stay two-column; long free text wraps under its label. */
function filaOTexto(out: FacturaLinea[], label: string, value: string): void {
  const l = sinEspaciosDuros(label);
  const v = sinEspaciosDuros(value);
  if (l.length + 1 + v.length <= TICKET_COLUMNAS || v.length <= TICKET_COLUMNAS / 2) {
    out.push({ tipo: 'fila', izq: l, der: v });
  } else {
    out.push({ tipo: 'texto', texto: l });
    out.push({ tipo: 'texto', texto: `  ${v}` });
  }
}

/** Body of the turno ticket: the on-screen sections, then signature and brand footer. */
function cuerpoSecciones(out: FacturaLinea[], d: CierreImpresion): void {
  for (const s of d.secciones ?? []) {
    out.push({ tipo: 'texto', texto: sinEspaciosDuros(s.heading).toUpperCase(), negrita: true });
    for (const r of s.rows) filaOTexto(out, r.label, r.value);
    out.push({ tipo: 'sep' });
  }
  const nota = d.nota?.trim();
  if (nota) {
    out.push({ tipo: 'texto', texto: sinEspaciosDuros(nota) });
    out.push({ tipo: 'sep' });
  }
  out.push({ tipo: 'texto', texto: '' });
  out.push({ tipo: 'texto', texto: '' });
  out.push({ tipo: 'texto', texto: `Firma: ${'_'.repeat(TICKET_COLUMNAS - 'Firma: '.length)}` });
  out.push({ tipo: 'texto', texto: `${d.operador}` });
  out.push({ tipo: 'sep' });
  out.push({ tipo: 'texto', texto: 'Comprobante de cierre de turno.', centro: true });
  out.push(MARCA_PIE);
}

/** ESC/POS bytes for the thermal printer. */
export function cierreAEscpos(d: CierreImpresion, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(construirCierre(d), marca);
}

/** HTML rendering (browser mode). */
export function cierreAHtml(d: CierreImpresion): string {
  return lineasAHtml(construirCierre(d), 'cierre-print');
}

/**
 * Print the slip through the real bridge contract (`{ buffer, ticketId, cut }`
 * in Electron; HTML + `window.print` in browser mode). Never throws: the
 * cierre is already persisted when this runs.
 */
export async function imprimirCierre(
  d: CierreImpresion,
  bridge: Pick<BridgeSurface, 'imprimir'> | undefined = bridgeActual(),
): Promise<ResultadoImpresion> {
  const marca = await marcaParaBridge(bridge);
  return enviarAlBridge(bridge, {
    escpos: () => cierreAEscpos(d, marca),
    html: () => cierreAHtml(d),
    ticketId: `${d.tipo}-${d.uuidArqueo ?? d.uuidSesion ?? Date.now()}`,
  });
}
