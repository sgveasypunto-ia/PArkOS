/**
 * Worst-case fixtures (UUID of 36, long motivo, long names) through EVERY ticket
 * template: no line may exceed 48 columns, neither as a physical ESC/POS line
 * nor as a logical row of the HTML / on-screen model, and a long id is never cut.
 */
import { describe, expect, it } from 'vitest';

import { lineasDeTiquete, type TiqueteTipo } from '../escposBuilder';
import { renderTiqueteHtml } from '../fallbackBrowser';
import { expandirLineas } from '../facturaPrint';
import { TICKET_COLUMNAS } from '../ticketBase';
import {
  arqueo,
  entradaConPlaca,
  entradaSinPlaca,
  recibo,
  reimpresionEntrada,
  reimpresionSalida,
  reimpresionSalidaMensualidad,
  salida,
  salidaMensualidad,
} from './tiqueteFixtures';

const UUID_36 = '3f8a1b2c-9d4e-4f60-8a7b-0123456789ab';
const UUID_REIMPRESION = '9c1d2e3f-4a5b-4c6d-8e7f-a1b2c3d4e5f6';
const LARGO = 'Reclamo del cliente por perdida del tiquete original durante una visita prolongada al centro comercial';
const NOMBRE_LARGO = 'Inversiones y Representaciones Internacionales del Caribe y Antillas Sociedad por Acciones Simplificada';
const TOKEN_LARGO = 'X'.repeat(70);

const EMPRESA = {
  nombre: NOMBRE_LARGO,
  nit: '900123456-7',
  direccion: 'Carrera 43A No. 1 Sur - 31, Local 105, Centro Comercial Gran Plaza del Caribe, Torre Norte',
  regimen: 'Responsable de IVA, gran contribuyente y autorretenedor',
};
const SUCURSAL = { encabezado: 'Sede Centro Comercial Gran Plaza del Caribe Torre Norte Piso 3' };
const COMUNES = {
  empresa: EMPRESA,
  sucursal: SUCURSAL,
  operario: 'Operador con un nombre y apellidos particularmente largos de prueba',
  horarioAtencion: 'Lunes a viernes de 6:00 a 22:00, sabados domingos y festivos de 8:00 a 20:00',
  polizaRC: `POL-${TOKEN_LARGO}`,
  observaciones: LARGO,
  folio: UUID_36,
};

const ESCENARIOS: ReadonlyArray<readonly [string, TiqueteTipo, unknown]> = [
  ['entrada con placa', 'entrada', entradaConPlaca(COMUNES)],
  ['entrada sin placa', 'entrada', { ...entradaSinPlaca(), ...COMUNES, consecutivo: 'INDEFINIDO-000001-3f8a1b2c' }],
  ['salida', 'salida', salida({ ...COMUNES, resolucionFE: `RES-${TOKEN_LARGO}`, medioPago: LARGO })],
  ['salida con mensualidad', 'salida-mensualidad', { ...salidaMensualidad(), ...COMUNES }],
  [
    'recibo de pago',
    'recibo_pago',
    { ...recibo(), ...COMUNES, resolucionFE: `RES-${TOKEN_LARGO}` },
  ],
  [
    'reimpresion de entrada',
    'reimpresion',
    {
      ...reimpresionEntrada(UUID_REIMPRESION),
      motivo: LARGO,
      folioOriginal: UUID_36,
      empresa: EMPRESA,
      payload: entradaConPlaca(COMUNES),
    },
  ],
  [
    'reimpresion de salida',
    'reimpresion',
    { ...reimpresionSalida(), motivo: LARGO, folioOriginal: UUID_36, empresa: EMPRESA, payload: salida(COMUNES) },
  ],
  [
    'reimpresion de salida con mensualidad',
    'reimpresion',
    {
      ...reimpresionSalidaMensualidad(),
      motivo: LARGO,
      folioOriginal: UUID_36,
      empresa: EMPRESA,
      payload: { ...salidaMensualidad(), ...COMUNES },
    },
  ],
  [
    'arqueo parcial',
    'arqueo',
    { ...arqueo(), sucursal: SUCURSAL, justificacion: LARGO },
  ],
];

function textosHtml(html: string): string[] {
  const out: string[] = [];
  for (const m of html.matchAll(/<(?:p|span)\b[^>]*>([^<]*)<\/(?:p|span)>/g)) {
    out.push((m[1] ?? '').replace(/&amp;|&lt;|&gt;|&quot;|&#39;/g, '?'));
  }
  return out;
}

describe.each(ESCENARIOS)('peor caso, %s', (_nombre, tipo, payload) => {
  const lineas = lineasDeTiquete(tipo, payload);

  it('ESC/POS: ninguna linea fisica pasa de 48 columnas', () => {
    for (const l of expandirLineas(lineas)) expect(l.texto.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
  });

  it('modelo y HTML: ninguna fila logica pasa de 48 columnas', () => {
    for (const l of lineas) {
      if (l.tipo === 'texto') expect(l.texto.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
      if (l.tipo === 'fila') expect(l.izq.length + 1 + l.der.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
    }
    for (const t of textosHtml(renderTiqueteHtml(tipo, payload))) {
      expect(t.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
    }
  });
});

describe('un identificador largo no se corta', () => {
  it('reimpresion: "Folio original:" en su linea y el UUID completo en la siguiente', () => {
    const fisicas = expandirLineas(lineasDeTiquete('reimpresion', ESCENARIOS[5]![2])).map((l) => l.texto);
    const i = fisicas.indexOf('Folio original:');
    expect(i).toBeGreaterThanOrEqual(0);
    expect(fisicas[i + 1]).toBe(UUID_36);
  });

  it('cabecera de la reimpresion: leyenda, numero y motivo siguen presentes', () => {
    const texto = expandirLineas(lineasDeTiquete('reimpresion', ESCENARIOS[5]![2]))
      .map((l) => l.texto)
      .join(' ');
    expect(texto).toContain('*** REIMPRESIÓN ***');
    expect(texto).toContain('Reimpresión No. ' + UUID_REIMPRESION);
    expect(texto).toContain('Motivo: Reclamo del cliente');
  });
});
