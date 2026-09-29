import { useMemo } from 'react';
import { Tree, type TreeItem } from '@/components/ui/tree';
import { usePermisos, usePermisosUsuario } from '../hooks/usePermisos';
import { asignarPermiso, revocarPermiso } from '../api/usuariosApi';
import { useSWRConfig } from 'swr';

interface PermisosTreeProps {
  uuidUsuario: string;
}

function agruparPermisosPorPrefijo(codigos: string[]): TreeItem[] {
  const grupos: Record<string, string[]> = {};

  codigos.forEach((codigo) => {
    const prefijo = codigo.split('_')[0] ?? 'otros';
    if (!grupos[prefijo]) {
      grupos[prefijo] = [];
    }
    grupos[prefijo].push(codigo);
  });

  return Object.entries(grupos).map(([prefijo, codigos]) => ({
    id: prefijo,
    label: prefijo.toUpperCase(),
    children: codigos.map((codigo) => ({
      id: codigo,
      label: codigo,
    })),
  }));
}

export function PermisosTree({ uuidUsuario }: PermisosTreeProps) {
  const { permisos, isLoading: loadingPermisos } = usePermisos();
  const { permisosUsuario, isLoading: loadingPermisosUsuario, mutate } = usePermisosUsuario(uuidUsuario);
  const { mutate: globalMutate } = useSWRConfig();

  const treeItems = useMemo(() => {
    const codigos = permisos.map((p) => p.codigo);
    return agruparPermisosPorPrefijo(codigos);
  }, [permisos]);

  const selectedIds = useMemo(() => {
    return permisosUsuario
      .filter((pu) => pu.vigente_hasta === null)
      .map((pu) => pu.codigo);
  }, [permisosUsuario]);

  const handleSelectionChange = async (newSelectedIds: string[]) => {
    const added = newSelectedIds.filter((id) => !selectedIds.includes(id));
    const removed = selectedIds.filter((id) => !newSelectedIds.includes(id));

    try {
      for (const codigo of added) {
        const permiso = permisos.find((p) => p.codigo === codigo);
        if (permiso) {
          await asignarPermiso(uuidUsuario, permiso.uuid);
        }
      }

      for (const codigo of removed) {
        const permiso = permisos.find((p) => p.codigo === codigo);
        if (permiso) {
          await revocarPermiso(uuidUsuario, permiso.uuid);
        }
      }

      await mutate();
      await globalMutate(`permisos-usuario-${uuidUsuario}`);
    } catch (error) {
      alert('Error al actualizar permisos');
    }
  };

  if (loadingPermisos || loadingPermisosUsuario) {
    return <div>Cargando permisos...</div>;
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Permisos del usuario</h2>
      <Tree
        items={treeItems}
        selectedIds={selectedIds}
        onSelectionChange={handleSelectionChange}
      />
    </div>
  );
}
