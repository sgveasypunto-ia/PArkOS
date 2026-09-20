/**
 * `ventaSuscripcionApi.ts` — Zod mirror of the F1.12 backend
 * `VentaSuscripcionCreate` + `VentaSuscripcionResponse` wire shape
 * for `POST /api/v1/clientes/venta-suscripcion` (HU-F9.1, REQ-OPS-177).
 *
 * Mirrors `features/facturacion/api/facturaApi.ts` (F8.1) precedent:
 * the renderer-side Zod parser enforces the discriminator + nested
 * invariants so a misbehaving backend (extra fields, wrong types)
 * surfaces as a parse error instead of silently rendering a
 * half-truthy venta confirmation.
 *
 * Defense in depth (mirrors F1.12 Layer 4 — Pydantic `extra='forbid'`):
 * `VentaSuscripcionCreateSchema` rejects any extra fields the
 * backend smuggles in. The backend rejects at Pydantic time; the
 * renderer mirrors the same gate.
 */
import { z } from 'zod';

/**
 * Cliente payload — the operator types `nit`, `nombre`, `email`.
 * The Pydantic schema on the backend (`schemas/clientes.py`) accepts
 * the same shape for embedded-cliente (vs `uuid_cliente` reference
 * for existing-cliente); F9.1 always uses the embedded shape
 * (the wizard is operator-facing sale flow, not lookup-then-buy).
 */
const clienteSchema = z.object({
  nit: z.string().min(6, 'nit_min_6'),
  nombre: z.string().min(1, 'nombre_requerido'),
  email: z
    .string()
    .email('email_formato_invalido')
    .nullable()
    .optional(),
});

/**
 * F1.12 backend REQ-OPS-086 — placa format constraints
 * (`FORMATO_AUTO = ^[A-Z]{3}[0-9]{3}$` or
 * `FORMATO_MOTO = ^[A-Z]{3}[0-9]{2}[A-Z]$`). Renderer-side mirror
 * catches the operator's typo before the network round-trip.
 */
const placaRegex = z
  .string()
  .regex(/^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/, 'placa_formato_invalido');

/**
 * `VentaSuscripcionCreateSchema` — discriminated union:
 *   - `cobrar_ahora=true`  → `medio_pago` REQUIRED (efectivo | datafono)
 *   - `cobrar_ahora=false` → `medio_pago` OPTIONAL (deferred billing)
 *
 * `extra='forbid'` (F1.12 Layer 4) blocks client smuggling of
 * server-derived fields (`uuid_sucursal`, `vigente_desde`,
 * `monto_prorrateado`, etc.).
 */
const ventaCreateBase = {
  cliente: clienteSchema,
  placas: z
    .array(placaRegex)
    .min(1, 'placas_min_1')
    .max(2, 'placas_max_2'),
  uuid_tipo_subscripcion: z.string().uuid('uuid_tipo_subscripcion_invalido'),
  fecha_inicio_cobertura: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
};

export const VentaSuscripcionCreateSchema = z
  .discriminatedUnion('cobrar_ahora', [
    z
      .object({
        ...ventaCreateBase,
        cobrar_ahora: z.literal(true),
        medio_pago: z.enum(['efectivo', 'datafono']),
        emitir_factura_electronica: z.boolean().optional(),
      })
      .strict(),
    z
      .object({
        ...ventaCreateBase,
        cobrar_ahora: z.literal(false),
        medio_pago: z.enum(['efectivo', 'datafono']).optional(),
        emitir_factura_electronica: z.boolean().optional(),
      })
      .strict(),
  ]);
export type VentaSuscripcionCreate = z.infer<typeof VentaSuscripcionCreateSchema>;

/**
 * `VentaSuscripcionReadSchema` — response parse. Mirrors F1.12
 * `VentaSuscripcionResponse`. `uuid_factura` is `null` when
 * `cobrar_ahora=false` (deferred billing); `monto_prorrateado`
 * is `null` when `fecha_inicio_cobertura.day <= 15`.
 */
export const VentaSuscripcionReadSchema = z
  .object({
    uuid_subscripcion: z.string().uuid(),
    uuid_cliente: z.string().uuid(),
    uuid_vehiculos: z.array(z.string().uuid()),
    uuid_factura: z.string().uuid().nullable(),
    monto_prorrateado: z.number().nullable(),
  })
  .strict();
export type VentaSuscripcionRead = z.infer<typeof VentaSuscripcionReadSchema>;

export const POST_VENTA_SUSCRIPCION_PATH = '/api/v1/clientes/venta-suscripcion';
