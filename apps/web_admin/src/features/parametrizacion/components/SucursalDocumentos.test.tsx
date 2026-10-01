/**
 * `SucursalDocumentos.test.tsx` — invariantes del tab "Documentos" de
 * `SucursalDetalle` (HU-F15.4).
 *
 *   T1: bloquea la UI de gestión (no fetch, no formularios) cuando la
 *       sucursal ACTIVA difiere de la de la ruta.
 *   T2: permite operar cuando no hay sucursal activa seleccionada
 *       (`selected === null` -> modo "global" del backend, BR de scope).
 *   T3: loading state mientras el SWR resuelve.
 *   T4: sin documentos cargados, muestra el empty state por cada tipo
 *       de archivo y el textarea vacío para observaciones.
 *   T5: subir un logo válido (tamaño + formato ok) hace POST (sin
 *       `current`) con `formato` = MIME real del `File`.
 *   T6: un archivo de más de 1MB se rechaza en cliente SIN llamar a la
 *       API.
 *   T7: un formato no permitido para `logo` (ej. PDF) se rechaza en
 *       cliente SIN llamar a la API.
 *   T8: cuando ya existe un documento vigente de ese tipo, el submit usa
 *       PUT (se le pasa `current` a `upsertDocumento`).
 *   T9: observaciones (BR3): escribir texto y guardar codifica a base64
 *       con `formato: 'text/plain'`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { SWRConfig } from 'swr';

import { SucursalDocumentos } from './SucursalDocumentos';
import * as documentosApi from '../api/documentosApi';
import * as sucursalCtx from '@/lib/sucursal-context';

vi.mock('../api/documentosApi', () => ({
  listDocumentosPorSucursal: vi.fn(),
  upsertDocumento: vi.fn(),
}));
vi.mock('@/lib/sucursal-context', () => ({
  useSucursal: vi.fn(),
}));

const listDocumentosPorSucursal = vi.mocked(documentosApi.listDocumentosPorSucursal);
const upsertDocumento = vi.mocked(documentosApi.upsertDocumento);
const useSucursal = vi.mocked(sucursalCtx.useSucursal);

const UUID_SUCURSAL = '00000000-0000-0000-0000-00000000d001';
const UUID_OTRA = '00000000-0000-0000-0000-00000000d002';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    children,
  );
}

function renderTab(uuidSucursal: string = UUID_SUCURSAL): void {
  render(
    createElement(wrapper, null, createElement(SucursalDocumentos, { uuidSucursal })),
  );
}

beforeEach(() => {
  listDocumentosPorSucursal.mockReset();
  upsertDocumento.mockReset();
  useSucursal.mockReset();
  useSucursal.mockReturnValue({ selected: UUID_SUCURSAL, setSelected: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SucursalDocumentos — scope gating', () => {
  it('T1: bloquea la UI y NO hace fetch cuando la sucursal activa difiere de la ruta', () => {
    useSucursal.mockReturnValue({ selected: UUID_OTRA, setSelected: vi.fn() });
    renderTab();
    expect(screen.getByTestId('sucursal-documentos-scope-blocked')).toBeInTheDocument();
    expect(listDocumentosPorSucursal).not.toHaveBeenCalled();
  });

  it('T2: permite operar cuando no hay sucursal activa seleccionada (modo global)', async () => {
    useSucursal.mockReturnValue({ selected: null, setSelected: vi.fn() });
    listDocumentosPorSucursal.mockResolvedValue([]);
    renderTab();
    await waitFor(() => {
      expect(screen.getByTestId('sucursal-documentos-root')).toBeInTheDocument();
    });
    expect(listDocumentosPorSucursal).toHaveBeenCalledWith(UUID_SUCURSAL);
  });
});

describe('SucursalDocumentos — estados de carga', () => {
  it('T3: muestra loading mientras el SWR está pending', () => {
    listDocumentosPorSucursal.mockReturnValue(new Promise(() => undefined));
    renderTab();
    expect(screen.getByTestId('sucursal-documentos-loading')).toBeInTheDocument();
  });

  it('T4: sin documentos cargados muestra el empty state por tipo de archivo', async () => {
    listDocumentosPorSucursal.mockResolvedValue([]);
    renderTab();
    await waitFor(() => {
      expect(screen.getByTestId('sucursal-documentos-root')).toBeInTheDocument();
    });
    expect(screen.getByTestId('sucursal-documentos-empty-logo')).toBeInTheDocument();
    expect(screen.getByTestId('sucursal-documentos-empty-certificado')).toBeInTheDocument();
    expect(screen.getByTestId('sucursal-documentos-empty-plantilla_ticket')).toBeInTheDocument();
    expect(
      (screen.getByTestId('sucursal-documentos-textarea-observaciones') as HTMLTextAreaElement)
        .value,
    ).toBe('');
  });
});

describe('SucursalDocumentos — upload de archivos', () => {
  it('T5: sube un logo válido -> POST (sin current) con el MIME real del File', async () => {
    const user = userEvent.setup();
    listDocumentosPorSucursal.mockResolvedValue([]);
    upsertDocumento.mockResolvedValue({
      uuid: 'doc-1',
      uuid_sucursal: UUID_SUCURSAL,
      tipo: 'logo',
      formato: 'image/png',
      documento_b64: 'QUJD',
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: 'sincronizado',
    });
    renderTab();
    await waitFor(() => screen.getByTestId('sucursal-documentos-root'));

    const file = new File([new Uint8Array(10)], 'logo.png', { type: 'image/png' });
    const input = screen.getByTestId('sucursal-documentos-file-logo');
    await user.upload(input, file);
    await user.click(screen.getByTestId('sucursal-documentos-submit-logo'));

    await waitFor(() => expect(upsertDocumento).toHaveBeenCalledTimes(1));
    const [current, payload] = upsertDocumento.mock.calls[0]!;
    expect(current).toBeUndefined();
    expect(payload).toMatchObject({
      uuid_sucursal: UUID_SUCURSAL,
      tipo: 'logo',
      formato: 'image/png',
    });
    expect(typeof payload.documento_b64).toBe('string');
    expect(payload.documento_b64.length).toBeGreaterThan(0);
  });

  it('T6: rechaza un archivo de más de 1MB sin llamar a la API', async () => {
    const user = userEvent.setup();
    listDocumentosPorSucursal.mockResolvedValue([]);
    renderTab();
    await waitFor(() => screen.getByTestId('sucursal-documentos-root'));

    const bigFile = new File([new Uint8Array(1_048_577)], 'logo.png', { type: 'image/png' });
    const input = screen.getByTestId('sucursal-documentos-file-logo');
    await user.upload(input, bigFile);
    await user.click(screen.getByTestId('sucursal-documentos-submit-logo'));

    expect(await screen.findByTestId('sucursal-documentos-local-error-logo')).toHaveTextContent(
      /1 MB/,
    );
    expect(upsertDocumento).not.toHaveBeenCalled();
  });

  it('T7: rechaza un formato no permitido para logo (PDF) sin llamar a la API', async () => {
    // `applyAccept: false` (config de la instancia, no del `.upload()`)
    // bypassea la emulación del atributo HTML `accept` que hace
    // user-event -- ese atributo es solo una ayuda de UI del browser
    // que el usuario PUEDE evitar (ej. "Todos los archivos"), así que la
    // defensa real que este test apunta es el chequeo JS
    // `validarFormatoArchivo`, no el atributo `accept` en sí.
    const user = userEvent.setup({ applyAccept: false });
    listDocumentosPorSucursal.mockResolvedValue([]);
    renderTab();
    await waitFor(() => screen.getByTestId('sucursal-documentos-root'));

    const pdfFile = new File([new Uint8Array(10)], 'logo.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('sucursal-documentos-file-logo');
    await user.upload(input, pdfFile);
    await user.click(screen.getByTestId('sucursal-documentos-submit-logo'));

    expect(await screen.findByTestId('sucursal-documentos-local-error-logo')).toHaveTextContent(
      /no permitido/i,
    );
    expect(upsertDocumento).not.toHaveBeenCalled();
  });

  it('T8: si ya existe un documento vigente de ese tipo, el submit se hace con PUT (current pasado)', async () => {
    const user = userEvent.setup();
    const existente = {
      uuid: 'doc-existente',
      uuid_sucursal: UUID_SUCURSAL,
      tipo: 'logo',
      formato: 'image/png',
      documento_b64: 'QUJD',
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: 'sincronizado',
    };
    listDocumentosPorSucursal.mockResolvedValue([existente]);
    upsertDocumento.mockResolvedValue(existente);
    renderTab();
    await waitFor(() => screen.getByTestId('sucursal-documentos-preview-logo'));

    const file = new File([new Uint8Array(10)], 'logo-nuevo.png', { type: 'image/png' });
    const input = screen.getByTestId('sucursal-documentos-file-logo');
    await user.upload(input, file);
    await user.click(screen.getByTestId('sucursal-documentos-submit-logo'));

    await waitFor(() => expect(upsertDocumento).toHaveBeenCalledTimes(1));
    const [current] = upsertDocumento.mock.calls[0]!;
    expect(current).toEqual(existente);
  });
});

describe('SucursalDocumentos — observaciones (BR3, texto plano)', () => {
  it('T9: escribir texto y guardar codifica a base64 con formato text/plain', async () => {
    const user = userEvent.setup();
    listDocumentosPorSucursal.mockResolvedValue([]);
    upsertDocumento.mockResolvedValue({
      uuid: 'doc-obs',
      uuid_sucursal: UUID_SUCURSAL,
      tipo: 'observaciones',
      formato: 'text/plain',
      documento_b64: 'b2JzZXJ2YWNpb24=',
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: 'sincronizado',
    });
    renderTab();
    await waitFor(() => screen.getByTestId('sucursal-documentos-root'));

    const textarea = screen.getByTestId('sucursal-documentos-textarea-observaciones');
    await user.type(textarea, 'Horario especial en diciembre.');
    await user.click(screen.getByTestId('sucursal-documentos-submit-observaciones'));

    await waitFor(() => expect(upsertDocumento).toHaveBeenCalledTimes(1));
    const [, payload] = upsertDocumento.mock.calls[0]!;
    expect(payload.tipo).toBe('observaciones');
    expect(payload.formato).toBe('text/plain');
    expect(atob(payload.documento_b64)).toBe('Horario especial en diciembre.');
  });
});
