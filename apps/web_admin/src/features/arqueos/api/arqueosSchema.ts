/**
 * `arqueosSchema.ts` — Zod schemas + TS types for the F18.2 admin
 * arqueo surface.
 *
 * Wire shapes mirror the BE 1:1:
 *   - ``ArqueoRead``       matches ``schemas/caja.py::ArqueoRead``.
 *   - ``ArqueoListResponse`` matches ``{items: ArqueoRead[], next_cursor: string|null}``.
 *   - ``DiferenciasRead``  matches ``schemas/caja.py::ArqueoDiferenciasResponse``
 *     (GET /caja-sesion/arqueos/{uuid}/diferencias). Same numeric fields,
 *     but the BE serializes the raw ``Float`` values so we mirror them as
 *     ``number`` on the FE (Pydantic ``Decimal`` -> ``float`` on the wire).
 *
 * Filters mirror the BE ``ArqueoListQueryParams`` (F18.1):
 *   - ``uuid_sucursal`` / ``fecha_desde`` / ``fecha_hasta`` / ``uuid_tipo_arqueo``
 *     are all OPTIONAL -- no "at least one" rule. When none is provided,
 *     the BE returns the most-recent ``limit`` arqueos across every branch.
 *   - ``limit`` defaults to 20, clamped server-side 1..100.
 *   - ``cursor`` opaque base64 JSON ``(ts, uuid)`` from the previous
 *     page's last row. Omitted on the first page.
 */
import { z } from 'zod';

export const arqueoReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  fecha_retencion_hasta: z.string(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_arqueo: z.string().uuid().nullable(),
  uuid_sesion: z.string().uuid().nullable(),
  valor_efectivo_esperado: z.string().nullable(),
  valor_datafono_esperado: z.string().nullable(),
  valor_efectivo_reportado: z.string().nullable(),
  valor_datafono_reportado: z.string().nullable(),
});

export type ArqueoRead = z.infer<typeof arqueoReadSchema>;

/**
 * Query shape for ``GET /api/v1/caja/arqueo``.
 *
 * The Zod parser is permissive -- all fields optional, mirroring the
 * BE's permissive Pydantic schema. The route at
 * ``features/arqueos/hooks/useArqueosAdmin.ts`` builds the URL
 * search params with only the non-empty fields, so an empty object
 * hits the endpoint with no params at all (most-recent ``limit`` rows
 * across every branch).
 */
export const arqueosListQuerySchema = z.object({
  uuid_sucursal: z.string().uuid().optional(),
  fecha_desde: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  fecha_hasta: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  uuid_tipo_arqueo: z.string().uuid().optional(),
  limit: z.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
});

export type ArqueosListQuery = z.infer<typeof arqueosListQuerySchema>;

export const arqueosListResponseSchema = z.object({
  items: z.array(arqueoReadSchema),
  next_cursor: z.string().nullable(),
});

export type ArqueosListResponse = z.infer<typeof arqueosListResponseSchema>;

/**
 * Per-arqueo deltas (GET /caja-sesion/arqueos/{uuid}/diferencias).
 *
 * The BE serializes ``Decimal`` as ``float`` -- the schema accepts
 * ``number`` directly so we don't coerce. The shape carries all four
 * signed components plus the two computed differences; the FE renders
 * the abs values via i18n'd labels.
 */
export const diferenciasReadSchema = z.object({
  uuid_arqueo: z.string().uuid(),
  valor_efectivo_esperado: z.number(),
  valor_datafono_esperado: z.number(),
  valor_efectivo_reportado: z.number(),
  valor_datafono_reportado: z.number(),
  diferencia_efectivo: z.number(),
  diferencia_datafono: z.number(),
});

export type DiferenciasRead = z.infer<typeof diferenciasReadSchema>;

/**
 * Per-arqueo resumen row (the response of ``GET /arqueo/resumen``).
 *
 * Carries the operator-/admin-side ``valor_efectivo_esperado /
 * reportado / diferencia`` plus the ``alerta_generada`` + ``alerta_uuid``
 * flags that the production handler sets when ``diferencia != 0`` (the
 * alerta generation is gated on the row at Step 10, not on this read
 * endpoint). Used by the F18.3 resumen tab.
 */
export const arqueoResumenItemSchema = z.object({
  uuid: z.string().uuid().nullable(),
  uuid_tipo_arqueo: z.string().uuid().nullable(),
  codigo_tipo_arqueo: z.string().nullable(),
  uuid_sesion: z.string().uuid().nullable(),
  valor_efectivo_esperado: z.string().nullable(),
  valor_datafono_esperado: z.string().nullable(),
  valor_efectivo_reportado: z.string().nullable(),
  valor_datafono_reportado: z.string().nullable(),
  diferencia_efectivo: z.string().nullable(),
  diferencia_datafono: z.string().nullable(),
  descuadre_pct: z.string().nullable(),
  alerta_generada: z.boolean().nullable(),
  alerta_uuid: z.string().uuid().nullable(),
});

export type ArqueoResumenItem = z.infer<typeof arqueoResumenItemSchema>;