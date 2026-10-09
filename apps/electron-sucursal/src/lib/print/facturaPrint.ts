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
import {
  ANCHO_LOGO_ENCABEZADO,
  ANCHO_LOGO_PIE,
  MARCA_ENCABEZADO,
  MARCA_PIE,
  cargarMarcaRaster,
  logoDataUri,
  type MarcaRaster,
} from './marcaTicket';
import {
  TICKET_ANCHO_IMPRIMIBLE_MM,
  cutPartial,
  escCenter,
  escInit,
  escLeft,
  lf,
  TICKET_COLUMNAS,
  ajustarTexto,
  escAreaImprimible,
  escNegrita,
  filaTicket,
  separadorTicket,
} from './ticketBase';
import { formatCOPDecimal, formatFechaCorta } from './escposTemplates';
import { ejecutarImpresion } from './avisoImpresion';
import { printHtml } from './printHtml';
import {
  conceptoLegible,
  ETIQUETA_SUBTOTAL_BASE,
  descuentoEnBase,
  esLineaDescuento,
  etiquetaSemanticaLineas,
  semanticaLineas,
} from './facturaTextos';

/** Printable columns of the invoice: 80 mm paper, Font A (see `ticketBase.ts`). */
export const FACTURA_COLUMNAS = TICKET_COLUMNAS;

export type FacturaLinea =
  | { tipo: 'texto'; texto: string; centro?: boolean; negrita?: boolean }
  | { tipo: 'fila'; izq: string; der: string; negrita?: boolean; sangria?: boolean }
  | { tipo: 'sep' }
  /** easypunto logo (header / footer): raster on ESC/POS, `<img>` on HTML, text fallback otherwise. */
  | { tipo: 'marca'; posicion: 'encabezado' | 'pie' };

export function dinero(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return formatCOPDecimal(value).replace(/\u00a0/g, ' ');
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

/**
 * Razon social para el ticket: sin caracteres de control (un ESC/GS en el
 * nombre se ejecutaria como comando de la impresora) y con espacios colapsados.
 */
function sanearTexto(valor: string): string {
  const sinControl = Array.from(valor, (c) => {
    const code = c.charCodeAt(0);
    return code < 0x20 || code === 0x7f ? ' ' : c;
  }).join('');
  return sinControl.replace(/\s+/g, ' ').trim();
}

/**
 * `Empresa: <valor>` ajustado al ancho termico: parte en palabras, las lineas de
 * continuacion llevan sangria de 2 y una palabra mas larga que la linea se corta.
 */
function lineasEmpresa(valor: string, cols: number): string[] {
  const prefijo = 'Empresa: ';
  const out: string[] = [];
  let actual = prefijo;
  let vacia = true;
  for (let palabra of valor.split(' ')) {
    while (true) {
      const candidata = vacia ? actual + palabra : `${actual} ${palabra}`;
      if (candidata.length <= cols) {
        actual = candidata;
        vacia = false;
        break;
      }
      if (!vacia) {
        out.push(actual);
        actual = '  ';
        vacia = true;
        continue;
      }
      const espacio = cols - actual.length;
      out.push(actual + palabra.slice(0, espacio));
      palabra = palabra.slice(espacio);
      actual = '  ';
      if (palabra === '') break;
    }
  }
  if (!vacia) out.push(actual);
  return out;
}

/**
 * Lineas `Empresa: <razon social>` del ticket de salida, saneadas y ajustadas al
 * ancho termico. Vacio si no hay empresa. Fuente unica: la usan la plantilla de
 * impresion y la vista del ticket en pantalla (FacturaDisplayModal).
 */
export function lineasEmpresaTicket(
  empresa: string | null | undefined,
  cols: number = FACTURA_COLUMNAS,
): string[] {
  const saneada = sanearTexto(empresa ?? '');
  return saneada ? lineasEmpresa(saneada, cols) : [];
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

  out.push(MARCA_ENCABEZADO);

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
    // Cliente empresa dueño de la suscripcion: solo su razon social (sin NIT ni datos personales).
    for (const l of lineasEmpresaTicket(v.empresa_suscripcion)) texto(l);
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
  out.push(MARCA_PIE);
  return out;
}

/** Brand name printed when the logo image is unavailable. */
const TEXTO_MARCA = 'easypunto';

/** One physical printed line (already wrapped to the ticket width). */
export interface LineaFisica {
  texto: string;
  centro: boolean;
  negrita: boolean;
}

/**
 * Expand the channel-neutral lines into physical lines of at most `cols`
 * columns (word wrap, two-column rows, separators). Shared by the plain-text
 * dump and the ESC/POS renderer so both print exactly the same thing.
 */
export function expandirLineas(lineas: FacturaLinea[], cols: number = FACTURA_COLUMNAS): LineaFisica[] {
  const out: LineaFisica[] = [];
  for (const l of lineas) {
    if (l.tipo === 'sep') {
      out.push({ texto: separadorTicket(cols), centro: false, negrita: false });
    } else if (l.tipo === 'marca') {
      // Text fallback (also what the plain-text dump shows): the brand name.
      out.push({ texto: TEXTO_MARCA, centro: true, negrita: true });
    } else if (l.tipo === 'fila') {
      for (const t of filaTicket(l.izq, l.der, cols, l.sangria === true)) {
        out.push({ texto: t, centro: false, negrita: l.negrita === true });
      }
    } else {
      for (const t of ajustarTexto(l.texto, cols)) {
        out.push({ texto: t, centro: l.centro === true, negrita: l.negrita === true });
      }
    }
  }
  return out;
}

/** Plain-text rendering of the document (what the thermal printer receives). */
export function facturaATexto(lineas: FacturaLinea[], cols: number = FACTURA_COLUMNAS): string {
  return expandirLineas(lineas, cols)
    .map((l) => l.texto)
    .join('\n');
}

/**
 * ESC/POS bytes for a channel-neutral list of lines on 80 mm paper.
 * Commands: ESC @ (init), GS L 0 0 (left margin 0), GS W 0x40 0x02 (printable
 * width 576 dots), ESC M 0 (Font A, 48 columns), ESC a 1 / ESC a 0 (centre),
 * ESC E n (bold), GS V 0 (partial cut).
 */
export function lineasAEscpos(lineas: FacturaLinea[], marca: MarcaRaster | null = null): Buffer {
  const u = (t: string): Buffer => Buffer.from(t, 'utf8');
  const parts: Buffer[] = [escInit(), escAreaImprimible()];
  for (const linea of lineas) {
    if (linea.tipo === 'marca' && marca) {
      // Raster logo (GS v 0), centred; the printer advances the paper itself.
      parts.push(escCenter(), linea.posicion === 'pie' ? marca.pie : marca.encabezado, escLeft());
      continue;
    }
    for (const l of expandirLineas([linea])) {
      if (l.centro) parts.push(escCenter());
      if (l.negrita) parts.push(escNegrita(true));
      parts.push(u(`${l.texto}\n`));
      if (l.negrita) parts.push(escNegrita(false));
      if (l.centro) parts.push(escLeft());
    }
  }
  parts.push(u('\n'), cutPartial(), lf());
  return Buffer.concat(parts);
}

/**
 * ESC/POS bytes for the thermal printer. `marca` = raster logo from
 * `cargarMarcaRaster()`; without it the brand prints as text.
 */
export function facturaAEscpos(f: FacturaRead, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(construirFactura(f), marca);
}

/**
 * Raster logo to hand to `lineasAEscpos` for this bridge: none in browser mode
 * (HTML uses the vector `<img>`) or without bridge; otherwise the cached raster
 * (`null` if it cannot be produced → text fallback). Never throws.
 */
export async function marcaParaBridge(bridge: Pick<BridgeSurface, 'imprimir'> | undefined): Promise<MarcaRaster | null> {
  if (!bridge?.imprimir || (bridge.imprimir as { modo?: string }).modo === 'browser') return null;
  return cargarMarcaRaster();
}

function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Fixed-width ticket CSS: 72 mm of content on an 80 mm roll, monospace sized so
 * that 48 columns fill the width (Courier advance = 0.6 em → 1.5 mm per column
 * = 2.5 mm font). No height, no viewport units: the length is free and the
 * width never depends on the window.
 */
const ESTILO_TICKET =
  `font-family:'Courier New',Courier,monospace;font-size:2.5mm;line-height:1.25;width:${TICKET_ANCHO_IMPRIMIBLE_MM}mm;margin:0 auto;box-sizing:border-box;color:#000;background:#fff`;

/** HTML rendering (browser mode) of a list of lines, semantic rows. */
export function lineasAHtml(lineas: FacturaLinea[], testid: string): string {
  const body = lineas
    .map((l) => {
      if (l.tipo === 'sep') return '<hr style="border:0;border-top:1px dashed #000;margin:1mm 0" />';
      if (l.tipo === 'marca') {
        // Vector logo, black and white; widths mirror the raster (dots / 8 = mm), never above the 72 mm area.
        const mm = (l.posicion === 'pie' ? ANCHO_LOGO_PIE : ANCHO_LOGO_ENCABEZADO) / 8;
        return `<p style="text-align:center;margin:1mm 0"><img alt="easypunto" src="${logoDataUri()}" style="width:${mm}mm;max-width:${TICKET_ANCHO_IMPRIMIBLE_MM}mm;height:auto;filter:grayscale(1) contrast(1.5)" /></p>`;
      }
      if (l.tipo === 'fila') {
        const style = `display:flex;justify-content:space-between;gap:2mm${l.sangria ? ';padding-left:3mm' : ''}${l.negrita ? ';font-weight:bold' : ''}`;
        return `<div class="fila" style="${style}"><span style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(l.izq)}</span> <span style="white-space:nowrap">${esc(l.der)}</span></div>`;
      }
      const style = `${l.centro ? 'text-align:center;' : ''}${l.negrita ? 'font-weight:bold;' : ''}margin:0;white-space:pre-wrap;overflow-wrap:anywhere`;
      return `<p style="${style}">${esc(l.texto)}</p>`;
    })
    .join('\n');
  return `<style>@page { size: 80mm auto; margin: 0 }</style>
<div data-testid="${testid}" style="${ESTILO_TICKET}">
${body}
</div>`;
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
  const marca = await marcaParaBridge(bridge);
  return enviarAlBridge(bridge, {
    escpos: () => facturaAEscpos(factura, marca),
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
