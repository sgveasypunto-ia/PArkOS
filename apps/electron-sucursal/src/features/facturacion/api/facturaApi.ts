/**
 * `facturaApi.ts` — Zod mirror of the F1.9 / F1.10 `FacturaRead`
 * wire shape for `POST /api/v1/facturacion/factura` (HU-F8.1,
 * REQ-OPS-167).
 *
 * Mirrors `features/operacion/api/salidaApi.ts` precedent (F7.2):
 * the renderer-side Zod parser enforces the discriminator + nested
 * invariants so a misbehaving backend (extra fields, wrong types)
 * surfaces as a parse error instead of silently rendering a
 * half-truthy pago confirmation.
 *
 * Wire contract (discriminated union by `medio_pago`):
 *   - `efectivo`   → `{ monto_recibido_cents, vuelto_cents }` required
 *   - `datafono`   → `{ voucher }` required
 *   - `transferencia` → `{ voucher }` required (F8.x reserve)
 *
 * `cliente` always required (DEC-SUC-04 — consumidor final default
 * `NIT `222222222222222`); `email` is OPTIONAL but if present must
 * satisfy RFC 5322 via the shared Pydantic-style regex (F1.10 source).
 *
 * `factura_electronica` is OPTIONAL (BR1 + BR5 — FE may be pending,
 * rejected, or absent; the FE document is emitted async by the
 * cloud-side DIAN dispatcher).
 */
import { z } from 'zod';

/**
 * Email RFC 5322 lite — pragmatic subset that matches the F1.10
 * Pydantic `EmailStr` validator. The full RFC is impractical to
 * implement in a renderer; this subset catches the operator-facing
 * typos (missing `@`, missing TLD, illegal whitespace) without
 * rejecting legitimate edge cases like `+aliases`.
 */
const emailRfc5322Lite = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const clienteSchema = z.object({
  nit: z.string().min(6, 'nit_min_6'),
  nombre: z.string().min(1, 'nombre_requerido'),
  email: z.string().regex(emailRfc5322Lite).nullable().optional(),
});

const baseReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid(),
  uuid_ingreso: z.string().uuid().nullable(),
  created_at: z.string(),
  numero_recibo: z.string().regex(/^sucursal-\d{8}-\d{6}$/, 'numero_recibo_formato'),
  cliente: clienteSchema,
  factura_electronica: z.unknown().nullable().optional(),
});

const efectivoReadSchema = baseReadSchema.extend({
  medio_pago: z.literal('efectivo'),
  monto_recibido_cents: z.number().int().nonnegative(),
  total_cents: z.number().int().nonnegative(),
  vuelto_cents: z.number().int().nonnegative(),
});

const datafonoReadSchema = baseReadSchema.extend({
  medio_pago: z.literal('datafono'),
  total_cents: z.number().int().nonnegative(),
  voucher: z.string().min(1, 'voucher_requerido'),
});

export const FacturaReadSchema = z.discriminatedUnion('medio_pago', [
  efectivoReadSchema,
  datafonoReadSchema,
]);
export type FacturaRead = z.infer<typeof FacturaReadSchema>;

const POST_PATH = '/api/v1/facturacion/factura';

export interface PostFacturaEfectivo {
  uuid_ingreso: string;
  medio_pago: 'efectivo';
  monto_recibido_cents: number;
  total_cents: number;
  cliente: { nit: string; nombre: string; email?: string | null };
}

export interface PostFacturaDatafono {
  uuid_ingreso: string;
  medio_pago: 'datafono';
  total_cents: number;
  voucher: string;
  cliente: { nit: string; nombre: string; email?: string | null };
}

export type PostFacturaPayload = PostFacturaEfectivo | PostFacturaDatafono;

/**
 * Discriminated POST payload schema — Zod mirror used by the hook
 * to validate the input BEFORE sending it. Catches malformed
 * `{medio_pago, monto_recibido_cents, voucher}` tuples early.
 */
export const PostFacturaSchema = z.discriminatedUnion('medio_pago', [
  z.object({
    uuid_ingreso: z.string().uuid(),
    medio_pago: z.literal('efectivo'),
    monto_recibido_cents: z.number().int().positive(),
    total_cents: z.number().int().nonnegative(),
    cliente: clienteSchema,
  }),
  z.object({
    uuid_ingreso: z.string().uuid(),
    medio_pago: z.literal('datafono'),
    total_cents: z.number().int().nonnegative(),
    voucher: z.string().min(1, 'voucher_requerido'),
    cliente: clienteSchema,
  }),
]);

/**
 * `postFactura(payload, idempotencyKey)` — typed wrapper around
 * `parkosFetch` that forwards the supplied `Idempotency-Key` header
 * verbatim (the hook owns the SHA-256 closure via F7.2
 * `buildIdempotencyKey` so this fn stays header-agnostic about HOW
 * the key was derived).
 *
 * Errors propagate as `ParkosHttpError`. The hook (P3 / F3.1
 * invariant) catches 401 and clears the auth store.
 */
export async function postFactura(
  payload: PostFacturaPayload,
  idempotencyKey: string,
): Promise<FacturaRead> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  // Validate the payload locally so a mis-typed caller throws Zod
  // errors at the API boundary instead of leaking to the network.
  PostFacturaSchema.parse(payload);
  const raw = await parkosFetch<unknown>(POST_PATH, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });
  return FacturaReadSchema.parse(raw);
}

export const FACTURA_POST_PATH = POST_PATH;