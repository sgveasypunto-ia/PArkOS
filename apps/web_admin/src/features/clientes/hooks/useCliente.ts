/**
 * `useCliente.ts` — SWR hook for `<ClienteDetalle />` + `<ClienteDatosTab />`
 * (HU-F20.1). Mirrors `features/empresa/hooks/useEmpresa.ts`'s shape:
 * `cliente`, `isLoading`, `error`, `refresh`, plus an `update` mutator
 * that revalidates the cache in place (no extra round-trip) after a
 * successful `PUT`.
 */
import useSWR from 'swr';

import { getCliente, updateCliente, type Cliente, type ClienteUpdateInput } from '../api/clientesApi';

export interface UseClienteReturn {
  cliente: Cliente | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Cliente | undefined>;
  update: (input: ClienteUpdateInput) => Promise<Cliente>;
}

export function useCliente(uuid: string | undefined): UseClienteReturn {
  const { data, error, isLoading, mutate } = useSWR<Cliente>(
    uuid ? `/api/v1/clientes/clientes/${uuid}` : null,
    () => getCliente(uuid as string),
    { revalidateOnFocus: false },
  );

  async function update(input: ClienteUpdateInput): Promise<Cliente> {
    const updated = await updateCliente(uuid as string, input);
    await mutate(updated, { revalidate: false });
    return updated;
  }

  return {
    cliente: data,
    isLoading,
    error,
    refresh: mutate,
    update,
  };
}
