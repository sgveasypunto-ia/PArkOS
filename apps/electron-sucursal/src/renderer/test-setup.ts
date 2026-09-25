import '@testing-library/jest-dom/vitest';

/**
 * F5.2 (HU-F5.2) — Buffer polyfill for vitest + jsdom.
 *
 * jsdom does not provide `Buffer` as a global (it emulates a browser
 * environment). `escposBuilder.build(...)` returns a Node `Buffer`
 * (per DEC-SUC-08 / F5.1 `bridge.imprimir` contract: `payload.buffer`
 * base64 → `escpos-usb` `Device.print(Buffer)`), and the byte-level
 * fixtures in `escposBuilder.test.ts` need `Buffer.from([...])`.
 *
 * Resolution: import the `buffer` npm package (devDependency added in
 * F5.2 T1.2 — `buffer@^6.0.3`) and assign to `globalThis.Buffer` so
 * every test file in this app sees the global.
 *
 * Additive — keeps F4.x tests passing (they did not reference Buffer;
 * adding the global is a no-op for them).
 */
import { Buffer as NodeBuffer } from 'buffer';

(globalThis as { Buffer: typeof NodeBuffer }).Buffer = NodeBuffer;

/**
 * HU-INGRESO-SIN-PLACA — Radix UI (`@radix-ui/react-select`,
 * `@radix-ui/react-popover`) shim for jsdom.
 *
 * jsdom does NOT implement `Element.hasPointerCapture` /
 * `Element.releasePointerCapture` / `Element.scrollIntoView`. Radix
 * Select's pointer-event handlers call these on click targets; without
 * the shim the test throws `TypeError: target.hasPointerCapture is not
 * a function`. The fix mirrors the Radix UI testing-recipe:
 *   - add the missing prototype methods as no-ops.
 *   - stub `scrollIntoView` on Element + HTMLElement prototypes.
 *
 * Additive — no existing test references these methods, so the shim
 * is a no-op for them.
 */
if (typeof Element !== 'undefined') {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = function hasPointerCapture(): boolean {
      return false;
    };
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = function releasePointerCapture(): void {
      // no-op
    };
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function scrollIntoView(): void {
      // no-op
    };
  }
}
if (typeof HTMLElement !== 'undefined' && !HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = function scrollIntoView(): void {
    // no-op
  };
}

/**
 * `<TurnoActivoToggle />` fix (superposición navbar/placa-card) —
 * `ResizeObserver` polyfill for jsdom.
 *
 * jsdom does NOT implement `ResizeObserver`. `@floating-ui/dom` (used
 * internally by `@radix-ui/react-popper`, which `<Popover>`/`<DropdownMenu>`
 * both build on) falls back to an endless `requestAnimationFrame` polling
 * loop for its `autoUpdate` position tracking whenever `ResizeObserver` is
 * undefined — that loop never stops on its own inside a test, so any test
 * that opens a Radix Popover/DropdownMenu content hangs for ~25-30s real
 * time before Vitest's watchdog can even fire (the endless rAF scheduling
 * starves the event loop). The fix is the same one used by Radix's own
 * testing recipe: stub `ResizeObserver` as a no-op so floating-ui takes its
 * normal (non-polling) code path.
 *
 * Additive — no existing test references `ResizeObserver`, so the shim is a
 * no-op for them.
 */
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe(): void {
      // no-op
    }
    unobserve(): void {
      // no-op
    }
    disconnect(): void {
      // no-op
    }
  }
  (globalThis as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver =
    ResizeObserverStub;
}