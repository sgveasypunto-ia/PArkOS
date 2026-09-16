# Manual de usuario final — Panel de administración (web_admin)

> Guía de uso de **web_admin**, el panel de administración multi-tenant de easypunto_parkos. Todo lo descrito aquí está verificado contra el código real de `apps/web_admin/src` (páginas, componentes y textos de `i18n/locales/es-CO.json`) — no es una proyección de diseño.

## Alcance y estado actual

- Esta guía cubre únicamente **web_admin** (React + Vite + TypeScript + Tailwind + shadcn/ui), el único frontend que existe hoy en el proyecto.
- **No existe todavía** una interfaz para el operador de sucursal ("web_sucursal"). Es una pieza de **roadmap/futuro**: el propio despliegue de sucursal ya deja el puerto de su API expuesto en la red local pensando en esa futura PWA, pero el frontend en sí no está construido. Si necesitás operar una sucursal hoy, no hay pantalla para eso.

## Rutas de la aplicación

| Ruta | Página | Notas |
|---|---|---|
| `/login` | `Login.tsx` | Ver "Iniciar sesión" abajo — es un placeholder, no un formulario funcional. |
| `/dashboard` | `Dashboard.tsx` | Panel principal. Único módulo funcional hoy. |
| `/` y cualquier otra ruta | — | Redirigen automáticamente a `/dashboard`. |

## Iniciar sesión (`/login`)

**Estado actual: pantalla de marcador de posición (placeholder), sin formulario funcional.**

Al entrar a `/login` ves:

- El nombre de la aplicación ("Parkos Admin") y su tagline.
- Un aviso: *"El formulario de inicio de sesión se conecta en PR10c."*

No hay campos de usuario/contraseña ni botón de ingreso todavía — el propio código documenta esta pantalla como un stub a la espera de conectar el flujo real de JWT contra el backend. El resto del panel ya está preparado para adjuntar un token de sesión guardado en el navegador una vez que ese flujo exista, pero hoy nada lo escribe desde la interfaz.

## Selector de sucursal

En la cabecera del panel hay un desplegable, con la etiqueta **"Seleccionar sucursal"**, que:

- Lista solo las sucursales que el usuario tiene permitidas.
- Si no tenés ninguna sucursal permitida, muestra "No hay sucursales disponibles" en vez del desplegable.
- Recuerda tu última selección: queda guardada en el navegador y se restaura automáticamente la próxima vez que abrís el panel — no hace falta volver a elegirla en cada visita.
- Es accesible por teclado (flechas, Enter/Espacio, Home/End, búsqueda por tipeo) y cumple WCAG 2.1 AA.
- Al cambiar de sucursal, las métricas del panel se recargan para la nueva sucursal — nunca quedan datos de la sucursal anterior a la vista.

Si es tu primer ingreso y todavía no elegiste sucursal, el panel selecciona automáticamente la primera sucursal permitida que encuentra.

## Panel principal (`/dashboard`)

Título: **"Panel de sucursal"** — subtítulo: **"Métricas en vivo de la sucursal seleccionada."**

Muestra 3 tarjetas de métricas de la sucursal activa:

| Tarjeta | Qué muestra |
|---|---|
| Ingresos | Cantidad de ingresos de vehículos registrados. |
| Facturas | Cantidad de facturas emitidas. |
| Alertas abiertas | Cantidad de alertas sin resolver. |

Estados posibles:

| Situación | Qué ves |
|---|---|
| Cargando datos | "…" en cada tarjeta. |
| Sin sucursal seleccionada | "Seleccioná una sucursal para ver el panel." (las tarjetas no se muestran). |
| Error al cargar el panel | "No se pudo cargar el panel de la sucursal." y "—" en las tarjetas. |

## Qué no hace todavía este panel (huecos verificados en el código)

- **Login real**: no hay formulario ni validación de credenciales; es texto fijo.
- **Monto total de ingresos** y **última sincronización**: el backend ya devuelve estos datos y hasta existen los textos ya traducidos ("Monto total (COP)", "Última sincronización") en el archivo de idioma — pero el panel todavía no los renderiza en ninguna tarjeta.
- **Facturas electrónicas**: ese dato también llega del backend por separado y tampoco se muestra hoy (solo se ve el total general de "Facturas").
- **web_sucursal**: no existe (ver "Alcance y estado actual" arriba).

## Ver también

- [Manual de operaciones](./operaciones.md) — despliegue, variables de entorno y observabilidad.
- [Configuración de desarrollo](../03-desarrollo/setup.md) — cómo levantar web_admin localmente.
- [Seguridad](../02-arquitectura/seguridad.md) — modelo de autenticación/autorización previsto.
