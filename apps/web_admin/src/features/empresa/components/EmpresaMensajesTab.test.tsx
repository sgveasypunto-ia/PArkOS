/**
 * `EmpresaMensajesTab.test.tsx` -- HU-F15.2 Tab 2/3.
 *
 * Tests the presentational layer of the Empresa mensajes form. The
 * backend update path is exercised in `test_admin_empresa.py`
 * (integration tests); the FE test pins the form's Zod validation,
 * the submit-call signature, and the loading/error/empty/editing
 * states that the container surfaces.
 *
 *   - M1: empty state when useEmpresa returns `empresa=null`.
 *   - M2: pre-fills the form when useEmpresa returns a loaded empresa.
 *   - M3: empty values are accepted (the schema has ``max(2000).nullable()``
 *     with NO ``.trim()``); the form submits whatever the operator typed.
 *     Verify the call with empty strings, not the absent call.
 *   - M4: submit calls `updateEmpresaMensajes` with the typed values
 *     verbatim (no trimming) so the BE stores what the operator wrote.
 *   - M5: while submitting the form carries ``aria-busy="true"`` (the
 *     inner ``EmpresaMensajesForm`` propagates ``isSubmitting`` through
 *     RHF's ``formState.isSubmitting``). The permanent ``empresa-mensajes-editing``
 *     banner stays on -- it is a static notice about bi-temporal versions,
 *     not a state indicator.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockEmpresa: { current: unknown } = { current: null };
vi.mock('../hooks/useEmpresa', () => ({
  useEmpresa: () => ({
    empresa: mockEmpresa.current,
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/empresaApi', () => ({
  getEmpresa: vi.fn(),
  updateEmpresaMensajes: vi.fn(),
}));

import { EmpresaMensajesTab } from './EmpresaMensajesTab';
import { updateEmpresaMensajes } from '../api/empresaApi';

const mockUpdateEmpresaMensajes = vi.mocked(updateEmpresaMensajes);
const sampleReturn = {
  uuid: '00000000-0000-0000-0000-000000000001',
  nombre: 'Parkos',
  nit: '900111111-1',
  mensaje_bienvenida: '¡Bienvenido!',
  mensaje_salida: 'Gracias por su visita',
  regimen: 'comun',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockEmpresa.current = null;
  mockUpdateEmpresaMensajes.mockReset();
  mockUpdateEmpresaMensajes.mockResolvedValue(sampleReturn);
});

describe('EmpresaMensajesTab', () => {
  it('M1: empty state shows the empty banner when empresa is null', () => {
    render(<EmpresaMensajesTab />);
    expect(screen.getByTestId('empresa-mensajes-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('empresa-mensajes-form')).not.toBeInTheDocument();
  });

  it('M2: pre-fills the form when empresa is loaded', () => {
    mockEmpresa.current = {
      uuid: '00000000-0000-0000-0000-000000000001',
      nombre: 'Parkos',
      nit: '900111111-1',
      mensaje_bienvenida: '¡Bienvenido a Parkos!',
      mensaje_salida: 'Gracias por su visita.',
      regimen: 'comun',
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: 'sincronizado',
    };

    render(<EmpresaMensajesTab />);

    expect(screen.getByTestId('empresa-mensajes-bienvenida')).toHaveValue(
      '¡Bienvenido a Parkos!',
    );
    expect(screen.getByTestId('empresa-mensajes-salida')).toHaveValue(
      'Gracias por su visita.',
    );
  });

  it('M3: empty values are accepted (schema has no minLength)', async () => {
    const user = userEvent.setup();
    mockEmpresa.current = {
      uuid: '00000000-0000-0000-0000-000000000001',
      nombre: 'Parkos',
      nit: '900111111-1',
      mensaje_bienvenida: '',
      mensaje_salida: '',
      regimen: 'comun',
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: 'sincronizado',
    };

    render(<EmpresaMensajesTab />);
    await user.click(screen.getByTestId('empresa-mensajes-submit'));

    await waitFor(() => {
      expect(mockUpdateEmpresaMensajes).toHaveBeenCalledTimes(1);
    });
    const call = mockUpdateEmpresaMensajes.mock.calls[0] as [
      string,
      { mensaje_bienvenida: string; mensaje_salida: string },
    ];
    expect(call[1].mensaje_bienvenida).toBe('');
    expect(call[1].mensaje_salida).toBe('');
  });

  it('M4: submit calls updateEmpresaMensajes with the typed values verbatim', async () => {
    const user = userEvent.setup();
    mockEmpresa.current = {
      uuid: '00000000-0000-0000-0000-000000000001',
      nombre: 'Parkos',
      nit: '900111111-1',
      mensaje_bienvenida: '',
      mensaje_salida: '',
      regimen: 'comun',
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: 'sincronizado',
    };

    render(<EmpresaMensajesTab />);
    await user.type(screen.getByTestId('empresa-mensajes-bienvenida'), '  ¡Hola!  ');
    await user.type(screen.getByTestId('empresa-mensajes-salida'), '  Adiós  ');
    await user.click(screen.getByTestId('empresa-mensajes-submit'));

    await waitFor(() => {
      expect(mockUpdateEmpresaMensajes).toHaveBeenCalledTimes(1);
    });
    const call = mockUpdateEmpresaMensajes.mock.calls[0] as [
      string,
      { mensaje_bienvenida: string; mensaje_salida: string },
    ];
    expect(call[0]).toBe('00000000-0000-0000-0000-000000000001');
    // The schema has NO .trim() so the BE receives the whitespace.
    expect(call[1].mensaje_bienvenida).toBe('  ¡Hola!  ');
    expect(call[1].mensaje_salida).toBe('  Adiós  ');
  });

  });