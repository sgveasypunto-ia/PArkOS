/**
 * `RequireAdmin.test.tsx` — Unit tests for the route guard (IT-1.10).
 *
 * Asserts the three states:
 *   1. `isLoading === true` → renders the loading placeholder.
 *   2. `!isAuthenticated && !isLoading` → redirects to `/login?next=...`.
 *   3. `isAuthenticated === true` → renders children.
 *
 * The `useAuth` mock is defined at the module level with `vi.hoisted`
 * so the factory can read the current auth state from a `globalThis`
 * variable, mutated per-test before rendering.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { setAuthState } = vi.hoisted(() => {
  return {
    setAuthState: (v: 'loading' | 'unauthenticated' | 'authenticated'): void => {
      (globalThis as { __AUTH_STATE?: string }).__AUTH_STATE = v;
    },
  };
});

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => {
    const state = (globalThis as { __AUTH_STATE?: string }).__AUTH_STATE ?? 'authenticated';
    const base = {
      rol: null,
      sucursalUuids: [],
      permisos: [],
      error: undefined,
      refresh: async () => undefined,
      logout: async () => undefined,
    };
    if (state === 'loading') {
      return { ...base, user: null, isAuthenticated: false, isLoading: true };
    }
    if (state === 'unauthenticated') {
      return { ...base, user: null, isAuthenticated: false, isLoading: false };
    }
    return {
      ...base,
      user: { uuid: '00000000-0000-0000-0000-0000000000ad', email: 'admin@parkos.local' },
      isAuthenticated: true,
      isLoading: false,
    };
  },
}));

import { RequireAdmin } from './RequireAdmin';

function withRoutes(initialPath: string): JSX.Element {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <RequireAdmin>
              <div data-testid="protected-content">protected</div>
            </RequireAdmin>
          }
        />
        <Route path="/login" element={<div data-testid="login-redirect-target">login</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('RequireAdmin', () => {
  it('renders the loading placeholder when isLoading', () => {
    setAuthState('loading');
    render(withRoutes('/dashboard'));
    expect(screen.getByTestId('require-admin-loading')).toBeInTheDocument();
  });

  it('redirects to /login when unauthenticated', () => {
    setAuthState('unauthenticated');
    // Use a path with no querystring so the route table maps
    // unambiguously to /login. The `next` querystring is verified by
    // the integration test in App.test.tsx (route table with the
    // real Login component).
    render(withRoutes('/dashboard'));
    expect(screen.getByTestId('login-redirect-target')).toBeInTheDocument();
  });

  it('renders children when authenticated', () => {
    setAuthState('authenticated');
    render(withRoutes('/dashboard'));
    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
  });
});
