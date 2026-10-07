/**
 * Hook-level regression for the Idempotency-Key-per-user-action contract.
 *
 * The backend middleware persists and replays the stored response when the
 * same `Idempotency-Key` arrives again within 24h. A key derived only from
 * `method|path|body` therefore replays an OLD result for a NEW action:
 *   (1) exit -> dismiss payment drawer (anular) -> exit again => the second
 *       POST /salidas got the annulled salida back.
 *   (2) exit a plate and re-enter it => POST /ingresos replayed the old
 *       ingreso (old folio, no new row).
 *
 * The fake `parkosFetch` below emulates replay-by-key, so a repeated key
 * returns the FIRST response for that key.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@parkos/ui-kit/store', () => {
  const state = { accessToken: 'tok-abc', clear: vi.fn() };
  return {
    useAuthStore: Object.assign(
      (sel: (s: typeof state) => unknown) => sel(state),
      { getState: () => state },
    ),
  };
});

interface Call {
  path: string;
  key: string;
}
const calls: Call[] = [];
const stored = new Map<string, unknown>();
let seq = 0;

/** Backend emulation: same key => stored response; otherwise a fresh row. */
const fakeParkosFetch = vi.fn(
  async (path: string, init?: { headers?: Record<string, string> }) => {
    const key = init?.headers?.['Idempotency-Key'] ?? `auto-${++seq}`;
    calls.push({ path, key });
    // Slow enough that a double click overlaps the first request.
    await new Promise((r) => setTimeout(r, 5));
    const replay = stored.get(key);
    if (replay !== undefined) return replay;
    const row = buildRow(path, ++seq);
    stored.set(key, row);
    return row;
  },
);

function buildRow(path: string, n: number): unknown {
  const uuid = `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
  if (path.endsWith('/ingresos')) {
    return {
      uuid,
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
      consecutivo: null,
    };
  }
  if (path.endsWith('/salidas')) {
    return {
      uuid,
      uuid_sucursal: '00000000-0000-0000-0000-0000000000a2',
      uuid_ingreso: '00000000-0000-0000-0000-000000000001',
      fecha_salida: '2026-09-19T11:00:00Z',
      created_at: '2026-09-19T11:00:00Z',
      created_by: '00000000-0000-0000-0000-0000000000a4',
      sync_status: 'pending',
      sync_timestamp: null,
      sync_attempts: 0,
      tipo_salida: 'ROTACION',
      forzado_en_creacion: false,
      motivo_forzado: null,
      cotizacion_snapshot: null,
    };
  }
  return { uuid };
}

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: Parameters<typeof fakeParkosFetch>) => fakeParkosFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    public readonly body: string;
    constructor(status: number, body = '') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
    }
  },
}));

import { act, renderHook } from '@testing-library/react';

import { useAnularSalidaNoPagada } from '../../facturacion/hooks/useAnularSalidaNoPagada';
import { useRegistrarSalida } from '../hooks/useRegistrarSalida';
import { postIngreso } from './ingresoApi';

const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';

beforeEach(() => {
  calls.length = 0;
  stored.clear();
  seq = 0;
  fakeParkosFetch.mockClear();
});

describe('Idempotency-Key is per user action', () => {
  it('salida -> anular -> salida again sends DIFFERENT keys and gets a new row', async () => {
    const salida = renderHook(() => useRegistrarSalida());
    const anular = renderHook(() => useAnularSalidaNoPagada());

    let first: { uuid: string } | undefined;
    await act(async () => {
      first = await salida.result.current.trigger({ uuid_ingreso: UUID_INGRESO });
    });
    await act(async () => {
      await anular.result.current.trigger({ uuid_salida: first!.uuid });
    });
    let second: { uuid: string } | undefined;
    await act(async () => {
      second = await salida.result.current.trigger({ uuid_ingreso: UUID_INGRESO });
    });

    const salidaCalls = calls.filter((c) => c.path.endsWith('/salidas'));
    expect(salidaCalls).toHaveLength(2);
    expect(salidaCalls[0]!.key).not.toBe(salidaCalls[1]!.key);
    expect(second!.uuid).not.toBe(first!.uuid);
  });

  it('anular twice on the same salida (separate actions) sends different keys', async () => {
    const anular = renderHook(() => useAnularSalidaNoPagada());
    await act(async () => {
      await anular.result.current.trigger({ uuid_salida: 'u1' });
    });
    await act(async () => {
      await anular.result.current.trigger({ uuid_salida: 'u1' });
    });
    expect(calls).toHaveLength(2);
    expect(calls[0]!.key).not.toBe(calls[1]!.key);
  });

  it('salida then ingreso re-entry of the same plate sends DIFFERENT ingreso keys', async () => {
    const payload = {
      placa_presente: true as const,
      placa: 'QAI001',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    };
    const a = await postIngreso(payload);
    const b = await postIngreso(payload);

    const ingresoCalls = calls.filter((c) => c.path.endsWith('/ingresos'));
    expect(ingresoCalls[0]!.key).not.toBe(ingresoCalls[1]!.key);
    expect(b.uuid).not.toBe(a.uuid);
  });

  it('double click on the same salida sends the SAME key twice (backend dedupes)', async () => {
    const salida = renderHook(() => useRegistrarSalida());
    let r1: { uuid: string } | undefined;
    let r2: { uuid: string } | undefined;
    await act(async () => {
      const p1 = salida.result.current.trigger({ uuid_ingreso: UUID_INGRESO });
      // A real double click lands tens of ms later, while the first POST is
      // still in flight (the fake takes 5ms). Staggered by one macrotask
      // because vitest resolves two same-tick dynamic imports of a mocked
      // module to the real one (test-env quirk, not production behavior).
      await new Promise((r) => setTimeout(r, 1));
      const p2 = salida.result.current.trigger({ uuid_ingreso: UUID_INGRESO });
      [r1, r2] = await Promise.all([p1, p2]);
    });

    const salidaCalls = calls.filter((c) => c.path.endsWith('/salidas'));
    expect(salidaCalls).toHaveLength(2);
    expect(salidaCalls[0]!.key).toBe(salidaCalls[1]!.key);
    expect(r1!.uuid).toBe(r2!.uuid);
  });

  it('double click on postIngreso sends the SAME key twice', async () => {
    const payload = {
      placa_presente: true as const,
      placa: 'QAI002',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    };
    const [a, b] = await Promise.all([postIngreso(payload), postIngreso(payload)]);
    const ingresoCalls = calls.filter((c) => c.path.endsWith('/ingresos'));
    expect(ingresoCalls[0]!.key).toBe(ingresoCalls[1]!.key);
    expect(a.uuid).toBe(b.uuid);
  });
});
