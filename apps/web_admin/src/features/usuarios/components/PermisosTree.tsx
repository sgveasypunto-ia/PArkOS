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
  const {
    permisos,
    isLoading: loadingPermisos,
    error: errorPermisos,
  } = usePermisos();
  const {
    permisosUsuario,
    isLoading: loadingPermisosUsuario,
    error: errorPermisosUsuario,
    mutate,
  } = usePermisosUsuario(uuidUsuario);
  const { mutate: globalMutate } = useSWRConfig();

  // `codigo` is `str | None` on the wire (``prod.permisos.permiso`` is
  // a nullable column), so a catalog row with a NULL code must not
  // reach `split()` -- it would throw and take down the whole tab.
  const treeItems = useMemo(() => {
    const codigos = permisos
      .map((p) => p.codigo)
      .filter((codigo): codigo is string => codigo !== null);
    return agruparPermisosPorPrefijo(codigos);
  }, [permisos]);

  const selectedLeafIds = useMemo(() => {
    return permisosUsuario
      .filter((pu) => pu.vigente_hasta === null)
      .map((pu) => pu.codigo)
      .filter((codigo): codigo is string => codigo !== null);
  }, [permisosUsuario]);

  /**
   * `Tree` renders each checkbox as `selectedIds.includes(item.id)`, so a
   * group id must be present in that array for the group box to render as
   * checked. A group is checked only when every child it owns is held --
   * partial ownership renders unchecked rather than falsely claiming the
   * whole group. These synthetic ids are stripped again by
   * `resolveToLeafCodes` before any request is issued, so they never
   * reach `asignarPermiso`.
   */
  const selectedIds = useMemo(() => {
    const selected = new Set(selectedLeafIds);
    const ids = [...selectedLeafIds];
    for (const group of treeItems) {
      const children = group.children ?? [];
      if (children.length > 0 && children.every((c) => selected.has(c.id))) {
        ids.push(group.id);
      }
    }
    return ids;
  }, [selectedLeafIds, treeItems]);

  /**
   * The tree mixes two id spaces: synthetic group ids (``ADMIN``, from
   * `agruparPermisosPorPrefijo`) and real permission codes
   * (``ADMIN_USUARIOS_CREAR``). ``Tree`` toggles exactly the id it was
   * clicked -- it has no notion of a parent selecting its children.
   * Without this expansion, clicking a group produced a synthetic id
   * that `permisos.find()` never matched, so the request was silently
   * dropped and the checkbox snapped back on refetch.
   */
  const resolveToLeafCodes = (ids: string[]): Set<string> => {
    const leaves = new Set<string>();
    for (const id of ids) {
      const node = treeItems.find((item) => item.id === id);
      if (node?.children) {
        node.children.forEach((child) => leaves.add(child.id));
      } else {
        leaves.add(id);
      }
    }
    return leaves;
  };

  const handleSelectionChange = async (newSelectedIds: string[]) => {
    const next = new Set<string>();
    const groupIdSet = new Set(treeItems.map((item) => item.id));

    for (const id of newSelectedIds) {
      if (groupIdSet.has(id)) {
        const group = treeItems.find((item) => item.id === id);
        group?.children?.forEach((child) => next.add(child.id));
      } else {
        next.add(id);
      }
    }

    // Unchecking a group has to actively drop its children. `Tree`
    // removes only the clicked id, so the children would otherwise still
    // be present in `newSelectedIds` and the revoke would never fire --
    // the mirror image of the original add-side bug.
    for (const groupId of groupIdSet) {
      if (selectedIds.includes(groupId) && !newSelectedIds.includes(groupId)) {
        const group = treeItems.find((item) => item.id === groupId);
        group?.children?.forEach((child) => next.delete(child.id));
      }
    }

    const current = resolveToLeafCodes(selectedIds);
    const added = [...next].filter((codigo) => !current.has(codigo));
    const removed = [...current].filter((codigo) => !next.has(codigo));

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
      alert(
        `Error al actualizar permisos: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };

  if (loadingPermisos || loadingPermisosUsuario) {
    return <div>Cargando permisos...</div>;
  }

  // A failed fetch must not read as "the user has no permissions" --
  // that silent failure is what made this tab untriageable.
  const loadError = errorPermisos ?? errorPermisosUsuario;
  if (loadError) {
    return (
      <div className="text-red-600">
        No se pudieron cargar los permisos:{' '}
        {loadError instanceof Error ? loadError.message : String(loadError)}
      </div>
    );
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