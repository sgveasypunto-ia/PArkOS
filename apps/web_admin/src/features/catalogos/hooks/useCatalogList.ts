/**
 * useCatalogList — SWR por recurso de catálogo.
 *
 * Key estable basada en el resource. Mutate después de POST/PUT
 * invalida la cache y dispara refetch (mismo patrón que
 * `useTarifasList` y `useAdminUsuarios`).
 */
import useSWR from 'swr';

import {
  type CatalogResource,
  type CatalogRow,
  listCatalog,
} from '../api/catalogApi';

export const catalogKey = (resource: CatalogResource): string =>
  `/api/v1/catalogos/${resource}`;

export function useCatalogList(resource: CatalogResource) {
  const { data, error, isLoading, mutate } = useSWR<CatalogRow[]>(
    catalogKey(resource),
    () => listCatalog(resource),
    { revalidateOnFocus: false },
  );

  return {
    rows: data ?? [],
    error,
    isLoading,
    mutate,
  };
}
