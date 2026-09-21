/**
 * Shared TS types for the F12.1 "Mi turno" panel (REQ-OPS-184..190).
 *
 * `MiTurnoRead` mirrors the backend Pydantic `MiTurnoRead` field-for-field
 * (snake_case verbatim — DA-F12.1-1 GATING). The shape is locked by:
 *   - BE pytest: `backend/tests/unit/test_mi_turno_schema.py` reads
 *     `MiTurnoRead.model_fields.keys()`.
 *   - FE vitest: `apps/electron-sucursal/src/lib/api/schemas/__tests__/
 *     mi-turno.test.ts` reads `Object.keys(MiTurnoSchema.shape)`.
 *
 * Adding a field here without updating BE breaks CI on both pyramids.
 */
export interface MiTurnoRead {
  uuid_sesion: string;
  uuid_sucursal: string;
  timestamp_calculo: string;
  ingresos_count: number;
  salidas_count: number;
  total_cobrado_efectivo_cop: number;
  total_cobrado_datafono_cop: number;
}

/**
 * Convenience: the SUM of the two medio_pago buckets. The panel renders
 * this as the `totalCobrado` KPI cell (informational; the canonical
 * wire values live on ``total_cobrado_efectivo_cop`` and
 * ``total_cobrado_datafono_cop``).
 */
export function totalCobradoFromMiTurno(read: MiTurnoRead): number {
  return read.total_cobrado_efectivo_cop + read.total_cobrado_datafono_cop;
}

/**
 * All-zero fallback used by the panel when:
 *   - `uuid_sesion` is `null` (operator hasn't opened turno), OR
 *   - the SWR data is `undefined` (loading or 5xx mid-poll).
 *
 * BE always returns 200 with zeros for the zero-state (REQ-OPS-184 S2,
 * DA-F12.1-4). The fallback mirrors that contract so the panel never
 * has to special-case missing data.
 */
export function emptyMiTurno(uuid_sesion: string | null, uuid_sucursal: string | null): MiTurnoRead {
  return {
    uuid_sesion: uuid_sesion ?? '00000000-0000-0000-0000-000000000000',
    uuid_sucursal: uuid_sucursal ?? '00000000-0000-0000-0000-000000000000',
    timestamp_calculo: new Date(0).toISOString(),
    ingresos_count: 0,
    salidas_count: 0,
    total_cobrado_efectivo_cop: 0,
    total_cobrado_datafono_cop: 0,
  };
}