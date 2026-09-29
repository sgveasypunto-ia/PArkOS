import { useParams } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUsuario } from '../hooks/useUsuario';
import { UsuarioForm } from '../components/UsuarioForm';
import { PermisosTree } from '../components/PermisosTree';
import { SucursalesAsignadas } from '../components/SucursalesAsignadas';
import { BitacoraUsuario } from '../components/BitacoraUsuario';

export function UsuarioDetalle() {
  const { uuid } = useParams<{ uuid: string }>();
  const { usuario, isLoading, error } = useUsuario(uuid);

  if (isLoading) {
    return <div className="p-6">Cargando usuario...</div>;
  }

  if (error) {
    return (
      <div className="p-6 text-red-600">
        Error al cargar usuario: {error.message}
      </div>
    );
  }

  if (!usuario) {
    return <div className="p-6">Usuario no encontrado</div>;
  }

  return (
    <div className="container mx-auto p-6">
      <h1 className="mb-6 text-2xl font-bold">
        {usuario.nombre} {usuario.apellido}
      </h1>

      <Tabs defaultValue="datos">
        <TabsList>
          <TabsTrigger value="datos">Datos</TabsTrigger>
          <TabsTrigger value="permisos">Permisos</TabsTrigger>
          <TabsTrigger value="sucursales">Sucursales</TabsTrigger>
          <TabsTrigger value="bitacora">Bitácora</TabsTrigger>
        </TabsList>

        <TabsContent value="datos" className="mt-6">
          <UsuarioForm usuario={usuario} />
        </TabsContent>

        <TabsContent value="permisos" className="mt-6">
          <PermisosTree uuidUsuario={usuario.uuid} />
        </TabsContent>

        <TabsContent value="sucursales" className="mt-6">
          <SucursalesAsignadas uuidUsuario={usuario.uuid} />
        </TabsContent>

        <TabsContent value="bitacora" className="mt-6">
          <BitacoraUsuario uuidUsuario={usuario.uuid} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
