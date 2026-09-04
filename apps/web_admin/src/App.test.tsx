import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

describe('App', () => {
  it('redirects the root path to /dashboard and renders the dashboard heading', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    // The dashboard heading uses the i18n key app.dashboard which
    // resolves to "Panel" (es-CO default).
    expect(screen.getByText(/Parkos Admin|Panel/i)).toBeInTheDocument();
  });

  it('renders the login page on /login', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('page-login')).toBeInTheDocument();
  });

  it('renders the dashboard page on /dashboard', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
  });
});
