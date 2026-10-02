/**
 * `<ClientesList />` — HU-F20.1 cross-branch client directory.
 *
 * SWR-backed via `useClientes()` -> `GET /api/v1/clientes/clientes?limit=200`.
 * A single page (200 rows) is an acceptable MVP given the list endpoint's
 * no-search-param constraint (see `clientesApi.ts`'s module docblock),
 * but clientes can outgrow 200 rows -- a "Cargar más" button fetches and
 * appends another page via `next_cursor`. KNOWN SCALING CAVEAT: this is
 * accumulate-everything-client-side pagination, not real server-side
 * search; a real fix would wire the already-defined but dead
 * `ClientesFilter` schema (`schemas/clientes.py`) into the generic list
 * endpoint (`router_factory.make_router`) -- out of scope here.
 *
 * Search is a free-text client-side filter over the accumulated array
 * (substring match on `numero_identificacion` OR `nombre`+`apellido`,
 * case-insensitive), debounced ~300ms. No existing debounce hook was
 * found anywhere in `apps/web_admin/src` (checked before writing this),
 * so a minimal local `setTimeout` debounce is used instead of adding a
 * new dependency.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { useClientes } from '../hooks/useClientes';
import type { Cliente } from '../api/clientesApi';

const DEBOUNCE_MS = 300;

function filterClientes(items: Cliente[], query: string): Cliente[] {
  const q = query.trim().toLowerCase();
  if (q === '') return items;
  return items.filter((c) => {
    const numero = (c.numero_identificacion ?? '').toLowerCase();
    const nombreCompleto = `${c.nombre ?? ''} ${c.apellido ?? ''}`.toLowerCase();
    return numero.includes(q) || nombreCompleto.includes(q);
  });
}

export default function ClientesList(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { clientes, isLoading, error, hasMore, isLoadingMore, loadMore } = useClientes();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [search]);

  const filtered = useMemo(
    () => filterClientes(clientes, debouncedSearch),
    [clientes, debouncedSearch],
  );

  return (
    <main
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-clientes"
    >
      <header>
        <h1 className="text-2xl font-semibold">{t('clientes.title', 'Clientes')}</h1>
        <p className="text-muted-foreground text-sm">
          {t('clientes.subtitle', 'Directorio de clientes de todas las sucursales.')}
        </p>
      </header>

      <Input
        type="search"
        placeholder={t('clientes.searchPlaceholder', 'Buscar por identificación o nombre...')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        data-testid="clientes-search"
        aria-label={t('clientes.searchLabel', 'Buscar clientes')}
      />

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="clientes-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('clientes.error', 'No se pudo cargar el listado. Reintentá.')}
        </p>
      )}

      {isLoading && (
        <p
          role="status"
          aria-live="polite"
          data-testid="clientes-loading"
          className="text-sm text-muted-foreground"
        >
          {t('common.loading', 'Cargando…')}
        </p>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <p role="status" data-testid="clientes-empty" className="text-sm text-muted-foreground">
          {t('clientes.empty', 'No hay clientes para mostrar.')}
        </p>
      )}

      {!isLoading && !error && filtered.length > 0 && (
        <Table data-testid="clientes-table">
          <TableCaption className="sr-only">
            {t('clientes.tableCaption', 'Listado de clientes')}
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">
                {t('clientes.columnas.identificacion', 'Identificación')}
              </TableHead>
              <TableHead scope="col">{t('clientes.columnas.nombre', 'Nombre')}</TableHead>
              <TableHead scope="col">{t('clientes.columnas.telefono', 'Teléfono')}</TableHead>
              <TableHead scope="col">{t('clientes.columnas.email', 'Email')}</TableHead>
              <TableHead scope="col">{t('clientes.columnas.estado', 'Estado')}</TableHead>
              <TableHead scope="col">
                <span className="sr-only">{t('common.acciones', 'Acciones')}</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((c) => (
              <TableRow key={c.uuid} data-testid={`clientes-row-${c.uuid}`}>
                <TableCell>
                  {c.tipo_identificador ?? '—'} {c.numero_identificacion ?? '—'}
                </TableCell>
                <TableCell>{`${c.nombre ?? ''} ${c.apellido ?? ''}`.trim() || '—'}</TableCell>
                <TableCell>{c.telefono ?? '—'}</TableCell>
                <TableCell>{c.email ?? '—'}</TableCell>
                <TableCell>
                  <Badge variant={c.estado === 'activo' ? 'success' : 'secondary'}>
                    {c.estado}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/clientes/${c.uuid}`)}
                    data-testid={`clientes-detalle-${c.uuid}`}
                  >
                    {t('clientes.detalle', 'Detalle')}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {hasMore && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            onClick={() => void loadMore()}
            disabled={isLoadingMore}
            data-testid="clientes-cargar-mas"
          >
            {isLoadingMore
              ? t('common.loading', 'Cargando…')
              : t('clientes.cargarMas', 'Cargar más')}
          </Button>
        </div>
      )}
    </main>
  );
}
