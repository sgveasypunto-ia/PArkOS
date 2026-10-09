/**
 * DEV-ONLY helper (not production code): renders the cierre-de-turno ticket
 * scenarios to a standalone HTML file and a monospaced 48-column text dump, so
 * the 80 mm ticket can be reviewed without a printer.
 *
 *   PARKOS_VISTA_PREVIA=1 npx vitest run src/lib/print/__tests__/vistaPreviaCierreTurno.test.ts
 *
 * writes (to `<repo>/.agent-generated/`, or `$PARKOS_VISTA_PREVIA_DIR`):
 *   - ticket-cierre-turno-80mm.html : open in a 302 px wide viewport (80 mm @ 96 dpi).
 *   - ticket-cierre-turno-80mm.txt  : same lines as plain text, 48 columns, with a
 *     ruler and a `|` marker on column 49 (nothing may touch it).
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { cierreAHtml, construirCierre } from '../arqueoPrint';
import { facturaATexto } from '../facturaPrint';
import { TICKET_COLUMNAS } from '../ticketBase';
import { ESCENARIOS_CIERRE } from './cierreTurnoFixtures';

/** Plain-text dump of every scenario, with a column ruler and a right-edge marker. */
export function volcadoTextoCierreTurno(): string {
  const regla = '1234567890'.repeat(5).slice(0, TICKET_COLUMNAS);
  return ESCENARIOS_CIERRE.map(({ nombre, cierre }) => {
    const lineas = facturaATexto(construirCierre(cierre), TICKET_COLUMNAS)
      .split('\n')
      .map((l) => `${l.padEnd(TICKET_COLUMNAS)}|`);
    return [`=== ${nombre} (${TICKET_COLUMNAS} columnas; el logo se imprime como imagen) ===`, regla, ...lineas].join('\n');
  }).join('\n\n');
}

/** Standalone HTML page: every scenario in a 302 px (80 mm @ 96 dpi) column. */
export function paginaHtmlCierreTurno(): string {
  const tickets = ESCENARIOS_CIERRE.map(
    ({ nombre, cierre }) =>
      `<section style="width:302px;margin:0 auto 24px;background:#fff;box-shadow:0 0 4px #888;padding:8px 0"><h2 style="font:12px sans-serif;margin:0 8px 8px;color:#666">${nombre}</h2>${cierreAHtml(cierre)}</section>`,
  ).join('\n');
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Ticket cierre de turno 80 mm</title></head><body style="margin:0;background:#ddd;padding:16px 0">\n${tickets}\n</body></html>`;
}

/** Write both files; returns their paths. */
export function escribirVistaPreviaCierreTurno(
  dir: string = process.env.PARKOS_VISTA_PREVIA_DIR ?? resolve(process.cwd(), '../../.agent-generated'),
): { html: string; txt: string } {
  mkdirSync(dir, { recursive: true });
  const html = join(dir, 'ticket-cierre-turno-80mm.html');
  const txt = join(dir, 'ticket-cierre-turno-80mm.txt');
  writeFileSync(html, paginaHtmlCierreTurno(), 'utf8');
  writeFileSync(txt, volcadoTextoCierreTurno(), 'utf8');
  return { html, txt };
}
