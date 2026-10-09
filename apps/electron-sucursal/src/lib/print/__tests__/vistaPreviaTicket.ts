/**
 * DEV-ONLY helper (not production code): renders the 80 mm invoice fixtures to
 * a standalone HTML file and a monospaced 48-column text dump so the ticket can
 * be reviewed without a printer.
 *
 *   PARKOS_VISTA_PREVIA=1 npx vitest run src/lib/print/__tests__/vistaPreviaTicket.test.ts
 *
 * writes (to `<repo>/.agent-generated/`, or `$PARKOS_VISTA_PREVIA_DIR`):
 *   - ticket-factura-80mm.html : open it in a browser and size the viewport to
 *     302 px wide (80 mm at 96 dpi). The ticket is 72 mm (272 px) wide, fixed.
 *   - ticket-factura-80mm.txt  : the same lines as plain text, 48 columns,
 *     with a ruler and a `|` marker on column 49 (nothing may touch it).
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

import type { FacturaRead } from '../../../features/facturacion/api/facturaApi';
import { construirFactura, facturaAHtml, facturaATexto } from '../facturaPrint';
import { TICKET_COLUMNAS } from '../ticketBase';
import {
  FACTURA_MENSUALIDAD_CERO,
  FACTURA_ROTACION_200,
  FACTURA_SUSCRIPCION_120000,
} from './facturaFixtures';

const EMPRESA_LARGA = 'Inversiones y Representaciones Internacionales del Caribe Colombiano SAS';

export const CASOS_VISTA_PREVIA: Array<{ nombre: string; factura: FacturaRead }> = [
  { nombre: 'Rotación simple', factura: FACTURA_ROTACION_200 },
  {
    nombre: 'Mensualidad $0 con Empresa larga',
    factura: {
      ...FACTURA_MENSUALIDAD_CERO,
      datos_vehiculo: { ...FACTURA_MENSUALIDAD_CERO.datos_vehiculo!, empresa_suscripcion: EMPRESA_LARGA },
    },
  },
  {
    nombre: 'Venta de suscripción con datáfono y voucher',
    factura: {
      ...FACTURA_SUSCRIPCION_120000,
      medio_pago: 'datafono',
      voucher: '004512',
      factura_electronica: {
        uuid: FACTURA_SUSCRIPCION_120000.factura_electronica!.uuid,
        prefijo: 'SETP',
        consecutivo: 5,
        estado_dian: 'aceptado',
        cufe: 'f3a9'.repeat(24),
      },
    },
  },
];

/** Plain-text dump of every case, with a column ruler and a right-edge marker. */
export function volcadoTexto(): string {
  const regla = '1234567890'.repeat(5).slice(0, TICKET_COLUMNAS);
  return CASOS_VISTA_PREVIA.map(({ nombre, factura }) => {
    const lineas = facturaATexto(construirFactura(factura), TICKET_COLUMNAS)
      .split('\n')
      .map((l) => `${l.padEnd(TICKET_COLUMNAS)}|`);
    return [`=== ${nombre} (${TICKET_COLUMNAS} columnas; el logo se imprime como imagen) ===`, regla, ...lineas].join('\n');
  }).join('\n\n');
}

/** Standalone HTML page: every case in a 302 px (80 mm @ 96 dpi) column. */
export function paginaHtml(): string {
  const tickets = CASOS_VISTA_PREVIA.map(
    ({ nombre, factura }) =>
      `<section style="width:302px;margin:0 auto 24px;background:#fff;box-shadow:0 0 4px #888;padding:8px 0"><h2 style="font:12px sans-serif;margin:0 8px 8px;color:#666">${nombre}</h2>${facturaAHtml(factura)}</section>`,
  ).join('\n');
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Ticket factura 80 mm</title></head><body style="margin:0;background:#ddd;padding:16px 0">\n${tickets}\n</body></html>`;
}

/** Write both files; returns their paths. */
export function escribirVistaPrevia(dir: string = process.env.PARKOS_VISTA_PREVIA_DIR ?? resolve(process.cwd(), '../../.agent-generated')): {
  html: string;
  txt: string;
} {
  mkdirSync(dir, { recursive: true });
  const html = join(dir, 'ticket-factura-80mm.html');
  const txt = join(dir, 'ticket-factura-80mm.txt');
  writeFileSync(html, paginaHtml(), 'utf8');
  writeFileSync(txt, volcadoTexto(), 'utf8');
  return { html, txt };
}
