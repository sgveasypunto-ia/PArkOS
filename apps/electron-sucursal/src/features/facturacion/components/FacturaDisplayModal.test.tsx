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
import { render, screen, cleanup } from '@testing-library/react';
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
    expect(fe.textContent).toContain('aceptado');
    expect(fe.textContent).toContain('abc123');
  });

  it('D5: "Cerrar" click → onClose fires', () => {
    const onClose = vi.fn();
    render(<FacturaDisplayModal factura={BASE_FACTURA} onClose={onClose} />);
    screen.getByTestId('factura-display-cerrar').click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
