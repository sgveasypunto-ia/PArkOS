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

  // Bug #2 fix (2026-10-14): the BE removed the datafono fields from
  // the diferencias response (commit 05888fde, REQ-OPS-192) and the
  // Zod schema now defaults them to 0. The panel must render the
  // datafono row gracefully (showing "—") when the legacy response
  // arrives, instead of breaking or surfacing a descuadre warning
  // for what is indistinguishable from "no datafono tracked here".
  it('renders "—" in the datafono cells when the response carries no datafono (legacy shape)', () => {
    const legacyResponse: DiferenciasRead = {
      uuid_arqueo: '00000000-0000-0000-0000-0000000000a2',
      valor_efectivo_esperado: 160000,
      valor_datafono_esperado: 0,
      valor_efectivo_reportado: 160000,
      valor_datafono_reportado: 0,
      diferencia_efectivo: 0,
      diferencia_datafono: 0,
    };
    render(
      <DiferenciasPanel
        diferencias={legacyResponse}
        isLoading={false}
        error={undefined}
      />,
    );

    // Efectivo row: data is real, no warning.
    expect(screen.getByTestId('diferencias-row-efectivo')).toBeInTheDocument();
    expect(screen.queryByTestId('diferencias-descuadre-warning')).not.toBeInTheDocument();

    // Datafono row: each cell shows "—" (the legacy-response marker)
    // instead of "0,00". The cells still render -- the row is not
    // removed (the operator might have configured datafono even if
    // the response shape is legacy).
    const datafonoRow = screen.getByTestId('diferencias-row-datafono');
    const datafonoChildren = Array.from(datafonoRow.children);
    expect(datafonoChildren[1]?.textContent).toBe('—');
    expect(datafonoChildren[2]?.textContent).toBe('—');
    expect(screen.getByTestId('diferencias-cell-datafono').textContent).toBe('—');
  });

  it('surfaces the descuadre warning on efectivo descuadre even when datafono=0 (legacy shape)', () => {
    // Legacy response (datafono=0) with efectivo descuadre: the warning
    // MUST fire -- efectivo is the canonical signal.
    const legacyDescuadre: DiferenciasRead = {
      uuid_arqueo: '00000000-0000-0000-0000-0000000000a3',
      valor_efectivo_esperado: 160000,
      valor_datafono_esperado: 0,
      valor_efectivo_reportado: 155000,
      valor_datafono_reportado: 0,
      diferencia_efectivo: -5000,
      diferencia_datafono: 0,
    };
    render(
      <DiferenciasPanel
        diferencias={legacyDescuadre}
        isLoading={false}
        error={undefined}
      />,
    );

    expect(screen.getByTestId('diferencias-descuadre-warning')).toBeInTheDocument();
    // Efectivo cell renders bold/red because diferencia_efectivo !== 0
    const efectivoCell = screen.getByTestId('diferencias-cell-efectivo');
    expect(efectivoCell.className).toMatch(/text-destructive/);
  });

  it('renders the datafono values when the response carries them (post-fix shape)', () => {
    // BE returned the legacy shape (REJECTED by the BE post-fix via
    // extra='forbid', but the FE Zod schema now defaults datafono=0
    // and ignores the fields -- here we simulate a perfectly-formed
    // response with datafono data and assert the cells render the
    // values, not the "—" fallback).
    const withDatafono: DiferenciasRead = {
      uuid_arqueo: '00000000-0000-0000-0000-0000000000a4',
      valor_efectivo_esperado: 100000,
      valor_datafono_esperado: 5000,
      valor_efectivo_reportado: 100000,
      valor_datafono_reportado: 4800,
      diferencia_efectivo: 0,
      diferencia_datafono: -200,
    };
    render(
      <DiferenciasPanel
        diferencias={withDatafono}
        isLoading={false}
        error={undefined}
      />,
    );

    const datafonoChildren = Array.from(
      screen.getByTestId('diferencias-row-datafono').children,
    );
    expect(datafonoChildren[1]?.textContent).toBe('5.000,00');
    expect(datafonoChildren[2]?.textContent).toBe('4.800,00');
    const diferenciaCell = screen.getByTestId('diferencias-cell-datafono');
    expect(diferenciaCell.textContent).toBe('-200,00');
    // diferencia_datafono=-200 != 0 and datafono data is real, so
    // the cell is destructive-styled.
    expect(diferenciaCell.className).toMatch(/text-destructive/);
  });
});