/**
 * `CatalogPage` — landing de `/catalogos`.
 *
 * INVARIANTE ARQUITECTÓNICO: este componente se monta FUERA de
 * `<RequireSucursal>` en `App.tsx`. Los catálogos son tenant-globales
 * (ninguna de las 9 tablas tiene `uuid_sucursal`) y se editan sin
 * seleccionar sucursal.
 *
 * Renderiza un `<Tabs>` con los 9 catálogos. Cada tab carga su
 * `<CatalogEditor>` con su config. Cada `<CatalogEditor>` es
 * independiente — cambia de tab y mantiene su propio estado.
 *
 * Pineado por `App.test.tsx` "does NOT mount the chrome on /" — la
 * ausencia del chrome en `/catalogos` es consecuencia del mismo
 * invariante (fuera de RequireSucursal).
 */
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';

import { CatalogEditor } from './components/CatalogEditor';
import { tipoArqueoConfig } from './configs/tipoArqueo.config';
import { tipoPersonaConfig } from './configs/tipoPersona.config';
import { tiposVehiculoConfig } from './configs/tiposVehiculo.config';
import { tipoSubscripcionesConfig } from './configs/tipoSubscripciones.config';
import { tipoTarifaConfig } from './configs/tipoTarifa.config';
import { tipoSucursalConfig } from './configs/tipoSucursal.config';
import { impuestosConfig } from './configs/impuestos.config';
import { otrosCobrosConfig } from './configs/otrosCobros.config';
import { costosServiciosConfig } from './configs/costosServicios.config';

const ALL_CONFIGS = [
  tipoPersonaConfig,
  tiposVehiculoConfig,
  tipoSubscripcionesConfig,
  tipoTarifaConfig,
  tipoSucursalConfig,
  tipoArqueoConfig,
  impuestosConfig,
  otrosCobrosConfig,
  costosServiciosConfig,
] as const;

export default function CatalogPage(): JSX.Element {
  const { t } = useTranslation();

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="catalog-page"
    >
      <PageHeader
        title={t('catalogos.title', 'Catálogos')}
        subtitle={t(
          'catalogos.subtitle',
          'Editá los catálogos globales. "Nueva versión" publica un cambio sin perder la versión anterior.',
        )}
      />

      <Tabs defaultValue={ALL_CONFIGS[0].resource}>
        <TabsList
          className="flex flex-wrap gap-1"
          aria-label={t('catalogos.tabsLabel', 'Catálogos')}
        >
          {ALL_CONFIGS.map((cfg) => (
            <TabsTrigger
              key={cfg.resource}
              value={cfg.resource}
              data-testid={`catalog-tab-${cfg.resource}`}
            >
              {cfg.pluralLabel}
            </TabsTrigger>
          ))}
        </TabsList>
        {ALL_CONFIGS.map((cfg) => (
          <TabsContent key={cfg.resource} value={cfg.resource} className="mt-4">
            <CatalogEditor config={cfg} />
          </TabsContent>
        ))}
      </Tabs>
    </main>
  );
}
