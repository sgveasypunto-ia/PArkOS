/**
 * `LogDetalle.test.tsx` -- HU-F20.4 detail page render tests, covering
 * the field-by-field diff (`lib/diffAuditLog.ts` is unit-tested on its
 * own; this covers the actual DOM render) and the router-state fallback.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import LogDetalle from './LogDetalle';
import type { AuditLogItem } from '../api/auditoriaSchema';

function makeItem(overrides: Partial<AuditLogItem> = {}): AuditLogItem {
  return {
    uuid: 'a',
    timestamp_evento: '2026-09-01T08:00:00',
    uuid_usuario: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_referencia: null,
    accion: 'actualizar',
    tabla_afectada: 'arqueo',
    datos_anteriores: { estado: 'abierta' },
    datos_nuevos: { estado: 'cerrada' },
    hash_anterior: 'a'.repeat(64),
    hash_actual: 'b'.repeat(64),
    ...overrides,
  };
}

function renderWithState(item: AuditLogItem | undefined, uuid = 'a') {
  return render(
    <MemoryRouter
      initialEntries={[
        { pathname: `/auditoria/log/${uuid}`, state: item ? { item } : undefined },
      ]}
    >
      <Routes>
        <Route path="/auditoria/log/:uuid" element={<LogDetalle />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LogDetalle', () => {
  it('renders a field-by-field diff row showing the before/after values', () => {
    renderWithState(makeItem());

    const row = screen.getByTestId('log-detalle-diff-row-estado');
    expect(row).toBeInTheDocument();
    expect(row).toHaveTextContent('abierta');
    expect(row).toHaveTextContent('cerrada');
  });

  it('renders the hash chain status badge', () => {
    renderWithState(makeItem());
    expect(screen.getByTestId('log-detalle-hash')).toBeInTheDocument();
  });

  it('shows the "volver al listado" fallback when there is no router state', () => {
    renderWithState(undefined);
    expect(screen.getByTestId('log-detalle-not-found')).toBeInTheDocument();
    expect(screen.getByTestId('log-detalle-back')).toBeInTheDocument();
  });

  it('shows the fallback when the state item uuid does not match the route param', () => {
    renderWithState(makeItem({ uuid: 'other' }), 'a');
    expect(screen.getByTestId('log-detalle-not-found')).toBeInTheDocument();
  });
});
