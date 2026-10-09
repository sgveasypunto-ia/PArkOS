import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { useSWRConfig } from 'swr';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { useSucursales } from '@/features/sucursales/hooks/useSucursales';
import { useSucursalesUsuario } from '../hooks/useSucursalesUsuario';
import { asignarSucursal, desasignarSucursal } from '../api/usuariosApi';

interface SucursalesAsignadasProps {
  uuidUsuario: string;
}

export function SucursalesAsignadas({ uuidUsuario }: SucursalesAsignadasProps) {
  const { t } = useTranslation();
  const { sucursalesUsuario, isLoading: loadingAsignadas, mutate } = useSucursalesUsuario(uuidUsuario);
  const { sucursales, isLoading: loadingTodas } = useSucursales();
  const { mutate: globalMutate } = useSWRConfig();
  const [query, setQuery] = useState<string>('');

  const sucursalesDisponibles = sucursales.filter(
    (s) => !sucursalesUsuario.some((su) => su.uuid_sucursal === s.uuid),
  );

  const sucursalesDisponiblesFiltradas = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q === '') return sucursalesDisponibles;
    return sucursalesDisponibles.filter((s) => {
      const name = (s.nombre ?? '').toLowerCase();
      const prefix = (s.prefijo_nombre ?? '').toLowerCase();
      return name.includes(q) || prefix.includes(q) || s.uuid.includes(q);
    });
  }, [sucursalesDisponibles, query]);

  const handleAsignar = async (uuidSucursal: string) => {
    try {
      await asignarSucursal(uuidUsuario, uuidSucursal);
      await mutate();
      await globalMutate(`sucursales-usuario-${uuidUsuario}`);
    } catch (error) {
      alert(
        `Error al asignar sucursal: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };

  const handleDesasignar = async (uuidSucursal: string) => {
    if (!confirm('¿Estás seguro de desasignar esta sucursal?')) {
      return;
    }

    try {
      await desasignarSucursal(uuidUsuario, uuidSucursal);
      await mutate();
      await globalMutate(`sucursales-usuario-${uuidUsuario}`);
    } catch (error) {
      alert(
        `Error al desasignar sucursal: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };

  if (loadingAsignadas || loadingTodas) {
    return <div>Cargando sucursales...</div>;
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Sucursales asignadas</h2>

      {sucursalesUsuario.length === 0 ? (
        <p className="text-muted-foreground">No hay sucursales asignadas</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nombre</TableHead>
              <TableHead>Prefijo</TableHead>
              <TableHead>Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sucursalesUsuario.map((su) => {
              const sucursal = sucursales.find((s) => s.uuid === su.uuid_sucursal);
              return (
                <TableRow key={su.uuid}>
                  <TableCell>{sucursal?.nombre ?? 'N/A'}</TableCell>
                  <TableCell>{sucursal?.prefijo_nombre ?? 'N/A'}</TableCell>
                  <TableCell>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDesasignar(su.uuid_sucursal)}
                    >
                      Desasignar
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {sucursalesDisponibles.length > 0 && (
        <div className="mt-6">
          <h3 className="text-lg font-semibold mb-2">Sucursales disponibles</h3>
          <div className="relative mb-3">
            <Search
              className="text-muted-foreground pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t(
                'gestionUsuarios.sucursalesAsignadas.searchPlaceholder',
                'Buscar por nombre, prefijo o UUID…',
              )}
              aria-label={t(
                'gestionUsuarios.sucursalesAsignadas.searchPlaceholder',
                'Buscar por nombre, prefijo o UUID…',
              )}
              data-testid="sucursales-asignadas-search"
              autoComplete="off"
              className="pl-8"
            />
          </div>
          {sucursalesDisponiblesFiltradas.length === 0 ? (
            <p
              className="text-muted-foreground text-sm"
              data-testid="sucursales-asignadas-empty-filter"
            >
              {t(
                'gestionUsuarios.sucursalesAsignadas.emptyFilter',
                'Sin resultados para la búsqueda.',
              )}
            </p>
          ) : (
            <div className="space-y-2">
              {sucursalesDisponiblesFiltradas.map((sucursal) => (
                <div key={sucursal.uuid} className="flex items-center justify-between p-2 border rounded">
                  <span>
                    {sucursal.nombre} ({sucursal.prefijo_nombre})
                  </span>
                  <Button size="sm" onClick={() => handleAsignar(sucursal.uuid)}>
                    Asignar
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
