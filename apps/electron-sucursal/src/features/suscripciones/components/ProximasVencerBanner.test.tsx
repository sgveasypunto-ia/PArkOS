/**
 * `<ProximasVencerBanner />` (PT-3): renders nothing without data; otherwise a
 * `role="status"` notice with the count and a CTA that opens the drawer.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // Minimal i18next stand-in: plural defaults + `{{var}}` interpolation.
    t: (_key: string, opts: Record<string, unknown> = {}) => {
      const raw =
        (opts.count === 1 ? opts.defaultValue_one : opts.defaultValue_other) ??
        opts.defaultValue ??
        _key;
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, k: string) => String(opts[k] ?? ''));
    },
  }),
}));

const mockData = vi.fn((): unknown[] | undefined => undefined);
vi.mock('../hooks/useSuscripcionesProximasVencer', () => ({
  useSuscripcionesProximasVencer: () => ({
    data: mockData(),
    error: undefined,
    isLoading: false,
    refresh: async () => undefined,
  }),
}));

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { ProximasVencerBanner } from './ProximasVencerBanner';

const item = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  uuid: 'u1',
  cliente_nombre: 'Cliente Alpha',
  plan_nombre: 'Mensual',
  placas: ['ABC123'],
  fecha_vencimiento: '2026-10-08',
  dias_restantes: 3,
  dias_alerta_pre_vencimiento: 7,
  puede_renovar: true,
  vencida: false,
  ...over,
});

beforeEach(() => {
  cleanup();
  useDashboardDrawerStore.getState().close();
  mockData.mockReturnValue(undefined);
});

describe('<ProximasVencerBanner />', () => {
  it('renders nothing while loading or when the feed is empty', () => {
    const { container, rerender } = render(<ProximasVencerBanner uuid_sucursal="s" />);
    expect(container.firstChild).toBeNull();
    mockData.mockReturnValue([]);
    rerender(<ProximasVencerBanner uuid_sucursal="s" />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the count, flags expired ones and names the closest', () => {
    mockData.mockReturnValue([item({ vencida: true, dias_restantes: -2 }), item({ uuid: 'u2' })]);
    render(<ProximasVencerBanner uuid_sucursal="s" />);
    const banner = screen.getByTestId('proximas-vencer-banner');
    expect(banner).toHaveAttribute('role', 'status');
    // UX3: "por vencer" and "vencidas" are counted apart (expired ones are NOT
    // folded into "próximas a vencer"), and the window is named.
    expect(banner).toHaveTextContent('1 suscripción por vencer y 1 vencida');
    expect(banner).toHaveTextContent('en su ventana de alerta');
    expect(banner).toHaveTextContent('Cliente Alpha');
  });

  it('UX3: only expired rows -> says vencidas, never "por vencer"', () => {
    mockData.mockReturnValue([item({ vencida: true, dias_restantes: -2 })]);
    render(<ProximasVencerBanner uuid_sucursal="s" />);
    const texto = screen.getByTestId('proximas-vencer-banner-texto');
    expect(texto).toHaveTextContent('1 suscripción vencida');
    expect(texto).not.toHaveTextContent('por vencer');
  });

  it('UX2: the CTA sets its own foreground (outline bg-background is dark in dark theme; inherited warning-foreground is unreadable)', () => {
    mockData.mockReturnValue([item()]);
    render(<ProximasVencerBanner uuid_sucursal="s" />);
    const cta = screen.getByTestId('proximas-vencer-banner-ver');
    expect(cta.className).toContain('text-foreground');
  });

  it('the CTA opens the subscriptions drawer', async () => {
    mockData.mockReturnValue([item()]);
    render(<ProximasVencerBanner uuid_sucursal="s" />);
    await userEvent.setup().click(screen.getByTestId('proximas-vencer-banner-ver'));
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('suscripciones');
  });
});
