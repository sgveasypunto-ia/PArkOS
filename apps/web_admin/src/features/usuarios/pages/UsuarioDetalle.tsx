import { useParams } from 'react-router-dom';
import { PageHeader } from '@/components/layout/PageHeader';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUsuario } from '../hooks/useUsuario';
import { UsuarioForm } from '../components/UsuarioForm';
import { PermisosTree } from '../components/PermisosTree';
import { SucursalesAsignadas } from '../components/SucursalesAsignadas';
import { BitacoraUsuario } from '../components/BitacoraUsuario';
import { SesionesActivasTable } from '../components/SesionesActivasTable';

export function UsuarioDetalle() {
  const { uuid } = useParams<{ uuid: string }>();
  const { usuario, isLoading, error } = useUsuario(uuid);

  if (isLoading) {
    return (
      <main
        className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
        data-testid="usuario-detalle-page"
      >
        <PageHeader title="Usuario" />
        <p className="text-sm text-muted-foreground">Cargando usuario...</p>
      </main>
    );
  }

  if (error) {
    return (
      <main
        className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
        data-testid="usuario-detalle-page"
      >
        <PageHeader title="Usuario" />
        <p role="alert" className="text-sm text-destructive">
          Error al cargar usuario: {error.message}
        </p>
      </main>
    );
  }

  if (!usuario) {
    return (
      <main
        className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
        data-testid="usuario-detalle-page"
      >
        <PageHeader title="Usuario" />
        <p className="text-sm text-muted-foreground">Usuario no encontrado</p>
      </main>
    );
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="usuario-detalle-page"
    >
      <PageHeader
        title={`${usuario.nombre ?? ''} ${usuario.apellido ?? ''}`.trim() || usuario.uuid}
        subtitle={
          <span className="font-mono text-xs">{usuario.uuid}</span>
        }
      />

      <Tabs defaultValue="datos">
        <TabsList>
          <TabsTrigger value="datos">Datos</TabsTrigger>
          <TabsTrigger value="permisos">Permisos</TabsTrigger>
          <TabsTrigger value="sucursales">Sucursales</TabsTrigger>
          <TabsTrigger value="bitacora">Bitácora</TabsTrigger>
          <TabsTrigger value="sesiones">Sesiones</TabsTrigger>
        </TabsList>

        <TabsContent value="datos" className="mt-4">
          <UsuarioForm usuario={usuario} />
        </TabsContent>

        <TabsContent value="permisos" className="mt-4">
          <PermisosTree uuidUsuario={usuario.uuid} />
        </TabsContent>

        <TabsContent value="sucursales" className="mt-4">
          <SucursalesAsignadas uuidUsuario={usuario.uuid} />
        </TabsContent>

        <TabsContent value="bitacora" className="mt-4">
          <BitacoraUsuario uuidUsuario={usuario.uuid} />
        </TabsContent>

        <TabsContent value="sesiones" className="mt-4">
          <SesionesActivasTable uuidUsuario={usuario.uuid} />
        </TabsContent>
      </Tabs>
    </main>
  );
}
