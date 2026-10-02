/**
 * `<ClienteDetalle />` — shell de 5 pestañas en `/clientes/:uuid`
 * (HU-F20.1). Same pattern as `features/parametrizacion/pages/
 * SucursalDetalle.tsx`: `useParams<{uuid}>()` + `useCliente(uuid)` SWR
 * hook with early loading/error/not-found returns, shadcn
 * `Tabs`/`TabsList`/`TabsTrigger`/`TabsContent` with local-state tabs
 * (not nested routes), `defaultValue="datos"`.
 */
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { useCliente } from '../hooks/useCliente';
import { ClienteDatosTab } from '../components/ClienteDatosTab';
import { ClienteVehiculosTab } from '../components/ClienteVehiculosTab';
import { ClienteSuscripciones } from '../components/ClienteSuscripciones';
import { ClienteFacturasTab } from '../components/ClienteFacturasTab';
import { ClienteBitacoraTab } from '../components/ClienteBitacoraTab';

const TABS = [
  { value: 'datos', labelKey: 'clienteDetalle.tabs.datos', testId: 'cliente-tab-datos' },
  {
    value: 'vehiculos',
    labelKey: 'clienteDetalle.tabs.vehiculos',
    testId: 'cliente-tab-vehiculos',
  },
  {
    value: 'suscripciones',
    labelKey: 'clienteDetalle.tabs.suscripciones',
    testId: 'cliente-tab-suscripciones',
  },
  { value: 'facturas', labelKey: 'clienteDetalle.tabs.facturas', testId: 'cliente-tab-facturas' },
  { value: 'bitacora', labelKey: 'clienteDetalle.tabs.bitacora', testId: 'cliente-tab-bitacora' },
] as const;

export default function ClienteDetalle(): JSX.Element {
  const { t } = useTranslation();
  const { uuid } = useParams<{ uuid: string }>();
  const { cliente, isLoading, error, update } = useCliente(uuid);

  if (isLoading) {
    return (
      <div className="p-6" data-testid="cliente-detalle-loading">
        {t('common.loading', 'Cargando…')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-destructive" data-testid="cliente-detalle-error">
        {t('clienteDetalle.loadError', 'Error al cargar el cliente: {{message}}', {
          message: error.message,
        })}
      </div>
    );
  }

  if (!cliente || !uuid) {
    return (
      <div className="p-6" data-testid="cliente-detalle-not-found">
        {t('clienteDetalle.notFound', 'Cliente no encontrado')}
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6" data-testid="cliente-detalle-page">
      <header className="mb-6">
        <h1 className="text-2xl font-bold" data-testid="cliente-detalle-nombre">
          {`${cliente.nombre ?? ''} ${cliente.apellido ?? ''}`.trim() || cliente.uuid}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm" data-testid="cliente-detalle-identificacion">
          {t('clienteDetalle.identificacion', '{{tipo}} {{numero}}', {
            tipo: cliente.tipo_identificador ?? '—',
            numero: cliente.numero_identificacion ?? '—',
          })}
        </p>
      </header>

      <Tabs defaultValue="datos">
        <TabsList
          className="flex flex-wrap gap-1"
          aria-label={t('clienteDetalle.tabsLabel', 'Secciones del cliente')}
        >
          {TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} data-testid={tab.testId}>
              {t(tab.labelKey, tab.value)}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="datos" className="mt-4">
          <ClienteDatosTab cliente={cliente} onSubmit={update} />
        </TabsContent>

        <TabsContent value="vehiculos" className="mt-4">
          <ClienteVehiculosTab uuidCliente={uuid} />
        </TabsContent>

        <TabsContent value="suscripciones" className="mt-4">
          <ClienteSuscripciones uuidCliente={uuid} />
        </TabsContent>

        <TabsContent value="facturas" className="mt-4">
          <ClienteFacturasTab uuidCliente={uuid} />
        </TabsContent>

        <TabsContent value="bitacora" className="mt-4">
          <ClienteBitacoraTab uuidCliente={uuid} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
