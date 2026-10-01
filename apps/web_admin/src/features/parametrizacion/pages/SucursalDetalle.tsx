/**
 * `SucursalDetalle` — shell de 7 pestañas en `/sucursales/:uuid` (HU-F15.1).
 *
 * Mismo patrón que `features/usuarios/pages/UsuarioDetalle.tsx`:
 * `useParams<{uuid}>()` + un hook `useX(uuid)` con loading/error/not-found
 * tempranos + `<Tabs defaultValue="general">` (shadcn `Tabs`/`TabsList`/
 * `TabsTrigger`/`TabsContent`, el mismo primitivo que `EmpresaPage.tsx`
 * también usa -- no se inventa un patrón de tabs nuevo).
 *
 * De las 7 pestañas:
 *   - **General**: completa -- `<SucursalGeneralForm />`.
 *   - **Tarifas** / **Capacidad**: embeben las pantallas YA existentes
 *     `<Tarifas />` / `<Cupos />` tal cual (CERO duplicación de código),
 *     con un aviso cuando la sucursal activa del topbar (de donde esas
 *     pantallas leen su scope -- `useSucursal().selected`, ver
 *     `lib/sucursal-context.tsx`) difiere de la sucursal que se está
 *     viendo en esta página. Ese aviso es deliberado: ni `Tarifas.tsx`
 *     ni `Cupos.tsx` aceptan un prop/param de scope -- ambas leen el
 *     contexto global del selector de sucursal del topbar, así que
 *     embeberlas tal cual (como pide la HU) significa que SIEMPRE
 *     muestran la sucursal activa global, no necesariamente el `:uuid`
 *     de la URL. Adaptar esas pantallas para aceptar un scope explícito
 *     es trabajo de otra HU -- acá no se las duplica ni se las reescribe.
 *   - **Documentos**: completa -- `<SucursalDocumentos />` (HU-F15.4:
 *     logo, póliza de responsabilidad civil, plantilla de ticket,
 *     observaciones). A diferencia de Tarifas/Capacidad (pantallas
 *     PRE-EXISTENTES reusadas tal cual), este es un componente NUEVO
 *     construido para esta HU, así que recibe el `uuid` de la ruta
 *     explícitamente -- ver el docstring de `SucursalDocumentos.tsx`
 *     para por qué igual necesita bloquear su propia UI ante un
 *     mismatch de sucursal activa (el backend solo scopea el GET por el
 *     header ambient, no por un query param confiable).
 *   - **Resoluciones** / **Caja**: placeholders "Próximamente" (otra HU
 *     las completa).
 *   - **Bitácora**: `<SucursalBitacoraTab />`, mismo enfoque que
 *     `EmpresaBitacoraTab` pero scopeada a esta sucursal.
 *
 * `ParametrizacionEfectivaSelector` + `useParametrizacionEfectiva` (BR4)
 * se montan una vez a nivel de página (no por-tab) y muestran un resumen
 * de cuántas tarifas/capacidades/resoluciones estaban vigentes en la
 * fecha elegida -- demuestra el filtro `vigente_en` del backend end-to-end
 * sin tener que tocar `Tarifas.tsx`/`Cupos.tsx` (eso también queda para
 * las HUs de Fase 15 que sí vayan a cablear el selector dentro de cada
 * pestaña, como anticipa el comentario de `ParametrizacionEfectivaSelector.tsx`).
 */
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Tarifas from '@/features/tarifas/pages/Tarifas';
import Cupos from '@/features/cupos/pages/Cupos';
import { useSucursal } from '@/lib/sucursal-context';

import { useSucursalDetalle } from '../../sucursales/hooks/useSucursalDetalle';
import { ParametrizacionEfectivaSelector } from '../components/ParametrizacionEfectivaSelector';
import { SucursalBitacoraTab } from '../components/SucursalBitacoraTab';
import { SucursalDocumentos } from '../components/SucursalDocumentos';
import { SucursalGeneralForm } from '../components/SucursalGeneralForm';
import { useParametrizacionEfectiva } from '../hooks/useParametrizacionEfectiva';

const TABS = [
  { value: 'general', labelKey: 'sucursalDetalle.tabs.general', testId: 'sucursal-tab-general' },
  { value: 'tarifas', labelKey: 'sucursalDetalle.tabs.tarifas', testId: 'sucursal-tab-tarifas' },
  { value: 'capacidad', labelKey: 'sucursalDetalle.tabs.capacidad', testId: 'sucursal-tab-capacidad' },
  { value: 'resoluciones', labelKey: 'sucursalDetalle.tabs.resoluciones', testId: 'sucursal-tab-resoluciones' },
  { value: 'caja', labelKey: 'sucursalDetalle.tabs.caja', testId: 'sucursal-tab-caja' },
  { value: 'documentos', labelKey: 'sucursalDetalle.tabs.documentos', testId: 'sucursal-tab-documentos' },
  { value: 'bitacora', labelKey: 'sucursalDetalle.tabs.bitacora', testId: 'sucursal-tab-bitacora' },
] as const;

function ProximamentePlaceholder({ slug, nombre }: { slug: string; nombre: string }): JSX.Element {
  const { t } = useTranslation();
  return (
    <div
      className="rounded-md border border-dashed bg-muted/40 px-4 py-8 text-center text-sm text-muted-foreground"
      data-testid={`sucursal-placeholder-${slug}`}
    >
      {t('sucursalDetalle.proximamente', '{{nombre}} — próximamente. Otra historia de usuario completa esta pestaña.', {
        nombre,
      })}
    </div>
  );
}

function ScopeMismatchNotice({ uuidRuta }: { uuidRuta: string }): JSX.Element | null {
  const { t } = useTranslation();
  const { selected } = useSucursal();
  if (selected === uuidRuta) return null;
  return (
    <p
      role="status"
      data-testid="sucursal-scope-mismatch-notice"
      className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
    >
      {t(
        'sucursalDetalle.scopeMismatch',
        'Esta pantalla muestra la sucursal ACTIVA en el selector del topbar, que puede ser distinta de la que estás viendo acá. Cambiá la sucursal activa para gestionar esta en particular.',
      )}
    </p>
  );
}

export default function SucursalDetalle(): JSX.Element {
  const { t } = useTranslation();
  const { uuid } = useParams<{ uuid: string }>();
  const { sucursal, isLoading, error, refresh } = useSucursalDetalle(uuid);
  const { fecha, setFecha, resetAHoy, counts, isLoading: isLoadingEfectiva } =
    useParametrizacionEfectiva(uuid);

  if (isLoading) {
    return (
      <div className="p-6" data-testid="sucursal-detalle-loading">
        {t('common.loading', 'Cargando…')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-destructive" data-testid="sucursal-detalle-error">
        {t('sucursalDetalle.loadError', 'Error al cargar la sucursal: {{message}}', {
          message: error.message,
        })}
      </div>
    );
  }

  if (!sucursal || !uuid) {
    return (
      <div className="p-6" data-testid="sucursal-detalle-not-found">
        {t('sucursalDetalle.notFound', 'Sucursal no encontrada')}
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6" data-testid="sucursal-detalle-page">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" data-testid="sucursal-detalle-nombre">
            {sucursal.nombre ?? sucursal.prefijo_nombre ?? sucursal.uuid}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm" data-testid="sucursal-detalle-estado">
            {t('sucursalDetalle.estado', 'Estado: {{estado}}', { estado: sucursal.estado })}
          </p>
        </div>

        <div className="flex flex-col items-end gap-1">
          <ParametrizacionEfectivaSelector
            value={fecha}
            onChange={setFecha}
            onResetHoy={resetAHoy}
          />
          {!isLoadingEfectiva && counts && (
            <p
              className="text-xs text-muted-foreground"
              data-testid="sucursal-parametrizacion-efectiva-resumen"
            >
              {t(
                'sucursalDetalle.parametrizacionResumen',
                '{{tarifas}} tarifa(s) · {{capacidad}} capacidad(es) · {{resoluciones}} resolución(es) vigente(s) el {{fecha}}',
                {
                  tarifas: counts.tarifasVigentes,
                  capacidad: counts.capacidadVigente,
                  resoluciones: counts.resolucionesVigentes,
                  fecha,
                },
              )}
            </p>
          )}
        </div>
      </header>

      <Tabs defaultValue="general">
        <TabsList
          className="flex flex-wrap gap-1"
          aria-label={t('sucursalDetalle.tabsLabel', 'Secciones de la sucursal')}
        >
          {TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} data-testid={tab.testId}>
              {t(tab.labelKey, tab.value)}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="general" className="mt-4">
          <SucursalGeneralForm
            sucursal={sucursal}
            onUpdated={refresh}
            onDeshabilitada={refresh}
          />
        </TabsContent>

        <TabsContent value="tarifas" className="mt-4">
          <ScopeMismatchNotice uuidRuta={uuid} />
          <Tarifas />
        </TabsContent>

        <TabsContent value="capacidad" className="mt-4">
          <ScopeMismatchNotice uuidRuta={uuid} />
          <Cupos />
        </TabsContent>

        <TabsContent value="resoluciones" className="mt-4">
          <ProximamentePlaceholder
            slug="resoluciones"
            nombre={t('sucursalDetalle.tabs.resoluciones', 'Resoluciones')}
          />
        </TabsContent>

        <TabsContent value="caja" className="mt-4">
          <ProximamentePlaceholder slug="caja" nombre={t('sucursalDetalle.tabs.caja', 'Caja')} />
        </TabsContent>

        <TabsContent value="documentos" className="mt-4">
          <SucursalDocumentos uuidSucursal={uuid} />
        </TabsContent>

        <TabsContent value="bitacora" className="mt-4">
          <SucursalBitacoraTab uuidSucursal={uuid} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
