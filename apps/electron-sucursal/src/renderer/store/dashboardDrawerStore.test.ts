/**
 * State-machine tests for `useDashboardDrawerStore` (REQ-OPS-138).
 *
 * Coverage:
 *   D1: initial state — `openDrawer: null`, `lastAnchorId: null`,
 *       `initialPlaca: null`.
 *   D2: `open(kind, anchorId)` sets state correctly.
 *   D3: opening a second drawer while one is already open swaps cleanly
 *       (single-drawer invariant).
 *   D4: `close()` resets all three fields to null.
 *   D5: `close()` after `close()` is a no-op (idempotent).
 *   D6: state is decoupled between hooks — both observers see the same
 *       store (singleton).
 *   D7: `isDrawerOpen` helper returns the right boolean for each kind.
 *   D8: `open(kind, anchorId, placa)` records `initialPlaca`; the
 *       default arg leaves it `null` (back-compat for callers that
 *       don't pass a placa).
 *   D9: `close()` clears `initialPlaca` after a placa-bearing open.
 *   D10: `open(kind, anchorId, placa, pagoContext, initialUuidIngreso)`
 *        records `initialUuidIngreso`; default arg leaves it `null`
 *        (HU-F7.1 búsqueda sin placa — consecutivo suggestion path).
 *   D11: `close()` clears `initialUuidIngreso` after an
 *        initialUuidIngreso-bearing open.
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
    expect(s.initialPlaca).toBeNull();
    expect(s.initialUuidIngreso).toBeNull();
  });

  it('D2: open(kind, anchorId) sets openDrawer + lastAnchorId', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('pago', 'anchor-pago');
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBe('pago');
    expect(s.lastAnchorId).toBe('anchor-pago');
    expect(s.initialPlaca).toBeNull();
  });

  it('D3: opening a second drawer swaps cleanly (single-drawer guard)', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('pago', 'anchor-pago');
    open('arqueo', 'anchor-arqueo');
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBe('arqueo');
    expect(s.lastAnchorId).toBe('anchor-arqueo');
    expect(s.initialPlaca).toBeNull();
  });

  it('D4: close() resets all three fields to null', () => {
    const { open, close } = useDashboardDrawerStore.getState();
    open('reimpresion', 'anchor-reimpresion', 'ABC123');
    close();
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBeNull();
    expect(s.lastAnchorId).toBeNull();
    expect(s.initialPlaca).toBeNull();
  });

  it('D5: close() is idempotent (no-op after no-op)', () => {
    const { close } = useDashboardDrawerStore.getState();
    close();
    close();
    const s = useDashboardDrawerStore.getState();
    expect(s.openDrawer).toBeNull();
    expect(s.lastAnchorId).toBeNull();
    expect(s.initialPlaca).toBeNull();
  });

  it('D6: store is a singleton — two hook consumers see the same state', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('fe-retry', 'anchor-fe');
    const observerA = useDashboardDrawerStore.getState();
    const observerB = useDashboardDrawerStore.getState();
    expect(observerA.openDrawer).toBe('fe-retry');
    expect(observerB.openDrawer).toBe('fe-retry');
    expect(observerA.lastAnchorId).toBe(observerB.lastAnchorId);
    expect(observerA.initialPlaca).toBe(observerB.initialPlaca);
  });

  it('D7: isDrawerOpen helper reflects active kind', () => {
    const state = useDashboardDrawerStore.getState();
    expect(isDrawerOpen(state, 'pago')).toBe(false);

    state.open('pago', 'anchor-pago');
    const reopened = useDashboardDrawerStore.getState();
    expect(isDrawerOpen(reopened, 'pago')).toBe(true);
    expect(isDrawerOpen(reopened, 'arqueo')).toBe(false);

    // Type-level smoke: the helper accepts every non-null DrawerKind,
    // including the F6/F7 kinds wired up in `fix/dashboard-f6-wire`.
    const kinds: NonNullDrawerKind[] = [
      'pago',
      'fe-retry',
      'reimpresion',
      'arqueo',
      'cierre-diario-multi',
      'ingreso',
      'salida',
      'suscripciones',
      'inventario',
    ];
    for (const k of kinds) {
      expect(typeof isDrawerOpen(reopened, k)).toBe('boolean');
    }
  });

  it('D8: open(kind, anchorId, placa) records initialPlaca; default arg is null', () => {
    const { open } = useDashboardDrawerStore.getState();

    // With placa: recorded.
    open('ingreso', 'anchor-placa', 'ABC123');
    const s1 = useDashboardDrawerStore.getState();
    expect(s1.openDrawer).toBe('ingreso');
    expect(s1.lastAnchorId).toBe('anchor-placa');
    expect(s1.initialPlaca).toBe('ABC123');

    // Re-open without placa → initialPlaca is cleared (single-open
    // swap semantics; no stale placa leaks from the previous open).
    open('salida', 'anchor-hotkey');
    const s2 = useDashboardDrawerStore.getState();
    expect(s2.openDrawer).toBe('salida');
    expect(s2.initialPlaca).toBeNull();
  });

  it('D9: close() clears initialPlaca after a placa-bearing open', () => {
    const { open, close } = useDashboardDrawerStore.getState();
    open('ingreso', 'anchor-placa', 'ABC12D');
    expect(useDashboardDrawerStore.getState().initialPlaca).toBe('ABC12D');
    close();
    expect(useDashboardDrawerStore.getState().initialPlaca).toBeNull();
  });

  it('D10: open(..., initialUuidIngreso) records it; default arg is null', () => {
    const { open } = useDashboardDrawerStore.getState();

    // With initialUuidIngreso: recorded.
    open('salida', 'anchor-consecutivo', null, null, 'uuid-ingreso-1');
    const s1 = useDashboardDrawerStore.getState();
    expect(s1.openDrawer).toBe('salida');
    expect(s1.initialPlaca).toBeNull();
    expect(s1.initialUuidIngreso).toBe('uuid-ingreso-1');

    // Re-open without it (back-compat callers) → cleared.
    open('salida', 'anchor-hotkey');
    const s2 = useDashboardDrawerStore.getState();
    expect(s2.openDrawer).toBe('salida');
    expect(s2.initialUuidIngreso).toBeNull();
  });

  it('D11: close() clears initialUuidIngreso after an initialUuidIngreso-bearing open', () => {
    const { open, close } = useDashboardDrawerStore.getState();
    open('salida', 'anchor-consecutivo', null, null, 'uuid-ingreso-2');
    expect(useDashboardDrawerStore.getState().initialUuidIngreso).toBe('uuid-ingreso-2');
    close();
    expect(useDashboardDrawerStore.getState().initialUuidIngreso).toBeNull();
  });
});
