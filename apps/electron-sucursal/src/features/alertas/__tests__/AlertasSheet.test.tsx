/**
 * `AlertasTrigger` + `AlertasSheet` — alertas como módulo colapsado:
 * trigger compacto con conteo, bottom sheet con el panel existente.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number; defaultValue?: string }) =>
      opts?.count !== undefined ? `${key}:${opts.count}` : key,
  }),
}));

const useAlertasMock = vi.fn();
vi.mock('../hooks/useAlertas', () => ({
  useAlertas: (...args: unknown[]) => useAlertasMock(...args),
}));
vi.mock('../hooks/useResolverAlerta', () => ({
  useResolverAlerta: () => ({ resolve: vi.fn(), isResolving: false, error: undefined }),
}));
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({ sucursal: { uuid: '00000000-0000-0000-0000-000000000001' } }),
}));

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { DrawerHost } from '../../caja/pages/DrawerHost';
import { AlertasTrigger } from '../components/AlertasTrigger';

const UUID = '00000000-0000-0000-0000-000000000001';

function alerta(i: number, severidad: 'alta' | 'media' | 'baja'): Record<string, unknown> {
  return {
    uuid: `00000000-0000-0000-0000-00000000010${i}`,
    tipo_alerta: 'descuadre_critico',
    estado: 'abierta',
    severidad,
    descripcion: `desc-${i}`,
    mensaje: `mensaje-${i}`,
    uuid_arqueo: null,
    uuid_alerta_padre: null,
    uuid_usuario: null,
    uuid_sucursal: UUID,
    timestamp_evento: '2026-09-21T10:00:00.000Z',
  };
}

function mockAlertas(list: Array<Record<string, unknown>>): void {
  useAlertasMock.mockReturnValue({
    data: list,
    mergedAlertas: list,
    openAlertsCount: list.length,
    error: undefined,
    refresh: async () => undefined,
  });
}

function renderAll(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <AlertasTrigger uuid_sucursal={UUID} />
      <DrawerHost />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useAlertasMock.mockReset();
  useDashboardDrawerStore.getState().close();
  vi.spyOn(console, 'debug').mockImplementation(() => undefined);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('<AlertasTrigger /> + <AlertasSheet />', () => {
  it('shows the open-alerts count with a severity accent and does not mount the panel', () => {
    mockAlertas([alerta(1, 'baja'), alerta(2, 'alta'), alerta(3, 'media')]);
    renderAll();

    const trigger = screen.getByTestId('alertas-trigger');
    expect(screen.getByTestId('alertas-trigger-count')).toHaveTextContent('3');
    expect(trigger).toHaveAttribute('data-severidad', 'alta');
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAttribute('aria-label', 'alertas:trigger.label:3');
    expect(screen.queryByTestId('alertas-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('alertas-sheet')).not.toBeInTheDocument();
  });

  it('click opens a bottom dialog with filters + the alert list; trigger is aria-expanded', () => {
    mockAlertas([alerta(1, 'alta'), alerta(2, 'media')]);
    renderAll();

    fireEvent.click(screen.getByTestId('alertas-trigger'));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBe(screen.getByTestId('alertas-sheet'));
    expect(dialog).toHaveAttribute('aria-labelledby', 'alertas-panel-title');
    expect(dialog.className).toContain('bottom-0');
    expect(within(dialog).getByTestId('open-alerts-count')).toHaveTextContent('2');
    expect(within(dialog).getAllByTestId('alerta-card')).toHaveLength(2);
    expect(screen.getByTestId('alertas-trigger')).toHaveAttribute('aria-expanded', 'true');
  });

  it('Escape and the close button hide the sheet', () => {
    mockAlertas([alerta(1, 'alta')]);
    renderAll();

    fireEvent.click(screen.getByTestId('alertas-trigger'));
    expect(screen.getByTestId('alertas-sheet')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByTestId('alertas-sheet')).not.toBeInTheDocument();
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();

    fireEvent.click(screen.getByTestId('alertas-trigger'));
    fireEvent.click(screen.getByTestId('sheet-close'));
    expect(screen.queryByTestId('alertas-sheet')).not.toBeInTheDocument();
  });

  it('zero alerts: quiet trigger without badge; sheet shows the empty state', () => {
    mockAlertas([]);
    renderAll();

    const trigger = screen.getByTestId('alertas-trigger');
    expect(trigger).toHaveAttribute('data-severidad', 'ninguna');
    expect(screen.queryByTestId('alertas-trigger-count')).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(screen.getByTestId('alertas-empty')).toBeInTheDocument();
    expect(screen.getByTestId('open-alerts-count')).toHaveTextContent('0');
  });

  it('renders nothing without branch context', () => {
    mockAlertas([]);
    const { container } = render(<AlertasTrigger uuid_sucursal={null} />);
    expect(container.firstChild).toBeNull();
  });
});
