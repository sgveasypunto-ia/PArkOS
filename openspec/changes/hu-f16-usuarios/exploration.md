# HU-F16 — Gestión de usuarios: card + lista + detalle — exploration

## 1. Estado actual del home y las cards

`apps/web_admin/src/pages/HomeHub.tsx:34-59` define `HUB_CARDS` (array exportado, data-driven). Hoy hay **3 entries**: `sucursales`, `catalogos`, `empresa`. El test `HomeHub.test.tsx` itera sobre `HUB_CARDS` (no hardcodea el conteo), así que agregar una 4ª card no requiere tocar el test.

Patrón de card: `<Link>` → `<Card>` + icono `lucide-react` + título i18n + descripción i18n + "Abrir →".

## 2. Patrón de lista + detalle existente

**Sucursales** (`SeleccionarSucursal.tsx:1-398`): página unificada con 2 tabs:
- Tab "Seleccionar": cards de sucursales (picker)
- Tab "Administrar": tabla HTML con acciones (Editar, Token pairing)

**Usuarios** (`features/admin/pages/UsuariosList.tsx:1-246`): ya existe una lista básica:
- Tabla HTML con columnas: email, nombre, rol, sucursales (badges), estado, acciones
- Modal "Crear nuevo usuario" con `AdminUsuarioForm`
- Modal "Asignar sucursales" con `AdminUsuarioSucursalesManager`
- **NO hay detalle**: el comentario en `UsuariosList.tsx:11-13` dice explícitamente "Edit by row is intentionally NOT exposed: the backend has no PUT `/admin/usuarios/{uuid}` endpoint"

**Diferencia clave con Empresa**:
- **Empresa** = singleton (1 fila por tenant) → ruta `/empresa` lleva directo al detalle con tabs
- **Usuarios** = lista (N filas por tenant) → ruta `/usuarios` lleva a la lista, click en fila → `/usuarios/:uuid` (detalle)

## 3. Router / layout

- Routing: `react-router-dom` v6 (`App.tsx:1`)
- **No hay sidebar**. La nav es la segunda fila de `AdminChrome` (`components/chrome/AdminChrome.tsx:114-138`), generada desde `lib/admin-sections.ts:67-145` (`ADMIN_SECTIONS`, 11 secciones).
- `ADMIN_SECTIONS` ya incluye `gestion-usuarios` (línea 90-95) con `permission: null` (issuer-only).
- Ruta actual: `/gestion-usuarios` está en el grupo **branch-scoped** (`App.tsx:112`), dentro de `<RequireSucursal>`. Para usuarios (que es tenant-global como Catálogos/Empresa), debe moverse al grupo **global** (auth required, NO branch required).

## 4. shadcn UI components instalados

| Componente | Instalado | Ubicación |
|---|---|---|
| Tabs | ✅ | `components/ui/tabs.tsx` |
| Dialog | ✅ | `components/ui/dialog.tsx` |
| Card | ✅ | `components/ui/card.tsx` |
| Badge | ✅ | `components/ui/badge.tsx` |
| Button | ✅ | `components/ui/button.tsx` |
| Input | ✅ | `components/ui/input.tsx` |
| Form (RHF) | ✅ | `components/ui/form.tsx` |
| **Table** | ❌ | No existe en web_admin (pero electron-sucursal tiene `<Table>` en `components/ui/table.tsx`) |
| **Tree** | ❌ | No existe |
| **Sheet** | ❌ | No existe |

**Table**: `apps/electron-sucursal/src/components/ui/table.tsx` existe y se usa en `Listado.tsx` (suscripciones). Puedo copiar el patrón o crear un wrapper simple.

**Tree**: Para permisos por árbol, necesito construir un componente propio. Opciones:
- (a) Componente custom con `<ul>` + checkboxes (más simple, sin dependencias)
- (b) Instalar `@radix-ui/react-accordion` o similar (más complejo)

**Sheet**: No es crítico. Puedo usar Dialog para el detalle o crear una ruta dedicada `/usuarios/:uuid`.

## 5. Backend de usuarios

### Endpoints existentes (`admin_usuarios.py:1-276`)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/admin/usuarios` | Crear usuario |
| GET | `/api/v1/admin/usuarios` | Listar usuarios activos |
| GET | `/api/v1/admin/usuarios/{uuid}` | Obtener un usuario |
| POST | `/api/v1/admin/usuarios/{uuid}/sucursales` | Asignar sucursal |
| GET | `/api/v1/admin/usuarios/{uuid}/sucursales` | Listar sucursales asignadas |
| DELETE | `/api/v1/admin/usuarios/{uuid}/sucursales/{sucursal}` | Desasignar sucursal |

### Endpoints faltantes (HU-F16.1, plan.md:3702-3711)

| Método | Ruta | Descripción | Estado |
|---|---|---|---|
| PUT | `/api/v1/admin/usuarios/{uuid}` | Editar usuario (close+insert) | ❌ NO existe |
| GET/POST | `/api/v1/admin/usuarios/{uuid}/permisos` | Listar/otorgar permisos | ❌ NO existe |
| POST | `/api/v1/admin/usuarios/{uuid}/permisos/{uuid_permiso}/revocar` | Revocar permiso | ❌ NO existe |
| POST | `/api/v1/admin/usuarios/{uuid}/reset-password` | Reset password | ❌ NO existe |
| GET | `/api/v1/admin/usuarios/{uuid}/login?activo=` | Historial login (con filtro) | ❌ NO existe (solo read-only en `usuarios_login.py`) |
| POST | `/api/v1/admin/usuarios/{uuid}/login/{login_uuid}/cerrar` | Cerrar sesión forzada | ❌ NO existe |

### Permisos por árbol

**ER** (`modelo_datos_er.mmd:31-66`):
- `permisos` ([V], catálogo): `uuid`, `permiso` (código como `config_catalogo`, `admin_usuarios`, etc.)
- `permisos_usuario` ([V], junction): `uuid`, `uuid_usuario`, `uuid_permiso` + audit/versioning

**No hay endpoint** para listar permisos disponibles ni para otorgar/revocar. El plan dice "agrupado por prefijo semántico (`config_*`, `admin_*`, `gestionar_*`, resto operativo)" con checkboxes.

### Guard "último admin"

**NO existe en el backend**. plan.md:3697 (BR5) dice: "No se permite desactivar al último usuario con permiso `admin_usuarios` activo — el backend cuenta cuántos `permisos_usuario` vigentes apuntan a ese código antes de cerrar la vigencia del usuario objetivo."

Error esperado: 409 `ultimo_admin_usuarios`.

## 6. Sesiones activas e historial

**Backend existente**:
- `usuarios_login.py:75-126` — `get_login_historico` (read-only, cursor pagination)
- `login_historico.py` — repo con `listar_intentos_paginado`
- `sesion_activa.py` — repo con `get_sesion_activa`

**Falta**:
- Filtro `?activo=true` (mostrar solo sesiones abiertas)
- Acción `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` (cierre forzado)

## 7. Diferencia IA: Empresa vs Usuarios

| Aspecto | Empresa (singleton) | Usuarios (lista) |
|---|---|---|
| **Card en HomeHub** | ✅ Ya existe | 🔲 A agregar |
| **Ruta** | `/empresa` → detalle directo | `/usuarios` → lista → `/usuarios/:uuid` → detalle |
| **Tabs** | Datos, Mensajes, Bitácora | Datos, Permisos (árbol), Sucursales, Bitácora |
| **Backend** | ✅ Completo (`GET/PUT /empresa/empresa`) | 🔲 Parcial (falta PUT, permisos, reset-password, sesiones) |
| **Guard "último admin"** | N/A | 🔲 Faltante (409 `ultimo_admin_usuarios`) |
| **Componentes UI** | ✅ Todos instalados | 🔲 Falta Table, Tree |

## 8. Test pinnings que se tocan

- `HomeHub.test.tsx` — **NO se toca** (data-driven sobre `HUB_CARDS`)
- `App.test.tsx` — agregar test para `/usuarios` en grupo global
- Nuevos tests para `UsuarioDetalle`, `PermisosTree`, etc.

## 9. Decisión de ubicación (cerrada)

**Card Usuarios en HomeHub**, al lado de Sucursales, Catálogos y Empresa. Ruta `/usuarios` en grupo **global** (auth required, NO branch required) — igual que Catálogos y Empresa.

## 10. Riesgos / cosas a no romper

- **Backend**: HU-F16.1 es un router nuevo completo (~420 LOC según plan.md). Es el más grande de la Parte II.
- **Permisos por árbol**: no hay endpoint backend, hay que construirlo.
- **Guard "último admin"**: no existe, hay que implementarlo en backend + manejar 409 en frontend.
- **Table/Tree**: componentes UI faltantes, hay que crearlos o instalar dependencias.
- **Ruta**: mover `/gestion-usuarios` de branch-scoped a global (cambio en `App.tsx`).
