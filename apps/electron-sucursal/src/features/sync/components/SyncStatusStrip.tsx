/**
 * `<SyncStatusStrip />` — F11.1 deprecation shim.
 *
 * This file used to export a 3-color chip derived from
 * `useSyncEstado().data.estado`. After F11.1 the backend no longer
 * returns `estado` (REQ-OPS-170 + DA-F11.1-7 GATING — backend
 * `SyncEstadoRead` ships `ultima_sync_at`, `lag_seg`, `pendientes`
 * only) and the chip is superseded by the global top-of-page
 * `<SyncBanner />` at `apps/electron-sucursal/src/components/SyncBanner.tsx`.
 *
 * To keep every existing import path working (`Dashboard.tsx:50`,
 * `Dashboard.cold-mount.test.tsx` stub, and any other in-tree
 * consumer) we re-export `<SyncBanner />` under the legacy name.
 * Removal of this shim is deferred to F12.x (R-CARRY-2).
 */
export { SyncBanner as SyncStatusStrip } from '../../../components/SyncBanner';
export type { SyncBannerProps as SyncStatusStripProps } from '../../../components/SyncBanner';
