/**
 * `<FacturaDetalle />` — drill-down page (REQ-X-01..11 of
 * `facturacion-admin/spec.md`).
 *
 * Route: `/facturacion/:uuid` (mounted in `App.tsx` by X.1b).
 *
 * Composition of 6 SWR fetches via `useFacturaDetalle(uuid)`. Each
 * section is a subcomponent that owns its own loading/error (REQ-X-11):
 * the page is NOT fatal-global — a 5xx on one section renders the
 * alert inline and the rest stays visible.
 *
 * The page is 404-tolerant for the header fetch: a missing uuid
 * (cross-tenant, deleted, fake) shows "Factura no encontrada" + back
 * link, not a stack trace.
 *
 * Container-presentational split (mirrors `ReporteriaFinanciera.tsx` +
 * `FacturasTable.tsx`): this file owns SWR + composition; the
 * subcomponents are presentational only.
 */
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';

import { findHashForFactura } from '../api/facturacionAdminApi';
import { useFacturaDetalle } from '../hooks/useFacturaDetalle';
import { deriveEstadoFactura } from '../lib/estadoFactura';

import { FacturaAccionesMenu } from '../components/FacturaAccionesMenu';
import { FacturaClienteCard } from '../components/FacturaClienteCard';
import { FacturaElectronicaCard } from '../components/FacturaElectronicaCard';
import { FacturaHeaderCard } from '../components/FacturaHeaderCard';
import { FacturaImpuestosTable } from '../components/FacturaImpuestosTable';
import { FacturaItemsTable } from '../components/FacturaItemsTable';
import { FacturaPagosTable } from '../components/FacturaPagosTable';

/**
 * `<FacturaNoEncontrada />` — 404 state.
 * Renders a back link to `/reporteria/financiera` (the entry point
 * the admin uses to find facturas). Uses `<Link>` so the back nav
 * preserves client-side routing state.
 */
function FacturaNoEncontrada(): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="factura-not-found"
      className="mx-auto max-w-2xl space-y-4 p-4"
    >
      <h1 className="text-2xl font-semibold">
        {t('header.notFound', 'Factura no encontrada')}
      </h1>
      <Button asChild variant="outline" data-testid="factura-not-found-back">
        <Link to="/reporteria/financiera">
          <ChevronLeft className="mr-2 h-4 w-4" aria-hidden />
          {t('header.notFoundBackLink', 'Volver a reportería financiera')}
        </Link>
      </Button>
    </div>
  );
}

/**
 * `<FacturaDetalleSkeleton />` — initial load state (header not yet
 * loaded). A single skeleton block; subcomponents render their own
 * inline loaders as data arrives.
 */
function FacturaDetalleSkeleton(): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="factura-detalle-skeleton"
      className="mx-auto max-w-4xl space-y-6 p-4"
    >
      <div className="h-8 w-1/3 animate-pulse rounded bg-muted" />
      <div className="h-48 animate-pulse rounded bg-muted" />
    </div>
  );
}

export function FacturaDetalle(): JSX.Element {
  const { uuid } = useParams<{ uuid: string }>();
  const { t } = useTranslation('facturacionAdmin');
  const swr = useFacturaDetalle(uuid ?? null);

  // 1. Header missing → 404 or loading.
  if (swr.header.error) {
    return <FacturaNoEncontrada />;
  }
  if (!swr.header.data) {
    return <FacturaDetalleSkeleton />;
  }
  const header = swr.header.data;

  // 2. Derive estado from log_transaccional (MVP shim — see
  // `lib/estadoFactura.ts`).
  const hashList = swr.hash.data;
  const estado = deriveEstadoFactura(hashList?.items ?? []);
  const hash = hashList ? findHashForFactura(header.uuid, hashList) : null;

  // 3. Compose 7 sections. Each owns loading/error inline.
  return (
    <article
      className="mx-auto max-w-4xl space-y-6 p-4"
      data-testid="factura-detalle"
    >
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">
          {t('header.title', 'Detalle de factura')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('header.subtitle', 'Investigación transaccional y acciones de admin.')}
        </p>
      </header>

      <FacturaHeaderCard
        header={header}
        estado={estado}
        fe={swr.fe.data}
        feLoading={swr.fe.isLoading}
        feError={swr.fe.error}
        hash={hash}
        hashLoading={swr.hash.isLoading}
        hashError={swr.hash.error}
        onRetryFe={() => swr.fe.mutate()}
        onRetryHash={() => swr.hash.mutate()}
      />

      <FacturaClienteCard cliente={null} />

      <FacturaItemsTable
        items={swr.detalle.data?.items ?? []}
        isLoading={swr.detalle.isLoading}
        error={swr.detalle.error}
        onRetry={() => swr.detalle.mutate()}
        uuidFactura={header.uuid}
      />

      <FacturaImpuestosTable
        items={swr.impuestos.data?.items ?? []}
        isLoading={swr.impuestos.isLoading}
        error={swr.impuestos.error}
        onRetry={() => swr.impuestos.mutate()}
        uuidFactura={header.uuid}
      />

      <FacturaPagosTable
        pagos={swr.pagos.data?.items ?? []}
        isLoading={swr.pagos.isLoading}
        error={swr.pagos.error}
        onRetry={() => swr.pagos.mutate()}
      />

      <FacturaElectronicaCard
        fe={swr.fe.data}
        isLoading={swr.fe.isLoading}
        error={swr.fe.error}
        isRetrying={false}
        onRetry={() => swr.fe.mutate()}
        onRetryFe={() => {
          // X.7 / X.1b follow-up: wire useReintentarFE.
          void 0;
        }}
      />

      <FacturaAccionesMenu
        uuid={header.uuid}
        uuid_ingreso={header.uuid_ingreso}
        uuid_salida={header.uuid_salida}
        estado={estado}
      />
    </article>
  );
}
