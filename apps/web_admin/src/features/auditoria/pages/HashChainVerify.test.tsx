/**
 * `HashChainVerify.test.tsx` -- HU-F20.4 page-level tests for the
 * on-demand verification sweep.
 *
 *  - T1: clicking "Verificar" calls `fetchVerifyChain` and renders the
 *    ok state when `anomalias` is empty.
 *  - T2: renders the anomaly table + "Exportar CSV" button when
 *    `ok: false`.
 *  - T3: "Exportar CSV" calls `exportToCsv` with the anomaly rows.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const useSucursalesDirectorioMock = vi.fn();
vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => useSucursalesDirectorioMock(),
}));

vi.mock('../api/auditoriaApi', () => ({
  fetchVerifyChain: vi.fn(),
}));

const exportToCsvMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/export/csv', () => ({
  exportToCsv: exportToCsvMock,
}));

import { fetchVerifyChain } from '../api/auditoriaApi';
import HashChainVerify from './HashChainVerify';

const mockedVerify = fetchVerifyChain as ReturnType<typeof vi.fn>;

describe('HashChainVerify', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: clicking "Verificar" calls fetchVerifyChain and renders the ok state', async () => {
    useSucursalesDirectorioMock.mockReturnValue({ sucursales: [] });
    mockedVerify.mockResolvedValue({ ok: true, anomalias: [] });

    const user = userEvent.setup();
    render(<HashChainVerify />);

    await user.click(screen.getByTestId('hash-chain-verify-button'));

    expect(await screen.findByTestId('hash-chain-verify-ok')).toBeInTheDocument();
    expect(mockedVerify).toHaveBeenCalledWith({
      tabla: 'log_transaccional',
      uuid_sucursal: undefined,
    });
  });

  it('T2: renders the anomaly table + export button when the sweep finds anomalies', async () => {
    useSucursalesDirectorioMock.mockReturnValue({ sucursales: [] });
    mockedVerify.mockResolvedValue({
      ok: false,
      anomalias: [
        {
          tabla: 'log_transaccional',
          uuid_sucursal: '22222222-2222-2222-2222-222222222222',
          uuid: '33333333-3333-3333-3333-333333333333',
          expected: 'a'.repeat(64),
          actual: 'b'.repeat(64),
          seq: 5,
          reason: 'hash_mismatch',
        },
      ],
    });

    const user = userEvent.setup();
    render(<HashChainVerify />);

    await user.click(screen.getByTestId('hash-chain-verify-button'));

    expect(
      await screen.findByTestId(
        'hash-chain-verify-anomalia-33333333-3333-3333-3333-333333333333',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('hash-chain-verify-export-csv')).toBeInTheDocument();
  });

  it('T3: clicking "Exportar CSV" calls exportToCsv with the anomaly rows', async () => {
    useSucursalesDirectorioMock.mockReturnValue({ sucursales: [] });
    const anomalias = [
      {
        tabla: 'log_transaccional',
        uuid_sucursal: null,
        uuid: '33333333-3333-3333-3333-333333333333',
        expected: 'a'.repeat(64),
        actual: null,
        seq: null,
        reason: 'missing_row',
      },
    ];
    mockedVerify.mockResolvedValue({ ok: false, anomalias });

    const user = userEvent.setup();
    render(<HashChainVerify />);

    await user.click(screen.getByTestId('hash-chain-verify-button'));
    await screen.findByTestId('hash-chain-verify-export-csv');

    await user.click(screen.getByTestId('hash-chain-verify-export-csv'));

    expect(exportToCsvMock).toHaveBeenCalledWith(
      'verify-chain-log_transaccional.csv',
      expect.any(Array),
      anomalias,
    );
  });
});
