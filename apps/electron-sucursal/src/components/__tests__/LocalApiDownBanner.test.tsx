/**
 * `LocalApiDownBanner.test.tsx` — Strict-TDD RED scaffold for HU-F11.1
 * (REQ-OPS-172 distinct hard-fault banner on 3 consecutive bridge failures).
 *
 * Coverage (verbatim tasks.md §C3.2 + design AD-3):
 *   S1: renders when `consecutiveFailures >= 3` with `role="alert"` and
 *       `aria-label="Estado de API local"`.
 *   S2: hidden when `consecutiveFailures < 3` (1 and 2).
 *   S3: copy is DISTINCT from `<SyncBanner />` (DA-F11.1-6 separation
 *       contract) — must NOT share i18n keys.
 *
 * Mocking strategy:
 *   - `vi.mock('react-i18next')` → returns the key string so tests
 *     assert on literal `localApiDown.*` keys (NO syncBanner.* keys).
 *   - `vi.mock('../../state/apiStatusStore')` → swap the store with a
 *     controlled stub. `selectApiStatusDown` is the gate.
 *
 * RED until C4 lands `apps/electron-sucursal/src/components/LocalApiDownBanner.tsx`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Track the live consecutiveFailures value so each scenario flips the
// gate explicitly.
const apiStatusState = { consecutiveFailures: 0 };

vi.mock('../../state/apiStatusStore', () => ({
  LOCAL_API_DOWN_THRESHOLD: 3,
  selectApiStatusDown: (s: { consecutiveFailures: number }) =>
    s.consecutiveFailures >= 3,
  useApiStatusStore: Object.assign(
    (selector: (s: { consecutiveFailures: number }) => unknown) =>
      selector(apiStatusState),
    { getState: () => apiStatusState },
  ),
}));

// Import after mocks so the mocked modules are wired.
import { LocalApiDownBanner } from '../LocalApiDownBanner';

beforeEach(() => {
  apiStatusState.consecutiveFailures = 0;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('<LocalApiDownBanner /> — REQ-OPS-172 (HU-F11.1)', () => {
  it('S1: renders at threshold = 3 with role="alert" + aria-label="Estado de API local"', () => {
    apiStatusState.consecutiveFailures = 3;
    render(<LocalApiDownBanner />);
    const banner = screen.getByTestId('local-api-down-banner');
    expect(banner).toBeTruthy();
    expect(banner.getAttribute('role')).toBe('alert');
    expect(banner.getAttribute('aria-label')).toBe('Estado de API local');
  });

  it('S1b: renders at threshold > 3 (4, 5)', () => {
    apiStatusState.consecutiveFailures = 5;
    render(<LocalApiDownBanner />);
    expect(screen.getByTestId('local-api-down-banner')).toBeTruthy();
  });

  it('S2a: hidden when consecutiveFailures === 1', () => {
    apiStatusState.consecutiveFailures = 1;
    render(<LocalApiDownBanner />);
    expect(screen.queryByTestId('local-api-down-banner')).toBeNull();
  });

  it('S2b: hidden when consecutiveFailures === 2', () => {
    apiStatusState.consecutiveFailures = 2;
    render(<LocalApiDownBanner />);
    expect(screen.queryByTestId('local-api-down-banner')).toBeNull();
  });

  it('S2c: hidden when consecutiveFailures === 0', () => {
    apiStatusState.consecutiveFailures = 0;
    render(<LocalApiDownBanner />);
    expect(screen.queryByTestId('local-api-down-banner')).toBeNull();
  });

  it('S3: copy is DISTINCT from <SyncBanner /> (DA-F11.1-6 separation)', () => {
    apiStatusState.consecutiveFailures = 3;
    render(<LocalApiDownBanner />);
    const banner = screen.getByTestId('local-api-down-banner');
    // The banner MUST use `localApiDown.*` keys, NOT `syncBanner.*`.
    expect(banner.textContent).toContain('localApiDown.copy');
    expect(banner.textContent).not.toContain('syncBanner.online');
    expect(banner.textContent).not.toContain('syncBanner.offline');
    expect(banner.textContent).not.toContain('syncBanner.lagging');
  });
});
