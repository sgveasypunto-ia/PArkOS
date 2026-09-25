/**
 * `facturaServicioApi.ts` — HU-F8.3 (ajuste 2026-09-25): cliente para
 * `POST /api/v1/facturacion/factura-servicio`.
 *
 * Factura de un servicio suelto (ej. reimpresión de tiquete) SIN
 * `prod.salidas` asociada -- ancla a `uuid_ingreso` en vez de
 * `uuid_salida`. Mismo shape/response que `facturaApi.ts`'s
 * `postFactura` (reusa `FacturaReadSchema`/`FacturaRead` tal cual --
 * el backend responde con el mismo `build_display_factura`), solo
 * cambia el request y la ruta.
 */
import { z } from 'zod';

import { FacturaReadSchema, type FacturaRead } from './facturaApi';

const POST_PATH = '/api/v1/facturacion/factura-servicio';

export interface FacturaServicioItemPost {
  tipo: 'servicio' | 'producto' | 'descuento';
  concepto: string;
  cantidad: number;
  valor_unitario: number;
  uuid_tarifa_sucursal?: string | null;
}

export interface FacturaServicioClienteDatosPost {
  tipo_identificador: 'NIT' | 'CC' | 'CE' | 'pasaporte';
  numero_identificacion: string;
  dv?: string | null;
  nombre: string;
  apellido?: string | null;
  email?: string | null;
  telefono?: string | null;
}

export interface PostFacturaServicioEfectivo {
  uuid_ingreso: string;
  medio_pago: 'efectivo';
  items: FacturaServicioItemPost[];
  subtotal: number;
  total: number;
  fe_con_datos?: boolean;
  fe_datos_cliente?: FacturaServicioClienteDatosPost;
}

export interface PostFacturaServicioDatafono {
  uuid_ingreso: string;
  medio_pago: 'datafono';
  items: FacturaServicioItemPost[];
  subtotal: number;
  total: number;
  referencia: string;
  fe_con_datos?: boolean;
  fe_datos_cliente?: FacturaServicioClienteDatosPost;
}

export type PostFacturaServicioPayload =
  | PostFacturaServicioEfectivo
  | PostFacturaServicioDatafono;

const itemPostSchema = z.object({
  tipo: z.enum(['servicio', 'producto', 'descuento']),
  concepto: z.string().min(1).max(255),
  cantidad: z.number().int().positive(),
  valor_unitario: z.number().nonnegative(),
  uuid_tarifa_sucursal: z.string().uuid().nullable().optional(),
});

const clienteDatosPostSchema = z.object({
  tipo_identificador: z.enum(['NIT', 'CC', 'CE', 'pasaporte']),
  numero_identificacion: z.string().min(5).max(20),
  dv: z.string().min(1).max(2).nullable().optional(),
  nombre: z.string().min(1).max(120),
  apellido: z.string().min(1).max(120).nullable().optional(),
  email: z.string().min(5).max(120).nullable().optional(),
  telefono: z.string().min(7).max(20).nullable().optional(),
});

export const PostFacturaServicioSchema = z.discriminatedUnion('medio_pago', [
  z.object({
    uuid_ingreso: z.string().uuid(),
    medio_pago: z.literal('efectivo'),
    items: z.array(itemPostSchema).min(1).max(50),
    subtotal: z.number(),
    total: z.number().nonnegative(),
    fe_con_datos: z.boolean().optional(),
    fe_datos_cliente: clienteDatosPostSchema.optional(),
  }),
  z.object({
    uuid_ingreso: z.string().uuid(),
    medio_pago: z.literal('datafono'),
    items: z.array(itemPostSchema).min(1).max(50),
    subtotal: z.number(),
    total: z.number().nonnegative(),
    referencia: z.string().min(1, 'voucher_requerido'),
    fe_con_datos: z.boolean().optional(),
    fe_datos_cliente: clienteDatosPostSchema.optional(),
  }),
]);

/**
 * `postFacturaServicio(payload, idempotencyKey)` — typed wrapper
 * around `parkosFetch`. Errors propagate as `ParkosHttpError`.
 */
export async function postFacturaServicio(
  payload: PostFacturaServicioPayload,
  idempotencyKey: string,
): Promise<FacturaRead> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  PostFacturaServicioSchema.parse(payload);
  const raw = await parkosFetch<unknown>(POST_PATH, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });
  return FacturaReadSchema.parse(raw);
}

export const FACTURA_SERVICIO_POST_PATH = POST_PATH;
