/**
 * Esc key + focus-restore test for the dashboard drawer contract
 * (REQ-OPS-138 §Esc).
 *
 * Coverage:
 *   E1: Opening a drawer with anchorId remembers the anchor.
 *   E2: Esc keyboard event while the drawer is open triggers the
 *       close path (store + DOM focus restore).
 *   E3: After Esc, `document.activeElement` === the trigger element
 *       that opened the drawer (focus restoration per REQ-OPS-138 §Esc).
 *   E4: Esc on a closed drawer is a no-op (no focus shift).
 *
 * Implementation note: the production panel components (PagoSheet,
 * ReimprimirTiqueteSheet) use a `useEffect` keyed on `[open, lastAnchorId]`
 * to restore focus. The current `close()` clears `lastAnchorId` first,
 * so the consumer must capture `lastAnchorId` BEFORE calling `close()`
 * — same pattern used by Radix Sheet's `onOpenChange(false)`. The
 * wrapper below follows that exact pattern so the test asserts the
 * documented contract (REQ-OPS-138 §Esc) end-to-end.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useEffect, useRef } from 'react';
import { render, screen, act } from '@testing-library/react';

import { useDashboardDrawerStore } from '../dashboardDrawerStore';

/**
 * Minimal drawer consumer that mirrors the `<PagoSheet />` /
 * `<ReimprimirTiqueteSheet />` Esc → close + focus-restore pattern.
 *
 * Pattern (verbatim from PagoSheet.tsx:110-116 + onOpenChange):
 *   - Esc fires → consumer captures `lastAnchorId` from the store
 *     BEFORE calling `close()` (because `close()` clears it).
 *   - Consumer then focuses the anchor element.
 *
 * Production sheets wrap this in a Radix Sheet's onOpenChange, but the
 * underlying contract is identical: capture → close → focus.
 */
function DrawerWithEscAndFocusRestore({
  triggerId,
  triggerLabel,
}: {
  triggerId: string;
  triggerLabel: string;
}): JSX.Element {
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Document-level Esc listener — same pattern as Radix Dialog/Sheet.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== 'Escape') return;
      const state = useDashboardDrawerStore.getState();
      if (state.openDrawer === null) return; // E4 — closed drawer is a no-op.

      // CRITICAL: capture `lastAnchorId` BEFORE close() — close() clears it.
      const anchorId = state.lastAnchorId;
      state.close();
      if (anchorId) {
        document.getElementById(anchorId)?.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <button
      ref={triggerRef}
      id={triggerId}
      type="button"
      data-testid="trigger"
      onClick={() => {
        useDashboardDrawerStore.getState().open('pago', triggerId);
      }}
    >
      {triggerLabel}
    </button>
  );
}

beforeEach(() => {
  useDashboardDrawerStore.getState().close();
});

describe('dashboard drawer Esc + focus restore — REQ-OPS-138 §Esc', () => {
  it('E1: open(kind, anchorId) remembers the anchor via lastAnchorId', () => {
    const { open } = useDashboardDrawerStore.getState();
    open('pago', 'trigger-pago');
    const s = useDashboardDrawerStore.getState();
    expect(s.lastAnchorId).toBe('trigger-pago');
    expect(s.openDrawer).toBe('pago');
  });

  it('E2 + E3: Esc closes the drawer AND restores focus to the trigger', () => {
    render(<DrawerWithEscAndFocusRestore triggerId="trigger-1" triggerLabel="Open drawer" />);
    const trigger = screen.getByTestId('trigger');

    // Open the drawer by clicking the trigger (mirrors real UI flow).
    act(() => {
      trigger.click();
    });
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('pago');
    expect(useDashboardDrawerStore.getState().lastAnchorId).toBe('trigger-1');

    // Move focus elsewhere (simulate Radix Sheet portal grabbing focus).
    const sink = document.createElement('button');
    sink.id = 'focus-sink';
    document.body.appendChild(sink);
    sink.focus();
    expect(document.activeElement).toBe(sink);

    // Fire Esc.
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });

    // Drawer closed.
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();

    // Focus restored to the trigger that opened the drawer.
    expect(document.activeElement).toBe(trigger);

    document.body.removeChild(sink);
  });

  it('E4: Esc on a closed drawer is a no-op (no focus shift)', () => {
    render(<DrawerWithEscAndFocusRestore triggerId="trigger-2" triggerLabel="Open drawer" />);
    const trigger = screen.getByTestId('trigger');
    trigger.focus();

    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });

    // Store still closed + focus unchanged.
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

// Silence unused-import linting on `vi` from auto-import rewrites.
vi.fn();