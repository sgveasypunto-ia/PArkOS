/**
 * `<SuscripcionesCohorte />` — unit tests (HU-F17.4, BR1).
 */
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { SuscripcionesCohorte } from './SuscripcionesCohorte';
import type { CohorteRetencionCell, CohorteSuscripcionItem } from '../api/reporteriaSchema';

describe('SuscripcionesCohorte', () => {
  it('T1: no cohorts renders the empty state', () => {
    render(
      <SuscripcionesCohorte cohortes={[]} data={[]} maxOffsetMeses={12} title="Cohortes" />,
    );
    expect(screen.getByTestId('suscripciones-cohorte-empty')).toBeInTheDocument();
  });

  it('T2: a present cell (measured, even 0%) renders a colored rect distinct from a missing (no-data) cell', () => {
    const cohortes: CohorteSuscripcionItem[] = [{ mes_cohorte: '2026-07-01', cohorte_size: 4 }];
    const data: CohorteRetencionCell[] = [
      {
        mes_cohorte: '2026-07-01',
        mes_offset: 0,
        cohorte_size: 4,
        retenidos: 0,
        porcentaje_retencion: 0,
      },
    ];
    render(
      <SuscripcionesCohorte cohortes={cohortes} data={data} maxOffsetMeses={2} title="Cohortes" />,
    );
    // offset 0 was measured (0%) -- a real, colored cell.
    expect(screen.getByTestId('suscripciones-cohorte-cell-2026-07-01-0')).toBeInTheDocument();
    // offset 1/2 have no data yet -- the distinct "no data" cell variant.
    expect(
      screen.getByTestId('suscripciones-cohorte-cell-2026-07-01-1-nodata'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('suscripciones-cohorte-cell-2026-07-01-2-nodata'),
    ).toBeInTheDocument();
  });

  it('T3: table view distinguishes "0%" (measured) from "—" (no data)', () => {
    const cohortes: CohorteSuscripcionItem[] = [{ mes_cohorte: '2026-07-01', cohorte_size: 4 }];
    const data: CohorteRetencionCell[] = [
      {
        mes_cohorte: '2026-07-01',
        mes_offset: 0,
        cohorte_size: 4,
        retenidos: 0,
        porcentaje_retencion: 0,
      },
    ];
    render(
      <SuscripcionesCohorte cohortes={cohortes} data={data} maxOffsetMeses={1} title="Cohortes" />,
    );
    fireEvent.click(screen.getByTestId('suscripciones-cohorte-toggle-table'));
    expect(screen.getByTestId('suscripciones-cohorte-table-cell-2026-07-01-0')).toHaveTextContent(
      '0%',
    );
    expect(screen.getByTestId('suscripciones-cohorte-table-cell-2026-07-01-1')).toHaveTextContent(
      '—',
    );
  });
});
