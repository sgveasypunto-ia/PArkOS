/**
 * `SyncStatusStrip.test.tsx` — Strict-TDD RED scaffold for HU-F11.1
 * (REQ-OPS-171 sync-to-cloud top-of-page banner; AD-deprecation shim).
 *
 * Drift anchor resolved: the existing
 * `apps/electron-sucursal/src/features/sync/components/SyncStatusStrip.tsx`
 * is a 3-color chip that consumes the legacy `data.estado` field. After
 * C2 (GREEN) it becomes a deprecation shim that re-exports the new
 * `<SyncBanner />` so the in-Dashboard import path
 * (`import { SyncStatusStrip } from '.../sync/components/SyncStatusStrip'`)
 * keeps working while the new top-of-page banner lives at
 * `apps/electron-sucursal/src/components/SyncBanner.tsx`.
 *
 * Coverage:
 *   S1: importing `SyncStatusStrip` from the legacy path returns the
 *       SAME module identity as importing `SyncBanner` from the new
 *       top-of-page path (deprecation shim re-export).
 *
 * The test is RED until C2 modifies `SyncStatusStrip.tsx` to a shim
 * re-exporting `SyncBanner`. Once GREEN, the existing
 * `Dashboard.tsx:50` import keeps working without source changes
 * elsewhere.
 */
import { describe, it, expect } from 'vitest';

import * as SyncStatusStripModule from '../components/SyncStatusStrip';
import * as SyncBannerModule from '../../../components/SyncBanner';

describe('SyncStatusStrip — deprecation shim (HU-F11.1)', () => {
  it('S1: SyncStatusStrip is a re-export of SyncBanner (preserves Dashboard import path)', () => {
    // The shim MUST re-export the same component identity. Today the
    // legacy chip exports `SyncStatusStrip` as its own function — this
    // assertion fails until C2 replaces the file with a re-export.
    expect(SyncStatusStripModule.SyncStatusStrip).toBe(
      SyncBannerModule.SyncBanner,
    );
  });
});
