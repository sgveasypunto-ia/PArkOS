/**
 * `facturaPrint.ts` — the ONE builder of every printed invoice.
 *
 * Operator requirement: "en todas las facturas que se imprimen se debe mostrar
 * el detalle de los impuestos aplicados". Every invoice type (rotación,
 * salida, servicio suelto, venta/renovación de suscripción, salida con
 * mensualidad $0) is printed from the SAME display payload (`FacturaRead`, as
 * returned by `POST /facturacion/factura` and shown by `<FacturaDisplayModal>`),
 * so what is printed is what the operator confirmed on screen:
 *
 *   emisor (razón social / NIT / régimen) → documento (recibo, fecha) →
 *   cliente → vehículo (if any) → ítems → subtotal, descuento, UNA línea por
 *   impuesto (nombre, %, valor + base) → TOTAL → pago → estado FE (consecutivo
 *   / CUFE, or "pendiente").
 *
 * `construirFactura()` produces a channel-neutral list of lines; ESC/POS
 * (Electron thermal printer) and HTML (browser mode → `window.print`) are two
 * thin renderers over that same list, so they cannot drift apart.
 *
 * `imprimirFactura()` is the only way the UI prints an invoice: it always sends
 * the COMPLETE document (base64 ESC/POS in Electron, HTML in browser mode). The
 * former `bridge.imprimir('recibo_pago', { uuid_factura, numero_recibo })`
 * envelope (no buffer: the main process rejected it) no longer exists.
 */
import type { BridgeSurface } from '../../../electron/bridge';
import type { FacturaRead } from '../../features/facturacion/api/facturaApi';
import { cutPartial, escBoldOff, escBoldOn, escCenter, escInit, escLeft, lf } from './escposBuilder';
import { formatCOPDecimal, formatFechaCorta } from './escposTemplates';
import { ejecutarImpresion } from './avisoImpresion';
import { printHtml } from './fallbackBrowser';
import {
  conceptoLegible,
  ETIQUETA_SUBTOTAL_BASE,
  descuentoEnBase,
  esLineaDescuento,
  etiquetaSemanticaLineas,
  semanticaLineas,
} from './facturaTextos';

/** Printable columns (58mm paper, Font A). 80mm paper simply leaves margin. */
export const FACTURA_COLUMNAS = 32;

export type FacturaLinea =
  | { tipo: 'texto'; texto: string; centro?: boolean; negrita?: boolean }
  | { tipo: 'fila'; izq: string; der: string; negrita?: boolean; sangria?: boolean }
  | { tipo: 'sep' };

export function dinero(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return formatCOPDecimal(value).replace(/ /g, ' ');
}

/** 0.19 → "19", 0.025 → "2.5", 0.1925 → "19.25" (no trailing zeros). */
function porcentaje(fraccion: number | null | undefined): string {
  if (fraccion === null || fraccion === undefined) return '';
  return `${Number((fraccion * 100).toFixed(2))}%`;
}

function tiempo(minutos: number | null | undefined): string {
  if (minutos === null || minutos === undefined) return '—';
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h <= 0 ? `${m} min` : `${h} h ${m} min`;
}

function etiquetaDocumento(tipo: string | null | undefined): string {
  switch (tipo) {
    case 'CC':
      return 'CC';
    case 'CE':
      return 'CE';
    case 'pasaporte':
      return 'Pasaporte';
    default:
      return 'NIT';
  }
}

function etiquetaFe(estado: string): string {
  switch (estado) {
    case 'aceptado':
      return 'aceptada por la DIAN';
    case 'enviado':
      return 'enviada a la DIAN';
    case 'rechazado':
      return 'rechazada por la DIAN';
    default:
      return 'pendiente de la DIAN';
  }
}

/** The single document model. Pure: same input, same lines. */
export function construirFactura(f: FacturaRead): FacturaLinea[] {
  const s = f.datos_sucursal;
  const out: FacturaLinea[] = [];
  const texto = (t: string, o: { centro?: boolean; negrita?: boolean } = {}): void => {
    out.push({ tipo: 'texto', texto: t, ...o });
  };
  const fila = (izq: string, der: string, o: { negrita?: boolean; sangria?: boolean } = {}): void => {
    out.push({ tipo: 'fila', izq, der, ...o });
  };
  const sep = (): void => {
    out.push({ tipo: 'sep' });
  };

  // Emisor
  texto(s.razon_social ?? 'Establecimiento', { centro: true, negrita: true });
  texto(`NIT ${s.nit ?? '—'}${s.regimen ? ` · ${s.regimen}` : ''}`, { centro: true });
  if (s.direccion) texto(s.direccion, { centro: true });
  if (s.telefono) texto(`Tel. ${s.telefono}`, { centro: true });
  sep();

  // Documento
  texto('FACTURA', { centro: true, negrita: true });
  texto(`Recibo ${f.numero_recibo}`, { centro: true });
  texto(`Fecha: ${formatFechaCorta(f.created_at)}`);

  // Cliente
  if (f.cliente) {
    const nombre = [f.cliente.nombre, f.cliente.apellido].filter(Boolean).join(' ');
    texto(`Cliente: ${nombre || '—'}`);
    const dv = f.cliente.tipo_identificador === 'NIT' && f.cliente.dv ? `-${f.cliente.dv}` : '';
    texto(
      `${etiquetaDocumento(f.cliente.tipo_identificador)} ${f.cliente.numero_identificacion ?? '—'}${dv}`,
    );
  } else {
    texto('Cliente: Consumidor final');
  }

  // Vehículo
  if (f.datos_vehiculo) {
    const v = f.datos_vehiculo;
    sep();
    if (v.placa) texto(`Placa: ${v.placa}`, { negrita: true });
    if (v.fecha_ingreso) texto(`Entrada: ${formatFechaCorta(v.fecha_ingreso)}`);
    if (v.fecha_salida) texto(`Salida: ${formatFechaCorta(v.fecha_salida)}`);
    if (v.minutos !== null && v.minutos !== undefined) texto(`Tiempo: ${tiempo(v.minutos)}`);
  }

  // Ítems
  sep();
  const etiquetaLineas = etiquetaSemanticaLineas(semanticaLineas(f));
  if (etiquetaLineas) texto(etiquetaLineas);
  for (const item of f.items) {
    const esDescuento = esLineaDescuento(item);
    fila(
      `${conceptoLegible(item.concepto)} x${item.cantidad}`,
      `${esDescuento && item.subtotal > 0 ? '- ' : ''}${dinero(item.subtotal)}`,
    );
  }

  // Totales + detalle por impuesto
  sep();
  fila(ETIQUETA_SUBTOTAL_BASE, dinero(f.subtotal));
  const descuento = descuentoEnBase(f);
  if (descuento > 0) fila('Descuento', `- ${dinero(descuento)}`);
  for (const imp of f.impuestos) {
    const nombre = imp.nombre_impuesto ?? imp.codigo_impuesto ?? 'Impuesto';
    const pct = porcentaje(imp.porcentaje_aplicado);
    // The tax base is stated ONCE, inside the tax line (no separate "Base" row).
    fila(`${nombre}${pct ? ` ${pct}` : ''} (base ${dinero(imp.base_calculo)})`, dinero(imp.valor));
  }
  fila('TOTAL', dinero(f.total), { negrita: true });

  // Pago
  sep();
  fila('Medio de pago', f.medio_pago);
  if (f.medio_pago === 'efectivo' && f.monto_recibido_cents != null) {
    fila('Recibido', dinero(f.monto_recibido_cents));
  }
  if (f.medio_pago === 'efectivo' && f.vuelto_cents != null && f.vuelto_cents > 0) {
    fila('Vueltos', dinero(f.vuelto_cents));
  }
  if (f.medio_pago === 'datafono' && f.voucher) texto(`Voucher: ${f.voucher}`);

  // Factura electrónica
  sep();
  if (f.factura_electronica) {
    const fe = f.factura_electronica;
    texto(
      `Factura electrónica ${fe.prefijo ?? ''}${fe.consecutivo ?? ''}`.trimEnd(),
      { negrita: true },
    );
    texto(`Estado: ${etiquetaFe(fe.estado_dian)}`);
    if (fe.cufe) texto(`CUFE: ${fe.cufe}`);
  } else {
    texto('Factura electrónica: pendiente de la DIAN (CUFE se asigna al emitirla)');
  }
  texto('Gracias por su visita.', { centro: true });
  return out;
}

/**
 * Two-column row. A label that does not fit next to the amount goes on its own
 * line(s) and the amount is right-aligned below: never truncate a concept.
 */
function ajustar(izq: string, der: string, cols: number, sangria: boolean): string {
  const prefijo = sangria ? "  " : "";
  const maxIzq = cols - prefijo.length - der.length - 1;
  if (izq.length <= maxIzq) {
    return `${prefijo}${izq}${" ".repeat(cols - prefijo.length - izq.length - der.length)}${der}`;
  }
  return `${prefijo}${izq}
${" ".repeat(Math.max(0, cols - der.length))}${der}`;
}

/** Plain-text rendering of the document (what the thermal printer receives). */
export function facturaATexto(lineas: FacturaLinea[], cols: number = FACTURA_COLUMNAS): string {
  return lineas
    .map((l) => {
      if (l.tipo === 'sep') return '-'.repeat(cols);
      if (l.tipo === 'fila') return ajustar(l.izq, l.der, cols, l.sangria === true);
      return l.texto;
    })
    .join('\n');
}

/** ESC/POS bytes for a channel-neutral list of lines (same framing as the other tiquetes). */
export function lineasAEscpos(lineas: FacturaLinea[]): Buffer {
  const u = (t: string): Buffer => Buffer.from(t, 'utf8');
  const parts: Buffer[] = [escInit()];
  for (const l of lineas) {
    const texto =
      l.tipo === 'sep'
        ? '-'.repeat(FACTURA_COLUMNAS)
        : l.tipo === 'fila'
          ? ajustar(l.izq, l.der, FACTURA_COLUMNAS, l.sangria === true)
          : l.texto;
    const centro = l.tipo === 'texto' && l.centro === true;
    const negrita = l.tipo !== 'sep' && l.negrita === true;
    if (centro) parts.push(escCenter());
    if (negrita) parts.push(escBoldOn());
    parts.push(u(`${texto}\n`));
    if (negrita) parts.push(escBoldOff());
    if (centro) parts.push(escLeft());
  }
  parts.push(u('\n'), cutPartial(), lf());
  return Buffer.concat(parts);
}

/** ESC/POS bytes for the thermal printer (same framing as the other tiquetes). */
export function facturaAEscpos(f: FacturaRead): Buffer {
  return lineasAEscpos(construirFactura(f));
}

function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** HTML rendering (browser mode) of a list of lines, semantic rows. */
export function lineasAHtml(lineas: FacturaLinea[], testid: string): string {
  const body = lineas
    .map((l) => {
      if (l.tipo === 'sep') return '<hr />';
      if (l.tipo === 'fila') {
        const style = `display:flex;justify-content:space-between;gap:8px${l.sangria ? ';padding-left:12px' : ''}${l.negrita ? ';font-weight:bold' : ''}`;
        return `<div class="fila" style="${style}"><span>${esc(l.izq)}</span> <span>${esc(l.der)}</span></div>`;
      }
      const style = `${l.centro ? 'text-align:center;' : ''}${l.negrita ? 'font-weight:bold;' : ''}margin:0;word-break:break-all`;
      return `<p style="${style}">${esc(l.texto)}</p>`;
    })
    .join('\n');
  return `<div data-testid="${testid}" style="font-family:monospace;font-size:12px">\n${body}\n</div>`;
}

/** HTML rendering (browser mode), semantic rows with the same lines. */
export function facturaAHtml(f: FacturaRead): string {
  return lineasAHtml(construirFactura(f), 'factura-print');
}

export interface ResultadoImpresion {
  ok: boolean;
  /** Why it did not print (never thrown: printing is best-effort, DEC-SUC-08). */
  motivo?: string;
}

/**
 * The ONE channel switch of every printed document:
 *   - Browser mode (`bridge.imprimir.modo === 'browser'`): HTML → `window.print`.
 *   - Electron: ESC/POS buffer (base64) → `bridge.imprimir({ buffer, ticketId, cut })`.
 * Never throws: a printer failure is reported as `{ ok: false }` so the caller
 * can surface it without blocking the operator (DEC-SUC-08).
 */
export async function enviarAlBridge(
  bridge: Pick<BridgeSurface, 'imprimir'> | undefined,
  doc: {
    escpos: () => Buffer;
    html: () => string;
    ticketId: string;
    uuidRegistro?: string;
  },
): Promise<ResultadoImpresion> {
  if (!bridge?.imprimir) return { ok: false, motivo: 'sin_bridge' };
  try {
    if ((bridge.imprimir as { modo?: string }).modo === 'browser') {
      printHtml(doc.html());
      return { ok: true };
    }
    const result = await bridge.imprimir({
      buffer: doc.escpos().toString('base64'),
      ticketId: doc.ticketId.slice(0, 64),
      cut: true,
      ...(doc.uuidRegistro !== undefined ? { uuidRegistro: doc.uuidRegistro } : {}),
    });
    // A bridge that answers nothing (or {ok:true}) counts as sent.
    return result && result.ok === false
      ? { ok: false, motivo: result.error ?? 'print_failed' }
      : { ok: true };
  } catch (err) {
    console.warn('[imprimir] bridge.imprimir failed (printer_offline / disconnected; el documento ya está registrado):', err);
    return { ok: false, motivo: 'excepcion' };
  }
}

/** Default bridge = `window.bridge` (undefined in tests / SSR). */
export function bridgeActual(): BridgeSurface | undefined {
  return (globalThis as unknown as { window?: { bridge?: BridgeSurface } }).window?.bridge;
}

/**
 * Print ANY invoice with its full tax detail (see `enviarAlBridge`).
 * Never throws: the invoice is already persisted.
 */
export async function imprimirFactura(
  factura: FacturaRead,
  bridge: Pick<BridgeSurface, 'imprimir'> | undefined = bridgeActual(),
): Promise<ResultadoImpresion> {
  return enviarAlBridge(bridge, {
    escpos: () => facturaAEscpos(factura),
    html: () => facturaAHtml(factura),
    ticketId: `factura-${factura.numero_recibo}`,
    uuidRegistro: factura.uuid,
  });
}

/** What a screen injects (tests) to observe/replace the real printing. */
export type ImprimirFacturaFn = (factura: FacturaRead) => void | Promise<unknown>;

/**
 * Fire the invoice print AFTER the current React commit (next microtask) and
 * swallow any failure: a printer offline/disconnected must never block the
 * operator (DEC-SUC-08; the invoice is already persisted). Shared by every
 * flow that prints an invoice so none keeps its own envelope helper.
 */
export function dispararImpresionFactura(
  factura: FacturaRead,
  imprimir: ImprimirFacturaFn = imprimirFactura,
): void {
  queueMicrotask(() => {
    // Failures are surfaced as a visible, non-blocking notice with retry
    // (`ejecutarImpresion`); nothing here ever throws into the caller.
    void ejecutarImpresion('la factura', async () => {
      const res = await imprimir(factura);
      return res !== null && typeof res === 'object' && (res as { ok?: unknown }).ok === false
        ? { ok: false }
        : { ok: true };
    });
  });
}
