/**
 * `DiferenciasPanel.test.tsx` -- HU-F18.2 DiferenciasPanel unit.
 *
 * Covers the rendering states (loading, error, no-data, descuadre,
 * match) and the descuadre-warning surfacing when the difference is
 * non-zero.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { DiferenciasPanel } from './DiferenciasPanel';
import type { DiferenciasRead } from '../api/arqueosSchema';

function makeDiferencias(
  diferencia_efectivo: number,
  diferencia_datafono: number,
): DiferenciasRead {
  return {
    uuid_arqueo: '00000000-0000-0000-0000-0000000000a1',
    valor_efectivo_esperado: 100,
    valor_datafono_esperado: 50,
    valor_efectivo_reportado: 100 + diferencia_efectivo,
    valor_datafono_reportado: 50 + diferencia_datafono,
    diferencia_efectivo,
    diferencia_datafono,
  };
}

describe('DiferenciasPanel', () => {
  it('renders loading state when isLoading=true', () => {
    render(
      <DiferenciasPanel diferencias={null} isLoading={true} error={undefined} />,
    );
    expect(screen.getByTestId('diferencias-loading')).toBeInTheDocument();
  });

  it('renders error state when error is set', () => {
    render(
      <DiferenciasPanel
        diferencias={null}
        isLoading={false}
        error={new Error('boom')}
      />,
    );
    expect(screen.getByTestId('diferencias-error')).toBeInTheDocument();
  });

  it('renders the descuadre warning when difference is non-zero', () => {
    render(
      <DiferenciasPanel
        diferencias={makeDiferencias(10, -3)}
        isLoading={false}
        error={undefined}
      />,
    );
    expect(screen.getByTestId('diferencias-panel')).toBeInTheDocument();
    expect(screen.getByTestId('diferencias-descuadre-warning')).toBeInTheDocument();
  });

  it('omits the descuadre warning when both differences are zero', () => {
    render(
      <DiferenciasPanel
        diferencias={makeDiferencias(0, 0)}
        isLoading={false}
        error={undefined}
      />,
    );
    expect(screen.queryByTestId('diferencias-descuadre-warning')).not.toBeInTheDocument();
  });

  it('renders the empty placeholder when diferencias is null', () => {
    render(
      <DiferenciasPanel diferencias={null} isLoading={false} error={undefined} />,
    );
    expect(screen.getByTestId('diferencias-empty')).toBeInTheDocument();
  });
});