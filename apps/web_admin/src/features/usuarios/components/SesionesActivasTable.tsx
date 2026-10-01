import { useTranslation } from 'react-i18next';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';

import { useSesionesActivas } from '../hooks/useLoginHistorico';
import type { Sesion } from '../api/usuariosSchema';

interface SesionesActivasTableProps {
  uuidUsuario: string;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function SesionesActivasTable({ uuidUsuario }: SesionesActivasTableProps) {
  const { t } = useTranslation();
  const { sesiones, isLoading, error, mutate } = useSesionesActivas(uuidUsuario);

  const handleCerrar = async (uuidSesion: string): Promise<void> => {
    if (!window.confirm(t('usuarios.sesiones.cerrarConfirm', '¿Cerrar esta sesión?'))) {
      return;
    }
    try {
      const { cerrarSesion } = await import('../api/usuariosApi');
      await cerrarSesion(uuidUsuario, uuidSesion);
      window.alert(t('usuarios.sesiones.cerrarSuccess', 'Sesión cerrada'));
      await mutate();
    } catch (err) {
      window.alert(
        `${t('usuarios.sesiones.cerrarError', 'Error al cerrar sesión')}: ${
          err instanceof Error ? err.message : String(err)
        }`,
      );
    }
  };

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="text-sm text-muted-foreground"
        data-testid="sesiones-loading"
      >
        {t('usuarios.sesiones.loading', 'Cargando sesiones...')}
      </div>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        data-testid="sesiones-error"
      >
        {error.message}
      </p>
    );
  }

  if (sesiones.length === 0) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="sesiones-empty"
      >
        {t('usuarios.sesiones.empty', 'No hay sesiones activas')}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3" data-testid="sesiones-activas-table">
      <h2 className="text-xl font-semibold">
        {t('usuarios.sesiones.title', 'Sesiones activas')}
      </h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('usuarios.sesiones.uuid', 'UUID')}</TableHead>
            <TableHead>{t('usuarios.sesiones.creadoEn', 'Creada en')}</TableHead>
            <TableHead>{t('usuarios.sesiones.estado', 'Estado')}</TableHead>
            <TableHead>{t('usuarios.sesiones.cerrar', 'Cerrar')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sesiones.map((s: Sesion) => (
            <TableRow key={s.uuid}>
              <TableCell className="font-mono text-xs">{s.uuid}</TableCell>
              <TableCell className="tabular-nums">{formatDateTime(s.creado_en)}</TableCell>
              <TableCell>{s.estado}</TableCell>
              <TableCell>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void handleCerrar(s.uuid)}
                  data-testid={`sesiones-cerrar-${s.uuid}`}
                >
                  {t('usuarios.sesiones.cerrar', 'Cerrar')}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}