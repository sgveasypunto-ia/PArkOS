/**
 * Shared `FacturaRead` fixtures for the invoice print tests: one per invoice
 * type (rotation, subscription sale/renewal, $0 subscription exit). Amounts
 * follow the backend rule "price includes IVA 19 %": base = total / 1.19.
 */
import type { FacturaRead } from '../../../features/facturacion/api/facturaApi';

const UUID = (n: number): string => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

export const FACTURA_BASE: FacturaRead = {
  uuid: UUID(1),
  created_at: '2026-10-07T10:30:00',
  uuid_sucursal: UUID(2),
  uuid_ingreso: null,
  uuid_salida: null,
  subtotal: 0,
  descuento: 0,
  total: 0,
  uuid_cliente: null,
  items: [],
  estado: 'pagada',
  medio_pago: 'efectivo',
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  numero_recibo: 'sucursal-20261007-000012',
  cliente: null,
  datos_sucursal: {
    razon_social: 'Parqueadero Centro',
    nit: '900123456-7',
    direccion: 'Calle 10 # 5-20',
    ciudad: 'Bogota',
    telefono: '3001234567',
    horario: '24h',
    regimen: 'Responsable de IVA',
  },
  datos_vehiculo: null,
  impuestos: [],
  pagos: [],
  factura_electronica: null,
};

function iva(base: number, valor: number, n: number): FacturaRead['impuestos'][number] {
  return {
    uuid: UUID(100 + n),
    uuid_impuesto: UUID(200 + n),
    nombre_impuesto: 'IVA',
    codigo_impuesto: '01',
    base_calculo: base,
    porcentaje_aplicado: 0.19,
    valor,
  };
}

/** Subscription sale / renewal, total 120.000 (IVA included). */
export const FACTURA_SUSCRIPCION_120000: FacturaRead = {
  ...FACTURA_BASE,
  subtotal: 100840.34,
  total: 120000,
  items: [
    {
      uuid: UUID(11),
      tipo: 'servicio',
      concepto: 'Mensualidad automovil',
      cantidad: 1,
      valor_unitario: 120000,
      subtotal: 120000,
    },
  ],
  cliente: {
    tipo_identificador: 'CC',
    numero_identificacion: '1020304050',
    dv: null,
    nombre: 'Laura',
    apellido: 'Martinez',
    email: null,
    telefono: null,
  },
  impuestos: [iva(100840.34, 19159.66, 1)],
  factura_electronica: {
    uuid: UUID(30),
    prefijo: 'SETP',
    consecutivo: 990000012,
    estado_dian: 'pendiente',
    cufe: null,
  },
};

/** Rotation exit of 200 COP with plate and times. */
export const FACTURA_ROTACION_200: FacturaRead = {
  ...FACTURA_BASE,
  uuid_ingreso: UUID(3),
  uuid_salida: UUID(4),
  subtotal: 168.07,
  total: 200,
  items: [
    {
      uuid: UUID(12),
      tipo: 'servicio',
      concepto: 'Servicio de parqueo',
      cantidad: 1,
      valor_unitario: 200,
      subtotal: 200,
    },
  ],
  datos_vehiculo: {
    placa: 'ABC123',
    uuid_tipo_vehiculo: null,
    fecha_ingreso: '2026-10-07T09:00:00',
    fecha_salida: '2026-10-07T10:30:00',
    minutos: 90,
  },
  impuestos: [iva(168.07, 31.93, 2)],
};

/** Subscription exit: full-value service line + equal discount, total $0. */
export const FACTURA_MENSUALIDAD_CERO: FacturaRead = {
  ...FACTURA_BASE,
  uuid_ingreso: UUID(5),
  uuid_salida: UUID(6),
  subtotal: 168.07,
  descuento: 168.07,
  total: 0,
  medio_pago: 'suscripcion',
  items: [
    {
      uuid: UUID(13),
      tipo: 'servicio',
      concepto: 'Estadia',
      cantidad: 1,
      valor_unitario: 200,
      subtotal: 200,
    },
    {
      uuid: UUID(14),
      tipo: 'descuento',
      concepto: 'Descuento por mensualidad - Mensual auto',
      cantidad: 1,
      valor_unitario: 200,
      subtotal: 200,
    },
  ],
  datos_vehiculo: {
    placa: 'XYZ987',
    uuid_tipo_vehiculo: null,
    fecha_ingreso: '2026-10-07T09:00:00',
    fecha_salida: '2026-10-07T10:30:00',
    minutos: 90,
  },
  impuestos: [iva(0, 0, 3)],
};
