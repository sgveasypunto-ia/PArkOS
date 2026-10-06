# Backend ignora el datafono en el cierre de turno y los arqueos — proposal

## Why

El datafono ya no es parte del flujo visual del operador. La UI lo removió en
cinco commits consecutivos ya mergeados a `dev` (`d6abd36f`, `c6784945`,
`7c603b35`, `481ca7e5` + un commit anterior) — el Arqueo Parcial hardcodea
`valor_datafono_reportado: 0` en `apps/electron-sucursal/src/features/caja/pages/ArqueoParcial.tsx:179`,
simplifica su cálculo local a solo efectivo, y la apertura persiste
`valor_inicial_datafono: 0` en `prod.sesion` sin que el operador lo tipee. La
capa de presentación dejó de mostrar y de capturar ese valor; el backend, sin
embargo, sigue esperándolo en el wire V2 (`schemas/caja.py:364`
`ArqueoCreateV2.valor_datafono_reportado: Decimal` requerido), computándolo
como esperado en `repo/arqueo.py:334-399` (`calcular_esperado_sesion` /
`calcular_esperado_cierre_dia` retornan `(esperado_efectivo, esperado_datafono)`),
sumándolo a la diferencia del arqueo (`caja_arqueo.py:365-372`,
`calcular_diferencia(... esperado_datafono)`), ponderándolo en el porcentaje
de descuadre (`caja_arqueo.py:391, 394` con `esperado_total = esperado_efectivo
+ esperado_datafono`), devolviéndolo en los responses (`ArqueoReadForHandler`
en `schemas/caja.py:368-387`, `ArqueoDiferenciasResponse` en
`caja_sesion.py:104-119`), consultándolo en el cierre (`caja_sesion.py:212,
247-270`), proyectándolo en el resumen "Mi turno"
(`repo/mi_turno.py:156, 169`), incluyéndolo en la decisión de descuadre
crítico (`repo/arqueo.py:417-435 es_descuadre_critico` con
`diferencia_datafono` + `tolerancia_datafono`), y disparando alertas de
`diferencia_datafono` (`workflows_alerta.py:458`).

La motivación de este change es cerrar la historia: la UI ya no pregunta ni
muestra; el backend deja de **usar** el valor. **El campo en la DB se
preserva** (compliance — `arqueo` es `[A]` append-only regulatorio; las
filas históricas con `valor_datafono_*` no nulo se conservan tal cual; el
cambio es forward-only). La lógica de cálculo, agregación, alerta y
respuesta deja de consultarlo.

## What changes

**Decisión global**: TODO el change es **backward-compatible**. Los campos
de wire (`ArqueoCreateV2.valor_datafono_reportado` y
`SesionUpdate.valor_final_datafono`) se vuelven **nullable con default
`None`** en lugar de `Decimal` requerido. Clientes que aún los manden
(kiosk legacy, integraciones externas, scripts de migración) siguen
funcionando — el handler los lee como `None`, la lógica los ignora, y la
respuesta se simplifica. Clientes nuevos pueden omitirlos. La respuesta
del cierre de turno y del arqueo deja de incluir los campos `datafono_*`
(el shape se reduce; no son nullable — se eliminan).

Los 8 concerns del orquestador, mapeados a los archivos verificados en
`codegraph`:

1. **Schema wire V2** — `schemas/caja.py:349-365`
   `ArqueoCreateV2.valor_datafono_reportado: Decimal` →
   `Decimal | None = None`. El validador acepta `None` o `Decimal`. El
   response `ArqueoReadForHandler` (`schemas/caja.py:368-387`) deja de
   incluir `valor_datafono_esperado`, `valor_datafono_reportado`,
   `diferencia_datafono`. `ArqueoDiferenciasResponse`
   (`caja_sesion.py:104-119`) deja de incluir los tres campos datafono.

2. **Schema wire cierre** — `caja_sesion.py:95-96` `SesionUpdate`
   (`CierreTurnoPut`) ya tiene `valor_final_datafono: float | None = None`
   (nullable, no se requiere cambio). Persiste `0` en
   `log_transaccional.datos_nuevos` (compatibilidad con la fila histórica
   que se conserve). La respuesta de cierre (`SesionCloseResponse` o
   equivalente) deja de incluir los campos datafono.

3. **Cálculo de diferencia en arqueo** —
   `caja_arqueo.py:365-372` deja de calcular `diferencia_datafono` ni lo
   incluye en el `INSERT` a `prod.arqueo` (línea 403-408). El flag
   `requiere_justificacion` se reduce a `diferencia_efectivo != 0`. El
   response handler (líneas 464-477) deja de poblar los campos datafono.
   `repo/arqueo.py::calcular_diferencia(...)` (línea 402) no cambia
   (función genérica, no específica de datafono); lo que cambia es que ya
   no se la llama con el datafono desde el handler.

4. **Porcentaje de descuadre** — `caja_arqueo.py:391, 394`:
   `esperado_total = esperado_efectivo + esperado_datafono` →
   `esperado_total = esperado_efectivo`; la fórmula
   `((diferencia_efectivo + diferencia_datafono) / esperado_total) * 100`
   se simplifica a `(diferencia_efectivo / esperado_total) * 100`.

5. **Cierre usa datafono del arqueo previo** — `caja_sesion.py:212, 247-270`:
   el handler de cierre pasa `valor_final_datafono=None` al close; la
   query de `ArqueoDiferenciasResponse` deja de proyectar los campos
   datafono; el response no incluye los campos datafono.

6. **Alertas** — `workflows_alerta.py:458` no emite alertas de tipo
   `diferencia_datafono`; `models/L_W/alerta.py:62`
   `valor_diferencia_datafono` YA ES `nullable=True` (verificado — no
   requiere cambio ORM); `schemas/workflows.py:348, 374, 392` (clases
   `AlertaCreate`, `AlertaRead`, `AlertaUpdate`) deja de poblar el campo
   en creación y deja de exponerlo en el response. **Decisión de
   compliance**: la columna NO se elimina (resguardo regulatorio +
   drill-down preservado para alertas pre-existentes). El route
   `apps/electron-sucursal/src/lib/alertas/router.ts:44` (drill-down
   `diferencia_datafono`) se mantiene en el mapa para alertas previas;
   no se navega a él desde flujos nuevos. `caja_arqueo.py:432-454` (el
   payload_json de `insertar_alerta_descuadre_critico`) deja de incluir
   `diferencia_datafono` y `tolerancia_datafono`.

7. **Resumen "Mi turno"** — `repo/mi_turno.py:156, 169`:
   `total_cobrado_datafono_cop` se mantiene en el response con valor
   `0` (default propuesto; **decisión abierta**, cerrar en design).
   Alternativa: eliminar el campo del response (más limpio, pero rompe
   la forma del payload para consumidores externos del resumen).

8. **Sync bidireccional** — `sync/motor/apply_row.py:300`:
   `valor_final_datafono=payload.get("valor_final_datafono")` deja de
   pasarse al `close_session_with_log(...)` (o se pasa como `None`, que
   es lo mismo). Default propuesto: pasar `None` explícitamente
   (decisión a cerrar en design con el equipo de sync). El
   `session_cycle.open_session(...)` en la misma línea 302-314 sigue
   aceptando `valor_inicial_datafono` (la apertura no cambia; la UI
   sigue mandando `0` por compat).

## Concerns adicionales descubiertos en code review

CodeGraph surfaced tres sitios de uso datafono que el brief original no
listaba. **Es responsabilidad de las fases spec/design cubrirlos** — los
enumero explícitamente para que no se pierdan:

- **`repo/arqueo.py:334-369` `calcular_esperado_sesion(...)`** — retorna
  tupla `(esperado_efectivo, esperado_datafono)`. Para el caso datafono
  ignorado, basta con descartar el segundo elemento. Decisión propuesta:
  cambiar la firma a `-> Decimal` (solo efectivo) y romper la simetría
  con `calcular_esperado_cierre_dia` (que también retorna tupla). Tests
  afectados: `tests/unit/test_arqueo_repo.py`.
- **`repo/arqueo.py:372-399` `calcular_esperado_cierre_dia(...)`** — idem.
- **`repo/arqueo.py:417-435` `es_descuadre_critico(...)`** — toma
  `diferencia_datafono` y `tolerancia_datafono`. La función se reduce a
  comparar solo `diferencia_efectivo` contra `tolerancia_efectivo`. La
  tolerancia datafono (`tolerancia_datafono`) queda como columna
  preservada en `prod.tolerancia_arq` o equivalente (compliance) pero
  no se lee en el flujo activo. Tests afectados:
  `tests/unit/test_arqueo_repo.py`.
- **`caja_arqueo.py:563-570`** — segundo handler (path `cierre_dia`)
  con `diferencia_datafono = repo_arqueo.calcular_diferencia(...)`.
  Mismo tratamiento que el concern 3.
- **`caja_arqueo.py:382-387`** — la llamada a `es_descuadre_critico(...)`
  pasa `diferencia_datafono` y `tolerancia_datafono`. Al simplificar la
  firma de `es_descuadre_critico`, esta llamada se reduce a solo
  efectivo. La tolerancia datafono ya no se consulta.

## Archivos a tocar

### Modificados (backend — verificado contra `codegraph`)

- `backend/packages/parkos_core/src/parkos_core/schemas/caja.py:349-365`
  — `ArqueoCreateV2.valor_datafono_reportado: Decimal | None = None`.
- `backend/packages/parkos_core/src/parkos_core/schemas/caja.py:368-387`
  — `ArqueoReadForHandler` sin campos datafono.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:355-477`
  — handler de arqueo: sin cálculo datafono, sin datafono en `INSERT`
  arqueo, `descuadre_pct` simplificado, response sin datafono.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:563-570`
  — handler de cierre_dia: sin datafono.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:95-96`
  — `SesionUpdate.valor_final_datafono` ya nullable (sin cambio).
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:104-119`
  — `ArqueoDiferenciasResponse` sin campos datafono.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:212, 247-270`
  — close handler: `valor_final_datafono=None`; query de cierre sin
  datafono; response sin datafono.
- `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py:334-435`
  — `calcular_esperado_sesion`, `calcular_esperado_cierre_dia`,
  `es_descuadre_critico` (firmas simplificadas, ver concerns adicionales).
- `backend/packages/parkos_core/src/parkos_core/api/v1/workflows_alerta.py:458`
  — no emite alerta de `diferencia_datafono`; el response no lo incluye.
- `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py:348, 374, 392`
  — `AlertaCreate`/`AlertaRead`/`AlertaUpdate` sin campo datafono.
- `backend/packages/parkos_core/src/parkos_core/repo/mi_turno.py:156, 169`
  — `total_cobrado_datafono_cop` retorna `0` (default; decisión final en
  design).
- `backend/packages/parkos_core/src/parkos_core/sync/motor/apply_row.py:300`
  — `close_session_with_log` recibe `valor_final_datafono=None` o se
  omite el kwarg (decisión final en design).

### NO se tocan

- `models/L_W/alerta.py:62` — `valor_diferencia_datafono` ya es
  `nullable=True` (verificado). No requiere migration.
- `apps/electron-sucursal/`, `apps/web_admin/` — la UI ya está correcta
  desde los 5 commits FE previos mergeados a `dev`; no se toca frontend.
- `backend/packages/parkos_core/migrations/versions/**` — **no se
  requiere migration nueva** (no se hace DROP ni ALTER; el ORM y el
  Pydantic se ajustan a la columna tal como está). El gatekeeper
  `openspec/scripts/check_schema_match.py` (h) debe seguir verde
  sin cambios.

## Decisiones abiertas (a cerrar en design)

- **D1. `total_cobrado_datafono_cop` en `mi_turno.py`**: ¿preservar
  con `0` o eliminar del response? **Default recomendado: preservar
  con `0`** (compatibilidad con consumidores externos del payload).
- **D2. `valor_final_datafono` en sync (`apply_row.py:300`)**: ¿se
  omite el kwarg o se pasa `None` explícitamente? **Default
  recomendado: pasar `None` explícitamente** (defensa contra futuras
  firmas que requieran el argumento posicional; semánticamente más
  explícito).
- **D3. Drill-down route `diferencia_datafono` en
  `apps/electron-sucursal/src/lib/alertas/router.ts:44`**: ¿se
  preserva el entry aunque no haya alertas nuevas? **Default
  recomendado: preservar** (alertas pre-existentes siguen en la
  bitácora; quitar la ruta las haría inaccesibles). Es un cambio de
  UI muerta — costo cero.
- **D4. Firmas de `calcular_esperado_sesion` /
  `calcular_esperado_cierre_dia`**: ¿retornan tupla con un solo
  elemento (datafono `None`) o se cambia la firma a `-> Decimal`? La
  segunda rompe el call site de `caja_arqueo.py:355-360` y del
  cierre_dia path; la primera preserva compatibilidad. **Default
  recomendado: cambiar la firma a `-> Decimal`** (más limpio, no se
  devuelve un valor que ya no se usa; tests + handler se actualizan
  en el mismo commit).
- **D5. `es_descuadre_critico` firma**: ¿se quita el parámetro
  `diferencia_datafono` / `tolerancia_datafono` o se dejan como
  opcionales con default `None`? **Default recomendado: quitar los
  parámetros** (más limpio; el call site ya no los pasa).

## Tradeoffs

- **Nullable wire vs remoción del campo**: optamos por nullable en el
  input (no remoción) para backward-compat con clientes que aún manden
  el valor. **Output** se reduce (los campos datafono se eliminan del
  response, no son nullable). Costo en input: el campo vive "muerto"
  en el schema forever. Aceptable porque el contrato de la API se
  mantiene estable y la API ya está documentada como C/Q/U (no
  DELETE).
- **Preservar columna `valor_diferencia_datafono` en DB vs DROP**:
  optamos por preservar. Razón: compliance (auditoría regulatoria
  exige reconstruir el estado en cualquier `vigente_hasta` histórico)
  + costo de una migration DROP COLUMN en una tabla particionada por
  `fecha_retencion_hasta` no compensa. Las alertas pre-existentes
  siguen visibles en la bitácora con su valor histórico intacto.
- **`prod.arqueo` sigue aceptando el campo en el INSERT**: la columna
  física no se quita. El handler simplemente deja de poblar
  `valor_datafono_*` y `diferencia_datafono`. Filas futuras tendrán
  esos campos en `NULL` o `0` (default de la columna); filas
  históricas con valor distinto se preservan tal cual.
- **Tolerancia datafono (`tolerancia_datafono`) preservada en DB**:
  aunque la decisión de descuadre (`es_descuadre_critico`) ya no la
  consulta, la columna se preserva por el mismo motivo compliance.

## Out of scope

- **NO** se dropean columnas de la DB (`valor_inicial_datafono`,
  `valor_final_datafono`, `valor_datafono_reportado`,
  `valor_diferencia_datafono`, `valor_esperado_datafono`,
  `tolerancia_datafono`, etc.).
- **NO** se borran alertas pre-existentes con
  `valor_diferencia_datafono != 0` — la bitácora histórica se
  preserva intacta.
- **NO** se modifica el contrato de apertura:
  `prod.sesion.valor_inicial_datafono` se sigue persistiendo con
  `0` (la UI ya lo manda así; el backend lo acepta).
- **NO** se cambia la lógica de pagos (datafono como método de cobro
  sigue existiendo en el modelo `prod.pagos` y la liquidación de la
  factura; **solo se ignora en el consolidado del cierre de turno y
  los arqueos**).
- **NO** se remueve el campo `datafono_*` del modelo de pagos ni del
  modelo `factura_pagos`. La cobranza con datafono se sigue
  contabilizando a nivel de transacción; este change es de **arqueo
  y cierre**, no de pagos.
- **NO** se migran filas históricas con `valor_datafono_* != 0` a
  `0`/`NULL`. El cambio es forward-only.
- **NO** se tocan apps/electron-sucursal ni apps/web_admin (la UI
  ya está lista).
- **NO** se cambian las reglas del datafono en otras superficies
  (reportes, dashboards, BI) — esas siguen mostrando datafono si lo
  hacen hoy.
- **NO** se introduce una nueva columna de auditoría
  (`datafono_ignorado_en_arqueo`, etc.) — el bitácora histórica
  refleja el cambio de comportamiento por la fecha de los commits,
  no por una columna.

## Impact

- **Backend — cálculo**: la diferencia esperada del arqueo parcial
  pasa a ser solo efectivo. `calcular_esperado_sesion` /
  `calcular_esperado_cierre_dia` ya no proyectan el datafono
  (decisión D4: firma reducida a `-> Decimal`).
- **Backend — descuadre**: `es_descuadre_critico` solo compara
  efectivo contra tolerancia efectivo. El datafono deja de participar
  en la decisión de alerta.
- **Backend — arqueo**: el `INSERT` a `prod.arqueo` no incluye los
  campos datafono. El response del POST no los expone. El
  `descuadre_pct` se calcula sobre el neto de efectivo.
- **Backend — cierre**: el PUT de cierre acepta un campo opcional
  (`valor_final_datafono`) que no usa. El response se achica.
- **Backend — alertas**: deja de emitirse la alerta de
  `diferencia_datafono`. Las alertas previas a este change siguen
  existiendo en la bitácora (regla: append-only).
- **Backend — `mi_turno`**: el resumen sigue devolviendo la misma
  forma de payload, con `total_cobrado_datafono_cop: 0`
  (decisión D1: default propuesto; confirmar en design).
- **Sync**: el `valor_final_datafono` deja de propagarse con valor
  (decisión D2: `None` explícito). Sin impacto en la integridad del
  hash chain: el campo no es parte de la cadena SHA256 de
  `log_transaccional` ni de `revocacion_factura`.
- **Frontend**: cero impacto (la UI ya hardcodea `0` y simplificó
  su cálculo local en commits previos mergeados a `dev`). El
  drill-down `diferencia_datafono` en `router.ts:44` se preserva
  por alertas históricas pero no se navega a él desde flujos
  nuevos.
- **Ops / compliance**: las filas históricas con datafono no nulo
  se preservan (auditoría regulatoria, DIAN). El operador no ve
  ni tipea el datafono en la UI; el cálculo interno deja de
  ponderarlo. La regla `REVOKE UPDATE, DELETE` sobre
  `prod.alerta` y `prod.arqueo` se mantiene intacta (no hay DROP
  ni TRUNCATE).
- **Compatibilidad con clientes existentes**: 100% backward-compat
  en el input. Un cliente que mande `valor_datafono_reportado: 100`
  en el wire del ArqueoCreateV2 recibe un 200 OK; el valor se
  ignora y la diferencia se calcula solo sobre el efectivo. El
  response del POST se reduce (breaking para clientes que lean
  los campos datafono del response — mitigación: la UI propia ya
  no los usa desde los commits FE previos).

## Acceptance criteria

- `ArqueoCreateV2.valor_datafono_reportado` acepta `null` y un
  `Decimal` (cualquiera de los dos, mismo comportamiento).
- `CierreTurnoPut` (`SesionUpdate.valor_final_datafono`) acepta
  `null` y un `Decimal` (ya nullable — el cambio es test-pinning).
- `ArqueoReadForHandler` y `ArqueoDiferenciasResponse` NO incluyen
  los campos `valor_datafono_*` ni `diferencia_datafono`.
- El `INSERT` a `prod.arqueo` en el flujo de arqueo parcial NO
  incluye `diferencia_datafono` ni `valor_datafono_*` (verificable
  en test integration que abre BD-transaction y assertea las
  columnas del INSERT).
- El porcentaje de descuadre en
  `prod.arqueo.descuadre_pct` se calcula como
  `(diferencia_efectivo / esperado_efectivo) * 100` sin sumar
  datafono.
- `es_descuadre_critico` se reduce a comparar efectivo contra
  tolerancia efectivo (test pinning con tabla de casos.
- NO se crean alertas nuevas de tipo `diferencia_datafono` (test
  integration que simula descuadre verifica cero filas en
  `prod.alerta` con `tipo_alerta='diferencia_datafono'`).
- `repo/mi_turno.py::total_cobrado_datafono_cop` retorna `0` para
  turnos sin datafono histórico (default propuesto; confirmar en
  design).
- Filas históricas con `valor_diferencia_datafono != 0` siguen
  visibles en la bitácora (`SELECT * FROM prod.alerta WHERE
  valor_diferencia_datafono IS NOT NULL AND created_at <
  '2026-10-06'`).
- `python openspec/scripts/check_schema_match.py` (h) verde —
  particiones de `prod.alerta` y `prod.arqueo` siguen cubiertas.
- `uv run pytest -q` (backend) pasa con la cobertura del 80%
  mantenida.
- `uv run ruff check . && uv run mypy packages/parkos_core/src`
  verde.

## Rollback

- **Nivel aplicación**: revertir el merge a `dev` con
  `git revert <commit-SHA> --no-edit`. **No se requieren migrations
  revertibles** (no hay migration en este change; el DDL existente
  se respeta).
- **Nivel ORM**: ningún cambio DDL. El rollback solo toca archivos
  `.py` (schemas, handlers, repo helpers). El comportamiento
  pre-change (datafono sumado a la diferencia) se restaura al
  revertir el merge.
- **Nivel lógico**: ningún dato histórico se modifica; el rollback
  no toca filas. La UI no requiere cambios (los 5 commits FE previos
  siguen en `dev` independientemente de este change — el contrato
  del POST sigue aceptando `valor_datafono_reportado` como `null`
  o `Decimal`).

## Reglas duras honradas

- **AUDIT-FIRST (3 niveles)**: ORM (nullable), Pydantic wire
  (nullable input / sin output), lógica (no consulta). Las 3 capas
  son separadas y se honran las 3.
- **Bi-temporal / sin DELETE físico**: ninguna tabla `[V]/[L]/[A]`
  se trunca ni se borra. El cambio es forward-only.
- **API contract C/Q/U**: no se introduce DELETE. La decisión de
  ignorar datafono se modela como campo nullable en el input +
  campo removido del output. El handler lo lee como `None`.
- **Cross-cutting changes van por SDD**: este change cruza wire
  contract, sync, compliance y alertas — va por SDD completo
  (proposal → spec → design → tasks → apply → verify → archive).
- **Commits separados por concern, merge a dev con `--no-ff`**: 8
  concerns + 1 commit por concern adicional descubierto (3 sitios
  nuevos en `repo/arqueo.py` consolidado en 1 commit) = ~9 PRs.
  Cada uno cierra con merge a `dev`. Author: `Parkos Dev
  <dev@parkos.local>`, sin trailer `Co-authored-by:`.
- **No migration nueva**: el DDL existente se respeta (la columna
  `valor_diferencia_datafono` ya es nullable; el resto de columnas
  datafono siguen como están).
- **Config.yaml `rules.proposal`**: rollback plan (✓ sección
  Rollback), referencia al modelo AUDIT-FIRST 51-entity (ADR-002)
  en `## Why` y `## Out of scope`, sync queue/conflict marcado
  como risk: medium (concern 8 — la replicación cambia, no toca
  cola ni conflictos).
