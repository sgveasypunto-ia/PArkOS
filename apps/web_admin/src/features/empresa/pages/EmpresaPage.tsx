/**
 * `<EmpresaPage />` — landing de `/empresa` (HU-F15.2 de
 * `plan.md:3537`).
 *
 * INVARIANTE ARQUITECTÓNICO: este componente se monta en el
 * grupo GLOBAL de `App.tsx` (auth required, NO branch required).
 * Empresa es un singleton tenant-global — la edición de `nombre`,
 * `nit`, `mensaje_bienvenida`, `mensaje_salida`, `regimen` no se
 * filtra por sucursal — así que vive en HomeHub junto a Sucursales
 * y Catálogos, no en AdminChrome.
 *
 * Renderiza un `<Tabs>` con 3 tabs:
 *   - Datos (default): `<EmpresaDatosTab />` (form RHF con
 *     `nombre`, `nit`, `regimen`; validación NIT módulo 11 inline).
 *   - Mensajes: `<EmpresaMensajesTab />` (textareas para los dos
 *     mensajes de ticket + preview).
 *   - Bitácora: `<EmpresaBitacoraTab />` (lista de cambios del
 *     singleton con `HashChainStatus` por fila).
 *
 * Pineado por `EmpresaPage.test.tsx`:
 *   - T1: el contenedor de la página se monta.
 *   - T2: el tab por defecto es "Datos" (su contenido visible).
 *   - T3: click en "Mensajes" muestra el contenido del tab Mensajes.
 *   - T4: click en "Bitácora" muestra el contenido del tab Bitácora.
 */
import { useTranslation } from 'react-i18next';

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';

import { EmpresaBitacoraTab } from '../components/EmpresaBitacoraTab';
import { EmpresaDatosTab } from '../components/EmpresaDatosTab';
import { EmpresaMensajesTab } from '../components/EmpresaMensajesTab';

const TABS = [
  { value: 'datos', labelKey: 'empresa.tabs.datos', testId: 'empresa-tab-datos' },
  { value: 'mensajes', labelKey: 'empresa.tabs.mensajes', testId: 'empresa-tab-mensajes' },
  { value: 'bitacora', labelKey: 'empresa.tabs.bitacora', testId: 'empresa-tab-bitacora' },
] as const;

export default function EmpresaPage(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      className="mx-auto max-w-6xl px-4 py-6"
      data-testid="empresa-page"
    >
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">
          {t('empresa.title', 'Empresa')}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          {t(
            'empresa.subtitle',
            'Datos tributarios, mensajes de ticket y bitácora del singleton Empresa.',
          )}
        </p>
      </header>

      <Tabs defaultValue="datos">
        <TabsList
          className="flex flex-wrap gap-1"
          aria-label={t('empresa.tabsLabel', 'Secciones de empresa')}
        >
          {TABS.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              data-testid={tab.testId}
            >
              {t(tab.labelKey, tab.value)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="datos" className="mt-4">
          <EmpresaDatosTab />
        </TabsContent>
        <TabsContent value="mensajes" className="mt-4">
          <EmpresaMensajesTab />
        </TabsContent>
        <TabsContent value="bitacora" className="mt-4">
          <EmpresaBitacoraTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
