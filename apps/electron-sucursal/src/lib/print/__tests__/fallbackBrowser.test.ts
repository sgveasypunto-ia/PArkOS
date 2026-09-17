/**
 * Unit tests for `fallbackBrowser.print()` (HU-F5.2).
 *
 * Verifies:
 *   1. The `<style>` element is injected into `document.head` with the
 *      DEC-SUC-08 verbatim `@page { size: 80mm auto; margin: 2mm }` rule.
 *   2. `window.print()` is called exactly once.
 *   3. The injected `<style>` is removed after the print call.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { print, PAGE_RULE } from '../fallbackBrowser';
import { validEntradaPayload } from './escposBuilder.test';

describe('fallbackBrowser.print("entrada", payload)', () => {
  let printSpy: ReturnType<typeof vi.spyOn>;
  let appendSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Clean DOM between tests.
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    printSpy = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    appendSpy = vi.spyOn(document.head, 'appendChild');
  });

  afterEach(() => {
    printSpy.mockRestore();
    appendSpy.mockRestore();
  });

  it('injects a <style> element with the DEC-SUC-08 @page rule (asserted via spy)', () => {
    print('entrada', validEntradaPayload());

    // The injected style node is captured by the appendChild spy as its
    // first argument. Verify the node is a <style> with the verbatim
    // DEC-SUC-08 @page rule.
    expect(appendSpy).toHaveBeenCalled();
    const injectedNode = appendSpy.mock.calls
      .map((call) => call[0])
      .find((node) => (node as Element).tagName?.toLowerCase?.() === 'style') as
      | (HTMLStyleElement & { id?: string })
      | undefined;
    expect(injectedNode).toBeDefined();
    expect(injectedNode?.textContent).toBe(PAGE_RULE);
    expect(PAGE_RULE).toBe('@page { size: 80mm auto; margin: 2mm }');
  });

  it('calls window.print() exactly once', () => {
    print('entrada', validEntradaPayload());
    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it('calls document.head.appendChild at least once', () => {
    print('entrada', validEntradaPayload());
    expect(appendSpy).toHaveBeenCalled();
  });

  it('removes the injected <style> after window.print() resolves', () => {
    print('entrada', validEntradaPayload());
    expect(document.getElementById('parkos-escpos-fallback-style')).toBeNull();
  });
});

describe('fallbackBrowser.print — invalid tipo', () => {
  it('throws EscposInvalidTipoError', () => {
    expect(() => print('nope' as never, {})).toThrow();
  });
});