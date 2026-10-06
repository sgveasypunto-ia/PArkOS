# Manual del instalador Parkos (sucursal)

Este documento describe, con fidelidad al código fuente actual del repositorio, el funcionamiento del instalador de la sucursal Parkos: `installer/parkos-installer.ps1`, el módulo de ciclo de vida `installer/payload/management/Parkos.psm1`, el orquestador de build `installer/build-release.ps1` y la herramienta de soporte `installer/tools/Get-ParkosSupportPassword.ps1`.

Convenciones usadas en este documento:

- Los bloques de código con mensajes de error son **copias literales** del texto que lanza el código (interpolaciones de variables como `$Port` se muestran tal cual aparecen en la fuente).
- Las referencias `DEC-INST-NN` citan decisiones de arquitectura documentadas en `plan.md`, sección "0.2 Decisiones de arquitectura del instalador" — no se repite aquí el contenido completo de cada una, solo la decisión relevante al punto que se describe.
- Donde el comportamiento no pudo confirmarse leyendo el código de este repositorio, se marca explícitamente como **comportamiento no verificado**.

---

## 1. Visión general

El instalador despliega, en una máquina Windows de una sucursal (sin Docker), el stack completo de Parkos:

- **PostgreSQL 16** (vía `winget`, con fallback a un ZIP oficial de EDB — DEC-INST-03).
- **`pg_partman`** como extensión SQL-only (sin background worker compilado), con mantenimiento de particiones disparado por una tarea programada de Windows (DEC-INST-13/14).
- **`api-sucursal`** y **`job-sync-sucursal`**: dos binarios Python congelados (PyInstaller `--onedir`), registrados como servicios de Windows vía **NSSM** (DEC-INST-09).
- **`web_sucursal`**: app de escritorio Electron, instalada vía MSI silencioso.
- **Módulo de gestión `Parkos`**: paquete PowerShell separado para operación post-instalación (diagnóstico, reparación, backups, desinstalación).

### Rutas por defecto

| Variable | Valor por defecto | Contenido |
|---|---|---|
| `-InstallPath` | `C:\Program Files\Parkos` | Binarios de los servicios, `releases\` archivadas, `nssm.exe`, `doctor\` |
| `-DataPath` | `C:\ProgramData\Parkos` | Datos de Postgres (solo instalación vía ZIP), secretos, logs, backups, scripts generados |
| (fijo, no parametrizable) | `C:\Program Files\PostgreSQL\16` | Instalación de PostgreSQL (winget o ZIP convergen en esta misma ruta) |
| (fijo) | `C:\Program Files\PowerShell\Modules\Parkos\1.0.0\` | Módulo de gestión `Parkos` instalado al final de la etapa 8 |

### Qué queda corriendo al final de una instalación completa

- Servicios Windows (NSSM): `ParkosApiSucursal`, `ParkosJobSyncSucursal` (más el servicio nativo de PostgreSQL, nombre resuelto dinámicamente por patrón `*postgresql*`).
- Tareas programadas: `ParkosPgPartmanMaintenance` (diaria, 2:00 a.m.) y, si el operador ejecutó la opción `M` del menú, `ParkosBackupDiario` (diaria, por defecto 03:00).
- Cuenta local de Windows `svc-parkos` (sin privilegios interactivos, usada como `ServiceAccount` de las tareas programadas).
- Certificado de máquina `CN=ParkosEnvProtection` en `Cert:\LocalMachine\My` (cifra el `.env` en reposo).
- App de escritorio `web_sucursal` instalada vía MSI.
- Módulo PowerShell `Parkos` instalado para gestión posterior.

### Diagrama de carpetas (texto)

```
C:\Program Files\Parkos\                        (InstallPath)
├── api-sucursal\                               (bundle onedir + api-sucursal.exe)
├── job-sync-sucursal\                          (bundle onedir + job-sync-sucursal.exe)
├── doctor\                                     (bundle onedir; copiado por Install-ManagementModule)
├── nssm.exe                                    (copiado por Install-ManagementModule)
└── releases\<version>\                         (escrito por Invoke-ParkosUpdate/REPLACE)
    ├── api-sucursal\
    ├── job-sync-sucursal\
    └── apps\<nombre-original>.msi               (solo versiones archivadas después de DEC-INST-28)

C:\Program Files\PostgreSQL\16\                 (ruta fija, independiente de -InstallPath)
├── bin\ (psql.exe, pg_dump.exe, pg_restore.exe, initdb.exe)
├── share\extension\                            (pg_partman--5.1.0.sql + .control)
└── data\ (o la que decida el instalador de EDB/winget — ver Limitaciones, §10.9)

C:\ProgramData\Parkos\                          (DataPath)
├── pg-data\                                    (datos de Postgres — SOLO si se instaló vía ZIP; ver §10.9)
├── secrets\                                    (ACL restringida a Administrators+SYSTEM)
│   ├── .env                                    (cifrado CMS, certificado CN=ParkosEnvProtection)
│   ├── jwt.key                                 (64 bytes aleatorios, firma JWT)
│   ├── sync-agent.jwt                          (no la crea este instalador — la escribe el flujo de pairing, Fase 29)
│   ├── pgpass.conf                              (credenciales formato .pgpass, ACL propia)
│   └── env-cert-thumbprint.txt                 (thumbprint del certificado, solo diagnóstico)
├── logs\
│   ├── api-sucursal.out.log / api-sucursal.err.log
│   ├── job-sync.out.log                        (job-sync-sucursal NUNCA tiene .err.log — ver §10)
│   ├── seed-api.out.log / seed-api.err.log     (proceso temporal de la etapa 4)
│   ├── electron-install.log
│   └── module.log                              (log del módulo Parkos, best-effort)
├── backups\
│   ├── pre-update-<versionSaliente>-<versionNueva>.dump
│   ├── pre-restore-<Version>-<timestamp>.dump
│   └── daily\backup-<timestamp>.dump           (retención abuelo-padre-hijo 7+4+1)
├── scripts\Invoke-DailyBackup.ps1              (generado por Register-ParkosBackupTask)
├── installer-runs\<timestamp>.log              (log estructurado de la cascada -Unattended)
├── manifest.sha256.json                        (hashes SHA256 de los binarios instalados)
├── current-version.txt                         (una línea, timestamp de la última actualización exitosa)
├── auto-update-paused.flag                     (informacional; nada lo lee hoy — ver §10)
└── pairing.json                                (leído por Test-Preflight y por el módulo al importarse;
                                                  no lo escribe ningún código de este repositorio — ver §10)
```

---

## 1bis. Flujo guiado (por defecto)

Ejecutar el instalador **sin ningún switch** (`parkos-installer.exe` o `pwsh .\parkos-installer.ps1`) inicia el flujo guiado, pensado para el operador de la sucursal: solo ejecuta pasos y escribe un único dato, el **UUID de la sucursal**. El menú de 9 etapas ya no es el comportamiento por defecto: se abre únicamente con `-Menu` (uso técnico). `-Menu` y `-Unattended` son incompatibles (`exit 2`).

### Qué hace el flujo guiado, en orden

1. `Invoke-ParkosGuidedInstall`: `Ensure-PowerShell7` + `Request-Elevation`. El relanzo (PowerShell 7 / administrador) **conserva todos los parámetros con nombre**: se reconstruyen desde `$PSBoundParameters` y se reenvían con `-EncodedCommand` (con `-File` los arreglos como `-SkipStage 2,7` llegaban aplanados como `27`). Las rutas `-MasterKeyPath` y `-PayloadPath` se convierten a absolutas porque el proceso elevado arranca en otro directorio.
2. `Invoke-ParkosUnattendedCascade -Guided`:
   - Verifica que el **payload esté compilado** (`Test-ParkosPayloadReady`). Si no, termina con `exit 2` **antes de pedir nada** y pide un instalador completo a soporte.
   - **Pre-flight** (ver abajo), con la clave maestra como requisito duro.
   - **EULA**: se muestra y se acepta con **Enter** (`-EulaAccepted` lo omite). Escribir `N` cancela sin cambios.
   - **Rutas**: nunca se preguntan. Se usan `C:\Program Files\Parkos` y `C:\ProgramData\Parkos`, o `-InstallPath` / `-DataPath` si se pasaron (se siguen rechazando `C:\Windows`, `Program Files (x86)` y rutas UNC).
   - **UUID de la sucursal**: único dato que se escribe. Forma estricta 8-4-4-4-12 hexadecimal; se toleran espacios alrededor y mayúsculas (se normaliza a minúsculas). Se vuelve a preguntar hasta **5 veces**; luego falla con `Demasiados intentos ...`. También puede venir por `-SucursalUuid`.
   - Corre las etapas **1 a 8** mostrando `Paso N de M: <descripción en lenguaje llano>`. La **etapa 0** (git/pnpm/uv + build) **no corre** salvo `-IncludeBuild`; como el payload ya está compilado, la etapa 0 cuenta como `Ok` (los prerequisitos de las etapas 1 y 7 se cumplen).
   - Si una etapa falla: se detiene, hace **rollback automático de esa etapa** y explica qué hacer (enviar el archivo de registro a soporte). Exit codes: `0` completo, `1` etapa fallida, `2` configuración/pre-flight inválidos.
3. Al terminar, la ventana espera Enter para que el operador pueda leer el resultado.

El registro de cada corrida queda en `$DataPath\installer-runs\<timestamp>.log`.

### URL del servidor (cloud)

Nunca se pregunta. Orden de resolución (`Resolve-ParkosCloudApiUrl`): parámetro `-CloudApiUrl` > variable de entorno `PARKOS_CLOUD_API_URL` (proceso, luego máquina, luego usuario) > `http://localhost:8000`. Debe ser `http://` o `https://`; si no, el instalador falla (`exit 2`) nombrando `PARKOS_CLOUD_API_URL`. La barra final se elimina.

### Pre-flight del flujo guiado

Además de las verificaciones de la sección 2:

- **Conectividad**: se mide `host:puerto` de la URL del cloud (`Test-NetConnection`), **no** `github.com:443`. Si el servidor es el propio equipo (`localhost`/`127.0.0.1`) y no responde, solo se imprime `[AVISO]` (puede no estar encendido todavía) y la instalación continúa; si es remoto y no responde, **bloquea** con `[FALLO] Conexion con el servidor Parkos`.
- **Clave maestra** (`payload\security\parkos-master.key`, >= 32 bytes): es el **único requisito duro** del flujo guiado. Sin ella el pre-flight **bloquea** con `[FALLO] Clave maestra de Parkos` y el mensaje accionable (pedirla a soporte por un canal seguro y copiarla a esa ruta, o usar `-MasterKeyPath`). En `-Menu` solo avisa. El instalador **nunca genera** claves.

### Tabla de errores frecuentes (lo que ve el operador)

| Qué ve el operador | Qué significa | Qué hacer |
|---|---|---|
| `Este instalador no trae los programas ya preparados ...` (exit 2) | El payload no está compilado | Pedir un instalador completo a soporte (o, en la máquina del técnico, correr con `-IncludeBuild`) |
| `[FALLO] Clave maestra de Parkos` | Falta `parkos-master.key` o es demasiado corta | Pedir la clave a soporte y copiarla a la ruta indicada |
| `[FALLO] Conexion con el servidor Parkos` | El servidor remoto no responde | Revisar red/internet y la variable `PARKOS_CLOUD_API_URL`; reintentar |
| `[AVISO] No se pudo contactar al servidor Parkos en localhost:8000` | El servidor local no está encendido o es otro equipo | No bloquea; si el servidor está en otro equipo, definir `PARKOS_CLOUD_API_URL` |
| `[FALLO] Permisos de administrador` | No se concedió el UAC | Volver a ejecutar y aceptar el aviso de permisos |
| `Demasiados intentos con un codigo de sucursal invalido` | El UUID se escribió mal 5 veces | Copiar el UUID desde el panel de administración y reejecutar |
| `No se pudo completar el paso N de M ...` (exit 1) | Falló una etapa; ya se deshizo | Enviar los mensajes y el archivo de registro a soporte |
| `La direccion del servidor Parkos (...) no es valida` | `PARKOS_CLOUD_API_URL` mal escrita | Corregirla (debe empezar con `http://` o `https://`) |

---

## 2. Modo interactivo (menú, `-Menu`)

`Invoke-ParkosInstall` (invocado con `-Menu`; ya no es el comportamiento por defecto) ejecuta, en orden, antes de mostrar el menú:

1. `Ensure-PowerShell7` — si corre bajo PowerShell 5.1, descarga el MSI de PowerShell 7.4.6, verifica su SHA256 (`ED331A04679B83D4C013705282D1F3F8D8300485EB04C081F36E11EAF1148BD0`), lo instala silenciosamente y relanza el script bajo `pwsh`.
2. `Request-Elevation` — si no corre como administrador, se relanza con `Start-Process pwsh -Verb RunAs`. Si el usuario rechaza el UAC: `'Se requieren permisos de administrador para instalar Parkos.'` y `exit 2`.
3. `Test-Preflight` — verificaciones bloqueantes (detalladas abajo). La clave maestra solo avisa en el menú.
4. `Show-Eula` (Enter acepta).
5. `Read-InstallPaths` (nunca pregunta: valores por defecto o parámetros).
6. `Read-SucursalUuid` (único prompt de datos). La URL del cloud no se pregunta (ver sección 1bis).
7. El bucle del menú (9 etapas numeradas + 8 opciones de letra + `Q`).

### Pre-flight (`Test-Preflight`)

| Verificación | Criterio |
|---|---|
| `Windows >= 10 21H2` | `[Environment]::OSVersion.Version.Build -ge 19044` |
| `PowerShell >= 7` | `$PSVersionTable.PSVersion.Major -ge 7` |
| `Permisos de administrador` | Rol `Administrator` del usuario actual |
| `Espacio en disco (>=5GB)` | Espacio libre en la unidad de `-InstallPath` |
| `Conexion con el servidor Parkos` | `Test-NetConnection` a `host:puerto` de la URL del cloud (`PARKOS_CLOUD_API_URL`, default `http://localhost:8000`), no a github.com. En `localhost` solo avisa; en un host remoto bloquea |
| `Sin instalacion previa` | Ausencia de `$DataPath\pairing.json` |
| `Clave maestra de Parkos` (**no bloqueante en `-Menu`; bloqueante en el flujo guiado**) | `payload\security\parkos-master.key` existe y mide >= 32 bytes. Si no, imprime `[AVISO]` con la ruta exacta y la remediación, pero **no** aborta el pre-flight (la etapa 0 no la necesita); la etapa 1 fallará sin ella. Se puede pasar `-MasterKeyPath <archivo>` para copiarla (validando el tamaño) antes del pre-flight |

Si falla cualquiera, el modo interactivo imprime `'Pre-flight fallo. Instalacion abortada, sin cambios en el sistema.'` y hace `exit 2`. Si ya existe `pairing.json`, además imprime: `'Ya existe una instalacion de Parkos en este equipo.'` y `'Use Repair-ParkosInstall o Update-ParkosStack en vez de una instalacion limpia (Fases 25/26).'`.

> **Comportamiento no verificado**: ningún código de `parkos-installer.ps1` ni de `Parkos.psm1` escribe `pairing.json`. Se lee (acá y al importar el módulo), pero su creación no está en este repositorio — presumiblemente la escribe `job-sync-sucursal` durante el flujo de pairing (Fase 29), fuera del alcance de estos archivos.

### Las 9 etapas numeradas (0–8)

Cada etapa es un ítem del menú que el operador puede correr o re-correr de forma independiente (DEC-INST-17): **el menú interactivo nunca hace rollback automático de una etapa fallida** — un `throw` dentro de una etapa se captura a nivel de menú, se marca la etapa como `Failed` y el operador decide si reintenta o resuelve el problema a mano. Esto es, textualmente, la decisión DEC-INST-17: *"Cada etapa mantiene su propio gate duro (lanza excepción en falla), capturado a nivel de menú para que una etapa fallida no mate toda la sesión."* La cascada `-Unattended` (§3) sí ejecuta rollback automático; el menú interactivo, nunca.

| # | Nombre (texto del menú) | Qué hace | Prerequisito (gate real) | Rollback (solo en cascada, nunca en el menú) |
|---|---|---|---|---|
| 0 | Descargar ultima version de main y compilar artefactos | `git fetch/checkout main/pull --ff-only` + `build-release.ps1` sin switches (build completo) en la máquina del **técnico** (DEC-INST-20), nunca en el equipo final | Requiere `git`, `pnpm`, `uv` en PATH | `$null` (de solo lectura sobre la máquina destino) |
| 1 | Instalar base de datos (Postgres + roles + pg_partman) | Detecta puertos libres, instala Postgres, crea roles `parkos`/`parkos_app` con passwords derivadas, genera `jwt.key`, cifra el `.env`, instala `pg_partman`, registra el mantenimiento programado | Ninguno (primera etapa real) | Desinstala Postgres con el mismo método que lo instaló (`winget uninstall` o borrar ZIP) + borra `pg-data` |
| 2 | Ejecutar migraciones de base de datos | Corre `migrate.exe -c alembic.ini upgrade head` | Gate interno: `if ($null -eq $script:roles) { throw 'Corre primero "Instalar base de datos" (opcion 1).' }` — **no está en el mapa de prerequisitos visual del menú** (ver nota abajo) | `migrate.exe -c alembic.ini downgrade base`; si falla, solo `WARN`, nunca revienta el rollback |
| 3 | Confirmar UUID de sucursal (creada desde el panel admin) | Reescribe la línea `PARKOS_SUCURSAL_UUID=` del `.env` | `if ($script:StageStatus.db -ne [ParkosStageState]::Ok) { throw 'Corre primero "Instalar base de datos" (opcion 1).' }` | `$null` (solo reescribe una línea; DEC-INST-22 ya no inserta nada en `prod.sucursal`) |
| 4 | Sembrar catalogos iniciales (arranca api-sucursal temporalmente) | Levanta `api-sucursal.exe` como proceso temporal (loopback), corre `seed.exe` contra la API real, lo detiene | `if ($script:StageStatus.migrate -ne [ParkosStageState]::Ok) { throw 'Corre primero "Ejecutar migraciones" (opcion 2).' }` | `$null` — **limitación documentada**: no existe tracking de qué filas creó esta corrida; un `DELETE` genérico sería peligroso |
| 5 | Instalar servicio api-sucursal (NSSM) | Copia el bundle, registra `ParkosApiSucursal` con NSSM, arranca el servicio, espera `/health` 200 | Ninguno explícito (asume que el `.env` ya existe) | `nssm stop` + `nssm remove ParkosApiSucursal confirm` |
| 6 | Instalar job de sincronizacion (NSSM) | Igual que la 5, para `ParkosJobSyncSucursal`, espera un ciclo de sondeo en el log | Ninguno explícito | `nssm stop` + `nssm remove ParkosJobSyncSucursal confirm` |
| 7 | Instalar aplicacion de escritorio (web_sucursal) | Instala el MSI de `web_sucursal` silenciosamente | Ninguno explícito | `msiexec /x <msi> /qn` (recalcula la ruta del MSI de forma autónoma) |
| 8 | Verificacion final (Postgres, JWT, servicios) | Corre `Test-PostInstallation` (4 checks) + `Install-ManagementModule` | Ninguno explícito | `$null` (de solo lectura) |

**Nota verificada sobre el indicador `[BLOQ]`**: `Get-ParkosStageMenuLines` solo muestra la etiqueta `[BLOQ]` para las etapas 3 y 4 (mapeadas en `$stagePrereqs` dentro de `Invoke-ParkosInstall`), aunque la etapa 2 también tiene un gate real (`$script:roles -eq $null`). Esto significa que el menú **no advierte visualmente** que la etapa 2 va a fallar si se corre antes de la etapa 1 — el `throw` sí ocurre igual al intentarlo, solo falta el indicador previo. Confirmado comparando `Get-ParkosStageDefinitions` (etapa 2) contra el hashtable `$stagePrereqs` de `Invoke-ParkosInstall`.

### Opciones de letra (A/R/U/V/X/D/M/C) y Q

El módulo `Parkos` se importa perezosamente (lazy) la primera vez que se usa cualquiera de estas opciones, siempre desde el payload local (`$script:PayloadRoot\management\Parkos.psd1`), nunca desde la copia bajo `Program Files\PowerShell\Modules\Parkos\` (que recién existe al terminar la etapa 8).

Gate de "instalación incompleta": si no las 9 etapas están en `Ok`, se pregunta `'La instalacion no esta completa. Continuar? (s/N)'` antes de ejecutar la opción — **excepto** `A`, `D` y `X`, que están **exentas** de este gate (funcionan siempre, incluso con una instalación incompleta o rota).

| Letra | Acción real invocada | Confirmación interactiva | Exenta del gate de incompletitud |
|---|---|---|---|
| `A` | `Get-ParkosHealth -Detailed` | Ninguna | Sí |
| `R` | `Repair-ParkosInstall` | `'Forzar sin confirmacion interactiva? (s/N)'` → `-Force` o sin él | No |
| `U` | `Invoke-ParkosUpdate` (etiqueta del menú: "Update-ParkosStack" — **no existe ninguna función con ese nombre**; se invoca `Invoke-ParkosUpdate` seteando `$script:PayloadPath` antes, porque esa función es `param()`) | Pide `'Ruta del nuevo payload (-PayloadPath)'`; vacío cancela sin invocar nada | No |
| `V` | `Invoke-ParkosRestore` (etiqueta del menú: "Restore-ParkosVersion" — mismo caso, no existe esa función) | Lista versiones en `$InstallPath\releases\`, pide `'Version a restaurar'`; vacío cancela | No |
| `X` | `Uninstall-Parkos` (con o sin `-PurgeData` según `'Purgar tambien los datos? (s/N)'`) | La confirmación de doble palabra vive dentro de `Uninstall-Parkos` (ver §6) | Sí |
| `D` | `Export-ParkosDiagnostics` | Ninguna | Sí |
| `M` | `Register-ParkosBackupTask -DailyAt <hora>` (`'Hora diaria del backup [03:00]'`) | Ninguna | No |
| `C` | `Test-CrashRecovery` | `'Esto reinicia Postgres a la fuerza. Continuar? (s/N)'` | No |
| `Q` | Sale del bucle | Si la instalación está incompleta: `'La instalacion NO esta completa. Etapas pendientes: ... Salir de todos modos? (s/N)'` | — |

---

## 3. Modo desatendido (`-Unattended`)

`-Unattended -Command Install` **nunca** cae en `Invoke-ParkosInstall` (el menú interactivo, que siempre termina bloqueado en un `Read-Host`) — ejecuta `Invoke-ParkosUnattendedCascade`: las mismas 9 etapas definidas en `Get-ParkosStageDefinitions`, corridas automáticamente 0→8, sin ningún `Read-Host`.

### Parámetros requeridos y validaciones (`Assert-ParkosCascadeParamsValid`)

| Parámetro | Validación | Mensaje exacto si falla |
|---|---|---|
| `-SkipStage` | Cada valor entre 0 y 8 | `"-SkipStage contiene un valor invalido ($stageNumber) - cada etapa debe estar entre 0 y 8."` |
| `-StopAfterStage` | `-1` o entre 0 y 8 | `"-StopAfterStage invalido ($StopAfterStage) - debe ser -1 (correr todas las etapas) o un valor entre 0 y 8."` |
| `-SkipStage` conteniendo `1` (Postgres) | Requiere `-Force` | `'Saltar la etapa 1 (Postgres) puede dejar el resto de las etapas sin base de datos - si estas seguro, agrega -Force.'` (con `-Force`: solo advierte, no bloquea) |
| `-Unattended` sin `-EulaAccepted` | — | `'-Unattended requiere -EulaAccepted (ver Show-Eula).'` |
| `-Unattended` sin `-CloudApiUrl` | Ya no es obligatorio | Se toma de `PARKOS_CLOUD_API_URL` o `http://localhost:8000` |

`-SucursalUuid` **no** se revalida en `Assert-ParkosCascadeParamsValid` — `Read-SucursalUuid` ya lanza su propia excepción (`'-SucursalUuid es obligatorio en modo -Unattended (la sucursal se crea desde el panel admin, no desde este instalador).'`) para evitar duplicar la misma validación en dos lugares.

### Qué pasa si falla una etapa: rollback automático por etapa

A diferencia del menú interactivo, la cascada sí ejecuta el `Rollback` de la etapa fallida (si existe) antes de abortar. Tabla de lo que hace cada `Rollback` real (ver también la tabla de §2):

| Etapa | Rollback real |
|---|---|
| 0 (build) | Ninguno (`$null`) |
| 1 (db) | `winget uninstall --id PostgreSQL.PostgreSQL.16 --silent` (si se instaló por winget) o borrar el directorio del ZIP (si se instaló por ZIP) — decidido por `$script:PostgresInstallMethod`; siempre borra `pg-data` |
| 2 (migrate) | `migrate.exe -c alembic.ini downgrade base`; si falla, solo `WARN`, nunca revienta el rollback de la cascada |
| 3 (sucursal) | Ninguno |
| 4 (seed) | Ninguno (limitación documentada, ver §10) |
| 5 (api) | `nssm stop` + `nssm remove ParkosApiSucursal confirm` |
| 6 (job) | `nssm stop` + `nssm remove ParkosJobSyncSucursal confirm` |
| 7 (electron) | `msiexec /x <msi> /qn` (recalcula la ruta del MSI de forma autónoma — un `Rollback` corre en su propio scope hijo, no ve variables locales de su `Action` sibling) |
| 8 (verify) | Ninguno |

Si el propio `Rollback` falla, se registra como `[FAIL]` en el log pero **no** interrumpe el reporte final de la etapa que falló originalmente.

### Exit codes

| Código | Significado |
|---|---|
| `0` | Las 9 etapas corrieron u omitieron explícitamente (`-SkipStage`) sin fallos, o la cascada se cortó deliberadamente por `-StopAfterStage` |
| `1` | Una etapa falló a mitad de la cascada (con su `Rollback` ya intentado, haya tenido éxito o no); las etapas siguientes nunca corren |
| `2` | Validación de parámetros o pre-flight fallidos — nada se ejecutó todavía |

El wrapper delgado del dispatcher final (`if ($MyInvocation.InvocationName -ne '.') { ... }`) es el único lugar del archivo que traduce el `ExitCode` devuelto a un `exit` real de proceso — `Invoke-ParkosUnattendedCascade` en sí nunca llama `exit` (para seguir siendo testeable bajo Pester, que no intercepta un `exit` real de forma confiable).

### Formato del log (`$DataPath\installer-runs\<timestamp>.log`)

Un solo archivo por corrida completa (el timestamp se fija una vez, al arrancar la cascada). Cada línea, escrita a consola y a archivo simultáneamente:

```
[yyyy-MM-ddTHH:mm:ss] [Level] Message
```

Niveles usados: `INIT`, `STAGE <n>`, `ROLLBACK`, `INSTALL`. Ejemplo de secuencia para una etapa exitosa: `[STAGE 1] Iniciando` → `[STAGE 1] [OK] Instalar base de datos...` → `[STAGE 1] Estado: Ok (Ns)`. Para una etapa fallida: `[STAGE 2] [FAIL] <mensaje>` → `[ROLLBACK] [OK]`/`[FAIL] <mensaje>` → `[INSTALL] Exit code: 1`.

---

## 4. `-Command Update`

`Invoke-ParkosUpdate` reemplaza binarios ya instalados por un payload nuevo (compilado en otra máquina con `build-release.ps1`), con backup obligatorio y rollback automático ante cualquier falla posterior al reemplazo.

### Secuencia completa

| Paso | Qué hace | Se puede omitir? |
|---|---|---|
| **PRE-CHECK** | Valida `-PayloadPath`; si no hay `-Force`, importa el módulo `Parkos` y corre `Get-ParkosHealth` — si `ExitCode -eq 2`, aborta (ver mensaje abajo) | `-Force` omite solo este pre-check, nunca el backup ni la verificación de integridad |
| **BACKUP** | `pg_dump -Fc` del esquema completo a `$DataPath\backups\pre-update-<versionSaliente>-<versionNueva>.dump`; verifica con `pg_restore --list` que tenga al menos un objeto | Nunca (corre incluso con `-Force`) |
| **STOP** | `Stop-ParkosServicesInOrder` (job de sync primero, luego api) | No |
| **VERIFY BINARIES** | Valida cada archivo del payload nuevo contra `manifest.sha256.json` (claves = rutas relativas, DEC-INST-26) | No |
| **REPLACE** | Mueve los binarios actuales a `releases\<versionSaliente>\`, copia los nuevos, rota a conservar solo las 2 releases más recientes, regenera `manifest.sha256.json`, archiva el MSI nuevo bajo `releases\<versionNueva>\apps\` | No |
| **MIGRATE** | `migrate.exe -c alembic.ini upgrade head` del payload **nuevo**, recuperando la password del superusuario `parkos` desde `pgpass.conf` (DEC-INST-25) | No |
| **RESTART** | `Start-ParkosServicesInOrder` (api primero, luego job de sync) | No |
| **SMOKE TEST** | `GET /health` (200 esperado) + `GET /api/v1/sync/hello` (público, sin auth — DEC-INST-27) | No |
| **SUCCESS** | Escribe el Event Log (`ParkosInstaller`, EventId 9001, best-effort) y sobreescribe `current-version.txt` con la versión nueva | — |

### Rollback tier-1 vs tier-2

- **Tier-1** (solo si falla **VERIFY BINARIES**): REPLACE todavía no corrió — nada cambió en disco ni en la base de datos. La única recuperación es reiniciar los servicios que STOP acababa de detener (`Start-ParkosServicesInOrder`). **Nunca** se llama al rollback completo acá.
- **Tier-2** (si falla **MIGRATE**, **RESTART** o **SMOKE TEST**): REPLACE ya corrió. Se ejecuta `Invoke-ParkosUpdateFullRollback`: `pg_restore --clean --if-exists` del dump de backup, mueve los binarios desde `releases\<versionSaliente>\` de vuelta a su lugar, regenera el manifest y reinicia los servicios.

### `-WhatIf` / `-RollbackOnly` / `-Force`

- **`-WhatIf`**: imprime los 9 nombres de paso con `[WHATIF]` y retorna `{ExitCode=0; Detail='WhatIf: ningun paso se ejecuto realmente.'}` sin tocar nada.
- **`-RollbackOnly`**: ignora todo lo anterior — mueve los binarios desde la release más reciente bajo `releases\` de vuelta a su lugar (sin backup nuevo, sin verificar un payload nuevo), regenera el manifest y reinicia servicios. Si no hay releases previas: `"No hay releases previas en $releasesPath - no hay nada a lo cual revertir."`
- **`-Force`**: omite únicamente el pre-check de salud (`Get-ParkosHealth`); nunca omite el backup ni la verificación de integridad del payload.

### Exit codes

`Invoke-ParkosUpdate` solo devuelve `0` (éxito) o `1` (fallo, vía el objeto `{ExitCode;Detail}`) por su ruta estructurada. Una falla en **PRE-CHECK** (p. ej. `-PayloadPath` vacío/inexistente, o `Get-ParkosHealth` crítico sin `-Force`) es un `throw` **no capturado** dentro de la función — el proceso termina con el exit code por defecto de PowerShell ante una excepción no manejada, no con un código 0/1/2 documentado explícitamente (a diferencia de la cascada de instalación, que sí define 0/1/2).

---

## 5. `-Command Restore`

`Invoke-ParkosRestore` revierte la instalación a una versión previa archivada bajo `$InstallPath\releases\<Version>\` — el mismo árbol que REPLACE de `Invoke-ParkosUpdate` ya escribe (DEC-INST-30; **nunca** bajo `$DataPath`).

### Flujo completo

1. Valida `-Version` (obligatorio): `'-Version es obligatorio para -Command Restore (ejemplo: -Version 20250101-000000).'`
2. Valida que `releases\<Version>\` exista: `"No existe la version '$Version' en $releasesPath. Versiones disponibles: $availableText."`
3. **Confirmación de doble paso**: interactivamente, la palabra exacta `RESTAURAR` (`"Esto va a restaurar Parkos a la version '$Version'. Escriba RESTAURAR para continuar (cualquier otra respuesta cancela sin tocar nada)"`); en modo `-Unattended`, el switch explícito `-UnattendedRestoreConfirmed` (sin él: `'-UnattendedRestoreConfirmed es obligatorio junto con -Unattended para -Command Restore (evita que un flag copiado por error dispare un restore desatendido).'`).
4. `-WhatIf`: retorna sin ejecutar nada real.
5. Escribe `$DataPath\auto-update-paused.flag` (timestamp + versión restaurada — **puramente informacional**, nada lo lee hoy).
6. **STOP**: `Stop-ParkosServicesInOrder`.
7. **BACKUP**: `pg_dump` previo al restore (`pre-restore-<Version>-<timestamp>.dump`).
8. **REPLACE BINARIES**: copia `api-sucursal`/`job-sync-sucursal` desde `releases\<Version>\` — **siempre** se revierten; si falta alguno: `"Falta $releaseBundle - la version '$Version' archivada no tiene este binario disponible."` Regenera el manifest y sobreescribe `current-version.txt`.
9. **RESTORE DATABASE** (solo con `-RestoreDatabase`, default `$false`): busca en `$DataPath\backups\` el dump cuyo nombre empiece **exactamente** con `pre-update-<Version>-`. Si hay varios, usa el más reciente por nombre. Si no hay ninguno que matchee, **nunca adivina** con otro dump — advierte y continúa sin tocar la base de datos.
10. **REINSTALL MSI** (best-effort): si existe `releases\<Version>\apps\*.msi`, desinstala la versión actual (`Uninstall-ParkosElectron`) e instala la archivada. Si no existe el MSI archivado (caso del §siguiente), advierte y continúa sin revertir la app de escritorio.
11. **RESTART**: `Start-ParkosServicesInOrder`.

### Heurística real de `-RestoreDatabase`

El dump debe matchear el patrón `pre-update-<Version>-*.dump` **exactamente** — ese es el dump que `Invoke-ParkosUpdate` tomó justo *antes* de actualizar *desde* esa versión, representando su estado real. No existe una heurística de "usar el dump más reciente que sea" como fallback.

### El caso del MSI no archivado

Solo las versiones archivadas **después** de DEC-INST-28 tienen un MSI bajo `releases\<version>\apps\`. Para una versión archivada antes de ese cambio, `Invoke-ParkosRestore` advierte (`Write-Host -ForegroundColor Yellow`) y continúa sin revertir la app de escritorio — no es un aborto, es una limitación conocida y documentada en el propio código.

### Exit codes

Igual que `Invoke-ParkosUpdate`: `0` éxito, `1` fallo (vía `{ExitCode;Detail}`, capturado por un único `try/catch` que envuelve todo el cuerpo posterior a la confirmación). Una cancelación por el operador (respuesta distinta de `RESTAURAR`) devuelve `{ExitCode=0; Detail='Restore cancelado por el operador antes de cualquier cambio.'}` — no es un fallo.

---

## 6. Módulo `Parkos` (ciclo de vida post-instalación)

Manifiesto (`Parkos.psd1`): `ModuleVersion = '1.0.0'`, `PowerShellVersion = '7.0'`, 8 funciones exportadas. Instalado en `C:\Program Files\PowerShell\Modules\Parkos\1.0.0\`.

### `Get-ParkosHealth [-Detailed]`

Corre 6 checks (Postgres alcanzable, servicio `ParkosApiSucursal`, servicio `ParkosJobSyncSucursal`, `/health` 200, `doctor.exe`, espacio en disco: `FAIL` bajo 5 GB libres, `WARN` si queda <=10%). El servicio de sync es el **único no crítico**: detenido es `WARN`, no `FAIL`. Si no hay instalación ni `.env`, reporta una sola línea `[FAIL] Parkos no esta instalado` (ExitCode 2, `NotInstalled=$true`). Devuelve `{ExitCode; Checks}` y además setea `$global:LASTEXITCODE`.

Regla de exit code: `0` si los 6 checks están OK, `1` si hay al menos un `WARN` y cero `FAIL`, `2` si hay al menos un `FAIL`.

### `Repair-ParkosInstall [-Force] [-WhatIf]`

Requiere administrador (`throw 'Repair-ParkosInstall requiere permisos de administrador.'`). Si `Get-ParkosHealth` ya reporta `ExitCode -eq 0`: `'[Parkos] Instalacion saludable, nada que reparar.'`, retorna `ExitCode=0`.

La detección de los 7 escenarios corre siempre (incluso bajo `-WhatIf`); el auto-fix de cada uno corre en orden E1→E7, salvo `-WhatIf` (solo reporta) o que el operador decline el prompt `'Reparar? (s/N)'` (salvo `-Force`).

| Escenario | Qué detecta | Auto-fix aplicado | ¿Aborta el resto de la reparación? |
|---|---|---|---|
| **E1** | Registro NSSM faltante para `ParkosApiSucursal` y/o `ParkosJobSyncSucursal` | Re-registra con `nssm.exe` (mismos parámetros que la instalación original, leídos del `.env` existente) | No |
| **E2** | Un servicio registrado existe pero no está `Running` (corre para CUALQUIER servicio detenido, incluidos los que E1 acaba de registrar) | `Start-Service` con 3 reintentos, backoff 1/5/30s; para `ParkosApiSucursal` valida `/health` 200, para el de sync solo el estado del servicio | No (si tiene éxito) — si los 3 reintentos se agotan, **escala a E7** |
| **E3** | Hash SHA256 de un binario instalado no coincide con `manifest.sha256.json` | Busca en `releases\` (más reciente primero) una copia que coincida y la restaura | No — si no hay release disponible, queda como `WARN` no reparado, continúa con el resto |
| **E4** | ACL de `secrets\` expone un principal distinto de `BUILTIN\Administrators` o `NT AUTHORITY\*` | `Set-ParkosSecretsAcl` (re-aplica `icacls /inheritance:r /grant:r Administrators:F SYSTEM:F /T`) | No |
| **E5** | `.env` ausente o no parseable | Busca el backup `*.env*` más reciente en `backups\` y lo restaura | No — si no hay backup, queda como `WARN` no reparado, continúa con el resto |
| **E6** | La base de datos falla la verificación SQL de integridad (`SELECT 1` / `SELECT current_user = 'parkos_app'`) | Ninguno — **aborta** el resto de la reparación, llama `Export-ParkosDiagnostics` | **Sí** — `ExitCode=3` |
| **E7** | Los 3 reintentos de E2 se agotaron sin que el servicio arrancara | Ninguno — **aborta** el resto, llama `Export-ParkosDiagnostics` | **Sí** — `ExitCode=3` |

Si `Get-ParkosHealth` reportó fallas pero ningún escenario E1-E6 aplica: `'[Parkos] Get-ParkosHealth reporto fallas pero ningun escenario E1-E6 conocido aplica; no hay auto-fix disponible.'`, `ExitCode=3`.

### `Uninstall-Parkos [-PurgeData] [-UnattendedPurgeConfirmed] [-Unattended]`

Requiere administrador **siempre**, con o sin `-PurgeData` (DEC-INST-36 — desregistrar servicios NSSM y la tarea programada ya exigen admin de por sí). Confirmación de doble palabra: `DESINSTALAR` (sin purga) o `CONFIRMAR` (con `-PurgeData`); en `-Unattended` con `-PurgeData` exige además `-UnattendedPurgeConfirmed`.

Siempre borra (con o sin `-PurgeData`): servicios NSSM, tarea `ParkosPgPartmanMaintenance`, MSI de `web_sucursal`, `InstallPath` completo (binarios + `releases\` — DEC-INST-37: `releases\` vive bajo `InstallPath`, no se puede preservar por separado) y, al final, el propio directorio del módulo.

Solo con `-PurgeData` borra además: `logs\`, `pg-data\` (bajo `DataPath`), `backups\`, `secrets\`, `installer-runs\`, la tarea `ParkosBackupDiario` (si existe), el usuario local `svc-parkos`, y el servicio + carpeta de instalación de Postgres.

Cada paso corre en su propio `try/catch`: un paso que falla se registra como advertencia y no frena el resto. `ExitCode=1` si hubo alguna advertencia, `0` si todo se limpió sin errores.

### `Export-ParkosDiagnostics [-OutputPath]`

**No** exige administrador (el plan lo pide así explícitamente); sin esos permisos, `secrets\` queda inaccesible por su propia ACL y los archivos que dependen de leerlo (`doctor.json`, `pgsql-roles.txt`, `pgsql-databases.txt`, `env-redacted.txt`) se omiten con advertencia, nunca con `throw`.

Genera un ZIP (default: `<Escritorio>\parkos-diag-<timestamp>.zip`) con 12 artefactos: `versions.txt`, `health.txt`, `doctor.json`, `services.txt`, `postgres-config.txt`, `pgsql-roles.txt`, `pgsql-databases.txt`, `logs\` (3 archivos), `nssm-dump-api.txt`, `nssm-dump-job.txt`, `env-redacted.txt`, `eventlog.csv`. Cualquier fuente individual ausente se omite con advertencia, nunca aborta el export completo.

La única razón real de aborto es el **gate de seguridad final** (`Test-ParkosDiagnosticsContainSecrets`): si algún archivo "ya redactado" todavía contiene un valor sin forma de placeholder `<redactado, N caracteres>`, hace `throw` explícito **antes** de `Compress-Archive` — nunca se genera un ZIP con un posible secreto adentro.

### `Register-ParkosBackupTask [-DailyAt '03:00']`

Requiere administrador. Precondiciones, en orden (cualquiera no cumplida hace `throw`, nunca continúa en silencio):

1. Postgres corriendo + `parkos_app` con acceso real (`SELECT 1`).
2. Espacio libre en el disco de `DataPath` superior al doble del tamaño estimado de la base (`pg_database_size('parkos')`).
3. El usuario `svc-parkos` ya debe existir (lo crea `Ensure-ServiceAccount` del instalador — este cmdlet nunca lo crea).

Genera `$DataPath\scripts\Invoke-DailyBackup.ps1` (script standalone, ACL `Administrators:F SYSTEM:F svc-parkos:RX`), registra la tarea `ParkosBackupDiario` (`ServiceAccount` = `svc-parkos`, `RunOnlyIfNetworkAvailable=$false`), y corre un **backup de prueba inmediato** — si falla, desregistra la tarea (best-effort) y hace `throw`, nunca deja `ParkosBackupDiario` apuntando a un script sin validar.

El script generado aplica la retención abuelo-padre-hijo (7+4+1) **antes** de generar el dump nuevo de cada corrida.

### `Test-CrashRecovery [-TimeoutSeconds 30]`

Requiere administrador. **Gate bloqueante** (antes de tocar cualquier proceso): exige `fsync` y `full_page_writes` efectivamente en `on` (línea sin comentar, valor `on`) en `postgresql.conf`; si no, `throw "Configuracion insegura, abortando: ..."` — nunca llega a matar el proceso de Postgres.

Simula un corte abrupto: abre una transacción de prueba en segundo plano (`pg_sleep(2)`), espera ~1s, mata el proceso de Postgres a la fuerza (`Stop-Process -Force`, PID resuelto vía `Get-CimInstance Win32_Service`), reinicia el servicio, espera hasta `-TimeoutSeconds` a que vuelva a aceptar conexiones, y verifica que la fila de prueba sobrevivió (recuperación WAL). `ExitCode=0` si la fila sobrevivió, `1` si el puerto no respondió a tiempo o la fila no coincide.

### `Get-ParkosVersion`

**Sigue siendo un placeholder de PR1, no implementado.** El cuerpo real es:

```powershell
Write-Host '[Parkos] Get-ParkosVersion aun no esta implementado (placeholder PR1).' -ForegroundColor Yellow
return
```

No reporta ninguna versión real hoy, pese a estar exportado en el manifiesto y a que `Export-ParkosDiagnostics` lo invoca para `versions.txt` (donde termina escribiendo ese mismo texto de placeholder).

### `Test-ParkosSecretsAcl`

Verifica que el ACL de `DataPath\secrets` solo otorgue acceso a `BUILTIN\Administrators` o cualquier principal `NT AUTHORITY\*`. `ExitCode=0` si es así, `1` si hay un principal adicional (usuario interactivo, dominio, `Everyone`, `BUILTIN\Users`, etc.).

---

## 7. Seguridad

### Cifrado CMS del `.env`

El `.env` de runtime se cifra con **CMS** (Cryptographic Message Syntax) contra un certificado de máquina `CN=ParkosEnvProtection` (`Protect-CmsMessage`/`Unprotect-CmsMessage`), no con DPAPI (no existe una API DPAPI de alcance de máquina expuesta por ningún cmdlet nativo — `ConvertTo-SecureString` solo cifra con alcance de usuario, inútil para un archivo que `svc-parkos` necesita leer).

`Get-OrCreateParkosEnvCert` es idempotente por `Subject` exacto (nunca por thumbprint): busca primero en `Cert:\LocalMachine\My` antes de crear uno nuevo con `New-SelfSignedCertificate -Type DocumentEncryptionCert` (el único tipo que `Protect-CmsMessage` acepta como destinatario válido). Si el certificado no existe al momento de escribir el `.env`:

```
No se encontro el certificado 'CN=ParkosEnvProtection' en Cert:\LocalMachine\My - corre Get-OrCreateParkosEnvCert antes de escribir el .env (el cifrado CMS del runtime env depende de el).
```

`Grant-ParkosEnvCertKeyAccess` intenta otorgar lectura de la clave privada a `svc-parkos` (necesaria para que el backup diario, corriendo bajo esa cuenta, pueda descifrar el `.env`) — es **best-effort**: si falla, solo advierte, nunca bloquea la instalación.

`Read-ParkosEnvLines` (instalador) / `Import-ParkosEnvFile` (módulo) detectan CMS vs. texto plano **por contenido** (encabezado `-----BEGIN CMS-----`), nunca por convención de nombre — así un `.env` en texto plano de una instalación anterior sigue siendo legible.

### Gate de fortaleza/denylist del JWT

`Test-JwtSecretGate` exige: (a) archivo de al menos 32 bytes, (b) hash SHA256 fuera de una denylist de 6 secretos de desarrollo/placeholder conocidos (`_DEFAULT_DEV_SECRET` real del backend, `dev-secret-change-me`, `changeme`, `insecure-default-key`, `test-secret-key`, `secret`). Mensajes exactos: `'Secreto JWT demasiado corto. Regenerar.'` / `'Secreto JWT es uno de desarrollo conocido. Regenerar.'`. Deliberadamente **no** implementa la allowlist de secretos buenos que pedía el plan original (HU-F27.3-T3): lógicamente incoherente para un secreto que `New-JwtSigningKey` genera aleatorio (64 bytes) en cada instalación.

### Passwords derivadas (HMAC)

Las 3 passwords de Postgres (`postgres` bootstrap, superusuario `parkos`, runtime `parkos_app`) ya **no** son aleatorias — se derivan determinísticamente (DEC-INST-42):

```
password = Base64(HMAC-SHA256(clave_maestra, "<uuid_sucursal>:<purpose>")) con '+','/','=' reemplazados por 'x'
```

`Purpose` ∈ `{'postgres-bootstrap', 'parkos-superuser', 'parkos-app'}` — distinto por rol, garantizando que las 3 nunca coincidan entre sí aunque compartan UUID y clave maestra. La clave maestra (`installer/payload/security/parkos-master.key`, ≥32 bytes) es un secreto de la **empresa**, no de la instalación: nunca se genera automáticamente ni se versiona en git; `build-release.ps1` hace `throw` si falta antes de un build real. Motivo: el UUID de sucursal no es secreto (aparece sin redactar en `env-redacted.txt` y en el panel admin) — derivar solo del UUID permitiría a cualquiera con el UUID reconstruir la password real.

### ACL de `secrets\`

`icacls $Path /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' /T` — rompe la herencia y deja acceso exclusivo a Administradores + SYSTEM sobre todo el árbol `secrets\`. Verificable con `Test-ParkosSecretsAcl` y auto-reparable con `Repair-ParkosInstall` (escenario E4).

### Herramienta de soporte `Get-ParkosSupportPassword.ps1`

Uso **exclusivo** del equipo de soporte, ejecutada en la máquina **propia** de soporte — nunca en la máquina de un cliente. Reconstruye las 3 passwords derivadas a partir de `-SucursalUuid` (no secreto) y `-MasterKeyPath` (obligatorio, sin default — copia propia de soporte de la clave maestra, obtenida por un canal seguro de la compañía, fuera del alcance del script).

Reusa `New-ParkosDerivedPassword` vía **dot-source** de `parkos-installer.ps1` (`. (Join-Path $PSScriptRoot '..\parkos-installer.ps1')`) — el guard `if ($MyInvocation.InvocationName -ne '.')` al final de ese archivo evita que el dot-source dispare el menú real.

Modelo de amenaza / comportamiento:

- Por defecto (**sin** `-Reveal`): cada password se copia al portapapeles, una a la vez — **nunca se imprime en pantalla**. Con `-Purpose all` (default), pide confirmar con Enter entre cada password (salvo la última) para no perder una que el operador de soporte todavía no pegó.
- Con `-Reveal`: imprime la tabla completa en texto plano (advirtiendo que queda en el historial de la consola) — pensado para sesiones sin portapapeles disponible (ej. SSH headless).
- Ninguna password se escribe jamás a disco, ni siquiera temporalmente.

---

## 8. Catálogo de errores/excepciones

Cada entrada cita el mensaje **exacto** (interpolaciones de PowerShell tal como aparecen en el código) y la función donde ocurre.

### 8.1 Elevación, PowerShell 7, pre-flight, EULA, rutas

| Mensaje | Función |
|---|---|
| `'Se requieren permisos de administrador para instalar Parkos.'` (+ `exit 2`) | `Request-Elevation` |
| `'Hash de PowerShell 7 no coincide; instalacion abortada por seguridad.'` | `Ensure-PowerShell7` |
| `'EULA no aceptada explicitamente - modo -Unattended requiere -EulaAccepted.'` | `Show-Eula` |
| `"EULA file not found at $EulaPath - a real EULA (with PostgreSQL/NSSM/Electron third-party attributions) must be staged there before this installer ships."` | `Show-Eula` |
| `"Ruta de instalacion invalida: $installPath (no se permite C:\Windows, Program Files (x86), ni rutas de red UNC)."` | `Read-InstallPaths` |
| `"Ruta de datos invalida: $dataPath (no se permite C:\Windows, Program Files (x86), ni rutas de red UNC)."` | `Read-InstallPaths` |

### 8.2 Etapa 0 — build en la máquina del técnico

| Mensaje | Función |
|---|---|
| `"Falta instalar: $($missing -join ', '). Alternativa: corre build-release.ps1 a mano en una maquina con el toolchain completo y copia installer\payload\ aca."` | `Invoke-SourceUpdateAndBuild` |
| `'git fetch origin main fallo.'` / `'git checkout main fallo.'` / `'git pull --ff-only fallo (la rama local diverge de origin/main - resolvelo manualmente antes de reintentar).'` | `Invoke-SourceUpdateAndBuild` |
| `"build-release.ps1 fallo (exit $LASTEXITCODE)."` | `Invoke-SourceUpdateAndBuild` |
| `"Build termino sin error pero falta el artefacto esperado: $rel"` | `Invoke-SourceUpdateAndBuild` |
| `'Build termino sin error pero no se encontro el MSI de web_sucursal en installer\payload\apps.'` | `Invoke-SourceUpdateAndBuild` |

### 8.3 Etapa 1 — Postgres, roles, passwords, pg_partman

| Mensaje | Función |
|---|---|
| `'Puertos 5432 y 5433 ambos ocupados; no se puede instalar Postgres de Parkos.'` | `Test-PostgresPorts` |
| `"Puertos $($CandidatePorts -join ', ') todos ocupados; no se puede instalar el servicio api-sucursal."` | `Test-ApiPort` |
| `'initdb fallo al inicializar el data directory de Postgres.'` | `Install-PostgresViaZip` |
| `"Ni winget ni el ZIP de fallback ($zipPath) estan disponibles; no se puede instalar Postgres."` | `Install-Postgres` |
| `"No se encontro la clave maestra de Parkos en $MasterKeyPath - es un secreto de la compania que NO se genera automaticamente ni vive en el repo. Solicitela al equipo de soporte por un canal seguro y copiela a esa ruta (o reintente con -MasterKeyPath <archivo>)."` | `Get-ParkosMasterKeyBytes` / `Get-ParkosMasterKeyProblem` |
| `"La clave maestra de Parkos en $MasterKeyPath es demasiado corta ($length bytes; minimo 32) - parece truncada o incorrecta. Solicite una copia valida al equipo de soporte por un canal seguro y reemplace ese archivo."` | `Get-ParkosMasterKeyBytes` / `Import-ParkosMasterKey` |
| `"No se encontro el archivo indicado en -MasterKeyPath ($SourcePath) - solicite la clave maestra al equipo de soporte por un canal seguro."` | `Import-ParkosMasterKey` |
| `'No se pudo configurar el superusuario parkos.'` | `Initialize-DatabaseRoles` |
| `'No se pudo crear la base de datos parkos.'` | `Initialize-DatabaseRoles` |
| `"No se pudo crear el schema partman (psql exit $LASTEXITCODE) - revisar .pgpass/autenticacion de 'parkos'."` | `Install-PgPartman` |
| `"CREATE EXTENSION pg_partman fallo (psql exit $LASTEXITCODE)."` | `Install-PgPartman` |
| `'pg_partman no quedo activo tras CREATE EXTENSION.'` | `Install-PgPartman` |
| `"No se encontro el certificado 'CN=ParkosEnvProtection' en Cert:\LocalMachine\My - corre Get-OrCreateParkosEnvCert antes de escribir el .env (el cifrado CMS del runtime env depende de el)."` | `Protect-ParkosEnvContent` |
| `"No se encontro el archivo de secreto JWT en $Path."` | `Test-JwtSecretGate` |
| `'Secreto JWT demasiado corto. Regenerar.'` | `Test-JwtSecretGate` |
| `'Secreto JWT es uno de desarrollo conocido. Regenerar.'` | `Test-JwtSecretGate` |

### 8.4 Etapa 2 — migraciones

| Mensaje | Función |
|---|---|
| `"alembic upgrade head fallo (exit $LASTEXITCODE)."` | `Invoke-MigrationsAndSeed` |
| `'Corre primero "Instalar base de datos" (opcion 1).'` | Gate inline de la etapa 2 (`$script:roles -eq $null`) |

### 8.5 Etapa 3 — UUID de sucursal

| Mensaje | Función |
|---|---|
| `'-SucursalUuid es obligatorio en modo -Unattended (la sucursal se crea desde el panel admin, no desde este instalador).'` | `Read-SucursalUuid` |
| `"El UUID de sucursal '$Uuid' no tiene formato valido (UUIDv4 esperado). Verificalo en el panel admin antes de reintentar."` | `Read-SucursalUuid` |
| `"No existe el archivo .env en $EnvFilePath - corre primero 'Instalar base de datos' (opcion 1)."` | `Update-SucursalUuidInEnvFile` |
| `'Corre primero "Instalar base de datos" (opcion 1).'` | Gate de la etapa 3 (`$script:StageStatus.db`) |

### 8.6 Etapa 4 — seed de catálogos

| Mensaje | Función |
|---|---|
| `'api-sucursal.exe (temporal, para seed) no respondio /health a tiempo.'` | `Invoke-CatalogSeed` |
| `"seed.exe fallo (exit $LASTEXITCODE)."` | `Invoke-CatalogSeed` |
| `'Corre primero "Ejecutar migraciones" (opcion 2).'` | Gate de la etapa 4 (`$script:StageStatus.migrate`) |

### 8.7 Etapas 5/6 — servicios NSSM

| Mensaje | Función |
|---|---|
| `'ParkosApiSucursal no respondio /health a tiempo tras el registro NSSM.'` | Acción de la etapa 5 |
| `'ParkosJobSyncSucursal no mostro un ciclo de sondeo en el log a tiempo.'` | Acción de la etapa 6 |

### 8.8 Etapa 7 — app de escritorio

| Mensaje | Función |
|---|---|
| `'No se encontro el MSI de web_sucursal en el payload.'` | Acción de la etapa 7 |
| `"Instalacion de web_sucursal fallo (exit $($proc.ExitCode)); ver $logPath"` | `Install-Electron` |
| `'MSI reporto exito pero web_sucursal no aparece en el registro de desinstalacion.'` | `Install-Electron` |

### 8.9 Etapa 8 — verificación final y módulo de gestión

| Mensaje | Función |
|---|---|
| `'Verificacion post-instalacion fallo; ver detalle arriba. La instalacion NO se considera exitosa.'` | `Test-PostInstallation` |
| `"Falta $src en el payload - no se puede instalar el modulo de gestion Parkos."` | `Install-ManagementModule` |
| `"Ya existe una version $moduleVersion del modulo Parkos en $destDir con contenido DISTINTO al del payload actual. Esto no se resuelve automaticamente (sin versionado automatico en PR1) - revisa manualmente cual version debe prevalecer antes de continuar."` | `Install-ManagementModule` |
| `"Falta $doctorSrc en el payload - no se puede instalar doctor.exe para el modulo de gestion Parkos."` | `Install-ManagementModule` |
| `"Falta $nssmSrc en el payload - no se puede instalar nssm.exe para el modulo de gestion Parkos."` | `Install-ManagementModule` |

### 8.10 Cascada `-Unattended` (validación)

| Mensaje | Función |
|---|---|
| `"-SkipStage contiene un valor invalido ($stageNumber) - cada etapa debe estar entre 0 y 8."` | `Assert-ParkosCascadeParamsValid` |
| `"-StopAfterStage invalido ($StopAfterStage) - debe ser -1 (correr todas las etapas) o un valor entre 0 y 8."` | `Assert-ParkosCascadeParamsValid` |
| `'Saltar la etapa 1 (Postgres) puede dejar el resto de las etapas sin base de datos - si estas seguro, agrega -Force.'` | `Assert-ParkosCascadeParamsValid` |
| `'-Unattended requiere -EulaAccepted (ver Show-Eula).'` | `Assert-ParkosCascadeParamsValid` |
| `'Pre-flight fallo - instalacion abortada, sin cambios en el sistema.'` | `Invoke-ParkosUnattendedCascade` |
| `"La direccion del servidor Parkos ('$value', tomada de $source) no es valida: ..."` | `Resolve-ParkosCloudApiUrl` |
| `'-Menu y -Unattended son incompatibles: ...'` | `Resolve-ParkosInstallMode` (`exit 2`) |
| `"Demasiados intentos con un codigo de sucursal invalido ($maxAttempts). ..."` | `Read-SucursalUuid` |

### 8.11 `-Command Update`

| Mensaje | Función |
|---|---|
| `"No se encontro el archivo .env en $EnvFilePath - corre primero una instalacion (Invoke-ParkosInstall) antes de actualizar."` | `Get-EnvFilePostgresPort` |
| `'No se pudo determinar el puerto de Postgres desde PARKOS_DB_URL ni DATABASE_URL en el .env.'` | `Get-EnvFilePostgresPort` |
| `"No se encontro pgpass.conf en $pgpassPath - no se puede recuperar la credencial de '$User'."` | `Get-PgPassPassword` |
| `"No se encontro una credencial para el usuario '$User' en el puerto $Port dentro de pgpass.conf."` | `Get-PgPassPassword` |
| `"pg_dump.exe fallo (exit $LASTEXITCODE) generando el backup en $DumpPath."` | `Invoke-ParkosPgDump` |
| `"pg_restore --clean --if-exists fallo (exit $LASTEXITCODE) restaurando $DumpPath durante el rollback."` | `Invoke-ParkosPgRestoreClean` |
| `'ParkosApiSucursal no respondio /health a tiempo tras el reinicio.'` | `Start-ParkosServicesInOrder` |
| `'ParkosJobSyncSucursal no mostro un ciclo de sondeo en el log tras el reinicio.'` | `Start-ParkosServicesInOrder` |
| `"No hay releases previas en $releasesPath - no hay nada a lo cual revertir."` | `Invoke-ParkosUpdate` (`-RollbackOnly`) |
| `"-PayloadPath vacio o inexistente ('$PayloadPath') - se requiere la carpeta con el payload nuevo (misma forma que installer\payload\)."` | `Invoke-ParkosUpdate` |
| `'Get-ParkosHealth reporto ExitCode 2 (critico) - corre Repair-ParkosInstall antes de actualizar, o usa -Force para omitir este pre-check (el backup y la verificacion de integridad del payload NUNCA se omiten).'` | `Invoke-ParkosUpdate` (PRE-CHECK) |
| `"El backup en $dumpPath quedo vacio o invalido (pg_restore --list no reporto objetos) - actualizacion abortada ANTES de detener servicios; nada mas se ejecuto."` | `Invoke-ParkosUpdate` (BACKUP) |
| `"Falta el manifest de integridad del payload en $manifestPath - no se puede verificar el payload nuevo."` | `Invoke-ParkosUpdate` (VERIFY BINARIES) |
| `"El payload nuevo no tiene el archivo esperado por el manifest: $relativePath."` | `Invoke-ParkosUpdate` (VERIFY BINARIES) |
| `"Hash SHA256 no coincide para $relativePath - el payload puede estar corrupto o alterado."` | `Invoke-ParkosUpdate` (VERIFY BINARIES) |
| `"alembic upgrade head fallo (exit $exitCode) durante la actualizacion."` | `Invoke-ParkosUpdate` (MIGRATE, dispara rollback tier-2) |
| `"/health respondio $($healthResp.StatusCode), se esperaba 200."` | `Invoke-ParkosUpdate` (SMOKE TEST, dispara rollback tier-2) |
| `"/api/v1/sync/hello respondio $($helloResp.StatusCode), se esperaba 200."` | `Invoke-ParkosUpdate` (SMOKE TEST, dispara rollback tier-2) |

### 8.12 `-Command Restore`

| Mensaje | Función |
|---|---|
| `'-Version es obligatorio para -Command Restore (ejemplo: -Version 20250101-000000).'` | `Invoke-ParkosRestore` |
| `"No existe la version '$Version' en $releasesPath. Versiones disponibles: $availableText."` | `Invoke-ParkosRestore` |
| `'-UnattendedRestoreConfirmed es obligatorio junto con -Unattended para -Command Restore (evita que un flag copiado por error dispare un restore desatendido).'` | `Invoke-ParkosRestore` |
| `"Falta $releaseBundle - la version '$Version' archivada no tiene este binario disponible."` | `Invoke-ParkosRestore` (REPLACE BINARIES) |

### 8.13 `Parkos.psm1` — helpers compartidos

| Mensaje | Función |
|---|---|
| `"No se encontro el archivo .env en $Path."` | `Import-ParkosEnvFile` |
| `'No se pudo determinar el puerto de Postgres desde PARKOS_DB_URL ni DATABASE_URL en el .env.'` | `Get-ParkosPostgresPort` |
| `"Falta el binario doctor.exe en $DoctorExePath - la instalacion no incluye el modulo de diagnostico."` | `Invoke-ParkosDoctorExe` |

### 8.14 `Get-ParkosHealth` / `Repair-ParkosInstall`

| Mensaje | Función |
|---|---|
| `'Repair-ParkosInstall requiere permisos de administrador.'` | `Repair-ParkosInstall` |
| `"No se encontro nssm.exe en $nssmPath - no se puede re-registrar el servicio NSSM faltante (E1)."` | `Repair-ParkosInstall` (E1) |

### 8.15 `Uninstall-Parkos`

| Mensaje | Función |
|---|---|
| `'Uninstall-Parkos requiere permisos de administrador.'` | `Uninstall-Parkos` |
| `'Uninstall-Parkos -PurgeData en modo -Unattended requiere -UnattendedPurgeConfirmed explicito, como confirmacion no interactiva de que el borrado de datos fue intencional.'` | `Uninstall-Parkos` |

### 8.16 `Export-ParkosDiagnostics`

| Mensaje | Función |
|---|---|
| `"Export-ParkosDiagnostics aborto antes de empaquetar: se detecto redaccion incompleta en: $findingsJoined. No se genero ningun ZIP."` (gate de secretos — `throw`, nunca `ExitCode`) | `Export-ParkosDiagnostics` |

### 8.17 `Register-ParkosBackupTask`

| Mensaje | Función |
|---|---|
| `'Register-ParkosBackupTask requiere permisos de administrador.'` | `Register-ParkosBackupTask` |
| `"Formato de hora invalido en -DailyAt: '$DailyAt' (use HH:mm, ejemplo: 03:00)."` | `Register-ParkosBackupTask` |
| `'Register-ParkosBackupTask requiere que Postgres este corriendo y que parkos_app tenga acceso (SELECT 1 fallo) - verificalo con Get-ParkosHealth antes de reintentar.'` | `Register-ParkosBackupTask` |
| `'No se pudo estimar el tamano de la base de datos parkos (pg_database_size no devolvio un valor numerico).'` | `Register-ParkosBackupTask` |
| `('Espacio insuficiente para backup: se necesitan al menos {0} MB, hay {1} MB libres en {2}:.' -f $requiredMb, $freeMb, $driveLetter)` | `Register-ParkosBackupTask` |
| `"El usuario de servicio 'svc-parkos' no existe todavia - corre el instalador (parkos-installer.ps1, Ensure-ServiceAccount) antes de registrar la tarea de backup."` | `Register-ParkosBackupTask` |
| `"El backup de prueba fallo (pwsh.exe exit $($testRun.ExitCode)) al ejecutar $scriptPath - la tarea ParkosBackupDiario NO quedo registrada. Revisar $(Join-Path $paths.LogsPath 'backup.log')."` | `Register-ParkosBackupTask` |
| (dentro del script generado `Invoke-DailyBackup.ps1`) `"No se encontro el .env en $envFilePath."` / `'No se pudo determinar el puerto de Postgres desde el .env.'` / `"pg_dump.exe fallo (exit $LASTEXITCODE) generando $dumpPath."` / `"El backup generado en $dumpPath no paso la verificacion de pg_restore --list (vacio o corrupto)."` | Script standalone generado |

### 8.18 `Test-CrashRecovery`

| Mensaje | Función |
|---|---|
| `'Test-CrashRecovery requiere permisos de administrador.'` | `Test-CrashRecovery` |
| `"No se encontro postgresql.conf en $confPath - no se puede verificar la configuracion de seguridad antes de la prueba de crash."` | `Test-CrashRecovery` |
| `"Configuracion insegura, abortando: $($detalle -join '; ')"` | `Test-CrashRecovery` (gate bloqueante, `fsync`/`full_page_writes`) |
| `"No se encontro el servicio de Windows de Postgres (patron '*postgresql*') - no se puede continuar con la prueba de crash recovery."` | `Test-CrashRecovery` |
| `"No se pudo resolver el PID del servicio '$pgServiceName'."` | `Test-CrashRecovery` |

### 8.19 `build-release.ps1`

| Mensaje | Función |
|---|---|
| `"Falta $manifestPath - el modulo Parkos.psd1 debe existir versionado en el repo (no se descarga)."` | `Get-ManagementModulePayload` |
| `"Falta $modulePath - el modulo Parkos.psm1 debe existir versionado en el repo (no se descarga)."` | `Get-ManagementModulePayload` |
| `"Falta $masterKeyPath - la clave maestra debe ser provista por el equipo de soporte antes de un build real, nunca se genera automaticamente."` | `Get-MasterKeyPayload` |
| `"PowerShell 7 MSI hash mismatch for $msiName. Expected $expectedSha256, got $actual. Aborting - do not ship an unverified binary."` | `Get-PowerShell7Msi` |
| `'pnpm build (electron-sucursal) failed.'` | `Build-WebSucursal` |
| `'electron-builder (build:packager) failed.'` | `Build-WebSucursal` |
| `"No .msi found under $distDir - check electron-builder.yml's win.target includes 'msi'."` | `Build-WebSucursal` |
| `"PyInstaller failed for $Name."` | `Invoke-ServiceFreeze` |

### 8.20 `Get-ParkosSupportPassword.ps1`

| Mensaje | Función |
|---|---|
| `"El UUID de sucursal '$SucursalUuid' no tiene formato valido (UUIDv4 esperado). Verificalo en el panel admin antes de reintentar."` | Validación de `-SucursalUuid` |
| `"No se encontro la clave maestra de Parkos en $MasterKeyPath - debe ser la copia propia de soporte, obtenida por un canal seguro de la compania (nunca debe vivir en una maquina de cliente/sucursal ni en este repositorio)."` | Validación de `-MasterKeyPath` |

---

## 9. Variables de entorno que escribe el `.env`

`Write-RuntimeEnvFile` escribe, en este orden exacto, las siguientes líneas (luego cifradas con CMS por `Protect-ParkosEnvContent`):

| Línea | Origen del valor |
|---|---|
| `PARKOS_DEPLOY=branch` | Fijo (literal) |
| `PARKOS_SYNC_ENGINE=catalog_branch` | Fijo (literal) — único valor ratificado (D22/ADR-001) para "branch workers"; obligatorio, sin default en `engine_flag.py::_parse()` (DEC-INST-43) |
| `PARKOS_SUCURSAL_UUID=$SucursalUuid` | Input del operador (o `-SucursalUuid`), validado como UUID por `Read-SucursalUuid` |
| `PARKOS_DB_URL=postgresql+psycopg://parkos_app:$AppPassword@127.0.0.1:$Port/parkos` | Compuesto: password derivada (HMAC, DEC-INST-42) + puerto detectado por `Test-PostgresPorts` |
| `DATABASE_URL=postgresql+asyncpg://parkos_app:$AppPassword@127.0.0.1:$Port/parkos` | Igual que la anterior, otro esquema/driver (leído por `db/engine.py`, no por el mismo gate que `PARKOS_DB_URL`) |
| `PARKOS_CLOUD_API_URL=$CloudApiUrl` | Input del operador (o `-CloudApiUrl`) |
| `PARKOS_JWT_KEY_PATH=$JwtKeyPath` | Generado: ruta fija `$DataPath\secrets\jwt.key`, contenido generado por `New-JwtSigningKey` (64 bytes aleatorios) |
| `PARKOS_SYNC_JWT_PATH=$SyncJwtPath` | Ruta fija `$DataPath\secrets\sync-agent.jwt` — el **archivo** no lo crea este instalador; lo escribe el flujo de pairing (Fase 29) |
| `PORT=$ApiPort` | Generado: puerto libre detectado por `Test-ApiPort` (candidatos 8000, 8001, 8002) |
| `PARKOS_API_ORIGIN=http://127.0.0.1:$ApiPort` | Derivado del mismo puerto; también se fija como variable de entorno de **máquina** vía `Set-MachineApiOrigin` (consumida por el bridge preload de Electron, no por `api-sucursal.exe`) |

No forman parte del `.env` (se agregan solo al `AppEnvironmentExtra` de NSSM al registrar el servicio de sync, en `Install-JobService`):

| Línea | Origen |
|---|---|
| `PARKOS_SYNC_POLL_INTERVAL_S=10` | Fijo (literal) |
| `PARKOS_SYNC_BATCH_SIZE=100` | Fijo (literal) |

---

## 10. Limitaciones conocidas

Documentadas explícitamente en comentarios del código (no inferidas):

1. **Rollback de catálogos sembrados (etapa 4) no implementado.** Un rollback real necesitaría trackear qué filas exactas creó la corrida; ese tracking no existe. Un `DELETE` genérico sería peligroso (podría borrar datos legítimos de una corrida anterior) — se prefiere documentar la limitación antes que inventar un `DELETE` amplio.
2. **MSI no archivado para versiones anteriores a DEC-INST-28.** `Invoke-ParkosRestore` advierte y continúa sin revertir la app de escritorio si la versión no tiene `releases\<version>\apps\*.msi`.
3. **Smoke test de `Invoke-ParkosUpdate` sin login autenticado real.** No existe un usuario `smoke-test@parkos.local` sembrado (solo `installer-seed@parkos.local`, rol admin) — el smoke test real es `/health` + `GET /api/v1/sync/hello` (público, sin auth). Un smoke test con login real queda pendiente de un usuario de solo lectura dedicado.
4. **Sin versionado automático del módulo de gestión.** `Install-ManagementModule` hace `throw` si ya existe una versión `1.0.0` con contenido distinto — exige resolución manual, no hay lógica de versionado incremental todavía.
5. **`releases\` no se puede preservar por separado en `Uninstall-Parkos` sin `-PurgeData`.** Vive bajo `InstallPath` (no bajo `DataPath`), que se borra siempre — DEC-INST-37 documenta esto como una limitación de layout, no un bug a corregir retroactivamente.
6. **`auto-update-paused.flag` es puramente informacional.** Lo escribe `Invoke-ParkosRestore`; ningún componente de este repositorio lo lee todavía.
7. **`current-version.txt` no existía antes de DEC-INST-24.** La primera actualización de una instalación previa a ese cambio sintetiza `unknown-<timestamp>` como nombre de versión saliente, con advertencia explícita de que no es un identificador de release real.
8. **`Get-ParkosVersion` sigue siendo un placeholder (PR1), no implementado.** No reporta ninguna versión real pese a estar exportado y ser invocado por `Export-ParkosDiagnostics`.
9. **Ruta del data directory de Postgres inconsistente según el método de instalación.** `Install-PostgresViaZip` fija el data directory en `$DataPath\pg-data`; `Install-PostgresViaWinget` **no** recibe ni fija ningún `PgDataPath` — el paquete winget/EDB decide su propia ubicación por defecto (típicamente bajo `C:\Program Files\PostgreSQL\16\data`, aunque esta ruta exacta depende del instalador EDB/BitRock y no está verificada contra este repositorio). Sin embargo, `Test-CrashRecovery` y la lectura de `postgres-config.txt` en `Export-ParkosDiagnostics` asumen siempre `$DataPath\pg-data\postgresql.conf` — con la instalación vía winget (el método preferente, DEC-INST-03), `Test-CrashRecovery` fallaría con `"No se encontro postgresql.conf en $confPath..."` salvo que ese archivo exista ahí por coincidencia.
10. **`pairing.json` se lee pero no se escribe en este repositorio.** Ver nota en §2 — presumiblemente lo escribe `job-sync-sucursal` durante el pairing (Fase 29); no verificado en estos archivos.
11. **El indicador visual `[BLOQ]` del menú no cubre el gate real de la etapa 2.** Ver nota en §2 — el `$stagePrereqs` de `Invoke-ParkosInstall` solo mapea las etapas 3 y 4.
12. **Etiquetas de menú que no corresponden a nombres de función reales.** "Update-ParkosStack" (opción `U`) y "Restore-ParkosVersion" (opción `V`) son solo texto descriptivo — las funciones reales son `Invoke-ParkosUpdate` e `Invoke-ParkosRestore`.
13. **ACL de la clave privada del certificado CMS para `svc-parkos` es best-effort.** Si `Grant-ParkosEnvCertKeyAccess` falla silenciosamente, el backup diario (que corre bajo `svc-parkos`) podría fallar más adelante al intentar descifrar el `.env` — sin que la instalación lo detecte en el momento.
14. **Sin allowlist de secretos JWT conocidos buenos.** Pedida por el plan original (HU-F27.3-T3); deliberadamente no implementada por ser lógicamente incoherente para un secreto aleatorio de 64 bytes.
15. **Sin canal piloto/beta real.** Canal único `latest` (DEC-INST-06); una versión candidata (`-rc.N`) se instala manualmente con `Repair-ParkosInstall -Version <rc>`, nunca vía un segundo feed de auto-update.

---

*Generado a partir del código en `installer/` — si el código cambia, este manual puede quedar desactualizado; revisarlo junto con cualquier cambio futuro al instalador.*
