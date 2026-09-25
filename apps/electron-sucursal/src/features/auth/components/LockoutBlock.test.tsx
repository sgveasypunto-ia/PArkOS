/**
 * Unit tests for `<LockoutBlock />` (F11.4 follow-up).
 *
 * Relocated from `LoginForm.test.tsx` (U7b, U9): the lockout alert +
 * countdown display used to render inside `<LoginForm>`, but per the
 * F11.4 follow-up they now render in `<LockoutBlock>`, mounted by the
 * `<Login>` container OUTSIDE the card (see `LockoutBlock.tsx` docblock
 * and `Login.tsx`). `<LoginForm>` no longer has this contract at all,
 * so the old tests were asserting on a component that doesn't render
 * this UI anymore — this file gives the behavior its correct home.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// `<LockoutBlock>` calls `useTranslation('auth')` directly (no
// I18nextProvider wrapper in these tests) — import the real i18next
// bootstrap so `t()` resolves real copy instead of raw keys.
import '@/i18n';

import { LockoutBlock } from './LockoutBlock';

describe('<LockoutBlock />', () => {
  beforeEach(() => {
    // `lockoutStorage.ts` persists the end-time in localStorage and
    // keeps whichever stored value is LONGER across mounts — clear it
    // so each test computes a fresh endTime from its own
    // `retryAfterSeconds` instead of inheriting a previous test's.
    window.localStorage.clear();
  });

  it('U7b: lockout message renders with role="status" (not "alert" — see docblock)', () => {
    render(<LockoutBlock retryAfterSeconds={300} onExpired={vi.fn()} />);
    const alert = screen.getByTestId('login-error-lockout');
    // Deliberate: a second role="alert" would compete with the
    // invalid-credentials alert for screen-reader focus.
    expect(alert).toHaveAttribute('role', 'status');
    expect(alert).toHaveTextContent('Cuenta bloqueada temporalmente');
  });

  it('U9: countdown display visible durante lockout activo con formato mm:ss', () => {
    render(<LockoutBlock retryAfterSeconds={60} onExpired={vi.fn()} />);
    const countdown = screen.getByTestId('login-countdown');
    expect(countdown).toBeInTheDocument();
    expect(countdown).toHaveAttribute('role', 'status');
    expect(countdown).toHaveAttribute('aria-live', 'polite');
    expect(countdown.textContent ?? '').toMatch(/\d{2}:\d{2}/);
  });
});
