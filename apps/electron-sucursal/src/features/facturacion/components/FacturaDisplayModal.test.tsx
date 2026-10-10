/**
 * Tests for `<FacturaDisplayModal />` (HU-F8.4 — post-pago breakdown).
 *
 * Coverage:
 *   D1: `factura=null` → modal not rendered (no testids in the DOM).
 *   D2: `factura` populated → every section renders with the right data
 *       (sucursal, cliente, vehículo, items, totales, medio de pago).
 *   D3: `cliente=null` → renders "Consumidor final" fallback.
 *   D4: `factura_electronica` populated → FE section renders.
 *   D5: "Cerrar" click → `onClose` fires.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { instalarBridgeImprimir, textoImpreso, expectDetalleImpuestos } from '../../../lib/print/__tests__/facturaAssert';
import { FACTURA_SUSCRIPCION_120000, FACTURA_ROTACION_200 } from '../../../lib/print/__tests__/facturaFixtures';
import { afterEach } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key }),
}));

import { FacturaDisplayModal } from './FacturaDisplayModal';
import type { FacturaRead } from '../api/facturaApi';

afterEach(() => {
  cleanup();
});

const BASE_FACTURA: FacturaRead = {
  uuid: 'factura-1',
  created_at: '2026-09-24T04:50:42.912039',
  uuid_sucursal: 'suc-1',
  uuid_ingreso: 'ingreso-1',
  uuid_salida: 'salida-1',
  subtotal: 81,
  descuento: 0,
  total: 100,
  uuid_cliente: null,
  items: [
    { uuid: 'item-1', tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 100, subtotal: 100 },
  ],
  estado: 'emitida',
  medio_pago: 'efectivo',
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  numero_recibo: '2049f2cd-20260924-000004',
  cliente: null,
  datos_sucursal: {
    razon_social: 'Suc 2049f2cd',
    nit: '90035e22a',
    direccion: 'Calle Smoke',
    ciudad: 'Bogota',
    telefono: '+571234567',
    horario: '24/7',
    regimen: 'comun',
  },
  datos_vehiculo: {
    placa: 'BUG023',
    uuid_tipo_vehiculo: 'tipo-1',
    fecha_ingreso: '2026-09-24T04:50:28.553462',
    fecha_salida: '2026-09-24T04:50:38.561137',
    minutos: 1,
  },
  impuestos: [
    {
      uuid: 'imp-1',
      uuid_impuesto: 'iva-1',
      nombre_impuesto: 'IVA',
      codigo_impuesto: 'IVA',
      base_calculo: 100,
      porcentaje_aplicado: 0.19,
      valor: 19,
    },
  ],
  pagos: [],
  factura_electronica: null,
};

describe('<FacturaDisplayModal /> — HU-F8.4', () => {
  it('D1: factura=null → modal not rendered', () => {
    render(<FacturaDisplayModal factura={null} onClose={vi.fn()} />);
    expect(screen.queryByTestId('factura-display-modal')).toBeNull();
  });

  it('D2: factura populada → renders sucursal, vehiculo, items, totales, medio de pago', () => {
    render(<FacturaDisplayModal factura={BASE_FACTURA} onClose={vi.fn()} />);

    expect(screen.getByTestId('factura-display-modal')).toBeTruthy();
    expect(screen.getByTestId('factura-display-sucursal').textContent).toContain('Suc 2049f2cd');
    expect(screen.getByTestId('factura-display-vehiculo').textContent).toContain('BUG023');
    expect(screen.getByTestId('factura-display-minutos').textContent).toContain('1 min');
    expect(screen.getAllByTestId('factura-display-item')).toHaveLength(1);
    expect(screen.getByTestId('factura-display-subtotal').textContent).toContain('81');
    expect(screen.getByTestId('factura-display-total').textContent).toContain('100');
    expect(screen.getAllByTestId('factura-display-impuesto')).toHaveLength(1);
    expect(screen.getByTestId('factura-display-mediopago').textContent).toContain('efectivo');
  });

  describe('Empresa dueña de la suscripción en la vista del ticket', () => {
    const conEmpresa = (empresa: string | null | undefined): FacturaRead => ({
      ...BASE_FACTURA,
      datos_vehiculo: {
        ...BASE_FACTURA.datos_vehiculo!,
        ...(empresa === undefined ? {} : { empresa_suscripcion: empresa }),
      },
    });

    it('muestra "Empresa: <razón social>" justo bajo la placa y antes del tiempo', () => {
      render(<FacturaDisplayModal factura={conEmpresa('Verif Empresa Ronda Tres SAS')} onClose={vi.fn()} />);
      const vehiculo = screen.getByTestId('factura-display-vehiculo');
      const empresa = screen.getByTestId('factura-display-empresa');
      // Mismo ancho que la impresión (80 mm = 48 columnas): 36 caracteres caben en una línea.
      expect(screen.getAllByTestId('factura-display-empresa-linea').map((l) => l.textContent)).toEqual([
        'Empresa: Verif Empresa Ronda Tres SAS',
      ]);
      const hijos = Array.from(vehiculo.children);
      const iPlaca = hijos.findIndex((h) => h.textContent === 'BUG023');
      expect(iPlaca).toBeGreaterThanOrEqual(0);
      expect(hijos[iPlaca + 1]).toBe(empresa);
      expect(hijos[iPlaca + 2]).toBe(screen.getByTestId('factura-display-minutos'));
    });

    it('nombre corto: una sola línea "Empresa: <razón social>"', () => {
      render(<FacturaDisplayModal factura={conEmpresa('ACME SAS')} onClose={vi.fn()} />);
      expect(screen.getByTestId('factura-display-empresa').textContent).toBe('Empresa: ACME SAS');
    });

    it.each([[undefined], [null], [''], ['   '], ['\x00\x1b']])(
      'sin empresa (%j): no renderiza la línea',
      (valor) => {
        render(<FacturaDisplayModal factura={conEmpresa(valor)} onClose={vi.fn()} />);
        expect(screen.queryByTestId('factura-display-empresa')).toBeNull();
        expect(screen.getByTestId('factura-display-vehiculo').textContent).not.toContain('Empresa');
      },
    );

    it('sanea caracteres de control y colapsa espacios', () => {
      render(<FacturaDisplayModal factura={conEmpresa('  ACME\x1b@\x00   Parqueo\n\tSAS  ')} onClose={vi.fn()} />);
      const texto = screen.getByTestId('factura-display-empresa').textContent ?? '';
      expect(texto).toBe('Empresa: ACME @ Parqueo SAS');
      expect(Array.from(texto).some((c) => c.charCodeAt(0) < 0x20 || c.charCodeAt(0) === 0x7f)).toBe(false);
    });

    it('un nombre largo se ajusta al ancho del ticket, igual que la impresión', () => {
      const largo = 'Corporacion Internacional de Servicios de Parqueo y Logistica Urbana del Caribe SAS ' + 'X'.repeat(50);
      render(<FacturaDisplayModal factura={conEmpresa(largo)} onClose={vi.fn()} />);
      const lineas = screen.getAllByTestId('factura-display-empresa-linea').map((l) => l.textContent ?? '');
      expect(lineas.length).toBeGreaterThan(1);
      for (const l of lineas) expect(l.length).toBeLessThanOrEqual(48);
      expect(lineas[0].startsWith('Empresa: ')).toBe(true);
      expect(lineas.slice(1).every((l) => l.startsWith('  '))).toBe(true);
      expect(lineas.join('').replace(/\s+/g, '')).toBe('Empresa:' + largo.replace(/\s+/g, ''));
    });

    it('el nombre se escapa (no se interpreta como HTML)', () => {
      render(<FacturaDisplayModal factura={conEmpresa('<img src=x onerror=alert(1)> SAS')} onClose={vi.fn()} />);
      expect(screen.getByTestId('factura-display-empresa').querySelector('img')).toBeNull();
      expect(screen.getByTestId('factura-display-empresa').textContent).toContain('<img');
    });
  });

  it('D3: cliente=null → renders "Consumidor final" fallback', () => {
    render(<FacturaDisplayModal factura={BASE_FACTURA} onClose={vi.fn()} />);
    expect(screen.getByTestId('factura-display-cliente').textContent).toContain('Consumidor final');
  });

  it('D8 (ajuste identificación persona/empresa): cliente persona natural/CC → label "Cédula de ciudadanía", sin sufijo DV', () => {
    render(
      <FacturaDisplayModal
        factura={{
          ...BASE_FACTURA,
          cliente: {
            tipo_identificador: 'CC',
            numero_identificacion: '1020304050',
            dv: null,
            nombre: 'Laura',
            apellido: 'Martinez',
            email: null,
            telefono: null,
          },
        }}
        onClose={vi.fn()}
      />,
    );
    const text = screen.getByTestId('factura-display-cliente').textContent ?? '';
    expect(text).toContain('Cédula de ciudadanía');
    expect(text).toContain('1020304050');
    expect(text).not.toContain('-');
  });

  it('D9 (ajuste identificación persona/empresa): cliente empresa/NIT con DV → label "NIT" + sufijo "-DV"', () => {
    render(
      <FacturaDisplayModal
        factura={{
          ...BASE_FACTURA,
          cliente: {
            tipo_identificador: 'NIT',
            numero_identificacion: '900123456',
            dv: '7',
            nombre: 'Empresa S.A.S.',
            apellido: null,
            email: null,
            telefono: null,
          },
        }}
        onClose={vi.fn()}
      />,
    );
    const text = screen.getByTestId('factura-display-cliente').textContent ?? '';
    expect(text).toContain('NIT 900123456-7');
  });

  it('D6 (bug fix, 2026-09-24): descuento=0 → does NOT render a stray literal "0"', () => {
    // Regression: `{f.descuento && f.descuento > 0 && (...)}` renders the
    // literal "0" when `descuento` is the falsy NUMBER 0 (React only
    // skips `false`/`null`/`undefined`, not other falsy values).
    render(<FacturaDisplayModal factura={BASE_FACTURA} onClose={vi.fn()} />);
    const totales = screen.getByTestId('factura-display-totales');
    expect(totales.textContent).not.toMatch(/Subtotal[^0-9]*\$?\s*81\s*0/);
    expect(screen.queryByText('Descuento')).toBeNull();
  });

  it('D7: descuento>0 → renders the "Descuento" line', () => {
    const withDescuento: FacturaRead = { ...BASE_FACTURA, descuento: 5 };
    render(<FacturaDisplayModal factura={withDescuento} onClose={vi.fn()} />);
    const totales = screen.getByTestId('factura-display-totales');
    expect(totales.textContent).toContain('Descuento');
  });

  it('D4: factura_electronica populada → renders FE section', () => {
    const withFe: FacturaRead = {
      ...BASE_FACTURA,
      factura_electronica: {
        uuid: 'fe-1',
        prefijo: 'SETP',
        consecutivo: 42,
        estado_dian: 'aceptado',
        cufe: 'abc123',
      },
    };
    render(<FacturaDisplayModal factura={withFe} onClose={vi.fn()} />);
    const fe = screen.getByTestId('factura-display-fe');
    expect(fe.textContent).toContain('SETP42');
    expect(fe.textContent).toContain('Factura electrónica');
    expect(fe.textContent).toContain('Aceptada por la DIAN');
    expect(fe.textContent).toContain('abc123');
  });

  it('D6 (FE siempre): emitida con estado DIAN pendiente -> se muestra el estado y NO hay aviso', () => {
    const emitida: FacturaRead = {
      ...BASE_FACTURA,
      factura_electronica: { uuid: 'fe-2', prefijo: 'SETP', consecutivo: 7, estado_dian: 'pendiente', cufe: null },
    };
    render(<FacturaDisplayModal factura={emitida} onClose={vi.fn()} />);
    expect(screen.getByTestId('factura-display-fe').textContent).toContain('pendiente de la DIAN');
    expect(screen.queryByTestId('factura-display-warning')).toBeNull();
  });

  it('D7 (FE siempre): emisión fallida -> aviso no bloqueante "se reintenta sola" y se puede cerrar/reimprimir', () => {
    const fallida: FacturaRead = {
      ...BASE_FACTURA,
      factura_electronica: null,
      factura_electronica_error: 'resolucion_facturacion_no_encontrada',
      factura_electronica_pendiente: true,
    };
    const onClose = vi.fn();
    render(<FacturaDisplayModal factura={fallida} onClose={onClose} />);
    const warning = screen.getByTestId('factura-display-warning');
    expect(warning.textContent).toMatch(/pendiente, se reintenta sola/i);
    expect(warning.textContent).toMatch(/resolución de facturación/);
    // The receipt stays fully usable.
    expect(screen.getByTestId('factura-display-total')).toBeDefined();
    screen.getByTestId('factura-display-cerrar').click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('D8: an explicit `warning` prop wins over the derived one', () => {
    const fallida: FacturaRead = { ...BASE_FACTURA, factura_electronica_pendiente: true };
    render(<FacturaDisplayModal factura={fallida} onClose={vi.fn()} warning="aviso del caller" />);
    expect(screen.getByTestId('factura-display-warning').textContent).toBe('aviso del caller');
  });

  it('D5: "Cerrar" click → onClose fires', () => {
    const onClose = vi.fn();
    render(<FacturaDisplayModal factura={BASE_FACTURA} onClose={onClose} />);
    screen.getByTestId('factura-display-cerrar').click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

/**
 * Applied-tax detail on every invoice (user requirement: "la factura debe
 * tener el detalle de impuestos aplicados, no solo el subvalor"): per tax
 * the name, rate, taxable base and amount, plus subtotal (base) and total.
 * One shared section for rotacion/salida/servicio/suscripcion/renovacion.
 */
describe('<FacturaDisplayModal /> — detalle de impuestos', () => {
  const SUSCRIPCION: FacturaRead = {
    ...BASE_FACTURA,
    uuid_ingreso: null,
    uuid_salida: null,
    datos_vehiculo: null,
    subtotal: 100840.34,
    total: 120000,
    items: [
      {
        uuid: 'item-s',
        tipo: 'servicio',
        concepto: 'subscripcion_mensual',
        cantidad: 1,
        valor_unitario: 100840.34,
        subtotal: 100840.34,
      },
    ],
    impuestos: [
      {
        uuid: 'imp-s',
        uuid_impuesto: 'iva-1',
        nombre_impuesto: 'IVA',
        codigo_impuesto: 'IVA',
        base_calculo: 100840.34,
        porcentaje_aplicado: 0.19,
        valor: 19159.66,
      },
    ],
  };

  it('T1: venta de suscripción → subtotal (base), IVA con tasa, base y valor, y total', () => {
    render(<FacturaDisplayModal factura={SUSCRIPCION} onClose={vi.fn()} />);

    expect(screen.getByTestId('factura-display-subtotal').textContent).toContain('100.840,34');
    const imp = screen.getByTestId('factura-display-impuesto');
    expect(imp.textContent).toContain('IVA');
    expect(imp.textContent).toContain('19.00%');
    expect(imp.textContent).toContain('19.159,66');
    expect(imp.textContent).toContain('100.840,34'); // base en la propia linea del impuesto
    expect(screen.queryByTestId('factura-display-impuesto-base')).toBeNull();
    expect(screen.getByTestId('factura-display-total').textContent).toContain('120.000');
  });

  it('T2: cada impuesto aplicado tiene su propia fila con base y valor', () => {
    render(
      <FacturaDisplayModal
        factura={{
          ...SUSCRIPCION,
          impuestos: [
            ...SUSCRIPCION.impuestos,
            {
              uuid: 'imp-2',
              uuid_impuesto: 'inc-1',
              nombre_impuesto: 'INC',
              codigo_impuesto: 'INC',
              base_calculo: 100840.34,
              porcentaje_aplicado: 0.08,
              valor: 8067.23,
            },
          ],
        }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getAllByTestId('factura-display-impuesto')).toHaveLength(2);
    expect(screen.queryAllByTestId('factura-display-impuesto-base')).toHaveLength(0);
  });

  it('T3: factura sin impuestos → no hay filas de impuesto pero sí subtotal y total', () => {
    render(
      <FacturaDisplayModal
        factura={{ ...BASE_FACTURA, impuestos: [], subtotal: 100, total: 100 }}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryAllByTestId('factura-display-impuesto')).toHaveLength(0);
    expect(screen.queryAllByTestId('factura-display-impuesto-base')).toHaveLength(0);
    expect(screen.getByTestId('factura-display-subtotal')).toBeTruthy();
    expect(screen.getByTestId('factura-display-total')).toBeTruthy();
  });
  it('T4: salida mensualidad ($0 con descuento) → Subtotal − Descuento + IVA = total, sin IVA positivo', () => {
    // AUD2: el IVA se persiste sobre el neto (0 / 0); el descuento se muestra
    // en base (subtotal − base del impuesto).
    render(
      <FacturaDisplayModal
        factura={{
          ...BASE_FACTURA,
          subtotal: 1260.5,
          descuento: 1500,
          total: 0,
          medio_pago: 'suscripcion',
          impuestos: [
            {
              uuid: 'imp-m',
              uuid_impuesto: 'iva-1',
              nombre_impuesto: 'IVA',
              codigo_impuesto: 'IVA',
              base_calculo: 0,
              porcentaje_aplicado: 0.19,
              valor: 0,
            },
          ],
        }}
        onClose={vi.fn()}
      />,
    );
    const totales = screen.getByTestId('factura-display-totales').textContent ?? '';
    expect(screen.getByTestId('factura-display-subtotal').textContent).toContain('1.260,50');
    expect(totales).toMatch(/Descuento\s*−\s*\$\s*1\.260,50/); // descuento en base
    expect(totales).not.toContain('1.500,00');
    expect(screen.getByTestId('factura-display-impuesto').textContent).toContain('0,00');
    expect(screen.getByTestId('factura-display-total').textContent).toContain('0,00');
  });

  it('D9: boton "Imprimir" imprime la factura completa (detalle de impuestos) por el bridge, sin cerrar el modal', async () => {
    const imprimir = instalarBridgeImprimir();
    const onClose = vi.fn();
    render(<FacturaDisplayModal factura={{ ...BASE_FACTURA, ...FACTURA_SUSCRIPCION_120000, numero_recibo: BASE_FACTURA.numero_recibo, uuid: FACTURA_SUSCRIPCION_120000.uuid }} onClose={onClose} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('factura-display-imprimir'));
    });
    expect(imprimir).toHaveBeenCalledTimes(1);
    const texto = textoImpreso(imprimir);
    expectDetalleImpuestos(texto, BASE_FACTURA.numero_recibo);
    expect(texto).toMatch(/IVA 19% \(base \$ ?[\d.]+,\d\d\)\s+\$ ?19\.159,66/);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('D10: reimpresion de la factura de un servicio: el boton imprime tambien con impuestos', async () => {
    const imprimir = instalarBridgeImprimir();
    render(<FacturaDisplayModal factura={{ ...BASE_FACTURA, uuid: FACTURA_ROTACION_200.uuid }} onClose={vi.fn()} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('factura-display-imprimir'));
    });
    const texto = textoImpreso(imprimir);
    expect(texto).toMatch(/IVA 19% \(base \$ ?[\d.]+,\d\d\)\s+\$ ?19,00/);
    expect(texto).not.toMatch(/Base \$/);
  });
});

/**
 * FB3 — invoice wording: Spanish concept (never the raw code), explicit
 * semantics of the line values vs the base subtotal, emisor NIT, Bogotá date.
 */
describe('<FacturaDisplayModal /> — textos de la factura (FB3)', () => {
  const SUSCRIPCION_REAL: FacturaRead = {
    ...BASE_FACTURA,
    created_at: '2026-10-07T21:07:00',
    uuid_ingreso: null,
    uuid_salida: null,
    datos_vehiculo: null,
    subtotal: 100840.34,
    total: 120000,
    datos_sucursal: { ...BASE_FACTURA.datos_sucursal, nit: '900000000-5' },
    items: [
      {
        uuid: 'item-s',
        tipo: 'servicio',
        concepto: 'subscripcion_mensual',
        cantidad: 1,
        valor_unitario: 100840.34,
        subtotal: 100840.34,
      },
    ],
    impuestos: [
      {
        uuid: 'imp-s',
        uuid_impuesto: 'iva-1',
        nombre_impuesto: 'IVA',
        codigo_impuesto: 'IVA',
        base_calculo: 100840.34,
        porcentaje_aplicado: 0.19,
        valor: 19159.66,
      },
    ],
  };

  it('F1: el concepto se muestra en español, no el código', () => {
    render(<FacturaDisplayModal factura={SUSCRIPCION_REAL} onClose={vi.fn()} />);
    const item = screen.getByTestId('factura-display-item').textContent ?? '';
    expect(item).toContain('Suscripción mensual');
    expect(item).not.toContain('subscripcion_mensual');
  });

  it('F2: las líneas declaran su semántica y el subtotal se rotula como base', () => {
    render(<FacturaDisplayModal factura={SUSCRIPCION_REAL} onClose={vi.fn()} />);
    expect(screen.getByTestId('factura-display-items').textContent).toContain('Valores antes de IVA');
    expect(screen.getByTestId('factura-display-totales').textContent).toContain('Subtotal (base)');
  });

  it('F3: factura de parqueo (líneas brutas) declara IVA incluido', () => {
    render(
      <FacturaDisplayModal
        factura={{
          ...SUSCRIPCION_REAL,
          subtotal: 1260.5,
          total: 1500,
          items: [{ ...SUSCRIPCION_REAL.items[0]!, concepto: 'parqueo_tiempo', valor_unitario: 1500, subtotal: 1500 }],
          impuestos: [{ ...SUSCRIPCION_REAL.impuestos[0]!, base_calculo: 1260.5, valor: 239.5 }],
        }}
        onClose={vi.fn()}
      />,
    );
    const items = screen.getByTestId('factura-display-items').textContent ?? '';
    expect(items).toContain('Parqueo por tiempo');
    expect(items).toContain('Valores con IVA incluido');
  });

  it('F4: el NIT del emisor se muestra con su DV y la fecha en hora de Bogotá', () => {
    render(<FacturaDisplayModal factura={SUSCRIPCION_REAL} onClose={vi.fn()} />);
    expect(screen.getByTestId('factura-display-sucursal').textContent).toContain('NIT 900000000-5');
    expect(screen.getByTestId('factura-display-desc').textContent).toContain('16:07');
  });
});

describe('FacturaDisplayModal — logo en la vista previa (igual que el impreso)', () => {
  it('muestra el logo easypunto arriba y abajo dentro del papel de la vista previa', () => {
    render(<FacturaDisplayModal factura={BASE_FACTURA} onClose={vi.fn()} />);
    const papel = screen.getByTestId('factura-display-preview');
    const cab = papel.querySelector('[data-testid="marca-ticket-encabezado"]');
    const pie = papel.querySelector('[data-testid="marca-ticket-pie"]');
    expect(cab?.getAttribute('src')).toMatch(/^data:image\/svg\+xml/);
    expect(cab?.getAttribute('alt')).toBe('easypunto');
    expect(pie?.getAttribute('src')).toMatch(/^data:image\/svg\+xml/);
    expect(papel.firstElementChild?.contains(cab as Node)).toBe(true);
    expect(papel.lastElementChild?.contains(pie as Node)).toBe(true);
  });
});
