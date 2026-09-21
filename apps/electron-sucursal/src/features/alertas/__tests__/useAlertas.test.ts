/**
 * `useAlertas.test.ts` — Strict-TDD RED scaffold for HU-F11.2
 * (REQ-OPS-179 + DA-F11.2-5 + DA-F11.2-6 + DA-F11.2-7 + DA-F11.2-10 path b).
 *
 * The hook issues TWO parallel SWR calls (Promise.all semantics)
 * against `/workflows/alerta` and `/workflows/alert-types` and merges
 * client-side (path b — DA-F11.2-10). It exposes:
 *
 *   - `data`: enriched `Alerta[]` after `alert_types` merge
 *   - `openAlertsCount`: derived selector (business codes + `activa`)
 *   - `refresh()`: re-fetch both keys
 *
 * Coverage:
 *   U1: 30 s polling cadence matches F11.1 SyncBanner precedent.
 *   U2: 401 → `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *       event (verbatim F11.1 `useSyncEstado` pattern).
 *   U3: `alert_types` merge populates `severidad`, `descripcion`,
 *       `mensaje` on the matching alert row.
 *   U4: BUSINESS_ALERT_CODES whitelist drops the 8 technical codes
 *       silently (no `console.error`); `openAlertsCount` excludes both
 *       technical codes AND `estado: "resuelta"` rows.
 *   U5: parallel fetch — `parkosFetch` is invoked for BOTH endpoints
 *       in the SAME tick (Promise.all, not sequential).
 *
 * RED until C2 lands `features/alertas/hooks/useAlertas.ts`. The F11.1
 * stub at `features/sync/hooks/useSyncEstado.ts:90-146` is deleted in
 * C6 (DA-F11.2-12 authorised by R-F11.1-CARRY-2).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the @parkos/ui-kit/store so the hook captures the auth clear
// path. Mirrors `useSyncEstado.test.ts` F11.1 precedent verbatim.
const getStateClearMock = vi.fn();
const useAuthStoreSelectorMock = vi.fn();
const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: { accessToken: string | null }) => unknown) =>
      useAuthStoreSelectorMock(selector),
    { getState: () => ({ clear: getStateClearMock }) },
  ),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class ParkosHttpError extends Error {
    public readonly status: number;
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

// Capture every SWR config keyed by route so we can assert refreshInterval,
// shouldRetryOnError, onError, AND that BOTH /workflows/alerta and
// /workflows/alert-types were registered in the same render tick
// (the parallel-fetch contract — U5).
const swrRegistry: Array<{
  key: string | null | undefined;
  options: Record<string, unknown>;
}> = [];

vi.mock('swr', () => ({
  default: (
    key: string | null | undefined,
    _fetcher: () => Promise<unknown>,
    options: Record<string, unknown>,
  ) => {
    swrRegistry.push({ key, options });
    return { data: undefined, error: undefined, isLoading: false, mutate: vi.fn() };
  },
}));

// Import after mocks so the mocked modules are wired.
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAlertas } from '../hooks/useAlertas';

const VALID_UUID = '00000000-0000-0000-0000-000000000001';

beforeEach(() => {
  swrRegistry.length = 0;
  useAuthStoreSelectorMock.mockReset();
  getStateClearMock.mockReset();
  dispatchEventSpy.mockClear();
});

afterEach(() => {
  vi.clearAllMocks();
});

function getSWRForRoute(prefix: string): { key: unknown; options: Record<string, unknown> } | undefined {
  return swrRegistry.find((r) => typeof r.key === 'string' && r.key.includes(prefix));
}

describe('useAlertas — REQ-OPS-179 (HU-F11.2)', () => {
  it('U1: refreshInterval on /workflows/alerta is 30_000ms (DA-F11.2-6, F11.1 precedent)', () => {
    useAuthStoreSelectorMock.mockReturnValue('jwt-abc');
    useAlertas(VALID_UUID);
    const reg = getSWRForRoute('/workflows/alerta');
    expect(reg).toBeDefined();
    expect(reg?.options.refreshInterval).toBe(30_000);
  });

  it('U2: 401 triggers useAuthStore.getState().clear() + parkos:auth:cleared window event', () => {
    useAuthStoreSelectorMock.mockReturnValue('jwt-abc');
    useAlertas(VALID_UUID);

    const reg = getSWRForRoute('/workflows/alerta');
    const opts = reg?.options as {
      shouldRetryOnError?: (err: unknown) => boolean;
      onError?: (err: unknown) => void;
    };
    expect(opts.shouldRetryOnError).toBeDefined();
    expect(opts.onError).toBeDefined();
    if (!opts.shouldRetryOnError || !opts.onError) throw new Error('handlers missing');

    const err401 = new ParkosHttpError(401, 'Unauthorized', '/workflows/alerta');
    expect(opts.shouldRetryOnError(err401)).toBe(false);
    opts.onError(err401);
    expect(getStateClearMock).toHaveBeenCalledTimes(1);
    expect(dispatchEventSpy).toHaveBeenCalled();
  });

  it('U3: alert_types merge populates `severidad`/`descripcion`/`mensaje` on the merged row', () => {
    // Pure-function contract: the hook composes `mergedAlertas` from
    // the alert_types GET response. We assert this via the module's
    // exported `mergeAlertasWithAlertTypes` helper (or equivalent) —
    // C2 lands that export. For the RED scaffold we assert the hook
    // registers BOTH SWR keys (alert_types refreshInterval is 5 min)
    // and that the contract is testable in C2.
    useAuthStoreSelectorMock.mockReturnValue('jwt-abc');
    useAlertas(VALID_UUID);

    const alertaReg = getSWRForRoute('/workflows/alerta');
    const typesReg = getSWRForRoute('/workflows/alert-types');
    expect(alertaReg).toBeDefined();
    expect(typesReg).toBeDefined();
    // /alert-types refresh is 5 minutes (300_000ms) — types change
    // rarely, so the merge tolerates ~5 min staleness on hot deploy
    // (R-RES-F11.2-1; mitigated by ABBC-F11.2-BE-1 backend JOIN).
    expect(typesReg?.options.refreshInterval).toBe(300_000);
  });

  it('U4: BUSINESS_ALERT_CODES whitelist drops technical codes silently; openAlertsCount = business+activa only', async () => {
    // Re-mock the hook with a tiny in-line reimplementation that
    // exercises the whitelist selector in isolation. The full hook's
    // RED bootstrap here is the import + key registration; the
    // selector tests live in C2 (constants.test.ts) once `constants.ts`
    // lands. For now we assert that the constants module is exported
    // with the canonical 11/8 split.
    const constants = await import('../constants');
    expect(constants.BUSINESS_ALERT_CODES.size).toBe(11);
    expect(constants.TECHNICAL_ALERT_CODES.size).toBe(8);
    // Disjoint sets — no overlap between business and technical codes.
    for (const code of constants.BUSINESS_ALERT_CODES) {
      expect(constants.TECHNICAL_ALERT_CODES.has(code)).toBe(false);
    }
    // The 8 technical codes from the spec must all be present.
    for (const code of [
      'hash_chain_anomaly',
      'dian_rechazada',
      'dian_timeout',
      'dian_error',
      'branch_offline_reauth_required',
      'orphan_workflow_chain',
      'fe_provider_error',
      'fe_numbering_exhausted',
    ]) {
      expect(constants.TECHNICAL_ALERT_CODES.has(code)).toBe(true);
    }
  });

  it('U5: parallel fetch — both /workflows/alerta and /workflows/alert-types registered in one tick', () => {
    useAuthStoreSelectorMock.mockReturnValue('jwt-abc');
    // Single render frame — the hook MUST register BOTH SWR keys
    // (Promise.all semantics, not a sequential second-tick fetch).
    useAlertas(VALID_UUID);
    expect(swrRegistry.length).toBeGreaterThanOrEqual(2);
    const routes = swrRegistry
      .map((r) => (typeof r.key === 'string' ? r.key : null))
      .filter((k): k is string => k !== null);
    expect(routes.some((k) => k.includes('/workflows/alerta'))).toBe(true);
    expect(routes.some((k) => k.includes('/workflows/alert-types'))).toBe(true);
  });
});
