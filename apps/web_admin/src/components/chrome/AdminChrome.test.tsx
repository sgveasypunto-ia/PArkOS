/**
 * `AdminChrome` — layout wrapper for branch-scoped routes.
 *
 * The header (brand, nav, branch selector, logout) now lives in
 * `<TopNav showBranchNav />`. This component only provides the
 * `<main>` wrapper for the `<Outlet />`.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AdminChrome } from './AdminChrome';

describe('AdminChrome', () => {
  it('renders the Outlet content', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AdminChrome />}>
            <Route path="/" element={<div data-testid="outlet-home" />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('outlet-home')).toBeInTheDocument();
  });
});
