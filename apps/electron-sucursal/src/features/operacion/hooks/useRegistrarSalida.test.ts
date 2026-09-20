/**
 * Tests for `useRegistrarSalida` SWR mutation hook (HU-F7.2,
 * REQ-OPS-154 + REQ-OPS-156).
 *
 * Coverage:
 *   R1: rotación → 201 with `tipo_salida='ROTACION'`,
 *       `estado='PENDIENTE_PAGO'` (canonical F1.7 wire shape).
 *   R2: mensualidad → 201 with `tipo_salida='MENSUALIDAD'`,
 *       `estado='MENSUALIDAD_PAGO'`-equivalent payload (F1.7 omits
 *       the `estado` field on the read; we assert the `cotizacion_snapshot`
 *       is null for MENSUALIDAD per the F1.7 contract).
 *   R3: doble clic — same `Idempotency-Key` header sent on both
 *       calls; server-side cache dedup (F1.6 IdempotencyKeyMiddleware)
 *       returns the cached 201 on the second call. We assert the
 *       hook forwards the SAME `Idempotency-Key` header on both
 *       calls (proxy for "the server will dedup").
 *   R4: 401 → hook MUST call `useAuthStore.getState().clear()` AND
 *       dispatch the `parkos:auth:cleared` event (REQ-OPS-107..110
 *       invariant preserved from F3.1; mirrored in `useCotizacion.ts`).
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

const mockFetch = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
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

import { useRegistrarSalida, SalidaDuplicadaError } from './useRegistrarSalida';
import { useAuthStore } from '@parkos/ui-kit/store';

const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';
const UUID_SALIDA = '00000000-0000-0000-0000-000000000002';

const rotacionResponse = {
  uuid: UUID_SALIDA,
  uuid_sucursal: '00000000-0000-0000-0000-0000000000a2',
  uuid_ingreso: UUID_INGRESO,
  fecha_salida: '2026-09-19T11:00:00Z',
  created_at: '2026-09-19T11:00:00Z',
  created_by: '00000000-0000-0000-0000-0000000000a4',
  sync_status: 'pending',
  sync_timestamp: null,
  sync_attempts: 0,
  tipo_salida: 'ROTACION',
  forzado_en_creacion: false,
  motivo_forzado: null,
  cotizacion_snapshot: {
    cobrar: true,
    subtotal: 41000,
    iva: 7790,
    total: 48790,
    tiempo_minutos: 32.5,
    tarifa_uuid: '00000000-0000-0000-0000-0000000000a5',
    vigente_hasta: '2026-09-19T11:15:00Z',
  },
};

const mensualidadResponse = {
  ...rotacionResponse,
  uuid: '00000000-0000-0000-0000-0000000000b1',
  tipo_salida: 'MENSUALIDAD',
  cotizacion_snapshot: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useRegistrarSalida — REQ-OPS-154 rotación | mensualidad', () => {
  it('R1: rotación POST 201 → SalidaReadForzado con tipo_salida=ROTACION', async () => {
    mockFetch.mockResolvedValueOnce(rotacionResponse);

    const { result } = renderHook(() => useRegistrarSalida());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({ uuid_ingreso: UUID_INGRESO });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/operacion/salidas');
    expect(mockFetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ uuid_ingreso: UUID_INGRESO }),
    });
    expect((data as { tipo_salida: string }).tipo_salida).toBe('ROTACION');
    expect((data as { uuid: string }).uuid).toBe(UUID_SALIDA);
    expect(result.current.isMutating).toBe(false);
  });

  it('R2: mensualidad POST 201 → tipo_salida=MENSUALIDAD con cotizacion_snapshot=null', async () => {
    mockFetch.mockResolvedValueOnce(mensualidadResponse);

    const { result } = renderHook(() => useRegistrarSalida());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({ uuid_ingreso: UUID_INGRESO });
    });

    expect((data as { tipo_salida: string }).tipo_salida).toBe('MENSUALIDAD');
    expect((data as { cotizacion_snapshot: unknown }).cotizacion_snapshot).toBeNull();
  });

  it('R3: doble clic → mismo Idempotency-Key header en ambas llamadas (server dedup)', async () => {
    // Both calls succeed with the same response (server-side cache hit).
    mockFetch.mockResolvedValue(rotacionResponse);

    const { result } = renderHook(() => useRegistrarSalida());

    await act(async () => {
      await result.current.trigger({ uuid_ingreso: UUID_INGRESO });
    });
    await act(async () => {
      await result.current.trigger({ uuid_ingreso: UUID_INGRESO });
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const headers1 = (mockFetch.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers;
    const headers2 = (mockFetch.mock.calls[1]?.[1] as { headers: Record<string, string> }).headers;
    expect(headers1['Idempotency-Key']).toMatch(/^[a-f0-9]{64}$/);
    expect(headers1['Idempotency-Key']).toBe(headers2['Idempotency-Key']);
  });

  it('R4: 401 → useAuthStore.clear() + parkos:auth:cleared event (REQ-OPS-107..110)', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/operacion/salidas'),
    );

    const { result } = renderHook(() => useRegistrarSalida());

    await act(async () => {
      await result.current.trigger({ uuid_ingreso: UUID_INGRESO }).catch(() => undefined);
    });

    // Defensive logout invariant: clear + dispatched event.
    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });

  it('R5: 409 salida_duplicada → SalidaDuplicadaError con uuid_ingreso (REQ-OPS-156)', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    // Backend 409 body shape per F1.7 Pydantic `SalidaDuplicadaError`:
    // {error: "salida_duplicada", uuid_ingreso: "..."}.
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        409,
        JSON.stringify({ error: 'salida_duplicada', uuid_ingreso: UUID_INGRESO }),
        '/api/v1/operacion/salidas',
      ),
    );

    const { result } = renderHook(() => useRegistrarSalida());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger({ uuid_ingreso: UUID_INGRESO });
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(SalidaDuplicadaError);
    expect((caught as { uuid_ingreso: string }).uuid_ingreso).toBe(UUID_INGRESO);
    expect((caught as { status: number }).status).toBe(409);
  });
});