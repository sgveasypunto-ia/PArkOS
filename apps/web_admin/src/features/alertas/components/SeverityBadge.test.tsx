/**
 * `SeverityBadge.test.tsx` -- web_admin consume el vocabulario del cable
 * (`prod.alert_types.severity`: critical | warning | info) SIN traduccion:
 * los tres valores se muestran tal cual y los filtros ofrecen los mismos tres.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ALERTA_SEVERITIES } from '../api/alertasSchema';
import { AlertasFilters } from './AlertasFilters';
import { SeverityBadge } from './SeverityBadge';

describe('web_admin severity vocabulary (wire contract)', () => {
  it('the wire vocabulary is exactly critical | warning | info', () => {
    expect([...ALERTA_SEVERITIES]).toEqual(['critical', 'warning', 'info']);
  });

  it.each(['critical', 'warning', 'info'] as const)('SeverityBadge renders wire value %s', (sev) => {
    render(<SeverityBadge severity={sev} />);
    expect(screen.getByTestId(`severity-badge-${sev}`)).toBeInTheDocument();
  });

  it('AlertasFilters offers the three wire values and nothing else', () => {
    render(
      <AlertasFilters
        value={{ uuid_sucursal: '', tipo_alerta: '', estado: '', severidad: '', desde: '', hasta: '' }}
        onChange={vi.fn()}
        onReset={vi.fn()}
        options={{ sucursalOptions: [] }}
      />,
    );
    const select = screen.getByTestId('alertas-filters-severidad') as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(['', 'critical', 'warning', 'info']);
  });
});
