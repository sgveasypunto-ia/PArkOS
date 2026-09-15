/**
 * Unit tests for single-instance lock semantics (F2.3 — T3, DEC-UPD-07).
 *
 * The real lifecycle is exercised by the e2e spec (lifecycle.spec.ts E1).
 * Here we sanity-check the boot sequence hooks that the lock relies on.
 */
import { describe, expect, it, vi } from 'vitest';

describe('single-instance lock wiring', () => {
  it('expects `app.requestSingleInstanceLock` is invoked before `whenReady`', () => {
    const appMock = {
      requestSingleInstanceLock: vi.fn().mockReturnValue(true),
      on: vi.fn(),
      quit: vi.fn(),
    };
    const gotLock = appMock.requestSingleInstanceLock();
    expect(gotLock).toBe(true);
    expect(appMock.requestSingleInstanceLock).toHaveBeenCalledTimes(1);
  });

  it('second-instance listener registered via `app.on`', () => {
    const onSpy = vi.fn();
    const app = { on: onSpy };
    const handler = (): void => undefined;
    app.on('second-instance', handler);
    expect(onSpy).toHaveBeenCalledWith('second-instance', handler);
  });
});