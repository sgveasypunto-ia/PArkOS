/**
 * `ticketBase.ts` — shared base of every 80 mm thermal ticket (invoice, cierre
 * de turno, future tickets).
 *
 * Paper: 80 mm roll (the 60 mm the customer quotes is the roll's OUTER
 * DIAMETER, not a length limit: tickets have no fixed height). A 203 dpi head
 * prints 576 dots = 72 mm; Font A is 12 dots wide, so 576 / 12 = 48 columns.
 * Some models print the full 80 mm (640 dots / 53 columns): change the two
 * constants below (and only them) for those.
 */

/** Printable dots across (203 dpi, 72 mm). Multiple of 8 (raster bytes). */
export const TICKET_PUNTOS = 576;

/** Printable columns with Font A (12 dots per glyph): TICKET_PUNTOS / 12. */
export const TICKET_COLUMNAS = 48;

/** Roll width and printable width, in millimetres (HTML fallback, 8 dots/mm). */
export const TICKET_ANCHO_PAPEL_MM = 80;
export const TICKET_ANCHO_IMPRIMIBLE_MM = TICKET_PUNTOS / 8;

/** `GS W nL nH` printable-area width + `GS L 0 0` left margin + `ESC M 0` Font A. */
export function escAreaImprimible(puntos: number = TICKET_PUNTOS): Buffer {
  const p = Math.max(0, Math.min(0xffff, Math.trunc(puntos)));
  return Buffer.from([
    0x1d, 0x4c, 0x00, 0x00, // GS L 0 0 : left margin 0
    0x1d, 0x57, p & 0xff, (p >> 8) & 0xff, // GS W nL nH : printable width in dots
    0x1b, 0x4d, 0x00, // ESC M 0 : Font A (12x24)
  ]);
}

/**
 * Word-wrap `texto` to `cols`. Leading spaces (indent) are kept on every
 * continuation line; a token longer than the line (a CUFE) is cut hard.
 */
export function ajustarTexto(texto: string, cols: number = TICKET_COLUMNAS): string[] {
  if (texto.length <= cols) return [texto];
  const sangria = /^ */.exec(texto)?.[0] ?? '';
  const ancho = Math.max(1, cols - sangria.length);
  const out: string[] = [];
  let actual = '';
  for (let palabra of texto.trim().split(/ +/)) {
    while (palabra.length > ancho) {
      if (actual !== '') {
        out.push(sangria + actual);
        actual = '';
      }
      out.push(sangria + palabra.slice(0, ancho));
      palabra = palabra.slice(ancho);
    }
    if (palabra === '') continue;
    const candidata = actual === '' ? palabra : `${actual} ${palabra}`;
    if (candidata.length <= ancho) {
      actual = candidata;
    } else {
      out.push(sangria + actual);
      actual = palabra;
    }
  }
  if (actual !== '') out.push(sangria + actual);
  return out;
}

/**
 * Two-column row (label left, amount right) as 1+ lines of at most `cols`.
 * A label that does not fit next to the amount is wrapped and the amount goes
 * right-aligned on the last line (or on its own line): never truncates.
 */
export function filaTicket(
  izq: string,
  der: string,
  cols: number = TICKET_COLUMNAS,
  sangria = false,
): string[] {
  const prefijo = sangria ? '  ' : '';
  const lineas = ajustarTexto(izq, cols - prefijo.length).map((l) => prefijo + l);
  const ultima = lineas[lineas.length - 1] as string;
  if (ultima.length + 1 + der.length <= cols) {
    lineas[lineas.length - 1] = ultima + ' '.repeat(cols - ultima.length - der.length) + der;
  } else {
    lineas.push(' '.repeat(Math.max(0, cols - der.length)) + der);
  }
  return lineas;
}

/** Separator line of exactly `cols` dashes. */
export function separadorTicket(cols: number = TICKET_COLUMNAS): string {
  return '-'.repeat(cols);
}

/** `ESC E n` — bold on/off (the standard 3-byte form, parameter included). */
export function escNegrita(on: boolean): Buffer {
  return Buffer.from([0x1b, 0x45, on ? 0x01 : 0x00]);
}

/** `ESC @` — initialize the printer (reset state). */
export function escInit(): Buffer {
  return Buffer.from([0x1b, 0x40]);
}

/** `ESC a 1` — centre alignment on. */
export function escCenter(): Buffer {
  return Buffer.from([0x1b, 0x61, 0x01]);
}

/** `ESC a 0` — left alignment (reset). */
export function escLeft(): Buffer {
  return Buffer.from([0x1b, 0x61, 0x00]);
}

/** `GS V 0` — partial cut. */
export function cutPartial(): Buffer {
  return Buffer.from([0x1d, 0x56, 0x00]);
}

/** `LF` — line feed (after the cut, recommended for the print buffer). */
export function lf(): Buffer {
  return Buffer.from([0x0a]);
}
