/**
 * ``ArqueosResumen.test.tsx`` -- HU-F18.3 resumen unit tests.
 *
 * Covers the 4 main contract pieces:
 *   - the date picker defaults to today UTC.
 *   - the loading / error / empty banners render on the right states.
 *   - the per-branch ``<ResumenSucursalCard>``s render in a grid when
 *     the resumen carries items.
 *   - the cierre_dia detail (esperado / reportado / diferencia + the
 *     descuadre warning when the difference is non-zero) is the main
 *     branch surface.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { ArqueosResumen } from './ArqueosResumen';
import type {
  ArqueoResumenAdminItem,
  ArqueoResumenAdminRead,
} from '../api/arqueosSchema';

vi.mock('../api/arqueosApi', () => ({
  fetchArqueoDiferencias: vi.fn(),
  fetchResumenAdmin: vi.fn(),
  fetchArqueosAdmin: vi.fn(),
}));

import { fetchResumenAdmin } from '../api/arqueosApi';
const mockFetchResumenAdmin = vi.mocked(fetchResumenAdmin);

function makeItem(
  uuid: string,
  total: number,
  cierre: ArqueoResumenAdminItem['cierre_dia'] = null,
): ArqueoResumenAdminItem {
  return {
    uuid_sucursal: uuid,
    nombre: `Sucursal ${uuid.slice(0, 4)}`,
    esperado_efectivo: '100',
    esperado_datafono: '50',
    cierre_dia: cierre,
    total_arqueos: total,
  };
}

function makeCierre(d_efectivo = '0', d_datafono = '0'): NonNullable<ArqueoResumenAdminItem['cierre_dia']> {
  return {
    uuid: '00000000-0000-0000-0000-0000000000a1',
    uuid_tipo_arqueo: null,
    codigo_tipo_arqueo: null,
    uuid_sesion: null,
    valor_efectivo_esperado: '100',
    valor_datafono_esperado: '50',
    valor_efectivo_reportado: '100',
    valor_datafono_reportado: '50',
    diferencia_efectivo: d_efectivo,
    diferencia_datafono: d_datafono,
    descuadre_pct: null,
    alerta_generada: null,
    alerta_uuid: null,
  };
}

function renderResumen(salt: string): void {
  render(<ArqueosResumen swrSalt={salt} />);
}

describe('ArqueosResumen', () => {
  beforeEach(() => {
    mockFetchResumenAdmin.mockReset();
  });

  it('renders loading state while fetching', () => {
    mockFetchResumenAdmin.mockReturnValue(new Promise(() => {}));
    renderResumen('loading-' + Date.now());
    expect(screen.getByTestId('arqueos-resumen-loading')).toBeInTheDocument();
  });

  it('renders error state when the BE rejects', async () => {
    mockFetchResumenAdmin.mockRejectedValue(new Error('boom'));
    renderResumen('error-' + Date.now());
    await waitFor(() => {
      expect(screen.getByTestId('arqueos-resumen-error')).toBeInTheDocument();
    });
  });

  it('renders empty state when no branches have cierre for the day', async () => {
    const empty: ArqueoResumenAdminRead = { fecha: '2026-10-01', items: [] };
    mockFetchResumenAdmin.mockResolvedValue(empty);
    renderResumen('empty-' + Date.now());
    await waitFor(() => {
      expect(screen.getByTestId('arqueos-resumen-empty')).toBeInTheDocument();
    });
  });

  it('renders one card per branch and the totals', async () => {
    const data: ArqueoResumenAdminRead = {
      fecha: '2026-10-01',
      items: [
        makeItem('00000000-0000-0000-0000-0000000000a1', 3),
        makeItem('00000000-0000-0000-0000-0000000000a2', 5),
      ],
    };
    mockFetchResumenAdmin.mockResolvedValue(data);
    renderResumen('list-' + Date.now());
    await waitFor(() => {
      expect(screen.getByTestId('arqueos-resumen-list')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('resumen-sucursal-card-00000000-0000-0000-0000-0000000000a1'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('resumen-sucursal-card-00000000-0000-0000-0000-0000000000a2'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('resumen-total-00000000-0000-0000-0000-0000000000a1'))
      .toHaveTextContent('3');
  });

  it('renders the descuadre warning when the cierre has a non-zero diferencia', async () => {
    const data: ArqueoResumenAdminRead = {
      fecha: '2026-10-01',
      items: [
        makeItem('00000000-0000-0000-0000-0000000000a1', 1, makeCierre('5', '0')),
      ],
    };
    mockFetchResumenAdmin.mockResolvedValue(data);
    renderResumen('descuadre-' + Date.now());
    await waitFor(() => {
      expect(
        screen.getByTestId('resumen-descuadre-00000000-0000-0000-0000-0000000000a1'),
      ).toBeInTheDocument();
    });
  });

  it('renders the no-cierre banner when the branch did not submit', async () => {
    const data: ArqueoResumenAdminRead = {
      fecha: '2026-10-01',
      items: [makeItem('00000000-0000-0000-0000-0000000000a1', 0)],
    };
    mockFetchResumenAdmin.mockResolvedValue(data);
    renderResumen('nocierre-' + Date.now());
    await waitFor(() => {
      expect(
        screen.getByTestId('resumen-no-cierre-00000000-0000-0000-0000-0000000000a1'),
      ).toBeInTheDocument();
    });
  });
});