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
 * was removed from the operator flow and is NEVER printed.
 */
import type { BridgeSurface } from '../../../electron/bridge';
import {
  bridgeActual,
  dinero,
  enviarAlBridge,
  lineasAEscpos,
  lineasAHtml,
  type FacturaLinea,
  type ResultadoImpresion,
} from './facturaPrint';
import { formatFechaCorta } from './escposTemplates';

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

  const titulo = d.tipo === 'cierre_turno' ? 'CIERRE DE TURNO' : 'CIERRE DIARIO';
  if (d.sucursal) texto(d.sucursal, { centro: true, negrita: true });
  texto(titulo, { centro: true, negrita: true });
  sep();
  texto(`Operador: ${d.operador}`);
  if (d.uuidSesion) texto(`Turno: ${d.uuidSesion.slice(-8)}`);
  if (d.aperturaIso) texto(`Apertura: ${formatFechaCorta(d.aperturaIso)}`);
  if (d.cierreIso) texto(`Cierre: ${formatFechaCorta(d.cierreIso)}`);
  if (d.uuidArqueo) texto(`Arqueo: ${d.uuidArqueo.slice(-8)}`);
  sep();
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
  return out;
}

/** ESC/POS bytes for the thermal printer. */
export function cierreAEscpos(d: CierreImpresion): Buffer {
  return lineasAEscpos(construirCierre(d));
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
  return enviarAlBridge(bridge, {
    escpos: () => cierreAEscpos(d),
    html: () => cierreAHtml(d),
    ticketId: `${d.tipo}-${d.uuidArqueo ?? d.uuidSesion ?? Date.now()}`,
  });
}
