/**
 * `AlertaCard.test.tsx` — Strict-TDD unit coverage for the single
 * alert card component (HU-F11.2, REQ-OPS-178 + DA-F11.2-4).
 *
 * Coverage:
 *   AC1: severity badge color matches the `severidad` value
 *       (alta / media / baja) via `aria-label` selector.
 *   AC2: drill-down button navigates per router map — for
 *       `descuadre_critico` + `uuid_arqueo: Y`, the rendered href
 *       is `/caja/arqueo/Y`.
 *   AC3: drill-down button for `capacidad_agotada_forzado` +
 *       `datos_nuevos.uuid_ingreso: Z` resolves to `/caja/ingreso/Z`.
 *   AC4: resolver button calls `useResolverAlerta().resolve(alert)`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const resolveMock = vi.fn(async () => null);
const useResolverAlertaMock = vi.fn();
vi.mock('../hooks/useResolverAlerta', () => ({
  useResolverAlerta: () => useResolverAlertaMock(),
}));

import { AlertaCard } from '../components/AlertaCard';
import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

const ARQUEO_UUID = '00000000-0000-0000-0000-0000000000aa';
const INGRESO_UUID = '00000000-0000-0000-0000-0000000000bb';

function makeAlert(overrides: Partial<MergedAlerta> = {}): MergedAlerta {
  return {
    uuid: '00000000-0000-0000-0000-000000000001',
    fecha_retencion_hasta: '2031-09-21',
    created_at: '2026-09-21T10:00:00.000Z',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '00000000-0000-0000-0000-000000000001',
    uuid_usuario: null,
    uuid_arqueo: null,
    tipo_alerta: 'descuadre_critico',
    valor_diferencia_efectivo: null,
    valor_diferencia_datafono: null,
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-21T10:00:00.000Z',
    vigente_desde: '2026-09-21T10:00:00.000Z',
    vigente_hasta: null,
    estado: 'activa',
    severidad: 'alta',
    descripcion: 'desc',
    mensaje: 'mensaje',
    ...overrides,
  };
}

beforeEach(() => {
  resolveMock.mockReset();
  useResolverAlertaMock.mockReset();
  useResolverAlertaMock.mockReturnValue({ resolve: resolveMock, isResolving: false, error: undefined });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderCard(alert: MergedAlerta): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ul>
        <AlertaCard alert={alert} />
      </ul>
    </MemoryRouter>,
  );
}

describe('<AlertaCard /> — REQ-OPS-178 + DA-F11.2-4 (HU-F11.2)', () => {
  it('AC1: severity badge label matches the severidad value', () => {
    renderCard(makeAlert({ severidad: 'alta' }));
    expect(screen.getByLabelText('severidad-alta')).toBeInTheDocument();

    cleanup();

    renderCard(makeAlert({ severidad: 'media' }));
    expect(screen.getByLabelText('severidad-media')).toBeInTheDocument();

    cleanup();

    renderCard(makeAlert({ severidad: 'baja' }));
    expect(screen.getByLabelText('severidad-baja')).toBeInTheDocument();
  });

  it('AC2: drill-down button for descuadre_critico + uuid_arqueo: Y resolves to /caja/arqueo/Y', () => {
    renderCard(makeAlert({ tipo_alerta: 'descuadre_critico', uuid_arqueo: ARQUEO_UUID }));
    const drill = screen.getByRole('link', { name: /drilldown-descuadre_critico/ });
    expect(drill.getAttribute('href')).toBe(`/caja/arqueo/${ARQUEO_UUID}`);
  });

  it('AC3: drill-down button for capacidad_agotada_forzado uses datos_nuevos.uuid_ingreso fallback (DA-F11.2-14)', () => {
    renderCard(
      makeAlert({
        tipo_alerta: 'capacidad_agotada_forzado',
        datos_nuevos: { uuid_ingreso: INGRESO_UUID },
      }),
    );
    const drill = screen.getByRole('link', { name: /drilldown-capacidad_agotada_forzado/ });
    expect(drill.getAttribute('href')).toBe(`/caja/ingreso/${INGRESO_UUID}`);
  });

  it('AC4: resolver button calls useResolverAlerta().resolve(alert) on click (DEC-SUC-25 append-only)', () => {
    const alert = makeAlert({ tipo_alerta: 'descuadre_critico', uuid_arqueo: ARQUEO_UUID });
    renderCard(alert);
    const button = screen.getByRole('button', { name: /marcar-revisada-descuadre_critico/ });
    fireEvent.click(button);
    expect(resolveMock).toHaveBeenCalledTimes(1);
    expect(resolveMock).toHaveBeenCalledWith(alert);
  });
});
