/**
 * Constants for the `operacion` feature (HU-F4.3).
 *
 * `OPERACION_REFRESH_INTERVAL_MS` is the SWR `refreshInterval` for the
 * `useOcupacion()` hook. It MUST stay in lockstep with the backend
 * `RefreshMvOcupacionWorker.DEFAULT_REFRESH_INTERVAL_S` (also 10s). When the
 * backend worker cadence changes, this constant changes too — a mismatch
 * would let the renderer lag behind the materialized view refresh.
 *
 * DEC-SUC-11 verbatim: 10_000 ms is the only cadence this hook accepts.
 * No WebSocket / SSE fallback exists in this slice (v2 may evaluate SSE).
 */
export const OPERACION_REFRESH_INTERVAL_MS = 10_000;

/**
 * SWR `dedupingInterval` for the occupancy key — collapses intra-tick
 * duplicate requests when multiple components mount `<OcupacionStrip />`
 * on the same screen (forward consumers: F4.4 dashboard, F6.x ingreso).
 *
 * DEC-SUC-11 verbatim: 5_000 ms is half of the refresh interval so two
 * mounts within the same window share the cached payload.
 */
export const OPERACION_DEDUPING_INTERVAL_MS = 5_000;