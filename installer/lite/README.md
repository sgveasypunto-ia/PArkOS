# Parkos LITE (demo / pruebas de usuario)

Sucursal completa en una maquina Windows, **sin Docker, sin servicios de
Windows, sin Electron, sin elevacion y sin conectividad al correr**:

- Postgres 16 local (proceso de usuario, rearmado desde las partes versionadas en el repo)
- `api-sucursal.exe` (PyInstaller; restaurado de las partes del repo, o compilado con `installer\build-release.ps1 -ApiSucursal -Migrate` solo si `backend/` cambio)
- front React de la sucursal servido por Vite en el navegador (no Electron)
- sin job de sync (la `sync_queue` simplemente crece), con datos de demo

Casi todo sale del propio repo (`installer\payload\parts`, versionado en git):
Postgres, pg_partman, `api-sucursal`/`migrate` y las herramientas portatiles
(git, uv, node, pnpm). Internet se necesita **solo** para las dependencias del
front (`pnpm install`), `git pull` y para recompilar la API si `backend/` cambio
respecto de lo versionado. Ya instalado, todo corre offline.

Manual completo (testers y soporte): [MANUAL.md](MANUAL.md).

## Requisitos

Solo Windows (PowerShell 5.1 o pwsh 7). Sin admin y sin winget. **Internet solo para
`pnpm install` del front** (registro npm, 1 a 5 minutos la primera vez); todo lo demas
viene en el repo.

El paso 10 (parte de la opcion 1) usa `git`, `uv`, `node` (>= 20) y `pnpm` (>= 10) del
sistema si ya son compatibles; si no, las toma **de las partes versionadas en el repo**
(`installer\payload\parts\tools-*`) y las deja como copias portatiles en `<LITE>\tools\`
(solo las ve el lite; no se toca el PATH ni el registro). Solo si faltan o no coinciden las
partes, las descarga. Orden de cada herramienta: **PATH compatible -> partes del repo -> descarga**.

| Herramienta | Version fijada | Del repo (id) | Si no, descarga | Verificacion |
|---|---|---|---|---|
| Node.js | 22.23.3 | `tools-node` (zip, 35,6 MB) | nodejs.org/dist | SHA-256 **fijado** (tabla de `ParkosLite.Tools.ps1`); la descarga ademas se contrasta con `SHASUMS256.txt` |
| pnpm | 10.0.0 (`packageManager` de `apps/`) | `tools-pnpm` (carpeta portatil, 5,1 MB) | `npm install -g --prefix tools\pnpm` | hash del manifest (la descarga: integridad npm) |
| uv | 0.12.23 | `tools-uv` (zip, 18,0 MB) | GitHub astral-sh/uv | SHA-256 **fijado** (+ asset `.sha256` si se descarga) |
| Git (MinGit) | 2.56.0.2 | `tools-mingit` (zip, 39,8 MB) | GitHub git-for-windows | SHA-256 **fijado** (digest del release) |

Python 3.13 (que baja `uv`) **no** esta versionado: solo se necesita para compilar los exe
(ruta de respaldo, ver "Bajar cambios"). En una instalacion normal no se usa.

Para quitarlas: borrar `<LITE>\tools` y correr la opcion 10. Detalle en [MANUAL.md](MANUAL.md#3-requisitos-previos).

## Como correrlo

```powershell
powershell -ExecutionPolicy Bypass -File installer\lite\parkos-lite.ps1
```

Elige la opcion **1** (Instalar todo, guiado) y al final abre la URL que imprime.
Parametros utiles: `-LitePath`, `-SourceBranch` (default `dev`), `-PgPort`,
`-ApiPort`, `-FrontPort` (0 = automatico: Postgres desde 5433, API desde 8100,
front desde 5173; si el puerto esta ocupado toma el siguiente libre).

## Menu

Una sola lista numerada (escribe el numero y Enter; `0` o `Q` sale):

| Grupo | Opcion | Accion |
|---|---|---|
| PRIMERA VEZ | 1 | Instalar todo (guiado): hace los pasos 10 a 15 solo y luego inicia todo. Si se corta, vuelve a elegir 1: retoma donde quedo |
| USO DIARIO | 2 | Iniciar todo (DB + API + front) |
| | 3 | Detener todo |
| | 4 | Reiniciar |
| | 5 | Estado |
| | 6 | Abrir el navegador |
| | 7 | Bajar cambios de `dev` y reiniciar |
| | 8 | Ver logs |
| | 9 | Arranque automatico de la base de datos |
| AVANZADO (paso a paso, en este orden) | 10 | Preparar entorno (herramientas, UUID de sucursal, puertos, passwords y llave JWT descartables) |
| | 11 | Instalar base de datos (rearma Postgres y pg_partman desde las partes del repo, initdb, roles, arranque automatico) |
| | 12 | API (.exe + migrate.exe): los restaura de las partes del repo (segundos) o, solo si `backend/` cambio, los compila (varios minutos) |
| | 13 | Migrar base de datos (`alembic upgrade head`) |
| | 14 | Cargar datos de demo (`seed_demo.sql`, re-ejecutable) |
| | 15 | Instalar dependencias del front (`pnpm install --ignore-scripts`, sin bajar Electron) |
| | 0 | Salir |

Los pasos 10 a 15 y "Iniciar todo" llevan una etiqueta de estado:
`[ OK ]`, `[FAIL]`, `[BLOQ]` (indica cual correr primero) o `[....]` (pendiente).
Una entrada invalida imprime `Opcion no valida, elige un numero de la lista` y
vuelve a mostrar el menu.

Cada paso depende del anterior (`[BLOQ]` indica cual correr primero). El estado
real se verifica probando (archivos, puertos, consultas), no solo con
`state.json`.

## Datos de demo

Usuarios (rol `operador`, solo para pruebas locales): `demo.operador@parkos.local`
y `demo.operador2@parkos.local`, clave **`Demo1234`**. Sucursal "Sucursal Demo",
tipos de vehiculo carro/moto/bicicleta/patineta con tarifas hora/fraccion/plena/
nocturna en COP, resolucion de facturacion de demo (prefijo DEMO), config de
caja y cupos. El seed nunca borra ni pisa: solo inserta lo que falta.

## Bajar cambios (opcion 7)

Detiene todo, `git fetch` + `git pull --ff-only` de `-SourceBranch` (se niega si
hay cambios locales en archivos versionados), reconstruye el exe **solo si
cambio `backend/` o `installer/bootstrap/`**, migra, `pnpm install` solo si
cambio un `package.json`/lockfile de `apps/`, re-siembra y arranca. Si el pull
falla, vuelve a arrancar la version anterior.

La decision de la API se recalcula tras el pull con `Get-ParkosPartsArtifactDecision`
(commit `builtFromCommit` de `installer\payload\parts\payload-parts.json` contra el
arbol de trabajo): si `backend/` e `installer/bootstrap/` no cambiaron desde ese commit se
**restauran** las partes (sin uv ni Python); si cambiaron (y las partes del repo aun no se
re-empaquetaron) el lite lo dice (`No se restaura la API desde el repositorio: ...`) y
**compila** (necesita uv/Python e Internet, 3 a 10 minutos). Si git no esta disponible o el
repo no trae las partes, compila como antes.

## Arranque automatico (opcion 9)

Por defecto, al activar la base de datos se crea la **tarea programada de
usuario `ParkosLiteDb`** (disparador *al iniciar sesion*, sin admin) que ejecuta
`parkos-lite.ps1 -Action StartDb` oculto: limpia un `postmaster.pid` huerfano
(solo si ningun postgres lo posee), hace `pg_ctl start -w` y espera a que acepte
conexiones. Si no se puede crear la tarea cae a la clave `HKCU\...\Run`.
Opcional: iniciar tambien API y front (`-Action StartAll`), o, **solo si el TUI
corre como administrador**, un servicio de Windows (`pg_ctl register`).
Re-activar reemplaza, nunca duplica; desactivar quita tarea, clave y servicio.

## De donde sale cada componente (orden de busqueda) e integridad

Regla: **primero el repo (`installer\payload\parts`), despues la cache, y solo al final la
red / la compilacion.**

| Componente | 1) Repo (partes) | 2) Respaldo | Verificacion |
|---|---|---|---|
| Postgres `16.15-1` (EDB) | `parts\postgres` (4 partes + `.sha256`), se rearma en `<LITE>\downloads` | cache `<LITE>\downloads`, luego descarga de EDB (3 intentos) | hash del `.sha256` versionado; el zip debe traer `pg_ctl/initdb/psql` |
| pg_partman `5.1.0` SQL-only | `parts\pg_partman-extension` -> `<LITE>\downloads\pg_partman\extension` | descarga de GitHub y ensamblado SQL-only | hash del manifest |
| `api-sucursal.exe` y `migrate.exe` | `parts\api-sucursal`, `parts\migrate` -> `installer\payload\services\` si `backend/` e `installer/bootstrap/` no cambiaron desde `builtFromCommit` | `build-release.ps1 -ApiSucursal -Migrate` (PyInstaller; necesita uv/Python e Internet) | hash del manifest; log `API restaurada desde el repositorio (commit xxxxxxx)` |
| git, uv, node, pnpm | `parts\tools-*` (ver Requisitos) | descarga | SHA-256 fijado / manifest |

El lite **nunca** restaura `powershell7-msi`, `nssm`, `web-sucursal-msi`, `doctor`, `seed` ni
`job-sync-sucursal` (son del instalador completo). Una parte danada o de otra version no rompe
la instalacion: se avisa y se cae al respaldo (descarga o compilacion); la excepcion es Postgres:
unas partes de Postgres defectuosas dan un error claro (`git checkout -- installer/payload/parts`)
en lugar de bajar en silencio otra copia.

Postgres: EnterpriseDB no publica SHA-256 oficial; el hash del `.sha256` versionado se compara
al rearmar. Si el zip viene de la descarga, el hash calculado en la primera descarga se guarda
en `<zip>.sha256` y se compara en cada reuso. Si no hay red, el TUI imprime la URL y la carpeta
donde dejar el archivo; el paso es re-ejecutable. La logica vive en
`installer\shared\ParkosPostgresDownload.ps1` y `installer\shared\ParkosPayloadParts.ps1`
(compartidas con el instalador completo).

**Que sigue necesitando Internet** despues de este cambio: (1) `pnpm install` de las
dependencias del front (`node_modules` no se versiona; el registro npm es obligatorio la primera
vez); (2) recompilar la API cuando `backend/` cambio respecto de las partes versionadas (uv baja
Python 3.13 y las dependencias de `backend/`); (3) `git pull` (opcion 7). Nada mas.

**Refrescar las partes del repo** (para el mantenedor): tras cambiar `backend/` o
`installer/bootstrap/`, `pwsh -File installer\build-release.ps1 -ApiSucursal -Migrate` y luego
`pwsh -File installer\tools\Pack-ParkosPayload.ps1 -Ids api-sucursal,migrate` (actualiza
`builtFromCommit`; versionar `installer\payload\parts`). Si sube la version de una herramienta
en `ParkosLite.Tools.ps1`, re-empaquetar `tools-*` con `Pack-ParkosPayloadArtifact` (ver
`installer\MANUAL.md`, seccion 5.4) para que el nombre y el SHA-256 coincidan con la tabla.

## Donde queda todo

`%LOCALAPPDATA%\ParkosLite` (fuera del repo): `pgsql\`, `data\` (datos de
Postgres, `api.env` sin cifrar, `secrets.json`, llave JWT), `logs\`, `run\`
(pids), `downloads\`, `state.json`. Para empezar de cero: opcion 3 (Detener todo), quitar el
arranque automatico (opcion 9) y borrar esa carpeta.

## Problemas comunes

- **Puerto ocupado**: se elige otro automaticamente; mira la opcion 5 (Estado).
- **La API no arranca**: opcion 8 (Ver logs) -> `api.err.log` / `api.out.log`.
- **`pg_ctl start` falla**: opcion 8 (Ver logs) -> `postgres.log`.
- **Pull rechazado**: hay cambios locales o la rama diverge; resuelve con git.
- **`pnpm`**: el lite instala con `--frozen-lockfile`, asi que el
  `apps/pnpm-lock.yaml` del repo es la fuente de verdad (instalacion
  reproducible, sin tocar el arbol git). Si falla con
  `ERR_PNPM_OUTDATED_LOCKFILE`, el lockfile no coincide con los `package.json`
  y hay que regenerarlo en el repo (`pnpm install --lockfile-only`).

## Limitaciones

- Sin sync ni conectividad: `sync_queue` crece, nada se envia a la nube ni a la DIAN.
- La impresion es un no-op en el navegador (shim `window.bridge` solo cuando no
  existe el de Electron, ver `apps/electron-sucursal/src/renderer/lib/browserBridge.ts`).
- Passwords y llave JWT son descartables y estan en texto plano en la carpeta
  del lite: es un entorno de demo, no de produccion.
- Los UUID de `carro/bicicleta/patineta` se siembran aqui porque las migraciones
  solo crean `moto` y `otro` (el resto llega normalmente por sync desde el admin).
