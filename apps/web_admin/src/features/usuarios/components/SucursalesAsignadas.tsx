import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useSucursalesUsuario } from '../hooks/useSucursalesUsuario';
import { asignarSucursal, desasignarSucursal } from '../api/usuariosApi';
import { useSucursales } from '@/features/sucursales/hooks/useSucursales';
import { useSWRConfig } from 'swr';

interface SucursalesAsignadasProps {
  uuidUsuario: string;
}

export function SucursalesAsignadas({ uuidUsuario }: SucursalesAsignadasProps) {
  const { sucursalesUsuario, isLoading: loadingAsignadas, mutate } = useSucursalesUsuario(uuidUsuario);
  const { sucursales, isLoading: loadingTodas } = useSucursales();
  const { mutate: globalMutate } = useSWRConfig();

  const sucursalesDisponibles = sucursales.filter(
    (s) => !sucursalesUsuario.some((su) => su.uuid_sucursal === s.uuid),
  );

  const handleAsignar = async (uuidSucursal: string) => {
    try {
      await asignarSucursal(uuidUsuario, uuidSucursal);
      await mutate();
      await globalMutate(`sucursales-usuario-${uuidUsuario}`);
    } catch (error) {
      alert('Error al asignar sucursal');
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
      alert('Error al desasignar sucursal');
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
          <div className="space-y-2">
            {sucursalesDisponibles.map((sucursal) => (
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
        </div>
      )}
    </div>
  );
}
