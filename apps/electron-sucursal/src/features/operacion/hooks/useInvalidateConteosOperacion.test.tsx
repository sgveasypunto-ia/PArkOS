/**
 * H6 regression — after ANY salida (rotacion or mensualidad) the per-plate
 * lookup used by `useIngresoActivo` (`/api/v1/operacion/ingresos?placa=X`,
 * no sucursal in the key) must be revalidated; otherwise a re-ingreso of the
 * same plate keeps seeing the pre-salida row ("sigue adentro").
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import useSWR, { SWRConfig } from 'swr';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { useInvalidateConteosOperacion } from './useInvalidateConteosOperacion';

const SUC = '11111111-1111-4111-8111-111111111111';
const SES = '22222222-2222-4222-8222-222222222222';

const wrapper = ({ children }: { children: ReactNode }) => (
  <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
    {children}
  </SWRConfig>
);

function mountWithKey(key: string, counter: { n: number }) {
  return renderHook(
    () => {
      useSWR(key, () => {
        counter.n += 1;
        return Promise.resolve([]);
      });
      return useInvalidateConteosOperacion();
    },
    { wrapper },
  );
}

describe('useInvalidateConteosOperacion', () => {
  it('revalidates the per-placa ingresos key (no sucursal in the key)', async () => {
    const counter = { n: 0 };
    const { result } = mountWithKey('/api/v1/operacion/ingresos?placa=ABC123', counter);
    await waitFor(() => expect(counter.n).toBe(1));

    await act(async () => {
      await result.current({ uuid_sucursal: SUC, uuid_sesion: SES });
    });

    await waitFor(() => expect(counter.n).toBe(2));
  });

  it('revalidates the per-sucursal ingresos list key', async () => {
    const counter = { n: 0 };
    const { result } = mountWithKey(`/api/v1/operacion/ingresos?uuid_sucursal=${SUC}`, counter);
    await waitFor(() => expect(counter.n).toBe(1));

    await act(async () => {
      await result.current({ uuid_sucursal: SUC, uuid_sesion: SES });
    });

    await waitFor(() => expect(counter.n).toBeGreaterThan(1));
  });

  it('leaves unrelated keys alone', async () => {
    const counter = { n: 0 };
    const { result } = mountWithKey('/api/v1/otra/cosa?placa=ABC123', counter);
    await waitFor(() => expect(counter.n).toBe(1));

    await act(async () => {
      await result.current({ uuid_sucursal: SUC, uuid_sesion: SES });
    });

    expect(counter.n).toBe(1);
  });
});
