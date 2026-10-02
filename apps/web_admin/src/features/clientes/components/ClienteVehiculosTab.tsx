/**
 * `<ClienteVehiculosTab />` — tab "Vehículos" de `ClienteDetalle`
 * (HU-F20.1). Read-only table: placa, estado.
 *
 * `vehiculos` has NO direct FK to `clientes` -- the only path from a
 * cliente to its vehicles is cliente -> subscripciones_cliente
 * (`uuid_cliente`) -> subscripcion_vehiculos (`uuid_subscripcion_cliente`)
 * -> vehiculos (`uuid_vehiculo`). Each hop is a client-side full-scan +
 * filter (`clientesApi.ts`'s `listSubscripcionesClienteByCliente` /
 * `listSubscripcionVehiculosByIds` / `listVehiculosByIds`, capped at 10
 * pages x 200 rows each) because the generic `make_router`-mounted list
 * endpoints have zero filter query params today (same root cause as the
 * search limitation in `ClientesList.tsx`). Flagged as a candidate for a
 * future backend improvement (wiring the already-defined but dead
 * `*Filter` schemas, `schemas/clientes.py`, into
 * `router_factory.make_router`) -- not fixed here (`router_factory.py`
 * is shared by many unrelated resources).
 *
 * `uuid_tipo_vehiculo` is rendered as its raw uuid: no reusable
 * tipo-vehiculo label/catalog hook was found with near-zero extra work,
 * so the column is omitted to keep this read minimal.
 */
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import {
  listSubscripcionesClienteByCliente,
  listSubscripcionVehiculosByIds,
  listVehiculosByIds,
  type Vehiculo,
} from '../api/clientesApi';

export interface ClienteVehiculosTabProps {
  uuidCliente: string;
}

export function ClienteVehiculosTab({ uuidCliente }: ClienteVehiculosTabProps): JSX.Element {
  const { t } = useTranslation();

  const { data, error, isLoading } = useSWR<Vehiculo[]>(
    `/clientes/${uuidCliente}/vehiculos`,
    async () => {
      const subscripciones = await listSubscripcionesClienteByCliente(uuidCliente);
      const subscripcionUuids = new Set(subscripciones.map((s) => s.uuid));
      const subVehiculos = await listSubscripcionVehiculosByIds(subscripcionUuids);
      const vehiculoUuids = new Set(
        subVehiculos
          .map((sv) => sv.uuid_vehiculo)
          .filter((uuid): uuid is string => uuid !== null),
      );
      return listVehiculosByIds(vehiculoUuids);
    },
    { revalidateOnFocus: false },
  );

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="cliente-vehiculos-loading"
        className="text-sm text-muted-foreground"
      >
        {t('common.loading', 'Cargando…')}
      </p>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="cliente-vehiculos-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {t('clienteVehiculos.error', 'No se pudieron cargar los vehículos.')}
      </p>
    );
  }

  const items = data ?? [];

  if (items.length === 0) {
    return (
      <p
        role="status"
        data-testid="cliente-vehiculos-empty"
        className="text-sm text-muted-foreground"
      >
        {t('clienteVehiculos.empty', 'Este cliente no tiene vehículos registrados.')}
      </p>
    );
  }

  return (
    <Table data-testid="cliente-vehiculos-table">
      <TableCaption className="sr-only">
        {t('clienteVehiculos.caption', 'Vehículos del cliente')}
      </TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">{t('clienteVehiculos.placa', 'Placa')}</TableHead>
          <TableHead scope="col">{t('clienteVehiculos.estado', 'Estado')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((v) => (
          <TableRow key={v.uuid} data-testid={`cliente-vehiculo-row-${v.uuid}`}>
            <TableCell>{v.placa ?? '—'}</TableCell>
            <TableCell>{v.estado}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
