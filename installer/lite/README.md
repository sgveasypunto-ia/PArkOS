# Parkos LITE (demo / pruebas de usuario)

Sucursal completa en una maquina Windows, **sin Docker, sin servicios de
Windows, sin Electron, sin elevacion y sin conectividad al correr**:

- Postgres 16 local (proceso de usuario, descargado por el propio TUI)
- `api-sucursal.exe` (PyInstaller, via `installer\build-release.ps1 -ApiSucursal -Migrate`)
- front React de la sucursal servido por Vite en el navegador (no Electron)
- sin job de sync (la `sync_queue` simplemente crece), con datos de demo

Internet se necesita **solo al instalar o al bajar cambios** (Postgres,
pg_partman, `git pull`, `pnpm`/`uv`). Ya instalado, todo corre offline.

Manual completo (testers y soporte): [MANUAL.md](MANUAL.md).

## Requisitos

Solo Windows (PowerShell 5.1 o pwsh 7) e internet **durante la instalacion**. Sin admin y sin winget.
El paso 10 (parte de la opcion 1) usa `git`, `uv`, `node` (>= 20) y `pnpm` (>= 10) del sistema si ya
son compatibles; si no, descarga copias portatiles a `<LITE>\tools\` (solo las ve el lite; no se toca
el PATH ni el registro de la maquina). Sin internet: el mensaje dice la URL y donde dejar el archivo
en `<LITE>\downloads`; luego repetir la opcion 10.

| Herramienta | Version fijada | Origen | Verificacion |
|---|---|---|---|
| Node.js | 22.23.3 | nodejs.org/dist (zip, ~30 MB) | SHA-256 fijado + `SHASUMS256.txt` |
| pnpm | 10.0.0 (`packageManager` de `apps/`) | `npm install -g --prefix tools\pnpm` | integridad npm |
| uv | 0.12.23 | GitHub astral-sh/uv (zip, ~18 MB) | SHA-256 fijado + asset `.sha256` |
| Git (MinGit) | 2.56.0.2 | GitHub git-for-windows (zip, ~40 MB) | SHA-256 fijado (digest del release) |

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
| | 11 | Instalar base de datos (descarga Postgres, initdb, roles, pg_partman, arranque automatico) |
| | 12 | Construir API (.exe + migrate.exe, varios minutos) |
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

## Arranque automatico (opcion 9)

Por defecto, al activar la base de datos se crea la **tarea programada de
usuario `ParkosLiteDb`** (disparador *al iniciar sesion*, sin admin) que ejecuta
`parkos-lite.ps1 -Action StartDb` oculto: limpia un `postmaster.pid` huerfano
(solo si ningun postgres lo posee), hace `pg_ctl start -w` y espera a que acepte
conexiones. Si no se puede crear la tarea cae a la clave `HKCU\...\Run`.
Opcional: iniciar tambien API y front (`-Action StartAll`), o, **solo si el TUI
corre como administrador**, un servicio de Windows (`pg_ctl register`).
Re-activar reemplaza, nunca duplica; desactivar quita tarea, clave y servicio.

## Descargas e integridad

Postgres `16.15-1` (EnterpriseDB) se baja a `<lite>\downloads` (se usa antes
`installer\payload\postgres\` si ya hay un zip). Descarga a `.part`, 3 intentos
con espera creciente, valida que el zip traiga `pg_ctl/initdb/psql`. EnterpriseDB
no publica un SHA-256 oficial: el hash calculado en la primera descarga se guarda
en `<zip>.sha256` y se compara en cada reuso. pg_partman `5.1.0` se descarga de
GitHub y se ensambla SQL-only (igual que `build-release.ps1`) salvo que exista
`installer\payload\pg_partman\extension`. Si no hay red, el TUI imprime la URL y
la carpeta donde dejar el archivo; el paso es re-ejecutable. Esta logica vive en
`installer\shared\ParkosPostgresDownload.ps1` (compartida con el instalador completo).

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
- **`pnpm`**: el lockfile del repo puede ir desfasado; el lite instala con
  `--lockfile=false` para no ensuciar el arbol git.

## Limitaciones

- Sin sync ni conectividad: `sync_queue` crece, nada se envia a la nube ni a la DIAN.
- La impresion es un no-op en el navegador (shim `window.bridge` solo cuando no
  existe el de Electron, ver `apps/electron-sucursal/src/renderer/lib/browserBridge.ts`).
- Passwords y llave JWT son descartables y estan en texto plano en la carpeta
  del lite: es un entorno de demo, no de produccion.
- Los UUID de `carro/bicicleta/patineta` se siembran aqui porque las migraciones
  solo crean `moto` y `otro` (el resto llega normalmente por sync desde el admin).
