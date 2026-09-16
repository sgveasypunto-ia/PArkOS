# easypunto_parkos — Visión general

easypunto_parkos es un sistema de gestión de parqueaderos con arquitectura
**multi-tenant cloud-edge**: una base de datos central en la nube administra
la red completa de sucursales, y cada sucursal opera con su propia base de
datos Postgres local, sincronizada de forma bidireccional con la nube. El
diseño es **audit-first**: cumplimiento DIAN (Colombia), modelo bi-temporal y
borrado lógico únicamente (no existe DELETE físico en ninguna capa).

> Fuente de las afirmaciones de esta página: `AGENTS.md` (raíz del repo),
> `modelo_datos_er.mmd` (raíz del repo) y el código en `backend/` y `apps/`,
> verificados en esta sesión de documentación (2026-09-10).

## Para quién

| Perfil | Aplicación | Estado |
|---|---|---|
| Administrador de la red de parqueaderos (multi-sucursal) | `apps/web_admin` | Construido parcialmente — ver [roadmap](./roadmap.md) |
| Operador de sucursal (cajero / kiosko) | `web_sucursal` | **Roadmap / futuro** — no existe en el repo hoy |

El operador de sucursal aparece en los documentos de planeación temprana
(`openspec/PROJECT_CONTEXT.md`) como usuario objetivo de `web_sucursal`,
`cajero` y `kiosko`, pero ninguna de esas aplicaciones tiene código en el
repositorio actual. Hoy solo existe la vía de administración (`web_admin`).

## Topología

```
web_admin <-> api_admin <-> job_sync_cloud <-> job_sync_sucursal <-> api_sucursal <-> web_sucursal
                                  |                                        |
                            Postgres (cloud)                    Postgres (sucursal, uno por sucursal)
```

Diagramas detallados (componentes, despliegue, secuencia de sync, etc.):
[`../02-arquitectura/diagramas-uml/`](../02-arquitectura/diagramas-uml/).

## Cómo se compone

### Backend

- **Stack**: Python 3.13, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2,
  Alembic. Workspace `uv` en `backend/`, paquetes
  `backend/packages/{parkos_core,api_admin,api_sucursal}`.
- `parkos_core` concentra:
  - Modelos ORM particionados por nivel de auditoría: `models/V` (versionado
    bi-temporal), `models/L_E` (eventos), `models/L_W` (workflows),
    `models/L_S` (sesiones), `models/A` (append-only / fuente de verdad).
  - Routers de negocio en `api/v1/`: `auth`, `sucursal`, `pairing`,
    `catalogos`, `configuracion`, `empresa`, `operacion`, `facturacion`,
    `caja`, `caja_sesion`, `workflows`, `clientes`, `admin_views`,
    `sync_router`.
  - El motor de sincronización (`sync/`, incluyendo el catálogo declarativo
    `sync/catalog/`) y el despachador DIAN (`dian/`).
  - Los jobs de sincronización (`jobs/sync_cloud.py`, `jobs/sync_sucursal.py`).
- Referencia de stack y decisiones: [`../02-arquitectura/decisiones-tecnicas.md`](../02-arquitectura/decisiones-tecnicas.md).
  Referencia de endpoints: [`../03-desarrollo/api-reference.md`](../03-desarrollo/api-reference.md).

### Frontend

- `apps/web_admin` — React 18 + Vite + TypeScript + Tailwind + shadcn/ui.
  Hoy tiene dos páginas construidas: `Login` (placeholder explícito en el
  código) y `Dashboard` (selector de sucursal + métricas reales por
  sucursal).
- `apps/ui-kit` — cliente de API compartido para las apps del monorepo. El
  scaffold existe (`src/api/{admin,branch}/generated/`), pero la generación
  del cliente todavía no corrió: ambas carpetas solo contienen un
  `.gitkeep`.
- `web_sucursal`, `cajero`, `kiosko`, `admin-cfg` — mencionados como PWAs
  objetivo en la planeación temprana, **no existen en el repo hoy**.
  Roadmap / futuro.
- Estándares y setup: [`../03-desarrollo/setup.md`](../03-desarrollo/setup.md),
  [`../03-desarrollo/estandares.md`](../03-desarrollo/estandares.md).

### Infraestructura

- Docker Compose para ambos entornos (`docker-compose.cloud.yml`,
  `docker-compose.branch.yml`) a partir de un único `Dockerfile` multi-stage.
- Manual operativo: [`../05-manuales/operaciones.md`](../05-manuales/operaciones.md).
- Runbooks operativos del motor de sync (8 documentos ya existentes, fuera
  del alcance de esta sección): [`../runbooks/sync/`](../runbooks/sync/).

## Modelo de datos y cumplimiento

- Fuente de verdad: `modelo_datos_er.mmd` (raíz del repo) — 51 entidades
  documentadas + 3 tablas non-ER intencionales (`idempotency_keys`,
  `pairing_tokens`, `revoked_sync_jwts`) = **54 tablas físicas** en el
  esquema `prod`. Verificado en esta sesión con
  `openspec/scripts/check_schema_match.py`: coincidencia del 100% contra las
  bases reales, sin drift.
- Compliance DIAN Colombia: facturación electrónica, retención 5+ años,
  cadena de hash SHA-256 (`hash_anterior`/`hash_actual`), modelo bi-temporal
  con borrado lógico únicamente.
- Detalle completo: [`../02-arquitectura/modelo-datos.md`](../02-arquitectura/modelo-datos.md).
  Seguridad y JWT: [`../02-arquitectura/seguridad.md`](../02-arquitectura/seguridad.md).

## Estado actual (resumen)

El backend está considerablemente más avanzado que el frontend: la mayoría
de los routers de negocio existen y el motor de sincronización fue
reescrito por completo en el cambio `sync-overhaul`. El frontend
`web_admin` tiene solo dos páginas construidas, y `web_sucursal` no existe.

- Detalle iteración por iteración, con evidencia de código: [`roadmap.md`](./roadmap.md).
- Historial de cambios derivado de `git log`: [`changelog.md`](./changelog.md).

## Mapa de la documentación

| Sección | Contenido | Ruta |
|---|---|---|
| General | Visión general (esta página), roadmap, changelog | `.` |
| Requisitos | Historias de usuario, requisitos funcionales y no funcionales | [`../01-requisitos/`](../01-requisitos/) |
| Arquitectura | Decisiones técnicas, modelo de datos, seguridad, diagramas UML | [`../02-arquitectura/`](../02-arquitectura/) |
| Desarrollo | Setup del entorno, estándares de código, referencia de API | [`../03-desarrollo/`](../03-desarrollo/) |
| QA / Testing | Plan de pruebas, casos de prueba | [`../04-qa-testing/`](../04-qa-testing/) |
| Manuales | Manual de usuario final, manual de operaciones | [`../05-manuales/`](../05-manuales/) |
| Runbooks de sync | 8 runbooks operativos del motor de sincronización (ya existentes) | [`../runbooks/sync/`](../runbooks/sync/) |

## Convenciones del repositorio

- **Git**: gitflow — `main` (producción) + `dev` (integración) + ramas
  feature; los PR mergean a `dev`, nunca directo a `main`.
- **Commits**: Conventional Commits, sin `Co-Authored-By` ni atribución de
  IA (ver [`changelog.md`](./changelog.md) para el historial derivado).
- No hay `README.md` ni `pyproject.toml` en la raíz del repositorio; sí
  existen `backend/pyproject.toml` y un `pyproject.toml` por paquete
  (`parkos_core`, `api_admin`, `api_sucursal`).
- No hay tags de versión publicados (`git tag` vacío) — ver
  [`changelog.md`](./changelog.md) para la convención real observada.
