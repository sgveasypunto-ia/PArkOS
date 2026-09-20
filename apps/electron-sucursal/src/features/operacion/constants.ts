/**
 * Constants for the `operacion` feature (HU-F4.3 + HU-F7.1).
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

/**
 * SWR `refreshInterval` for the cotizar polling (HU-F7.1, useCotizacion).
 * 1 second cadence — the cotización may change every minute as time
 * accumulates; we re-fetch once per second so the operator sees the
 * breakdown update near-realtime without overwhelming the backend.
 *
 * Rationale (plan.md:1685): the backend `vigente_hasta` is 15 minutes;
 * the renderer polls 60× within that window. Backend has no rate limit
 * concern — this is a single endpoint with bounded cardinality
 * (1 ingreso at a time).
 */
export const OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000;

/**
 * Per-fetch timeout for `useCotizacion` (HU-F7.1, useCotizacion).
 * 5 seconds — generous for localhost; aborts if the backend is hung.
 * Triggers SWR retry per the `shouldRetryOnError` policy (excludes
 * 401/403/404 terminal codes).
 */
export const OPERACION_COTIZAR_TIMEOUT_MS = 5_000;