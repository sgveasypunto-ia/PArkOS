# Parkos LITE (demo / pruebas de usuario)

Sucursal completa en una maquina Windows, **sin Docker, sin servicios de
Windows, sin Electron, sin elevacion y sin conectividad al correr**:

- Postgres 16 local (proceso de usuario, descargado por el propio TUI)
- `api-sucursal.exe` (PyInstaller, via `installer\build-release.ps1 -ApiSucursal -Migrate`)
- front React de la sucursal servido por Vite en el navegador (no Electron)
- sin job de sync (la `sync_queue` simplemente crece), con datos de demo

Internet se necesita **solo al instalar o al bajar cambios** (Postgres,
pg_partman, `git pull`, `pnpm`/`uv`). Ya instalado, todo corre offline.

## Requisitos

`git`, `uv`, `node` (LTS) y `pnpm`. El paso 1 del TUI dice que falta y como
instalarlo (`winget install ...`). Funciona con Windows PowerShell 5.1 o pwsh 7.

## Como correrlo

```powershell
powershell -ExecutionPolicy Bypass -File installer\lite\parkos-lite.ps1
```

Pulsa **G** (instalar todo, guiado) y al final abre la URL que imprime.
Parametros utiles: `-LitePath`, `-SourceBranch` (default `dev`), `-PgPort`,
`-ApiPort`, `-FrontPort` (0 = automatico: Postgres desde 5433, API desde 8100,
front desde 5173; si el puerto esta ocupado toma el siguiente libre).

## Menu

| Tecla | Accion |
|---|---|
| 1 | Preparar entorno (herramientas, UUID de sucursal, puertos, passwords y llave JWT descartables) |
| 2 | Instalar base de datos (descarga Postgres, initdb, roles, pg_partman, arranque automatico) |
| 3 | Construir API (.exe + migrate.exe, varios minutos) |
| 4 | Migrar base de datos (`alembic upgrade head`) |
| 5 | Cargar datos de demo (`seed_demo.sql`, re-ejecutable) |
| 6 | Instalar dependencias del front (`pnpm install --ignore-scripts`, sin bajar Electron) |
| 7 / 8 / 9 | Iniciar todo / Detener todo / Estado |
| G | Instalar todo (pasos 1-7) |
| B | Bajar cambios de `dev` y reiniciar |
| R / L / O | Reiniciar / Ver logs / Abrir navegador |
| A | Arranque automatico de la base de datos |

Cada paso depende del anterior (`[BLOQ]` indica cual correr primero). El estado
real se verifica probando (archivos, puertos, consultas), no solo con
`state.json`.

## Datos de demo

Usuarios (rol `operador`, solo para pruebas locales): `demo.operador@parkos.local`
y `demo.operador2@parkos.local`, clave **`Demo1234`**. Sucursal "Sucursal Demo",
tipos de vehiculo carro/moto/bicicleta/patineta con tarifas hora/fraccion/plena/
nocturna en COP, resolucion de facturacion de demo (prefijo DEMO), config de
caja y cupos. El seed nunca borra ni pisa: solo inserta lo que falta.

## Bajar cambios (opcion B)

Detiene todo, `git fetch` + `git pull --ff-only` de `-SourceBranch` (se niega si
hay cambios locales en archivos versionados), reconstruye el exe **solo si
cambio `backend/` o `installer/bootstrap/`**, migra, `pnpm install` solo si
cambio un `package.json`/lockfile de `apps/`, re-siembra y arranca. Si el pull
falla, vuelve a arrancar la version anterior.

## Arranque automatico (opcion A)

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
(pids), `downloads\`, `state.json`. Para empezar de cero: opcion 8, quitar el
arranque automatico (A) y borrar esa carpeta.

## Problemas comunes

- **Puerto ocupado**: se elige otro automaticamente; mira la opcion 9.
- **La API no arranca**: `L` -> `api.err.log` / `api.out.log`.
- **`pg_ctl start` falla**: `L` -> `postgres.log`.
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
