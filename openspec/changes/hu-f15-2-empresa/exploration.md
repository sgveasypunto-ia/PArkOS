# HU-F15.2 — Empresa: card + página con tabs — exploration

## 1. Estado actual del home y las cards

`apps/web_admin/src/pages/HomeHub.tsx:1-107` es la home post-login. Las cards
vienen de un array tipado `HUB_CARDS` (l. 34-51) y se renderizan como `<ul>` de
`<Link>` + `<Card>` con icono `lucide-react` + título + descripción i18n
(l. 67-104). Hoy hay **2 entries**: `sucursales` (`/seleccionar-sucursal`,
`Building2`) y `catalogos` (`/catalogos`, `FolderTree`).

Test pin: `apps/web_admin/src/pages/HomeHub.test.tsx:52` — H2 afirma literal
"renderiza 2 cards (sucursales y catalogos)". Hay que actualizar el conteo a 3.

`apps/web_admin/src/App.test.tsx:60-61` también referencia ambos testids pero
no afirma "only 2", así que sigue verde sin tocarlo.

## 2. Patrón de navegación de Sucursales y Catálogos

- `Sucursales`: card → `/seleccionar-sucursal` (`HomeHub.tsx:37`). Alias
  `/sucursales` redirige ahí (`App.tsx:108-111`).
- `Catálogos`: card → `/catalogos` (`HomeHub.tsx:45`).
- Ambas viven en `HUB_CARDS`, mismo formato (key, path, icon, titleKey,
  descriptionKey, testId).
- App.tsx:81-92: ambas rutas están en el grupo "global" (auth required, NO
  branch required) — el operador las ve apenas inicia sesión.

## 3. Router / layout

- Routing: `react-router-dom` v6 (`App.tsx:1`).
- **No hay sidebar.** La nav es la segunda fila de `AdminChrome`
  (`components/chrome/AdminChrome.tsx:114-138`), generada desde
  `lib/admin-sections.ts:67-145` (`ADMIN_SECTIONS`, 11 secciones).
- `AdminChrome` **solo monta en rutas branch-scoped** dentro de
  `<RequireSucursal>` (`App.tsx:101-130`). Las rutas globales (`/`, `/catalogos`,
  `/perfil`) llevan solo `<TopNav />` (identidad, sin nav de secciones).
- Empresa es singleton tenant-global → **no encaja en AdminChrome**, que la
  escondería antes de elegir sucursal. Va en HomeHub.

## 4. shadcn Tabs — instalado y usado

`apps/web_admin/src/components/ui/tabs.tsx:1` — Radix `@radix-ui/react-tabs`,
forwardRef, mismo patrón compound que el resto del design system. WCAG
keyboard nav (Left/Right, Home/End) heredado de Radix.

Patrón vivo: `features/catalogos/CatalogPage.tsx:66-86` — `<Tabs defaultValue>`
+ `<TabsList>` + `<TabsTrigger>` + `<TabsContent>`. Reutilizable tal cual para
los 3 tabs (Datos · Mensajes · Bitácora).

## 5. Estructura de carpetas + convención de imports

- `pages/` — top-level (HomeHub, Dashboard, Perfil, SeleccionarSucursal).
- `features/<dominio>/{pages,hooks,api,components,configs}/` — por dominio.
- `components/{auth,chrome,branch-selector,ui}/` — compartido.
- `lib/` — `admin-sections.ts`, `sucursal-context.tsx`, `fetch.ts`, `utils.ts`.
- Aliases: `@/` (path), `@parkos/ui-kit/hooks` para hooks compartidos
  (`AdminChrome.tsx:31`).
- Patrón API: `features/<x>/api/<x>Api.ts` + `<x>Schema.ts` (Zod). Molde:
  `features/sucursales/api/sucursalesApi.ts:13-15`,
  `features/sucursales/api/sucursalSchema.ts:5-12`.
- i18n: `src/i18n/locales/es-CO.json` (529 líneas), `useTranslation()` con
  default value como segundo arg.

## 6. Lo que YA existe del lado Empresa

- **Backend**: `GET/POST/PUT /api/v1/empresa/empresa` ya funcional
  (`backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py:1`,
  confirmado en `backend/packages/api_admin/openapi.json:8139`). Schemas
  Pydantic en `schemas/empresa.py::EmpresaCreate/Update/Read`.
- **Modelo ORM**: `backend/packages/parkos_core/src/parkos_core/models/V/empresa.py`.
- **ER canon** (`modelo_datos_er.mmd:291-312`): columnas editables —
  `nombre`, `nit` (UK), `mensaje_bienvenida`, `mensaje_salida`, `regimen` +
  audit/versioning/sync.
- **Frontend actual**: cero código. `grep -r "[Ee]mpresa" apps/web_admin/src`
  solo encuentra `/api/v1/empresa/sucursal` (lista de sucursales) y FKs
  `uuid_empresa`. No existe `features/empresa/`.

## 7. Plan.md reference + divergencia detectada

`plan.md:3537-3569` ya describe HU-F15.2 (T1 nit validator, T2
`EmpresaDetalle.tsx`, T3 `HashChainStatus.tsx`, T4 integración GET/PUT, T5
e2e). Tamaño estimado ~230 LOC.

**Divergencia**: el plan dice `src/features/parametrizacion/pages/`. Esa
carpeta **no existe** en el árbol actual de features. La convención real del
proyecto es `features/<dominio>/` con el nombre del dominio (`sucursales/`,
`catalogos/`, `tarifas/`, `cupos/`, `audit/`). Renombrar a `features/empresa/`
para no inventar un nuevo namespace raíz.

## 8. Test pinnings que se rompen o se tocan

- `pages/HomeHub.test.tsx:52` — H2 "renderiza 2 cards". Cambia a 3 y agrega
  assertion para `home-hub-card-empresa`.
- `pages/HomeHub.test.tsx:67` — H3 assertea que `catalogos` y `sucursales`
  son `<a>` con href + aria-label. Hay que extender la invariante a 3 cards
  (parametrizar el test sobre `HUB_CARDS` para que no haya que tocarlo cada
  vez).
- `App.test.tsx` no se toca.
- `e2e/` no tiene `empresa.spec.ts` todavía — se crea en T5.

## 9. Decisión de ubicación (cerrada)

**Card Empresa en HomeHub**, al lado de Sucursales y Catálogos, en
`HUB_CARDS`. No tocar `ADMIN_SECTIONS` ni `AdminChrome`. Coherente con el
carácter singleton tenant-global de Empresa (igual que Catálogos) y con el
hecho de que HomeHub vive fuera de `<RequireSucursal>`.

## 10. Riesgos / cosas a no romper

- `App.tsx` invariantes de routing: Empresa va en el grupo global
  (`App.tsx:81-92`), no en branch-scoped.
- i18n: los nuevos keys deben tener default en español hard-coded (segundo
  arg de `t()`) aunque no exista entrada en `es-CO.json` todavía — pineado
  por el patrón del resto del proyecto.
- No hardcodear UUID de empresa en cliente — se obtiene del endpoint.
- Bi-temporal: el PUT debe ser close+insert; la API ya lo hace, la UI solo
  envía la nueva versión.
