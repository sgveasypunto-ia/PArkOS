import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ejecutarImpresion, useAvisosImpresion } from '../../lib/print/avisoImpresion';
import { AvisosImpresion } from './AvisosImpresion';

describe('<AvisosImpresion />', () => {
  beforeEach(() => useAvisosImpresion.setState({ avisos: [] }));

  it('no pinta nada sin avisos', () => {
    const { container } = render(<AvisosImpresion />);
    expect(container).toBeEmptyDOMElement();
  });

  it('muestra "No se pudo imprimir…" y Reintentar vuelve a imprimir y limpia el aviso', async () => {
    const fn = vi
      .fn<() => Promise<{ ok: boolean }>>()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true });
    render(<AvisosImpresion />);
    await ejecutarImpresion('el cierre de turno', fn);
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent(/No se pudo imprimir el cierre de turno/);
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('Cerrar descarta el aviso', async () => {
    render(<AvisosImpresion />);
    await ejecutarImpresion('el tiquete', async () => ({ ok: false }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
