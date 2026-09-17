/**
 * State-machine tests for `useDashboardDrawerStore` (REQ-OPS-138).
 *
 * Coverage:
 *   D1: initial state — `openDrawer: null`, `lastAnchorId: null`.
 *   D2: `open(kind, anchorId)` sets state correctly.
 *   D3: opening a second drawer while one is already open swaps cleanly
 *       (single-drawer invariant).
 *   D4: `close()` resets both fields to null.
 *   D5: `close()` after `close()` is a no-op (idempotent).
 *   D6: state is decoupled between hooks — both observers see the same
 *       store (singleton).
 *   D7: `isDrawerOpen` helper returns the right boolean for each kind.
 */
import { describe, it, expect, beforeEach } from 'vitest';

import {
  useDashboardDrawerStore,
  isDrawerOpen,
  type NonNullDrawerKind,
} from './dashboardDrawerStore';

beforeEach(() => {
  // Reset to defaults between tests so order-independence holds.
  useDashboardDrawerStore.getState().close();
});

describe('useDashboardDrawerStore — REQ-OPS-138 state machine', () => {
  it('D1: initial state is closed', () => {
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBeNull();
    expect(s.lastAnchorId).toBeNull();
  });

  it('D2: open(kind, anchorId) sets openDrawer + lastAnchorId', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('pago', 'anchor-pago');
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBe('pago');
    expect(s.lastAnchorId).toBe('anchor-pago');
  });

  it('D3: opening a second drawer swaps cleanly (single-drawer guard)', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('pago', 'anchor-pago');
    open('arqueo', 'anchor-arqueo');
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBe('arqueo');
    expect(s.lastAnchorId).toBe('anchor-arqueo');
  });

  it('D4: close() resets both fields to null', () => {
    const { open, close } = useDashboardDrawerStore.getState();
    open('reimpresion', 'anchor-reimpresion');
    close();
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBeNull();
    expect(s.lastAnchorId).toBeNull();
  });

  it('D5: close() is idempotent (no-op after no-op)', () => {
    const { close } = useDashboardDrawerStore.getState();
    close();
    close();
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBeNull();
    expect(s.lastAnchorId).toBeNull();
  });

  it('D6: store is a singleton — two hook consumers see the same state', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('fe-retry', 'anchor-fe');
    const observerA = useDashboardDrawerStore.getState();
    const observerB = useDashboardDrawerStore.getState();
    expect(observerA.openDrawer).toBe('fe-retry');
    expect(observerB.openDrawer).toBe('fe-retry');
    expect(observerA.lastAnchorId).toBe(observerB.lastAnchorId);
  });

  it('D7: isDrawerOpen helper reflects active kind', () => {
    const state = useDashboardDrawerStore.getState();
    expect(isDrawerOpen(state, 'pago')).toBe(false);

    state.open('pago', 'anchor-pago');
    const reopened = useDashboardDrawerStore.getState();
    expect(isDrawerOpen(reopened, 'pago')).toBe(true);
    expect(isDrawerOpen(reopened, 'arqueo')).toBe(false);

    // Type-level smoke: the helper accepts every non-null DrawerKind.
    const kinds: NonNullDrawerKind[] = [
      'pago',
      'fe-retry',
      'reimpresion',
      'arqueo',
      'cierre-diario',
    ];
    for (const k of kinds) {
      expect(typeof isDrawerOpen(reopened, k)).toBe('boolean');
    }
  });
});