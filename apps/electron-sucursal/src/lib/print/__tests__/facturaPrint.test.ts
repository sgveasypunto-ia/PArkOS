/**
 * Invoice print builder: ONE document model (`construirFactura`) rendered to
 * ESC/POS (Electron) and HTML (browser mode), both carrying the per-tax
 * detail. `imprimirFactura` picks the channel and sends the COMPLETE document
 * (never the old `{uuid_factura, numero_recibo}` envelope).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  FACTURA_COLUMNAS,
  construirFactura,
  facturaAEscpos,
  facturaAHtml,
  facturaATexto,
  imprimirFactura,
} from '../facturaPrint';
import {
  FACTURA_BASE,
  FACTURA_MENSUALIDAD_CERO,
  FACTURA_ROTACION_200,
  FACTURA_SUSCRIPCION_120000,
} from './facturaFixtures';

const norm = (s: string): string => s.replace(/ /g, " ").replace(/[ 	]+/g, " ");

describe('construirFactura / facturaATexto', () => {
  it('suscripcion 120.000: header, cliente, items, base, IVA 19% y total', () => {
    const txt = norm(facturaATexto(construirFactura(FACTURA_SUSCRIPCION_120000)));
    expect(txt).toContain('Parqueadero Centro');
    expect(txt).toContain('NIT 900123456-7');
    expect(txt).toContain('sucursal-20261007-000012');
    expect(txt).toContain('Laura Martinez');
    expect(txt).toContain('1020304050');
    expect(txt).toContain('Mensualidad automovil');
    expect(txt).toMatch(/Subtotal \(base\)\s+\$ ?100\.840,34/);
    expect(txt).toMatch(/IVA 19% \(base \$ ?100\.840,34\)\s+\$ ?19\.159,66/);
    expect(txt).not.toMatch(/Base \$/);
    expect(txt).toMatch(/TOTAL \$ ?120\.000/);
    expect(txt).toContain('efectivo');
  });

  it('nota de FE pendiente cuando aun no hay CUFE y consecutivo cuando existe', () => {
    const txt = norm(facturaATexto(construirFactura(FACTURA_SUSCRIPCION_120000)));
    expect(txt).toContain('SETP990000012');
    expect(txt.toLowerCase()).toContain('pendiente');
    const sinFe = norm(facturaATexto(construirFactura(FACTURA_ROTACION_200)));
    expect(sinFe.toLowerCase()).toContain('pendiente');
    const conCufe = norm(
      facturaATexto(
        construirFactura({
          ...FACTURA_SUSCRIPCION_120000,
          factura_electronica: {
            uuid: FACTURA_SUSCRIPCION_120000.factura_electronica!.uuid,
            prefijo: 'SETP',
            consecutivo: 5,
            estado_dian: 'aceptado',
            cufe: 'abc123cufe',
          },
        }),
      ),
    );
    expect(conCufe).toContain('CUFE: abc123cufe');
  });

  it('rotacion 200: base 168,07 e IVA 31,93 con placa y tiempo', () => {
    const txt = norm(facturaATexto(construirFactura(FACTURA_ROTACION_200)));
    expect(txt).toMatch(/IVA 19% \(base \$ ?168,07\)\s+\$ ?31,93/);
    expect(txt).not.toMatch(/Base \$/);
    expect(txt).toMatch(/TOTAL \$ ?200/);
    expect(txt).toContain('ABC123');
    expect(txt).toContain('1 h 30 min');
    expect(txt).toContain('Consumidor final');
  });

  it('mensualidad $0: lineas en 0 con descuento', () => {
    const txt = norm(facturaATexto(construirFactura(FACTURA_MENSUALIDAD_CERO)));
    expect(txt).toMatch(/Descuento - \$ ?168,07/);
    expect(txt).toMatch(/IVA 19% \(base \$ ?0,00\)\s+\$ ?0,00/);
    expect(txt).not.toMatch(/Base \$/);
    expect(txt).toMatch(/TOTAL \$ ?0,00/);
    expect(txt).toContain('suscripcion');
  });

  it('sin impuestos persistidos (API vieja) no inventa lineas de impuesto', () => {
    const txt = norm(facturaATexto(construirFactura({ ...FACTURA_BASE, total: 100, subtotal: 100 })));
    expect(txt).not.toMatch(/IVA d/);
    expect(txt).toMatch(/TOTAL \$ ?100/);
  });
});

describe('empresa dueña de la suscripcion (ticket de salida)', () => {
  const conEmpresa = (empresa: string | null | undefined) => ({
    ...FACTURA_MENSUALIDAD_CERO,
    datos_vehiculo: {
      ...(FACTURA_MENSUALIDAD_CERO.datos_vehiculo as NonNullable<
        typeof FACTURA_MENSUALIDAD_CERO.datos_vehiculo
      >),
      ...(empresa === undefined ? {} : { empresa_suscripcion: empresa }),
    },
  });

  it('empresa con suscripcion vigente: imprime la razon social junto a la placa', () => {
    const txt = norm(facturaATexto(construirFactura(conEmpresa('Acme Parqueos SAS'))));
    expect(txt).toContain('Empresa: Acme Parqueos SAS');
    expect(txt.indexOf('Placa:')).toBeLessThan(txt.indexOf('Empresa:'));
  });

  it.each([[null], [undefined], ['   ']])(
    'sin empresa (%j): conserva el ticket actual sin linea Empresa',
    (valor) => {
      const txt = norm(facturaATexto(construirFactura(conEmpresa(valor as string | null | undefined))));
      expect(txt).not.toContain('Empresa:');
      expect(txt).toContain('Placa:');
    },
  );

  it('razon social larga: se ajusta al ancho termico sin cortar palabras ni perder texto', () => {
    const largo = 'Inversiones y Representaciones Internacionales del Caribe Colombiano SAS';
    const lineas = facturaATexto(construirFactura(conEmpresa(largo))).split('\n');
    const i = lineas.findIndex((l) => l.startsWith('Empresa:'));
    const bloque: string[] = [];
    for (let k = i; k < lineas.length && (k === i || lineas[k]?.startsWith('  ')); k++) {
      bloque.push(lineas[k] as string);
    }
    expect(bloque.length).toBeGreaterThan(1);
    for (const l of bloque) expect(l.length).toBeLessThanOrEqual(FACTURA_COLUMNAS);
    const unido = bloque.map((l) => l.trim()).join(' ').replace(/^Empresa: /, '');
    expect(unido).toBe(largo);
  });

  it('sanea caracteres de control (no inyecta comandos ESC/POS) y escapa HTML', () => {
    const malo = 'Acme\x1b@\x1dV\x00 <b>&Co';
    const buf = facturaAEscpos(conEmpresa(malo));
    const idx = buf.indexOf('Empresa: ');
    const fin = buf.indexOf(0x0a, idx);
    const linea = buf.subarray(idx, fin);
    expect([...linea].every((b) => b >= 0x20 && b !== 0x7f)).toBe(true);
    const html = facturaAHtml(conEmpresa(malo));
    expect(html).toContain('&lt;b&gt;&amp;Co');
    expect(html).not.toContain('<b>&Co');
  });
});

describe('facturaAEscpos', () => {
  it('buffer ESC/POS: init, texto con el detalle de impuestos y corte parcial', () => {
    const buf = facturaAEscpos(FACTURA_SUSCRIPCION_120000);
    expect([...buf.subarray(0, 2)]).toEqual([0x1b, 0x40]);
    const text = norm(buf.toString('utf8'));
    expect(text).toMatch(/IVA 19% \(base \$ ?[\d.]+,\d\d\)\s+\$ ?19\.159,66/);
    expect(text).toMatch(/Subtotal \(base\)\s+\$ ?100\.840,34/);
    expect(text).toMatch(/TOTAL \$ ?120\.000/);
    // GS V 0 (partial cut) near the end
    const tail = [...buf.subarray(buf.length - 4)];
    expect(tail).toEqual([0x1d, 0x56, 0x00, 0x0a]);
  });
});

describe('facturaAHtml', () => {
  it('HTML con el detalle por impuesto y escapado', () => {
    const html = facturaAHtml({
      ...FACTURA_SUSCRIPCION_120000,
      datos_sucursal: { ...FACTURA_SUSCRIPCION_120000.datos_sucursal, razon_social: 'A<b>&Co' },
    });
    expect(html).toContain('A&lt;b&gt;&amp;Co');
    const txt = norm(html.replace(/<[^>]+>/g, ' '));
    expect(txt).toMatch(/IVA 19% \(base \$ ?100\.840,34\)\s+\$ ?19\.159,66/);
    expect(txt).not.toMatch(/Base \$/);
    expect(txt).toMatch(/TOTAL \$ ?120\.000/);
  });
});

describe('imprimirFactura', () => {
  beforeEach(() => {
    window.print = vi.fn();
  });
  afterEach(() => {
    document.getElementById('parkos-escpos-fallback-container')?.remove();
    vi.restoreAllMocks();
  });

  function bridgeElectron() {
    const imprimir = vi.fn(async () => ({ ok: true, queueId: null }));
    return { imprimir, bridge: { imprimir: Object.assign(imprimir, {}) } as never };
  }

  it('Electron: envia {buffer base64, ticketId, cut, uuidRegistro} con el detalle completo', async () => {
    const { imprimir, bridge } = bridgeElectron();
    const res = await imprimirFactura(FACTURA_SUSCRIPCION_120000, bridge);
    expect(res.ok).toBe(true);
    expect(imprimir).toHaveBeenCalledTimes(1);
    const arg = (imprimir.mock.calls[0] as unknown[])[0] as Record<string, unknown>;
    expect(Object.keys(arg).sort()).toEqual(['buffer', 'cut', 'ticketId', 'uuidRegistro']);
    expect(arg.cut).toBe(true);
    expect((arg.ticketId as string).length).toBeLessThanOrEqual(64);
    const decoded = norm(Buffer.from(arg.buffer as string, 'base64').toString('utf8'));
    expect(decoded).toMatch(/IVA 19% \(base \$ ?[\d.]+,\d\d\)\s+\$ ?19\.159,66/);
    expect(window.print).not.toHaveBeenCalled();
  });

  it('modo navegador: imprime el HTML con el detalle via window.print', async () => {
    const imprimir = vi.fn();
    const bridge = { imprimir: Object.assign(imprimir, { modo: 'browser' as const }) } as never;
    const res = await imprimirFactura(FACTURA_ROTACION_200, bridge);
    expect(res.ok).toBe(true);
    expect(imprimir).not.toHaveBeenCalled();
    expect(window.print).toHaveBeenCalledTimes(1);
    const dom = norm(
      document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '',
    );
    expect(dom).toMatch(/IVA 19% \(base \$ ?168,07\)\s+\$ ?31,93/);
    expect(dom).not.toMatch(/Base \$/);
    expect(dom).toMatch(/TOTAL \$ ?200/);
  });

  it('sin bridge: no lanza y reporta el motivo', async () => {
    const res = await imprimirFactura(FACTURA_ROTACION_200, undefined);
    expect(res.ok).toBe(false);
  });

  it('el bridge rechaza (impresora offline): no lanza, devuelve ok=false', async () => {
    const imprimir = vi.fn(async () => {
      throw new Error('printer_offline');
    });
    const res = await imprimirFactura(FACTURA_ROTACION_200, { imprimir } as never);
    expect(res.ok).toBe(false);
  });
});
