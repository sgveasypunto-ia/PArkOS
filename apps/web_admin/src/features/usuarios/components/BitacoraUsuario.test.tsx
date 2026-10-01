/**
 * `BitacoraUsuario.test.tsx` — regression test for the schema drift that
 * broke the login-history table.
 *
 * The component read `creado_en`, `ip_origen` and `user_agent`, which
 * belong to the *session* shape (`sesionSchema`). The login-history
 * endpoint (`GET /admin/usuarios/{uuid}/login-historico`) returns
 * `LoginIntentoItem`: `uuid`, `timestamp_evento`, `timestamp_cierre`,
 * `estado`, `uuid_sucursal`. It never carried an IP or a user agent, so
 * those two columns rendered `undefined` forever.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SWRConfig } from 'swr';

import { BitacoraUsuario } from './BitacoraUsuario';
import * as api from '../api/usuariosApi';

const USUARIO = '11111111-1111-1111-1111-111111111111';
const SUCURSAL = 'cccccccc-cccc-cccc-cccc-cccccccccccc';

beforeEach(() => {
  vi.restoreAllMocks();
});

function montar(rows: unknown[]) {
  vi.spyOn(api, 'getLoginHistorico').mockResolvedValue(rows as never);
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <BitacoraUsuario uuidUsuario={USUARIO} />
    </SWRConfig>,
  );
}

describe('BitacoraUsuario', () => {
  it('renderiza las columnas del contrato LoginIntentoItem', async () => {
    montar([
      {
        uuid: 'l-1',
        timestamp_evento: '2026-03-04T15:30:00Z',
        timestamp_cierre: null,
        estado: 'exitoso',
        uuid_sucursal: SUCURSAL,
      },
    ]);

    expect(await screen.findByText('Fecha')).toBeInTheDocument();
    expect(screen.getByText('Sucursal')).toBeInTheDocument();
    expect(screen.getByText('Resultado')).toBeInTheDocument();
    // Never existed on this endpoint.
    expect(screen.queryByText('IP')).not.toBeInTheDocument();
    expect(screen.queryByText('User Agent')).not.toBeInTheDocument();
  });

  it('muestra la fecha y el prefijo de sucursal sin imprimir undefined', async () => {
    montar([
      {
        uuid: 'l-1',
        timestamp_evento: '2026-03-04T15:30:00Z',
        timestamp_cierre: null,
        estado: 'fallido',
        uuid_sucursal: SUCURSAL,
      },
    ]);

    expect(await screen.findByText('Fallido')).toBeInTheDocument();
    expect(screen.getByText(SUCURSAL.slice(0, 8))).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('undefined');
    expect(document.body.textContent).not.toContain('N/A');
  });

  it('tolera uuid_sucursal null', async () => {
    montar([
      {
        uuid: 'l-2',
        timestamp_evento: '2026-03-04T15:30:00Z',
        timestamp_cierre: null,
        estado: 'exitoso',
        uuid_sucursal: null,
      },
    ]);

    expect(await screen.findByText('Exitoso')).toBeInTheDocument();
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });
});