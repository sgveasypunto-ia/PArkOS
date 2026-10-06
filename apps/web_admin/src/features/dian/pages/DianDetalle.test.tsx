/**
 * PT-1: "Volver" in the DIAN detail returns to the previous screen (the queue
 * with its tab in the querystring), falling back to `/dian` on a deep link.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import DianDetalle from './DianDetalle';

function Probe(): JSX.Element {
  const location = useLocation();
  return <div data-testid="list-probe">{location.pathname + location.search}</div>;
}

function renderAt(entries: string[], index: number) {
  return render(
    <MemoryRouter initialEntries={entries} initialIndex={index}>
      <Routes>
        <Route path="/dian/:uuid" element={<DianDetalle />} />
        <Route path="/dian" element={<Probe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DianDetalle -- Volver', () => {
  it('returns to the previous URL keeping the queue tab', async () => {
    renderAt(['/dian?estado=rechazado', '/dian/abc'], 1);
    await userEvent.click(screen.getByTestId('dian-detalle-back'));
    expect(screen.getByTestId('list-probe')).toHaveTextContent('/dian?estado=rechazado');
  });

  it('falls back to /dian on a deep link', async () => {
    renderAt(['/dian/abc'], 0);
    await userEvent.click(screen.getByTestId('dian-detalle-back'));
    expect(screen.getByTestId('list-probe')).toHaveTextContent('/dian');
  });
});
