/**
 * `alertasSchema.ts` — Zod schemas + TS types for the HU-F19.5 admin
 * "bandeja de alertas" surface.
 *
 * Wire shapes mirror the BE 1:1 (verified against
 * `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py`,
 * concurrently extended by the HU-F19.5 backend slice in this same
 * worktree):
 *
 *   - `AlertaRead`      matches `schemas/workflows.py::AlertaListItem`
 *     (= `AlertaRead` + `severity`), the shape returned by every item of
 *     `GET /api/v1/workflows/alerta`.
 *   - `AlertasListResponse` matches `{items: AlertaRead[], next_cursor: string|null}`
 *     — same cursor-paginated envelope every other list endpoint in this
 *     repo uses (mirrors `arqueosSchema.ts`).
 *   - `severity` is `'critical' | 'warning' | 'info' | null` — the raw
 *     `prod.alert_types.severity` vocabulary (`alert_types_severity_check`),
 *     LEFT-JOINed onto `tipo_alerta`. `null` means `tipo_alerta` has no
 *     matching `alert_types` row (BR4) — the UI renders "—" for it, it is
 *     NOT an error state.
 *   - `estado` is exactly `'abierta' | 'en_revision' | 'resuelta'`.
 *
 * Query params for the list (per the HU-F19.5 contract handed down with
 * the task — the BE hand-builds this endpoint outside the generic
 * factory, same pattern as `workflows_alerta.py`'s `descartar` POST, so
 * it does NOT reuse `AlertaFilter`'s `timestamp_evento__gte/lte` names):
 *
 *   `uuid_sucursal`, `tipo_alerta`, `estado`, `severidad`, `desde`,
 *   `hasta`, `cursor`, `limit`.
 *
 * Single-item GET (`GET /api/v1/workflows/alerta/{uuid}`, the generic
 * `make_router` current-version read) returns plain `AlertaRead` —
 * WITHOUT `severity` (that field only exists on the hand-built list
 * endpoint's `AlertaListItem`). `alertaDetailReadSchema` models that by
 * making `severity` OPTIONAL (field absent) rather than nullable-only,
 * so `AlertaDetalle` can tell "BE doesn't carry this field here" apart
 * from "carried and explicitly null" — both render as "—" per BR4, but
 * the distinction is documented for future maintainers.
 */
import { z } from 'zod';

export const ALERTA_ESTADOS = ['abierta', 'en_revision', 'resuelta'] as const;
export type AlertaEstado = (typeof ALERTA_ESTADOS)[number];

/** Raw `prod.alert_types.severity` vocabulary (`alert_types_severity_check`). */
export const ALERTA_SEVERITIES = ['critical', 'warning', 'info'] as const;
export type AlertaSeverity = (typeof ALERTA_SEVERITIES)[number];

/** Shared fields present on every `prod.alerta` read-back, list or detail. */
const alertaBaseShape = {
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
  valor_diferencia_efectivo: z.string().nullable(),
  // The backend no longer sends the datafono difference (cash-only cuadre);
  // keep it optional so legacy payloads still parse.
  valor_diferencia_datafono: z.string().nullable().optional(),
  uuid_alerta_padre: z.string().uuid().nullable(),
  timestamp_evento: z.string().nullable(),
  vigente_desde: z.string().nullable(),
  vigente_hasta: z.string().nullable(),
  // Legacy rows were written with `estado = 'activo'`; read them as `abierta`
  // so a single old row does not make the whole inbox fail to parse.
  estado: z.preprocess((v) => (v === 'activo' ? 'abierta' : v), z.enum(ALERTA_ESTADOS).nullable()),
  // Free-form event payload. For `suscripcion_placa_agregada|quitada` it is
  // {placa, accion, uuid_subscripcion, uuid_vehiculo, uuid_sucursal, actor}.
  // Optional/nullable: older servers do not expose it.
  datos_nuevos: z.record(z.unknown()).nullable().optional(),
};

/** `GET /api/v1/workflows/alerta` list item — carries `severity` (BR4). */
export const alertaReadSchema = z.object({
  ...alertaBaseShape,
  severity: z.enum(ALERTA_SEVERITIES).nullable(),
});
export type AlertaRead = z.infer<typeof alertaReadSchema>;

/**
 * `GET /api/v1/workflows/alerta/{uuid}` single-item read — the generic
 * factory `read_schema` (`AlertaRead`, no `severity`). `.optional()`
 * (not `.nullable()`) because the field is ABSENT from the payload,
 * not present-and-null.
 */
export const alertaDetailReadSchema = z.object({
  ...alertaBaseShape,
  severity: z.enum(ALERTA_SEVERITIES).nullable().optional(),
});
export type AlertaDetailRead = z.infer<typeof alertaDetailReadSchema>;

export const alertasListResponseSchema = z.object({
  items: z.array(alertaReadSchema),
  next_cursor: z.string().nullable(),
});
export type AlertasListResponse = z.infer<typeof alertasListResponseSchema>;

/**
 * Query shape for `GET /api/v1/workflows/alerta`. All fields optional
 * except `limit` — mirrors `arqueosSchema.ts::ArqueosListQuery`. The
 * container builds the `URLSearchParams` with only the non-empty
 * fields (see `alertasApi.ts::fetchAlertas`).
 */
export interface AlertasListQuery {
  uuid_sucursal?: string;
  tipo_alerta?: string;
  estado?: AlertaEstado;
  severidad?: AlertaSeverity;
  desde?: string;
  hasta?: string;
  limit: number;
  cursor?: string;
}

/**
 * react-hook-form + zodResolver input for `<DescartarAlertaModal />`.
 * `observaciones` mandatory + non-blank, mirrors the BE's
 * `AlertaDescartarEndpoint` (`min_length=1`, `strip_whitespace=True`).
 */
export const alertaDescartarFormSchema = z.object({
  observaciones: z
    .string()
    .trim()
    .min(1, 'Las observaciones son obligatorias.'),
});
export type AlertaDescartarFormInput = z.infer<typeof alertaDescartarFormSchema>;
