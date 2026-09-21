/**
 * `alertas.ts` — FE Zod schemas for the alertas workflow endpoint
 * (HU-F11.2, REQ-OPS-177 + REQ-OPS-179 + REQ-OPS-180).
 *
 * Drift anchors resolved by these schemas:
 *   - DA-F11.2-1: BE `AlertaRead` returns 18 fields; FE MUST align.
 *   - DA-F11.2-9: state vocabulary `Literal["activa", "descartada",
 *     "resuelta"]` per BE Pydantic (`schemas/workflows.py:377`);
 *     legacy `abierta` / `cerrada` are FORBIDDEN.
 *   - DA-F11.2-14: `datos_nuevos: z.record(z.unknown()).nullable().optional()`
 *     so the schema parses today's BE response (column absent) and
 *     gracefully picks up the JSONB once ABBC-F11.2-BE-1 lands.
 *
 * The 18 fields correspond verbatim to BE `AlertaRead` declared at
 * `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py:328-353`.
 * Adding a 19th field here without a matching BE change is a
 * ZodError — defense in depth against BE schema drift (F11.1
 * REQ-OPS-170 precedent).
 */
import { z } from 'zod';

export const ALERTA_ESTADO = ['activa', 'descartada', 'resuelta'] as const;
export type AlertaEstado = (typeof ALERTA_ESTADO)[number];

export const AlertaSchema = z
  .object({
    uuid: z.string().uuid(),
    fecha_retencion_hasta: z.string(),
    created_at: z.string(),
    created_by: z.string().uuid().nullable(),
    sync_status: z.string().nullable(),
    sync_timestamp: z.string().nullable(),
    sync_attempts: z.number().int().nullable(),
    uuid_sucursal: z.string().uuid().nullable(),
    uuid_usuario: z.string().uuid().nullable(),
    uuid_arqueo: z.string().uuid().nullable(),
    tipo_alerta: z.string().nullable(),
    valor_diferencia_efectivo: z.union([z.string(), z.number()]).nullable(),
    valor_diferencia_datafono: z.union([z.string(), z.number()]).nullable(),
    uuid_alerta_padre: z.string().uuid().nullable(),
    timestamp_evento: z.string().nullable(),
    vigente_desde: z.string().nullable(),
    vigente_hasta: z.string().nullable(),
    estado: z.enum(ALERTA_ESTADO).nullable(),
    /**
     * DA-F11.2-14 — JSONB column. NOT exposed by `AlertaRead` today
     * (ABIERTO-07 / ABBC-F11.2-BE-1 tracks the BE addition). Declared
     * `.optional()` so the schema succeeds against the current BE
     * response AND gracefully picks up the column when the BE lands it.
     */
    datos_nuevos: z.record(z.unknown()).nullable().optional(),
  })
  .strict();

export type AlertaRead = z.infer<typeof AlertaSchema>;

export const AlertaReadListSchema = z.array(AlertaSchema);

/**
 * `AlertTypeSchema` — the second SWR payload
 * (`GET /workflows/alert-types?uuid_sucursal=X`) supplying
 * `severidad`, `descripcion`, and `mensaje` for the client-side
 * merge per REQ-OPS-179 path (b) — DA-F11.2-10 resolved.
 */
export const AlertTypeSchema = z
  .object({
    codigo: z.string(),
    severidad: z.enum(['alta', 'media', 'baja']),
    descripcion: z.string(),
    mensaje: z.string(),
  })
  .strict();

export type AlertTypeRead = z.infer<typeof AlertTypeSchema>;

export const AlertTypeReadListSchema = z.array(AlertTypeSchema);

/**
 * `MergedAlerta` — the post-merge row exposed by `useAlertas`. The
 * shape is the AlertaRead fields PLUS the three display fields from
 * the alert_types merge. Display fields are always present on the
 * merged row (drops silently if `alert_types` is missing the code,
 * per ABIERTO-06).
 */
export interface MergedAlerta extends AlertaRead {
  severidad: 'alta' | 'media' | 'baja';
  descripcion: string;
  mensaje: string;
}
