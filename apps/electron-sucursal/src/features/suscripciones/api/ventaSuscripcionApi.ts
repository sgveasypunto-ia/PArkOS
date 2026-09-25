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

import { FacturaReadSchema } from '../../facturacion/api/facturaApi';

/**
 * Cliente payload — el operador elige persona natural (CC/CE/pasaporte)
 * o empresa (NIT) en el paso 1 (`ClienteIdentificacionFields`, mismo
 * componente compartido que `PagoModal`). El schema backend
 * (`schemas/clientes.py::VentaSuscripcionCreate.cliente`) es
 * `ClientesCreate | None` verbatim — sin campo `nit`, solo
 * `tipo_identificador` + `numero_identificacion` (+ `dv` opcional,
 * solo persistido como validación cuando `tipo_identificador==='NIT'`
 * — DEC-VENTA-07 lo descarta antes del INSERT) + `apellido` (vacío
 * para persona jurídica, `.mmd` `clientes.apellido`).
 *
 * Ajuste (identificación persona natural/empresa): `tipo_identificador`
 * ya no es el literal `'NIT'` fijo — el paso 1 del wizard siempre pide
 * un cliente real identificado (a diferencia de `PagoModal`, acá no
 * hay checkbox ni "cliente genérico").
 *
 * BUGFIX (2026-09-25, encontrado por el operador probando la venta en
 * vivo): este schema mandaba `{nit, nombre, email}` -- el backend
 * respondía 422 `extra_forbidden` en `cliente.nit` SIEMPRE que se
 * creaba un cliente nuevo (sin `uuid_cliente`), porque ni siquiera
 * viajaban los campos requeridos `tipo_identificador`/
 * `numero_identificacion`. La venta de suscripción a un cliente nuevo
 * nunca pudo completarse por este contrato.
 */
const clienteSchema = z.object({
  tipo_identificador: z.enum(['NIT', 'CC', 'CE', 'pasaporte']),
  numero_identificacion: z.string().min(5, 'documento_min_5'),
  dv: z.string().optional(),
  nombre: z.string().min(1, 'nombre_requerido'),
  apellido: z.string().optional(),
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
 *
 * BUGFIX (2026-09-25): `.strict()` previously only recognised 5 of the
 * 11 fields `VentaSuscripcionResponse` (backend `schemas/clientes.py`)
 * actually returns -- `uuid_sucursal`, `fecha_inicio_cobertura`,
 * `fecha_vencimiento`, `valor_total_plan`, `uuid_factura_electronica`
 * and `uuid_envio_dian` were missing. `.strict()` rejects unknown
 * keys, so EVERY successful sale (`cobrar_ahora` true or false) threw
 * a `ZodError` in `mutateFn` instead of resolving -- the wizard never
 * reached its post-pago step, which is why the operator never saw a
 * ticket/factura confirmation. `factura` is the HU-F9.1 addition: the
 * enriched `FacturaRead` projection (same shape `POST /facturacion/
 * factura` returns) so the wizard can render `<FacturaDisplayModal />`
 * + fire the recibo print envelope, `null` when `cobrar_ahora=false`.
 *
 * BUGFIX part 2 (found live via Chrome DevTools while validating the
 * fix above): `monto_prorrateado` was `z.number().nullable()`, but
 * FastAPI/Pydantic serializes `Decimal` fields as JSON STRINGS (e.g.
 * `"22000.00"`), not numbers -- same convention `valor_total_plan`
 * already accounts for via `z.coerce.number()`. A non-null
 * `monto_prorrateado` (any sale after day 15, A-09 prorrateo) failed
 * `z.number()` validation, throwing inside `mutateFn` and silently
 * swallowing the whole successful response as an unhandled rejection.
 * `z.coerce.number()` composed with `.nullable()` still passes literal
 * JSON `null` through untouched (Zod short-circuits nullable BEFORE
 * running the inner schema).
 *
 * `factura_electronica_error` — KD-VENTA-03b (operator directive,
 * 2026-09-25): "el flujo tiene que garantizarse solo hasta que se
 * pague y se genere la factura". FE emission runs AFTER the payment
 * commits, in its own transaction; a failure there degrades
 * gracefully instead of undoing the sale. This field carries the
 * reason (`resolucion_facturacion_no_encontrada`, `numeracion_agotada`,
 * `resolucion_sin_prefijo`, `missing_sucursal_context`) so the wizard
 * can tell the operator "cobrado, FE pendiente" instead of silently
 * dropping it. `null` on success or when FE wasn't requested.
 */
export const VentaSuscripcionReadSchema = z
  .object({
    uuid_subscripcion: z.string().uuid(),
    uuid_cliente: z.string().uuid(),
    uuid_vehiculos: z.array(z.string().uuid()),
    uuid_sucursal: z.string().uuid(),
    fecha_inicio_cobertura: z.string(),
    fecha_vencimiento: z.string(),
    valor_total_plan: z.coerce.number(),
    monto_prorrateado: z.coerce.number().nullable(),
    uuid_factura: z.string().uuid().nullable(),
    uuid_factura_electronica: z.string().uuid().nullable(),
    uuid_envio_dian: z.string().uuid().nullable(),
    factura: FacturaReadSchema.nullable(),
    factura_electronica_error: z.string().nullable(),
  })
  .strict();
export type VentaSuscripcionRead = z.infer<typeof VentaSuscripcionReadSchema>;

export const POST_VENTA_SUSCRIPCION_PATH = '/api/v1/clientes/venta-suscripcion';

/**
 * `TipoSubscripcionSchema` — read shape for
 * `GET /api/v1/tipos-subscripciones?uuid_sucursal=X` (F1.12 archive,
 * `[V]` per plan.md §3.2). Mirrors the backend `TipoSubscripcionesRead`
 * Pydantic schema. The wizard step 3 surfaces this list as a
 * selectable grid (plan name, value, duration) so the operator
 * doesn't have to memorize / paste a UUID.
 */
export const TipoSubscripcionSchema = z
  .object({
    uuid: z.string().uuid(),
    tipo: z.string().min(1),
    valor: z.coerce.number().nonnegative(),
    duracion_dias: z.coerce.number().int().positive(),
    cantidad_maxima_vehiculos: z.coerce.number().int().positive(),
    mismo_tipo_vehiculo: z.boolean(),
    tipo_cliente_permitido: z
      .string()
      .nullable()
      .optional()
      .or(z.literal('')),
  });
// READ schema (no .strict()): BE is authoritative for bi-temporal +
// audit columns (vigente_desde / vigente_hasta / estado / created_at
// / created_by / sync_status) which the catalog endpoints include on
// every row. Rejecting them at the Zod parse boundary would break the
// FE every time the BE adds a new column -- `.passthrough`-equivalent
// behavior is the correct default for a read mirror.
export type TipoSubscripcion = z.infer<typeof TipoSubscripcionSchema>;

/**
 * List-envelope schema for the catalog GET endpoints. All Parkos
 * catalogs (catalogos.py) serialize as
 *   `{ items: TipoSubscripcion[], next_cursor: string | null }`
 * per the F1.12 cursor-pagination contract. The renderer-side Zod
 * mirror enforces the envelope so the catalog UI does not have to
 * handle `undefined` / array-vs-object drift.
 */
export const TipoSubscripcionListSchema = z.object({
  items: z.array(TipoSubscripcionSchema),
  next_cursor: z.string().nullable(),
});

/**
 * `GET /api/v1/catalogos/tipo-subscripciones?uuid_sucursal=X` --
 * server-side filtered by the active branch. Mounted in
 * `catalogos.py:148` under the `catalogos` prefix; F11.3 follow-up
 * after the previous path of `/api/v1/tipos-subscripciones` 404'd --
 * the BE puts every catalog under `/catalogos/{resource}`.
 */
export const GET_TIPOS_SUBSCRIPCION_PATH = '/api/v1/catalogos/tipo-subscripciones';
