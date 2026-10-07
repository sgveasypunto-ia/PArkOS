/**
 * `<ResolucionesDIAN />` — "Resoluciones" tab of `SucursalDetalle.tsx`
 * (HU-F15.3 T2/T4). Lists this branch's `resolucion_facturacion` rows
 * (client-side filtered by `uuid_sucursal` via `useResolucionesSucursal`),
 * lets the operator create a new one via `<ResolucionFormHarness />`, and
 * renders a per-row "agotandose" (BR2) banner for every vigente resolución
 * whose `consecutivo-actual` projection reports `agotandose: true`.
 *
 * Numbering (`prefijo` + `rango_desde`/`rango_hasta`) is entered here: the
 * create form asks for it, and every vigente row has an "Editar numeración"
 * action (bi-temporal PUT) so a resolución registered without numbering can
 * be completed. Without numbering the branch cannot emit electronic invoices
 * (`resolucion_sin_prefijo`), so rows missing it show a warning.
 *
 * `uuidSucursal` comes from the ROUTE (`SucursalDetalle`'s `:uuid` param),
 * NOT the topbar's active branch — same prop pattern as
 * `<SucursalBitacoraTab uuidSucursal>` right below it in
 * `SucursalDetalle.tsx`. This matters more here than for Bitácora: the
 * `GET /empresa/resolucion-facturacion` list has no server-side
 * `uuid_sucursal` filter (REQ-X3 dedicated router), so this component (via
 * its hook) is the ONLY place filtering by the correct branch happens —
 * reading the topbar's active branch instead of the route's would silently
 * show the wrong branch's resoluciones.
 *
 * Consecutivo-actual fetch strategy: one batched `Promise.all` over the
 * vigente rows, re-run whenever `resoluciones` changes (not a per-row SWR
 * hook). Chosen over per-row SWR because a branch realistically carries at
 * most a handful of open resoluciones at a time, so N individual SWR keys
 * (with their own cache entries, revalidation timers, etc.) is needless
 * bookkeeping for data this cheap and read-only; a single effect keyed off
 * the already-fetched list is simpler to reason about, at the cost of
 * re-fetching every row's consecutivo on each list revalidation (a 404 or
 * read-only polling tradeoff that's acceptable for an informational
 * banner).
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';

import { getConsecutivoActual } from '../api/resolucionFacturacionApi';
import type {
  ResolucionFacturacion,
  ResolucionFacturacionConsecutivoActual,
} from '../api/resolucionFacturacionSchema';
import { useResolucionesSucursal } from '../hooks/useResolucionesSucursal';
import { ResolucionFormHarness } from './ResolucionForm';

export interface ResolucionesDIANProps {
  uuidSucursal: string;
}

function AgotandoseBanner(): JSX.Element {
  const { t } = useTranslation();
  return (
    <p
      role="status"
      data-testid="resolucion-agotandose-banner"
      className="mt-2 flex items-center gap-2 rounded-md bg-warning px-3 py-2 text-xs text-warning-foreground"
    >
      <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
      {t(
        'resoluciones.agotandose',
        'Rango por agotarse: quedan menos de 100 números disponibles.',
      )}
    </p>
  );
}

function tieneNumeracion(r: ResolucionFacturacion): boolean {
  return Boolean(r.prefijo) && r.rango_desde !== null && r.rango_hasta !== null;
}

function SinNumeracionAviso(): JSX.Element {
  const { t } = useTranslation();
  return (
    <p
      role="status"
      data-testid="resolucion-sin-numeracion"
      className="mt-2 flex items-center gap-2 rounded-md bg-warning px-3 py-2 text-xs text-warning-foreground"
    >
      <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
      {t(
        'resoluciones.sinNumeracion',
        'Falta el prefijo y el rango: sin ellos esta sucursal no puede emitir factura electrónica.',
      )}
    </p>
  );
}

export function ResolucionesDIAN({ uuidSucursal }: ResolucionesDIANProps): JSX.Element {
  const { t } = useTranslation();
  const { resoluciones, isLoading, error, refresh } = useResolucionesSucursal(uuidSucursal);
  const [mostrandoForm, setMostrandoForm] = useState(false);
  const [editando, setEditando] = useState<ResolucionFacturacion | null>(null);
  const [consecutivos, setConsecutivos] = useState<
    Record<string, ResolucionFacturacionConsecutivoActual | null>
  >({});

  useEffect(() => {
    let cancelado = false;
    const vigentes = resoluciones.filter((r) => r.estado === 'activo');
    if (vigentes.length === 0) {
      setConsecutivos({});
      return;
    }
    Promise.all(
      vigentes.map(async (r) => [r.uuid, await getConsecutivoActual(r.uuid)] as const),
    )
      .then((pares) => {
        if (!cancelado) setConsecutivos(Object.fromEntries(pares));
      })
      .catch(() => {
        // Informational-only data — a batch failure just means no banners
        // render this pass, never a hard error for the whole tab.
        if (!cancelado) setConsecutivos({});
      });
    return () => {
      cancelado = true;
    };
  }, [resoluciones]);

  async function handleCreated(): Promise<void> {
    setMostrandoForm(false);
    setEditando(null);
    await refresh();
  }

  function cerrarForm(): void {
    setMostrandoForm(false);
    setEditando(null);
  }

  const formAbierto = mostrandoForm || editando !== null;

  return (
    <section
      aria-label={t('resoluciones.title', 'Resoluciones DIAN')}
      className="space-y-4"
      data-testid="resoluciones-dian-root"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">
            {t('resoluciones.title', 'Resoluciones DIAN')}
          </h3>
          <p className="text-muted-foreground text-xs">
            {t(
              'resoluciones.subtitle',
              'Resoluciones de numeración de facturación electrónica de esta sucursal.',
            )}
          </p>
        </div>
        {!formAbierto && (
          <Button onClick={() => setMostrandoForm(true)} data-testid="resolucion-new">
            {t('resoluciones.new', 'Nueva resolución')}
          </Button>
        )}
      </header>

      {formAbierto && (
        <div
          className="rounded-lg border bg-card p-4"
          data-testid="resolucion-form-container"
        >
          {editando && (
            <h4 className="mb-3 text-sm font-semibold" data-testid="resolucion-form-title">
              {t('resoluciones.editTitle', 'Editar numeración de la resolución')}{' '}
              {editando.numero_resolucion ?? ''}
            </h4>
          )}
          <ResolucionFormHarness
            key={editando?.uuid ?? 'nueva'}
            uuidSucursal={uuidSucursal}
            resolucion={editando ?? undefined}
            onCreated={handleCreated}
            onCancel={cerrarForm}
          />
        </div>
      )}

      {isLoading && (
        <p
          role="status"
          className="text-muted-foreground text-sm"
          data-testid="resolucion-loading"
        >
          {t('common.loading', 'Cargando…')}
        </p>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          data-testid="resolucion-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('resoluciones.loadError', 'No se pudieron cargar las resoluciones.')}
        </div>
      )}

      {!isLoading && !error && resoluciones.length === 0 && (
        <div
          role="status"
          data-testid="resolucion-empty"
          className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          {t(
            'resoluciones.empty',
            'Sin resoluciones registradas para esta sucursal.',
          )}
        </div>
      )}

      {!isLoading && !error && resoluciones.length > 0 && (
        <ul
          className="space-y-3"
          data-testid="resolucion-list"
          aria-label={t('resoluciones.listLabel', 'Resoluciones')}
        >
          {resoluciones.map((r) => (
            <li
              key={r.uuid}
              data-testid={`resolucion-row-${r.uuid}`}
              className="rounded-lg border bg-card px-4 py-3 text-sm"
            >
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div>
                  <p className="text-muted-foreground text-xs">
                    {t('resoluciones.field.numero', 'Número')}
                  </p>
                  <p data-testid="resolucion-numero">{r.numero_resolucion ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">
                    {t('resoluciones.field.prefijo', 'Prefijo')}
                  </p>
                  <p data-testid="resolucion-prefijo">{r.prefijo ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">
                    {t('resoluciones.field.rango', 'Rango')}
                  </p>
                  <p data-testid="resolucion-rango">
                    {r.rango_desde === null && r.rango_hasta === null
                      ? '—'
                      : `${r.rango_desde ?? '—'}–${r.rango_hasta ?? '—'}`}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">
                    {t('resoluciones.field.inicioVigencia', 'Vigente desde')}
                  </p>
                  <p data-testid="resolucion-fecha-inicio">
                    {r.fecha_inicio_vigencia ?? '—'}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">
                    {t('resoluciones.field.finVigencia', 'Vigente hasta')}
                  </p>
                  <p data-testid="resolucion-fecha-fin">{r.fecha_fin_vigencia ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">
                    {t('resoluciones.field.estado', 'Estado')}
                  </p>
                  <p data-testid="resolucion-estado">{r.estado}</p>
                </div>
              </div>
              {consecutivos[r.uuid]?.agotandose && <AgotandoseBanner />}
              {r.estado === 'activo' && !tieneNumeracion(r) && <SinNumeracionAviso />}
              {r.estado === 'activo' && (
                <div className="mt-3 flex justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={formAbierto}
                    onClick={() => setEditando(r)}
                    data-testid={`resolucion-edit-${r.uuid}`}
                    aria-label={t(
                      'resoluciones.editAria',
                      'Editar numeración de la resolución {{numero}}',
                      { numero: r.numero_resolucion ?? '' },
                    )}
                  >
                    {t('resoluciones.edit', 'Editar numeración')}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
