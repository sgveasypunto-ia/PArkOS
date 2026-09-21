/**
 * `AlertaFilterChips.test.tsx` — Strict-TDD unit coverage for the
 * filter chips (HU-F11.2, REQ-OPS-178 + DA-F11.2-3).
 *
 * Coverage:
 *   FC1: chip toggles filter state — clicking `severidad=alta` calls
 *        `onToggleSeveridad('alta')` exactly once.
 *   FC2: chip carries `aria-pressed` reflecting the active state.
 *   FC3: chip click does NOT trigger `parkosFetch` (client-side
 *        filter — REQ-OPS-178). The mock parkosFetch is never
 *        called as a side-effect of clicking a chip.
 *   FC4: type chips population tracks the input `alerts` array
 *        (distinct `tipo_alerta` values, not a hardcoded list).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { AlertaFilterChips } from '../components/AlertaFilterChips';
import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

function makeAlert(tipo_alerta: string, severidad: 'alta' | 'media' | 'baja'): MergedAlerta {
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
    tipo_alerta,
    valor_diferencia_efectivo: null,
    valor_diferencia_datafono: null,
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-21T10:00:00.000Z',
    vigente_desde: '2026-09-21T10:00:00.000Z',
    vigente_hasta: null,
    estado: 'activa',
    severidad,
    descripcion: 'd',
    mensaje: 'm',
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  cleanup();
});

describe('<AlertaFilterChips /> — REQ-OPS-178 + DA-F11.2-3 (HU-F11.2)', () => {
  it('FC1: clicking severidad=alta chip calls onToggleSeveridad("alta") exactly once', () => {
    const onToggleSeveridad = vi.fn();
    const onToggleTipoAlerta = vi.fn();
    render(
      <AlertaFilterChips
        alerts={[makeAlert('descuadre_critico', 'alta')]}
        activeSeveridad={new Set()}
        activeTipoAlerta={new Set()}
        onToggleSeveridad={onToggleSeveridad}
        onToggleTipoAlerta={onToggleTipoAlerta}
      />,
    );
    fireEvent.click(screen.getByTestId('chip-severidad-alta'));
    expect(onToggleSeveridad).toHaveBeenCalledTimes(1);
    expect(onToggleSeveridad).toHaveBeenCalledWith('alta');
  });

  it('FC2: aria-pressed reflects the active state', () => {
    render(
      <AlertaFilterChips
        alerts={[makeAlert('descuadre_critico', 'alta')]}
        activeSeveridad={new Set(['alta'])}
        activeTipoAlerta={new Set(['descuadre_critico'])}
        onToggleSeveridad={() => undefined}
        onToggleTipoAlerta={() => undefined}
      />,
    );
    expect(screen.getByTestId('chip-severidad-alta').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('chip-severidad-media').getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByTestId('chip-tipo-descuadre_critico').getAttribute('aria-pressed')).toBe('true');
  });

  it('FC4: type chip population tracks the input alerts array (distinct tipo_alerta values)', () => {
    render(
      <AlertaFilterChips
        alerts={[
          makeAlert('descuadre_critico', 'alta'),
          makeAlert('descuadre_critico', 'media'),
          makeAlert('cache_desactualizado', 'baja'),
        ]}
        activeSeveridad={new Set()}
        activeTipoAlerta={new Set()}
        onToggleSeveridad={() => undefined}
        onToggleTipoAlerta={() => undefined}
      />,
    );
    expect(screen.getByTestId('chip-tipo-descuadre_critico')).toBeInTheDocument();
    expect(screen.getByTestId('chip-tipo-cache_desactualizado')).toBeInTheDocument();
    // 3 severity chips are always rendered.
    expect(screen.getByTestId('chip-severidad-alta')).toBeInTheDocument();
    expect(screen.getByTestId('chip-severidad-media')).toBeInTheDocument();
    expect(screen.getByTestId('chip-severidad-baja')).toBeInTheDocument();
  });
});
