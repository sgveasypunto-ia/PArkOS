/**
 * Chart components — smoke tests (HU-F17.1, T6).
 *
 * These are hand-rolled SVG components (no charting library in this
 * repo), so the tests pin the two things most likely to regress: the
 * empty-data fallback (never an empty/broken SVG) and the accessible
 * surface each form is required to expose (dataviz skill check 6 --
 * direct value labels on the bar chart's WARN-contrast slots, a legend
 * on the pie, and a table-view toggle on the heatmap).
 */
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ChartLine } from './ChartLine';
import { ChartBar } from './ChartBar';
import { ChartPie } from './ChartPie';
import { HeatmapOcupacion } from './HeatmapOcupacion';

describe('ChartLine', () => {
  it('T1: empty data renders the fallback, not a broken SVG', () => {
    render(<ChartLine data={[]} title="Ingresos" />);
    expect(screen.getByTestId('chart-line-empty')).toBeInTheDocument();
  });

  it('T2: renders one point per data row', () => {
    render(
      <ChartLine
        data={[
          { fecha: '2026-09-01', monto_total: 100 },
          { fecha: '2026-09-02', monto_total: 200 },
        ]}
        title="Ingresos"
      />,
    );
    expect(screen.getByTestId('chart-line-point-0')).toBeInTheDocument();
    expect(screen.getByTestId('chart-line-point-1')).toBeInTheDocument();
  });
});

describe('ChartBar', () => {
  it('T1: empty data renders the fallback', () => {
    render(<ChartBar data={[]} title="Top sucursales" />);
    expect(screen.getByTestId('chart-bar-empty')).toBeInTheDocument();
  });

  it('T2: every bar carries a direct value label (contrast WARN relief)', () => {
    render(
      <ChartBar
        data={[
          { uuid_sucursal: '11111111-1111-1111-1111-111111111111', nombre: 'Suc A', monto_total: 900 },
        ]}
        title="Top sucursales"
      />,
    );
    expect(screen.getByText('$900')).toBeInTheDocument();
    expect(screen.getByText('Suc A')).toBeInTheDocument();
  });
});

describe('ChartPie', () => {
  it('T1: empty data renders the fallback', () => {
    render(<ChartPie data={[]} title="Estado FE" />);
    expect(screen.getByTestId('chart-pie-empty')).toBeInTheDocument();
  });

  it('T2: renders a legend entry per state with its percentage', () => {
    render(
      <ChartPie
        data={[
          { estado: 'enviada', count: 3 },
          { estado: 'pendiente', count: 1 },
        ]}
        title="Estado FE"
      />,
    );
    expect(screen.getByTestId('chart-pie-legend-enviada')).toHaveTextContent('75%');
    expect(screen.getByTestId('chart-pie-legend-pendiente')).toHaveTextContent('25%');
  });
});

describe('HeatmapOcupacion', () => {
  it('T1: no sucursales renders the fallback', () => {
    render(<HeatmapOcupacion data={[]} sucursales={[]} title="Actividad" />);
    expect(screen.getByTestId('heatmap-ocupacion-empty')).toBeInTheDocument();
  });

  it('T2: the table-view toggle swaps the SVG grid for an HTML table (accessibility relief)', () => {
    render(
      <HeatmapOcupacion
        data={[{ uuid_sucursal: '11111111-1111-1111-1111-111111111111', hora: 9, ingresos_count: 4 }]}
        sucursales={[{ uuid: '11111111-1111-1111-1111-111111111111', nombre: 'Suc A' }]}
        title="Actividad"
      />,
    );
    expect(screen.queryByTestId('heatmap-ocupacion-table')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('heatmap-ocupacion-toggle-table'));
    expect(screen.getByTestId('heatmap-ocupacion-table')).toBeInTheDocument();
    expect(screen.getByText('Suc A')).toBeInTheDocument();
  });
});
