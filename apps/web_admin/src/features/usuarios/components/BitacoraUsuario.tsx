import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useLoginHistorico } from '../hooks/useLoginHistorico';

interface BitacoraUsuarioProps {
  uuidUsuario: string;
}

export function BitacoraUsuario({ uuidUsuario }: BitacoraUsuarioProps) {
  const { loginHistorico, isLoading } = useLoginHistorico(uuidUsuario);

  if (isLoading) {
    return <div>Cargando bitácora...</div>;
  }

  if (loginHistorico.length === 0) {
    return <p className="text-muted-foreground">No hay registros en la bitácora</p>;
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Historial de login</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Fecha</TableHead>
            <TableHead>Sucursal</TableHead>
            <TableHead>Resultado</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loginHistorico.map((login) => (
            <TableRow key={login.uuid}>
              <TableCell>
                {login.timestamp_evento
                  ? new Date(login.timestamp_evento).toLocaleString()
                  : 'N/A'}
              </TableCell>
              <TableCell className="font-mono text-xs">
                {login.uuid_sucursal ? login.uuid_sucursal.slice(0, 8) : 'N/A'}
              </TableCell>
              <TableCell>
                {login.estado === 'exitoso' ? (
                  <span className="text-green-600">Exitoso</span>
                ) : (
                  <span className="text-red-600">
                    {login.estado === 'fallido' ? 'Fallido' : login.estado}
                  </span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
