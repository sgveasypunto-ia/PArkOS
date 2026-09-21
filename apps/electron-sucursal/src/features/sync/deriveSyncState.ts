/**
 * `deriveSyncState.ts` — pure selector from `SyncEstado` to `SyncState`
 * (HU-F11.1, AD-2).
 *
 *   - `never_synced` — `lag_seg === null` (branch has never synced).
 *   - `online`       — `lag_seg <= 60` (lag under 1 minute).
 *   - `lagging`      — `60 < lag_seg <= 3600` OR `pendientes > 5`.
 *   - `offline`      — `lag_seg > 3600` OR `pendientes > 100`
 *                      (safety net on pending backlog).
 *
 * The threshold values are D2-ratified (60/3600/5/100). The spec's
 * REQ-OPS-171 paragraph still states 300/3600/100 (R-CARRY-1); the
 * follow-up spec delta will realign REQ-OPS-171 to these values.
 *
 * `pendientes > 5` lifts a fresh backlog into `lagging` even when
 * the latest sync tick was inside the 60 s window — operators see
 * the warning before the lag clock catches up. The hard ceiling
 * `pendientes > 100` flips to `offline` regardless of `lag_seg` so a
 * stuck queue never masquerades as healthy.
 */
import type { SyncEstado } from './hooks/useSyncEstado';

export type SyncState = 'never_synced' | 'online' | 'lagging' | 'offline';

export function deriveSyncState(d: SyncEstado): SyncState {
  if (d.lag_seg === null) return 'never_synced';
  if (d.lag_seg > 3600 || d.pendientes > 100) return 'offline';
  // pendientes > 5 lifts the state to lagging EVEN when the lag clock
  // is fresh — operators see the warning before the 60s lag window
  // crosses. The hard ceiling (pendientes > 100 → offline) is checked
  // above so a stuck queue never masquerades as healthy.
  if (d.pendientes > 5) return 'lagging';
  if (d.lag_seg <= 60) return 'online';
  return 'lagging';
}
