/**
 * `PermisosTree.test.tsx` — regression tests for the group-cascade bug.
 *
 * The defect under test: `agruparPermisosPorPrefijo` mints synthetic
 * group ids (`ADMIN`), `Tree` toggles only the clicked id, and
 * `handleSelectionChange` looked the id up in the permission catalog.
 * The lookup missed, the request was silently dropped, and the checkbox
 * snapped back on the next refetch -- with no error anywhere.
 *
 * Every test here drives the real component and asserts on the requests
 * that reach `asignarPermiso` / `revocarPermiso`, because "the checkbox
 * looks right" is exactly the signal that failed to catch the bug.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';

import { PermisosTree } from './PermisosTree';
import * as api from '../api/usuariosApi';
import type { Permiso, PermisoUsuario } from '../api/usuariosSchema';

const USUARIO = '11111111-1111-1111-1111-111111111111';

const CATALOGO: Permiso[] = [
  { uuid: 'p-1', codigo: 'ADMIN_USUARIOS_VER', descripcion: null },
  { uuid: 'p-2', codigo: 'ADMIN_USUARIOS_CREAR', descripcion: null },
  { uuid: 'p-3', codigo: 'CAJA_ARQUEOS_CERRAR', descripcion: null },
];

function grant(codigo: string, vigenteHasta: string | null = null): PermisoUsuario {
  return {
    uuid: `pu-${codigo}`,
    uuid_usuario: USUARIO,
    uuid_permiso: CATALOGO.find((p) => p.codigo === codigo)?.uuid ?? 'x',
    codigo,
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: vigenteHasta,
  };
}

function montar({
  granted = [] as PermisoUsuario[],
  catalog = CATALOGO,
}: {
  granted?: PermisoUsuario[];
  catalog?: Permiso[];
} = {}) {
  vi.spyOn(api, 'getPermisos').mockResolvedValue(catalog);
  vi.spyOn(api, 'getPermisosUsuario').mockResolvedValue(granted);
  vi.spyOn(api, 'asignarPermiso').mockResolvedValue(undefined);
  vi.spyOn(api, 'revocarPermiso').mockResolvedValue(undefined);

  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <PermisosTree uuidUsuario={USUARIO} />
    </SWRConfig>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('PermisosTree', () => {
  it('asigna todos los hijos al marcar un grupo', async () => {
    montar({ granted: [] });
    await screen.findByLabelText('ADMIN');

    await userEvent.click(screen.getByLabelText('ADMIN'));

    await waitFor(() => {
      expect(api.asignarPermiso).toHaveBeenCalledTimes(2);
    });
    expect(api.asignarPermiso).toHaveBeenCalledWith(USUARIO, 'p-1');
    expect(api.asignarPermiso).toHaveBeenCalledWith(USUARIO, 'p-2');
    // A synthetic group id must never reach the API.
    expect(api.asignarPermiso).not.toHaveBeenCalledWith(USUARIO, 'ADMIN');
  });

  it('revoca todos los hijos al desmarcar un grupo', async () => {
    montar({
      granted: [grant('ADMIN_USUARIOS_VER'), grant('ADMIN_USUARIOS_CREAR')],
    });
    await screen.findByLabelText('ADMIN');

    await userEvent.click(screen.getByLabelText('ADMIN'));

    await waitFor(() => {
      expect(api.revocarPermiso).toHaveBeenCalledTimes(2);
    });
    expect(api.revocarPermiso).toHaveBeenCalledWith(USUARIO, 'p-1');
    expect(api.revocarPermiso).toHaveBeenCalledWith(USUARIO, 'p-2');
  });

  it('renderiza el grupo como marcado solo si tiene todos sus hijos', async () => {
    montar({ granted: [grant('ADMIN_USUARIOS_VER')] });
    const group = await screen.findByLabelText('ADMIN');
    // Partial ownership must not claim the whole group.
    expect(group).not.toBeChecked();
  });

  it('no falla cuando el catalogo trae un codigo NULL', async () => {
    montar({
      catalog: [
        ...CATALOGO,
        { uuid: 'p-null', codigo: null, descripcion: null },
      ],
      granted: [],
    });

    // `prod.permisos.permiso` is a nullable column, so `codigo` can be
    // NULL. The row must be skipped, not crash the tab on `split`.
    await screen.findByLabelText('ADMIN');
    expect(screen.getByLabelText('ADMIN_USUARIOS_VER')).toBeInTheDocument();
  });

  it('muestra el error en vez de un arbol vacio', async () => {
    vi.spyOn(api, 'getPermisos').mockRejectedValue(new Error('boom'));
    vi.spyOn(api, 'getPermisosUsuario').mockResolvedValue([]);

    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <PermisosTree uuidUsuario={USUARIO} />
      </SWRConfig>,
    );

    await waitFor(() => {
      expect(
        screen.getByText(/No se pudieron cargar los permisos/i),
      ).toBeInTheDocument();
    });
    // A failed fetch must not masquerade as "the user holds no permissions".
    expect(screen.queryByLabelText('ADMIN')).not.toBeInTheDocument();
  });
});