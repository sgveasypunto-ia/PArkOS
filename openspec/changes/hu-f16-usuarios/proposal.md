# HU-F16 — Gestión de usuarios: card + lista + detalle — proposal

## Why

Usuarios es una lista (no singleton como Empresa) que necesita:
1. Card en HomeHub (4ª card, al lado de Sucursales/Catálogos/Empresa)
2. Ruta `/usuarios` con lista filtrable (DataTable)
3. Detalle por usuario con 4 tabs: Datos, Permisos (árbol), Sucursales, Bitácora
4. Guard "último admin" (no permitir dejar el sistema sin admins)
5. Reset de password, sesiones activas, historial de login

**Estado actual**:
- `features/admin/` ya tiene `UsuariosList`, `AdminUsuarioTable`, `AdminUsuarioForm`, `AdminUsuarioSucursalesManager`
- Backend `admin_usuarios.py` tiene CRUD básico + asignación de sucursales
- **Falta**: PUT para editar, permisos (otorgar/revocar), reset-password, guard "último admin", sesiones activas, historial con filtros

**plan.md:3686-3859** ya describe HU-F16.1 a HU-F16.5 con el alcance completo. Esta propuesta aterriza la implementación frontend + los gaps de backend.

## What changes

### Frontend
1. **Card Usuarios en HomeHub** (4ª card, icono `Users` de lucide-react)
2. **Ruta `/usuarios`** en grupo global (auth, no branch)
3. **UsuariosList mejorado** con DataTable (filtros: rol, sucursal, estado) + click en fila → `/usuarios/:uuid`
4. **UsuarioDetalle** con 4 tabs:
   - **Datos**: form de edición (nombre, apellido, cedula, email, rol)
   - **Permisos**: árbol agrupado por prefijo (`config_*`, `admin_*`, `gestionar_*`, resto) con checkboxes
   - **Sucursales**: tabla de asignaciones + modal para asignar/revocar (reutilizar `AdminUsuarioSucursalesManager`)
   - **Bitácora**: lista de cambios filtrada por `tabla_afectada IN ('usuarios', 'permisos_usuario')`
5. **ResetPasswordModal**: muestra password temporal una sola vez
6. **SesionesActivas**: tabla de sesiones abiertas + botón "Cerrar sesión"
7. **LoginHistory**: lista paginada de intentos de login

### Backend (HU-F16.1)
1. **Router `usuarios.py`** completo con todos los endpoints faltantes
2. **Guard "último admin"**: contar `permisos_usuario` vigentes con `permiso='admin_usuarios'` antes de desactivar
3. **Permisos**: endpoints para listar catálogo, otorgar, revocar
4. **Reset password**: generar temporal de 12 chars, forzar cambio en próximo login
5. **Sesiones**: filtro `?activo=true` + acción `POST /login/{uuid}/cerrar`

### UI Components
1. **Table**: copiar patrón de `apps/electron-sucursal/src/components/ui/table.tsx`
2. **Tree**: componente custom con `<ul>` + checkboxes (agrupado por prefijo)

## Archivos a tocar

### Nuevos (frontend)
- `apps/web_admin/src/features/usuarios/pages/UsuariosList.tsx` (mover desde `features/admin/`)
- `apps/web_admin/src/features/usuarios/pages/UsuarioDetalle.tsx` (4 tabs)
- `apps/web_admin/src/features/usuarios/components/UsuarioForm.tsx` (edición)
- `apps/web_admin/src/features/usuarios/components/PermisosTree.tsx` (árbol de permisos)
- `apps/web_admin/src/features/usuarios/components/ResetPasswordModal.tsx`
- `apps/web_admin/src/features/usuarios/components/SesionesActivas.tsx`
- `apps/web_admin/src/features/usuarios/components/LoginHistory.tsx`
- `apps/web_admin/src/features/usuarios/api/usuariosApi.ts` (HTTP client)
- `apps/web_admin/src/features/usuarios/api/usuariosSchema.ts` (Zod)
- `apps/web_admin/src/features/usuarios/hooks/useUsuario.ts` (SWR)
- `apps/web_admin/src/features/usuarios/hooks/useUsuarioPermisos.ts`
- `apps/web_admin/src/features/usuarios/hooks/useUsuarioSucursales.ts` (mover desde `features/admin/`)
- `apps/web_admin/src/components/ui/table.tsx` (copiar de electron-sucursal)
- `apps/web_admin/src/components/ui/tree.tsx` (nuevo, custom)

### Nuevos (backend)
- `backend/packages/parkos_core/src/parkos_core/api/v1/usuarios.py` (router completo)
- `backend/packages/parkos_core/src/parkos_core/schemas/usuarios.py` (schemas)
- `backend/packages/parkos_core/src/parkos_core/repo/usuarios.py` (repo helpers)
- `backend/tests/integration/test_usuarios.py`

### Modificados
- `apps/web_admin/src/pages/HomeHub.tsx:34-59` — agregar 4ª card `usuarios`
- `apps/web_admin/src/App.tsx:89-92` — mover `/gestion-usuarios` a grupo global, agregar `/usuarios/:uuid`
- `apps/web_admin/src/lib/admin-sections.ts:90-95` — cambiar path de `gestion-usuarios` a `/usuarios`
- `apps/web_admin/src/i18n/locales/es-CO.json` — namespace `usuarios.*`

### NO se tocan
- `apps/web_admin/src/components/chrome/AdminChrome.tsx`
- `apps/web_admin/src/pages/Dashboard.tsx`
- Backend `admin_usuarios.py` (se mantiene para compatibilidad, nuevo router es `usuarios.py`)

## Orden de tareas

### Fase 1: Backend (HU-F16.1)
1. **T1**: Schemas `UsuariosCreate/Read/Update/Filter/ReadList` en `schemas/usuarios.py`
2. **T2**: Router `usuarios.py` con CRUD base (GET/POST/PUT)
3. **T3**: Endpoints custom: permisos (otorgar/revocar), reset-password, sucursales, login history, cerrar sesión
4. **T4**: Validación "último admin_usuarios" (409)
5. **T5**: Montar router en `api/v1/__init__.py`
6. **T6**: Tests de integración (9 endpoints + caso límite)

### Fase 2: Frontend — Card + Lista (HU-F16.2)
7. **T7**: Card Usuarios en HomeHub (icono `Users`)
8. **T8**: Ruta `/usuarios` en grupo global + `/usuarios/:uuid` para detalle
9. **T9**: Componente `Table` (copiar de electron-sucursal)
10. **T10**: `UsuariosList` mejorado con DataTable + filtros (rol, sucursal, estado)
11. **T11**: Click en fila → navegar a `/usuarios/:uuid`

### Fase 3: Frontend — Detalle (HU-F16.3 + HU-F16.4 + HU-F16.5)
12. **T12**: Componente `Tree` (custom, agrupado por prefijo)
13. **T13**: `UsuarioDetalle` con 4 tabs (Datos, Permisos, Sucursales, Bitácora)
14. **T14**: `UsuarioForm` (edición) + integración con PUT
15. **T15**: `PermisosTree` (árbol con checkboxes, otorgar/revocar)
16. **T16**: `ResetPasswordModal` (mostrar temporal una vez)
17. **T17**: `SesionesActivas` (tabla + botón cerrar)
18. **T18**: `LoginHistory` (lista paginada)
19. **T19**: Manejo de 409 `ultimo_admin_usuarios` en frontend

### Fase 4: Tests + e2e
20. **T20**: Tests unitarios para componentes nuevos
21. **T21**: e2e `usuarios-crear.spec.ts` (3 escenarios)
22. **T22**: e2e `usuarios-detalle.spec.ts` (2 escenarios)
23. **T23**: e2e `usuarios-reset.spec.ts` (3 escenarios)
24. **T24**: e2e `usuarios-sesiones.spec.ts` (2 escenarios)

## Decisión abierta (cerrada en exploration.md §9)

Card en **HomeHub**, ruta `/usuarios` en grupo **global** (auth, no branch). Igual que Catálogos y Empresa.

## Tradeoffs

### 1. Mover `/gestion-usuarios` a `/usuarios`
- **Pro**: naming más limpio, coherente con el resto de rutas globales
- **Contra**: rompe links existentes (pero hay redirect `/admin/usuarios` → `/gestion-usuarios`)
- **Decisión**: mover a `/usuarios`, mantener redirect `/gestion-usuarios` → `/usuarios` por compatibilidad

### 2. Tree component: custom vs librería
- **Custom** (recomendado): `<ul>` + checkboxes, agrupado por prefijo. Más simple, sin dependencias.
- **Librería** (`@radix-ui/react-accordion`): más complejo, overkill para este caso.
- **Decisión**: custom.

### 3. Detalle: ruta dedicada vs Sheet/Dialog
- **Ruta dedicada** (`/usuarios/:uuid`): más simple, deep-linkable, back/forward funciona.
- **Sheet/Dialog**: más "modal", pero pierde deep-link.
- **Decisión**: ruta dedicada.

### 4. Backend: router nuevo vs extender `admin_usuarios.py`
- **Router nuevo** (`usuarios.py`): más limpio, separado de `admin_usuarios.py` (que es branch-scoped).
- **Extender `admin_usuarios.py`**: menos archivos, pero mezcla concerns.
- **Decisión**: router nuevo `usuarios.py` (como dice plan.md:3727).

### 5. Permisos: árbol vs lista plana
- **Árbol** (agrupado por prefijo): más usable, agrupa permisos relacionados.
- **Lista plana**: más simple, pero 30+ permisos en una lista es difícil de navegar.
- **Decisión**: árbol (como dice plan.md:3771).

## Out of scope

- **HU-F17** (reportería) — siguiente fase
- **HU-F18** (auditoría avanzada) — siguiente fase
- **HU-F19** (impersonation) — no planeado
- **WebSocket** para sesiones en tiempo real — diferido a v2

## Acceptance criteria

- Backend: todos los endpoints de HU-F16.1 funcionan, guard "último admin" retorna 409
- Frontend: card en HomeHub, ruta `/usuarios` con DataTable, detalle con 4 tabs
- Tests: 100% de cobertura en componentes nuevos
- e2e: 10 escenarios cubiertos (crear, detalle, reset, sesiones)
- axe-core: WCAG 2.1 AA verde
- `python openspec/scripts/check_schema_match.py` sigue verde (no tocamos DB)
