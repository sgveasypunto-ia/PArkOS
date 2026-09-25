# Plan General — easypunto_parkos

## Portada

Este es el documento único de planificación técnica de `easypunto_parkos`, un sistema de gestión de parqueaderos con arquitectura offline-first: un frontend de escritorio para la operación diaria en cada sucursal (`web_sucursal`), una consola web de administración multi-sucursal (`web_admin`), y un instalador nativo de Windows que despliega el nodo de sucursal sin depender de Docker.

**A quién está dirigido.** A cualquier desarrollador que se sume al proyecto de ahora en adelante — nuevo o existente — como única hoja de ruta para construir, revisar o auditar el trabajo pendiente. Sustituye a los documentos de planificación previos (varios de ellos con errores de fidelidad frente al backend real y al modelo de datos, ya corregidos aquí — ver Parte IV y Anexo D).

**Este documento es autocontenido.** No hace falta abrir ningún otro archivo de planificación, auditoría o backlog anterior para ejecutar lo que describe. Las únicas dos referencias externas que sí hace falta tener a mano son:

1. El código fuente real del repositorio (`backend/packages/parkos_core`, `apps/`), como referencia de implementación.
2. `modelo_datos_er.mmd` (raíz del repositorio) — el modelo entidad-relación canónico, **inmutable**. Este plan lo respeta en su totalidad; toda desviación (una tabla nueva, un campo que no persiste, una adaptación del backend) está declarada explícitamente donde ocurre, nunca de forma tácita.

## Orden de construcción obligatorio: Sucursal → Admin → Instalador

Las 3 partes de este plan tienen una dependencia real entre sí, verificada al construir esta integración (no es una preferencia arbitraria de organización del documento):

1. **Parte I — `web_sucursal` (Fases 1-12) primero.** Corrige, entre otras cosas, el bug de `router_factory.py` (HU-F1.1 — ver Parte IV §1.2) que rompe el listado genérico de cualquier tabla sin `vigente_desde`. Ese fix es **prerrequisito real** de trabajo de Parte II: las Fases 18 (arqueos, Admin) leen `GET /caja/arqueo`, que está roto por el mismo bug aunque Parte II nunca lo menciona — construir Sucursal primero evita que Admin herede un bug que no es suyo.
2. **Parte II — `web_admin` (Fases 13-20) segundo.** Sombra los 9 permisos que bloquean casi toda escritura administrativa (HU-F13.1 — ver Parte IV §1.3) y crea `configuracion_caja` (HU-F13.3 — ver Parte IV §1.7), que la Parte III necesita como precondición para poder sembrarla.
3. **Parte III — instalador, despliegue y producción (Fases 21-30) al final.** El instalador empaqueta y despliega el binario ya construido de `web_sucursal` (HU-F24.3) y siembra datos contra endpoints que solo existen si Parte II ya los construyó (`configuracion_caja`, HU-F23.3 — con el ajuste de ruta que exige Parte IV §1.7). No tiene sentido construir el instalador antes que aquello que instala.

Construir en otro orden no es imposible, pero obliga a mantener *stubs* temporales para estas 3 dependencias reales — este plan asume el orden de arriba y no vuelve a mencionar la alternativa.

## Arquitectura global (resumen ejecutivo)

Dos nodos lógicos, uno de ellos con dos formas de despliegue. El detalle completo de cada uno vive en la Sección 0 de su propia parte — esto es solo el mapa para orientarse antes de entrar en el detalle.

```mermaid
flowchart LR
    subgraph CLOUD["Nodo Cloud (Parte II)"]
        WA["web_admin (PWA, CloudFront, sin Docker)"]
        API_C["parkos_core API (cloud)"]
        PG_C["PostgreSQL cloud — fuente de verdad"]
        DIAN["Proveedor de facturación electrónica DIAN"]
        WA --> API_C --> PG_C
        API_C -.-> DIAN
    end

    subgraph SUCURSAL["Nodo Sucursal (Parte I + Parte III)"]
        EL["web_sucursal (Electron, kiosko)"]
        API_S["api-sucursal (parkos_core, rol parkos_app)"]
        PG_S["PostgreSQL 16 + pg_partman nativo"]
        SYNC["job-sync-sucursal (outbox/backoff)"]
        EL --> API_S --> PG_S
        SYNC --> API_S
    end

    SYNC <-. "pairing + push/pull (sync_queue)" .-> API_C
```

- **Sucursal (Parte I + Parte III):** Postgres 16 nativo por sede (nunca SQLite), `api-sucursal` como servicio Windows (NSSM, rol `parkos_app` de mínimo privilegio — ver Parte IV §1.5), Electron branch-pinned a una sola sede. Parte I construye el frontend y cierra los gaps de backend que necesita; Parte III construye el instalador que despliega todo esto en campo sin Docker.
- **Cloud (Parte II):** `web_admin` como PWA sin binario nativo, multi-sucursal, con el `parkos_core` API y PostgreSQL cloud como fuente de verdad. Habla con el proveedor de facturación electrónica DIAN (configurado por variable de entorno, sin acoplar el plan a un proveedor específico).
- **Sincronización:** outbox pattern (`sync_queue`) desde cada sucursal hacia cloud, con *pairing* previo (Parte II, Fase 19) y *heartbeat*/backoff (Parte III, Fase 29).

## Glosario único reconciliado

Un término, una definición. Donde las 3 partes (o el corpus original de casos de uso) no coincidían, se resuelve la contradicción aquí con la fuente real (backend/ER) como criterio de desempate, y se explica brevemente el porqué.

| Término | Definición única (autoritativa) |
|---|---|
| **Turno / sesión** | Periodo de trabajo de un operador en una sucursal, tabla `sesion` (`[L-S]`). Estados reales: **`abierta` / `cerrada`** (verificado en `modelo_datos_er.mmd` línea 727 y en el backend real). *Nota de reconciliación:* el corpus original de casos de uso usaba `'ACTIVA'/'CERRADA'` — queda descartado; los estados reales están en minúsculas. |
| **Arqueo** | Conteo físico de caja contra lo esperado, tabla `arqueo` (`[A]`, insert-only — una corrección nunca es `UPDATE`, es un arqueo nuevo que referencia al anterior). El catálogo real `tipo_arqueo` tiene 3 valores (`cierre_turno \| auditoria \| cierre_sesion`, `.mmd` línea 171). Parte I (Sucursal) **añade un 4º valor**, `cierre_dia` (Adaptación A-07), para el cierre de todas las sesiones abiertas del día — un concepto de negocio (CU-10) que el catálogo original no cubría. El valor real `cierre_sesion` **no tiene ningún flujo implementado** en ninguna de las 3 partes (`ABIERTO-04`, Anexo E) — posible duplicado de `cierre_turno` pendiente de decisión. |
| **Cierre diario** | Un `arqueo` de tipo `cierre_dia` (adaptación de Parte I) que cierra todas las sesiones abiertas de la sucursal en el rango 00:00:00–23:59:59 hora local Colombia. Distinto de "cerrar un turno" (un solo `cierre_turno`, una sola sesión). |
| **Mensualidad / suscripción individual** | Pago anticipado (`subscripciones_cliente` + `subscripcion_vehiculos`) asociado a un cliente, hasta 2 placas, una sucursal + tipo de vehículo y una vigencia. El primer vehículo en patio no paga al salir (CU-03M); un segundo vehículo de la misma suscripción en patio simultáneamente paga como Rotación — **excepto en un plan empresa/flota** (`tipo_subscripciones.cantidad_maxima_vehiculos > 2`), donde varios vehículos simultáneos en patio es el comportamiento normal esperado y cada uno sale sin cobro (directiva del operador, 2026-09-24; migration `0050_cotizar_mensualidad_factura_descuento`). **Desde 2026-09-24**, toda salida sin cobro por mensualidad (1era placa de un plan personal, o cualquier placa de un plan empresa) genera de todas formas una factura completa — ver "Factura por mensualidad ($0)" abajo. |
| **Factura por mensualidad ($0)** | Directiva del operador (2026-09-24): cuando la salida no cobra por mensualidad vigente, la factura emitida (interna + Factura Electrónica DIAN, mismo pipeline que CU-04/CU-05) muestra el desglose fiscal COMPLETO (subtotal/IVA/total, como si fuera rotación) más una línea de descuento por el mismo valor (`factura_detalle` con `concepto="Descuento por mensualidad - <nombre del plan>"`), dejando `facturas.total = 0`. `facturas.descuento`/`factura_electronica.descuento` quedan poblados con el valor real (antes hardcodeado en `Decimal(0)`). `medio_pago='suscripcion'` identifica el pago (sin voucher, sin interacción del operador). El tiquete CU-15SM **no cambia** — sigue siendo el formato de 15 campos sin desglose de cobro (ver HU-F7.3). |
| **Tiquete** | Documento térmico impreso: de entrada (CU-15E, con QR — contenido exacto en `ABIERTO-01`, Anexo E), de salida (CU-15S, con desglose de cobro, impreso **después** del pago — DEC-SUC-27) o de salida-mensualidad (CU-15SM, sin campos de cobro, impreso de inmediato — el tiquete no lleva el desglose aunque desde 2026-09-24 sí exista una factura completa detrás, ver "Factura por mensualidad ($0)"). |
| **Base de caja** | El valor real y autoritativo con el que se abre un turno vive en `sesion.valor_inicial_efectivo` / `valor_inicial_datafono` (Parte I, Adaptación A-10) — **nunca** en una tabla de configuración aparte. `configuracion_caja` (tabla nueva de Parte II, ver Parte IV §1.7 / GAP-BE-08) solo guarda un valor **sugerido** (`base_inicial_sugerida`) que la pantalla de apertura de turno debería precargar como default editable — no lo sustituye. El "umbral de alerta" de descuadre no vive en `configuracion_caja`: reutiliza `configuracion_tolerancias.tolerancia_efectivo`/`tolerancia_datafono`, ya real. |
| **Factura (interna)** | `facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` — documento de venta interno, hechos legales de la emisión (nunca recalculado después). |
| **Factura Electrónica (FE)** | La versión DIAN de la factura interna (`factura_electronica`), numerada en la sucursal con su propia resolución (`resolucion_facturacion`) y enviada por el lado cloud a un **proveedor externo de facturación electrónica DIAN** (configurado vía variable de entorno, sin acoplar el plan a un proveedor específico por nombre). Estado real persistido en `envio_dian.estado` (`pendiente\|enviado\|aceptado\|rechazado`); `factura_electronica` no tiene columna de estado propia, siempre se deriva. Se emite **siempre** en cada pago de rotación (nunca hay camino "sin FE"). |
| **Ocupación** | Derivada: ingresos activos vs. `cantidad_vehiculos_sucursal.cantidad`, consultada con polling de 10 s — nunca una columna mutable `disponible` (DEC-SUC-11). |
| **Sincronización (outbox)** | `sync_queue` como cola local de eventos (UUID, prioridad, `next_retry_at`), procesada por `job-sync-sucursal` (Parte III) con backoff exponencial y regla "última escritura gana"; conflictos reales quedan en `sync_conflict` con ambas versiones. |

## Convención de IDs

| Prefijo | Qué identifica | Rango usado |
|---|---|---|
| `HU-F<fase>.<n>` | Historia de usuario | Fases 1-12 (Parte I) · 13-20 (Parte II) · 21-30 (Parte III) |
| `-T<m>` | Tarea atómica dentro de una HU | Todas las partes |
| `DEC-SUC-*` | Decisión de arquitectura de Sucursal | 01-29 (Parte I) |
| `DEC-ADM-*` | Decisión de arquitectura de Admin | 01-20 (Parte II) |
| `DEC-INST-*` | Decisión de arquitectura del Instalador | 01-16 (Parte III) |
| `RIESGO-SUC-*` | Riesgo de Sucursal | 01-14 (Parte I) |
| `RIESGO-ADM-*` | Riesgo de Admin | 01-20 (Parte II) |
| `RIESGO-INST-*` | Riesgo del Instalador | 01-16 (Parte III) |
| `ABIERTO-01..08` | Decisión abierta | Parte I |
| `ABIERTO-50..60` | Decisión abierta | Parte II |
| `ABIERTO-100..109` | Decisión abierta | Parte III |
| `ABIERTO-200` | Decisión abierta nueva, detectada al integrar las 3 partes | Anexo E |
| `GAP-BE-01..09` | Ajuste de backend transversal | Parte IV |
| `A-01..A-10` | Adaptación declarada del ER canónico | Parte I (Anexo I) |
| `CU-01..CU-15SM` | Caso de uso de negocio (corpus original, 18 CU + `FLUJO_CUS_ER` transversal — ver Anexo B) | Referenciado desde toda parte |

## Índice

- [Plan General — easypunto_parkos](#plan-general-easypunto_parkos)
  - [Portada](#portada)
  - [Orden de construcción obligatorio: Sucursal → Admin → Instalador](#orden-de-construcción-obligatorio-sucursal-admin-instalador)
  - [Arquitectura global (resumen ejecutivo)](#arquitectura-global-resumen-ejecutivo)
  - [Glosario único reconciliado](#glosario-único-reconciliado)
  - [Convención de IDs](#convención-de-ids)
  - [Índice](#índice)
  - [PARTE I — CONSTRUCCIÓN DE WEB_SUCURSAL](#parte-i-construcción-de-web_sucursal)
    - [Sección 0 — Visión y arquitectura de `web_sucursal`](#sección-0-visión-y-arquitectura-de-web_sucursal)
  - [Fase 1 — Prerrequisitos de backend](#fase-1-prerrequisitos-de-backend)
    - [HU-F1.1 — Corregir el bug de ordenamiento en `router_factory` para tablas sin `vigente_desde`](#hu-f11-corregir-el-bug-de-ordenamiento-en-router_factory-para-tablas-sin-vigente_desde)
    - [HU-F1.2 — `GET /auth/me`, cookie `httpOnly` y lockout real](#hu-f12-get-authme-cookie-httponly-y-lockout-real)
    - [HU-F1.3 — Constraint de sesión única y `GET /caja-sesion/sesion/me`](#hu-f13-constraint-de-sesión-única-y-get-caja-sesionsesionme)
    - [HU-F1.4 — Filtro `vigente_en` en tarifas](#hu-f14-filtro-vigente_en-en-tarifas)
    - [HU-F1.5 — Vista materializada de ocupación + endpoint](#hu-f15-vista-materializada-de-ocupación-endpoint)
    - [HU-F1.6 — Validaciones reales en `POST /operacion/ingresos`](#hu-f16-validaciones-reales-en-post-operacioningresos)
    - [HU-F1.7 — Endpoints de escritura de salida (rotación y mensualidad)](#hu-f17-endpoints-de-escritura-de-salida-rotación-y-mensualidad)
    - [HU-F1.8 — Función `calcular_cotizacion` + `GET /operacion/cotizar`](#hu-f18-función-calcular_cotizacion-get-operacioncotizar)
    - [HU-F1.9 — Facturación transaccional: factura, pagos, validación de NIT](#hu-f19-facturación-transaccional-factura-pagos-validación-de-nit)
    - [HU-F1.10 — Numeración de factura electrónica y estado DIAN](#hu-f110-numeración-de-factura-electrónica-y-estado-dian)
    - [HU-F1.11 — Workflow de reimpresión de tiquete (crear y anular)](#hu-f111-workflow-de-reimpresión-de-tiquete-crear-y-anular)
    - [HU-F1.12 — Venta atómica de suscripción (decisión de producto, no requisito literal del CU)](#hu-f112-venta-atómica-de-suscripción-decisión-de-producto-no-requisito-literal-del-cu)
    - [HU-F1.13 — Endpoints de arqueo y siembra de `cierre_dia`](#hu-f113-endpoints-de-arqueo-y-siembra-de-cierre_dia)
    - [HU-F1.14 — `GET /sync/estado` y siembra completa de `alert_types`](#hu-f114-get-syncestado-y-siembra-completa-de-alert_types)
    - [HU-F1.15 — Histórico de intentos de login (gap huérfano)](#hu-f115-histórico-de-intentos-de-login-gap-huérfano)
  - [Fase 2 — Andamiaje Electron](#fase-2-andamiaje-electron)
    - [HU-F2.1 — Scaffold del proyecto + `ui-kit` compartido + shadcn/ui](#hu-f21-scaffold-del-proyecto-ui-kit-compartido-shadcnui)
    - [HU-F2.2 — Cliente HTTP `parkosFetch`, bridge IPC y `authStore`](#hu-f22-cliente-http-parkosfetch-bridge-ipc-y-authstore)
    - [HU-F2.3 — Auto-actualización, single-instance y kiosko](#hu-f23-auto-actualización-single-instance-y-kiosko)
  - [Fase 3 — Autenticación y turno de caja](#fase-3-autenticación-y-turno-de-caja)
    - [HU-F3.1 — Login con `email` + `password`](#hu-f31-login-con-email-password)
    - [HU-F3.2 — Lockout visible y refresh transparente](#hu-f32-lockout-visible-y-refresh-transparente)
    - [HU-F3.3 — Abrir y cerrar turno](#hu-f33-abrir-y-cerrar-turno)
  - [Fase 4 — Catálogos y ocupación en vivo](#fase-4-catálogos-y-ocupación-en-vivo)
    - [HU-F4.1 — Detección de tipo de vehículo por placa](#hu-f41-detección-de-tipo-de-vehículo-por-placa)
    - [HU-F4.2 — Tarifas vigentes](#hu-f42-tarifas-vigentes)
    - [HU-F4.3 — Ocupación en vivo](#hu-f43-ocupación-en-vivo)
  - [Fase 5 — Impresión térmica](#fase-5-impresión-térmica)
    - [HU-F5.1 — Servicio de impresora en el main process](#hu-f51-servicio-de-impresora-en-el-main-process)
    - [HU-F5.2 — `escposBuilder` base y fallback de navegador](#hu-f52-escposbuilder-base-y-fallback-de-navegador)
  - [Fase 6 — Ingreso vehicular (CU-01) + tiquete de entrada (CU-15E)](#fase-6-ingreso-vehicular-cu-01-tiquete-de-entrada-cu-15e)
    - [HU-F6.1 — Flujo de ingreso en la pantalla principal](#hu-f61-flujo-de-ingreso-en-la-pantalla-principal)
    - [HU-F6.2 — Tiquete de entrada (CU-15E), con QR y logo añadidos](#hu-f62-tiquete-de-entrada-cu-15e-con-qr-y-logo-añadidos)
  - [Fase 7 — Salida y cálculo de tarifa (CU-02, CU-03, CU-03M) + tiquetes de salida (CU-15S, CU-15SM)](#fase-7-salida-y-cálculo-de-tarifa-cu-02-cu-03-cu-03m-tiquetes-de-salida-cu-15s-cu-15sm)
    - [HU-F7.1 — Búsqueda tolerante y cotización (CU-02)](#hu-f71-búsqueda-tolerante-y-cotización-cu-02)
    - [HU-F7.2 — Registrar salida (rotación y mensualidad)](#hu-f72-registrar-salida-rotación-y-mensualidad)
    - [HU-F7.3 — Tiquetes de salida (CU-15S) y salida-mensualidad (CU-15SM), impresos después del pago](#hu-f73-tiquetes-de-salida-cu-15s-y-salida-mensualidad-cu-15sm-impresos-después-del-pago)
  - [Fase 8 — Cobro y Factura Electrónica (CU-04, CU-05) + reimpresión de tiquete](#fase-8-cobro-y-factura-electrónica-cu-04-cu-05-reimpresión-de-tiquete)
    - [HU-F8.1 — Modal de pago (efectivo/datáfono) con FE](#hu-f81-modal-de-pago-efectivodatáfono-con-fe)
    - [HU-F8.2 — Estado de la Factura Electrónica y reintento](#hu-f82-estado-de-la-factura-electrónica-y-reintento)
    - [HU-F8.3 — Reimpresión de tiquete con costo (crear y anular)](#hu-f83-reimpresión-de-tiquete-con-costo-crear-y-anular)
  - [Fase 9 — Suscripciones y mensualidades operativas (CU-06)](#fase-9-suscripciones-y-mensualidades-operativas-cu-06)
    - [HU-F9.1 — Venta de suscripción desde caja](#hu-f91-venta-de-suscripción-desde-caja)
    - [HU-F9.2 — Listado, consulta y alerta de vencimiento próximo](#hu-f92-listado-consulta-y-alerta-de-vencimiento-próximo)
  - [Fase 10 — Arqueos de caja y cierre diario (CU-10)](#fase-10-arqueos-de-caja-y-cierre-diario-cu-10)
    - [HU-F10.1 — Arqueo parcial (auditoría, sin cierre)](#hu-f101-arqueo-parcial-auditoría-sin-cierre)
    - [HU-F10.2 — Cierre de turno](#hu-f102-cierre-de-turno)
    - [HU-F10.3 — Cierre diario](#hu-f103-cierre-diario)
  - [Fase 11 — Estado de sincronización y alertas operativas (CU-07 vista del operador, CU-14)](#fase-11-estado-de-sincronización-y-alertas-operativas-cu-07-vista-del-operador-cu-14)
    - [HU-F11.1 — Banner de estado de sincronización](#hu-f111-banner-de-estado-de-sincronización)
    - [HU-F11.2 — Panel de alertas locales](#hu-f112-panel-de-alertas-locales)
  - [Fase 12 — Reportería local mínima ("Mi turno", subset de CU-09)](#fase-12-reportería-local-mínima-mi-turno-subset-de-cu-09)
    - [HU-F12.1 — Panel "Mi turno"](#hu-f121-panel-mi-turno)
  - [Anexos de referencia rápida](#anexos-de-referencia-rápida)
    - [Anexo A — Endpoints consolidados de esta parte](#anexo-a-endpoints-consolidados-de-esta-parte)
    - [Anexo B — Inventario de páginas y organismos por fase](#anexo-b-inventario-de-páginas-y-organismos-por-fase)
    - [Anexo C — Mapa de fases, historias y tareas atómicas (resumen)](#anexo-c-mapa-de-fases-historias-y-tareas-atómicas-resumen)
    - [Anexo D — Catálogo consolidado de códigos de error](#anexo-d-catálogo-consolidado-de-códigos-de-error)
    - [Anexo E — Rutas de la aplicación](#anexo-e-rutas-de-la-aplicación)
    - [Anexo F — Definición de Hecho (DoD) por fase](#anexo-f-definición-de-hecho-dod-por-fase)
    - [Anexo G — Checklist maestro de aceptación (una fila por HU)](#anexo-g-checklist-maestro-de-aceptación-una-fila-por-hu)
    - [Anexo H — Reglas de negocio citadas por CU (referencia rápida, ya reconciliadas)](#anexo-h-reglas-de-negocio-citadas-por-cu-referencia-rápida-ya-reconciliadas)
    - [Anexo I — Tablas del ER tocadas por esta parte (impacto por tabla)](#anexo-i-tablas-del-er-tocadas-por-esta-parte-impacto-por-tabla)
    - [Anexo J — Comandos de desarrollo de referencia](#anexo-j-comandos-de-desarrollo-de-referencia)
  - [Riesgos y decisiones abiertas de Sucursal](#riesgos-y-decisiones-abiertas-de-sucursal)
    - [Riesgos](#riesgos)
    - [Decisiones abiertas](#decisiones-abiertas)
  - [PARTE II — CONSTRUCCIÓN DE WEB_ADMIN](#parte-ii-construcción-de-web_admin)
    - [Sección 0 — Visión y arquitectura de `web_admin`](#sección-0-visión-y-arquitectura-de-web_admin)
  - [Fase 13 — Fundamentos: backend admin, autenticación y despliegue](#fase-13-fundamentos-backend-admin-autenticación-y-despliegue)
    - [HU-F13.1 — Sembrar los permisos faltantes y reconciliar los códigos de `workflows.py`](#hu-f131-sembrar-los-permisos-faltantes-y-reconciliar-los-códigos-de-workflowspy)
    - [HU-F13.2 — Corregir el emisor JWT para los 6 roles de negocio de CU-08](#hu-f132-corregir-el-emisor-jwt-para-los-6-roles-de-negocio-de-cu-08)
    - [HU-F13.3 — Tabla `configuracion_caja` (backend real para CU-13)](#hu-f133-tabla-configuracion_caja-backend-real-para-cu-13)
    - [HU-F13.4 — Lecturas para `envio_dian` y `validacion_evento` (no existen hoy)](#hu-f134-lecturas-para-envio_dian-y-validacion_evento-no-existen-hoy)
    - [HU-F13.5 — `authStore` + `useAuth` + refresh transparente en 401](#hu-f135-authstore-useauth-refresh-transparente-en-401)
    - [HU-F13.6 — Login real (email + password), `ProtectedRoute` y `App.tsx`](#hu-f136-login-real-email-password-protectedroute-y-apptsx)
    - [HU-F13.7 — Despliegue: `Dockerfile` + servido de `web_admin`](#hu-f137-despliegue-dockerfile-servido-de-web_admin)
  - [Fase 14 — Parametrización: catálogos, tipos de vehículo, tarifas y capacidad](#fase-14-parametrización-catálogos-tipos-de-vehículo-tarifas-y-capacidad)
    - [HU-F14.1 — Catálogo `tipos_vehiculo` (solo lo que persiste de verdad)](#hu-f141-catálogo-tipos_vehiculo-solo-lo-que-persiste-de-verdad)
    - [HU-F14.2 — Catálogos simples restantes (`tipo_persona`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `tipo_subscripciones`, `impuestos`, `otros_cobros`, `costos_servicios`)](#hu-f142-catálogos-simples-restantes-tipo_persona-tipo_tarifa-tipo_sucursal-tipo_arqueo-tipo_subscripciones-impuestos-otros_cobros-costos_servicios)
    - [HU-F14.3 — Matriz de tarifas por sucursal (CU-11, parte tarifas)](#hu-f143-matriz-de-tarifas-por-sucursal-cu-11-parte-tarifas)
    - [HU-F14.4 — Capacidad por tipo de vehículo (CU-11, parte capacidad)](#hu-f144-capacidad-por-tipo-de-vehículo-cu-11-parte-capacidad)
  - [Fase 15 — Empresa, sucursal, resoluciones DIAN, documentos y caja](#fase-15-empresa-sucursal-resoluciones-dian-documentos-y-caja)
    - [HU-F15.1 — Detalle de sucursal: datos generales + parametrización efectiva](#hu-f151-detalle-de-sucursal-datos-generales-parametrización-efectiva)
    - [HU-F15.2 — Empresa: datos generales, mensajes de ticket, bitácora](#hu-f152-empresa-datos-generales-mensajes-de-ticket-bitácora)
    - [HU-F15.3 — Resoluciones de facturación DIAN por sucursal](#hu-f153-resoluciones-de-facturación-dian-por-sucursal)
    - [HU-F15.4 — Documentos de sucursal (logo, póliza RC, plantillas)](#hu-f154-documentos-de-sucursal-logo-póliza-rc-plantillas)
    - [HU-F15.5 — Caja: base inicial, redondeo y tolerancias (CU-13 completo)](#hu-f155-caja-base-inicial-redondeo-y-tolerancias-cu-13-completo)
  - [Fase 16 — Usuarios, perfiles y permisos (CU-08)](#fase-16-usuarios-perfiles-y-permisos-cu-08)
    - [HU-F16.1 — Backend: router `usuarios.py` completo](#hu-f161-backend-router-usuariospy-completo)
    - [HU-F16.2 — Listado y creación de usuarios](#hu-f162-listado-y-creación-de-usuarios)
    - [HU-F16.3 — Detalle de usuario: permisos por árbol](#hu-f163-detalle-de-usuario-permisos-por-árbol)
    - [HU-F16.4 — Reset de password, sucursales asignadas y último admin](#hu-f164-reset-de-password-sucursales-asignadas-y-último-admin)
    - [HU-F16.5 — Sesiones activas e historial de login](#hu-f165-sesiones-activas-e-historial-de-login)
  - [Fase 17 — Reportería y analítica (CU-09)](#fase-17-reportería-y-analítica-cu-09)
    - [HU-F17.1 — Cerrar el placeholder de `ingresos_monto_total` y ampliar el dashboard ejecutivo](#hu-f171-cerrar-el-placeholder-de-ingresos_monto_total-y-ampliar-el-dashboard-ejecutivo)
    - [HU-F17.2 — Reportería operacional (ingresos, salidas, ocupación)](#hu-f172-reportería-operacional-ingresos-salidas-ocupación)
    - [HU-F17.3 — Reportería financiera (facturas, FE, pagos) — corrección de columnas](#hu-f173-reportería-financiera-facturas-fe-pagos-corrección-de-columnas)
    - [HU-F17.4 — Reportería de suscripciones + exportes CSV/PDF](#hu-f174-reportería-de-suscripciones-exportes-csvpdf)
  - [Fase 18 — Arqueos y auditoría de caja (CU-10, lado admin)](#fase-18-arqueos-y-auditoría-de-caja-cu-10-lado-admin)
    - [HU-F18.1 — Backend: filtros de consulta en `GET /caja/arqueo`](#hu-f181-backend-filtros-de-consulta-en-get-cajaarqueo)
    - [HU-F18.2 — Listado y detalle de arqueos, con diferencias](#hu-f182-listado-y-detalle-de-arqueos-con-diferencias)
    - [HU-F18.3 — Resumen de arqueos por sesión y por día](#hu-f183-resumen-de-arqueos-por-sesión-y-por-día)
    - [HU-F18.4 — Exportar PDF firmado para auditoría externa](#hu-f184-exportar-pdf-firmado-para-auditoría-externa)
  - [Fase 19 — Sincronización, pairing y monitoreo de alertas (CU-07 admin, CU-14)](#fase-19-sincronización-pairing-y-monitoreo-de-alertas-cu-07-admin-cu-14)
    - [HU-F19.1 — Backend: lecturas de `sync_log`, `sync_conflict` y estado agregado](#hu-f191-backend-lecturas-de-sync_log-sync_conflict-y-estado-agregado)
    - [HU-F19.2 — Dashboard de sync: heatmap de lag, log y conflictos](#hu-f192-dashboard-de-sync-heatmap-de-lag-log-y-conflictos)
    - [HU-F19.3 — Pairing de sucursales (100% backend real, solo falta la UI)](#hu-f193-pairing-de-sucursales-100-backend-real-solo-falta-la-ui)
    - [HU-F19.4 — Backend: sembrar tipos de alerta operacionales y habilitar la transición "descartar"](#hu-f194-backend-sembrar-tipos-de-alerta-operacionales-y-habilitar-la-transición-descartar)
    - [HU-F19.5 — Bandeja de alertas y detalle con workflow](#hu-f195-bandeja-de-alertas-y-detalle-con-workflow)
    - [HU-F19.6 — Bandeja de validación de eventos (cloud-side, CU-07)](#hu-f196-bandeja-de-validación-de-eventos-cloud-side-cu-07)
  - [Fase 20 — Clientes y suscripciones, workflows, auditoría y DIAN](#fase-20-clientes-y-suscripciones-workflows-auditoría-y-dian)
    - [HU-F20.1 — Clientes: listado y detalle (datos, vehículos, suscripciones, facturas, bitácora)](#hu-f201-clientes-listado-y-detalle-datos-vehículos-suscripciones-facturas-bitácora)
    - [HU-F20.2 — Mantenimiento de suscripciones: alerta por suscripción y prorrateo](#hu-f202-mantenimiento-de-suscripciones-alerta-por-suscripción-y-prorrateo)
    - [HU-F20.3 — Workflows: anulaciones y reclamos (transiciones reales)](#hu-f203-workflows-anulaciones-y-reclamos-transiciones-reales)
    - [HU-F20.4 — Bitácora: `log_transaccional`, verificación de cadena y búsqueda global](#hu-f204-bitácora-log_transaccional-verificación-de-cadena-y-búsqueda-global)
    - [HU-F20.5 — Monitor de envíos DIAN: cola, reintento y revocación](#hu-f205-monitor-de-envíos-dian-cola-reintento-y-revocación)
  - [Matriz CU × Fases](#matriz-cu-fases)
  - [Endpoints del backend necesarios (consolidado)](#endpoints-del-backend-necesarios-consolidado)
  - [Catálogo de permisos reales (consolidado)](#catálogo-de-permisos-reales-consolidado)
  - [Estrategia de pruebas, calidad y CI](#estrategia-de-pruebas-calidad-y-ci)
    - [Pirámide de pruebas](#pirámide-de-pruebas)
    - [Orden de despliegue recomendado](#orden-de-despliegue-recomendado)
    - [Riesgos de calidad transversales](#riesgos-de-calidad-transversales)
  - [Riesgos y decisiones abiertas de Admin](#riesgos-y-decisiones-abiertas-de-admin)
    - [Resumen de fases (recapitulación)](#resumen-de-fases-recapitulación)
    - [Riesgos activos (`RIESGO-ADM-01` a `RIESGO-ADM-20`)](#riesgos-activos-riesgo-adm-01-a-riesgo-adm-20)
    - [Decisiones abiertas (`ABIERTO-50` a `ABIERTO-60`)](#decisiones-abiertas-abierto-50-a-abierto-60)
    - [Trazabilidad contra los CU originales](#trazabilidad-contra-los-cu-originales)
    - [Alcance explícitamente excluido de esta Parte II](#alcance-explícitamente-excluido-de-esta-parte-ii)
    - [Cierre](#cierre)
  - [PARTE III — INSTALADOR, DESPLIEGUE Y PRODUCCIÓN](#parte-iii-instalador-despliegue-y-producción)
  - [Sección 0 — Visión del instalador y arquitectura de despliegue](#sección-0-visión-del-instalador-y-arquitectura-de-despliegue)
    - [0.1 Qué instala, dónde y qué queda corriendo](#01-qué-instala-dónde-y-qué-queda-corriendo)
    - [0.2 Decisiones de arquitectura del instalador (DEC-INST-01…16)](#02-decisiones-de-arquitectura-del-instalador-dec-inst-0116)
    - [0.3 El rol de base de datos `parkos_app` y por qué el instalador nunca usa el superusuario](#03-el-rol-de-base-de-datos-parkos_app-y-por-qué-el-instalador-nunca-usa-el-superusuario)
    - [0.4 Modelo de sesión: JWT Bearer, no cookie](#04-modelo-de-sesión-jwt-bearer-no-cookie)
    - [0.5 Alcance y deslinde con el resto del documento maestro](#05-alcance-y-deslinde-con-el-resto-del-documento-maestro)
  - [Fase 21 — Instalación limpia: pre-flight, EULA, rutas y arranque del instalador](#fase-21-instalación-limpia-pre-flight-eula-rutas-y-arranque-del-instalador)
    - [Objetivo](#objetivo)
    - [Tablas ER relevantes](#tablas-er-relevantes)
    - [Diagrama de estados de la fase](#diagrama-de-estados-de-la-fase)
    - [HU-F21.1 — Pre-flight check con 6 verificaciones bloqueantes](#hu-f211-pre-flight-check-con-6-verificaciones-bloqueantes)
    - [HU-F21.2 — Auto-instalación de PowerShell 7 cuando el equipo trae 5.1](#hu-f212-auto-instalación-de-powershell-7-cuando-el-equipo-trae-51)
    - [HU-F21.3 — EULA y selección de rutas de instalación](#hu-f213-eula-y-selección-de-rutas-de-instalación)
  - [Fase 22 — Postgres nativo, roles de mínimo privilegio y `pg_partman` en Windows](#fase-22-postgres-nativo-roles-de-mínimo-privilegio-y-pg_partman-en-windows)
    - [Objetivo](#objetivo-1)
    - [Tablas ER relevantes](#tablas-er-relevantes-1)
    - [Diagrama de estados](#diagrama-de-estados)
    - [HU-F22.1 — Detección de puertos y coexistencia con un Postgres preexistente](#hu-f221-detección-de-puertos-y-coexistencia-con-un-postgres-preexistente)
    - [HU-F22.2 — Instalación de Postgres 16 vía `winget` con fallback a ZIP EDB](#hu-f222-instalación-de-postgres-16-vía-winget-con-fallback-a-zip-edb)
    - [HU-F22.3 — Creación del superusuario de migración y del rol `parkos_app` de runtime](#hu-f223-creación-del-superusuario-de-migración-y-del-rol-parkos_app-de-runtime)
    - [HU-F22.4 — `pg_partman` en Windows nativo: binarios, `shared_preload_libraries` y mantenimiento programado](#hu-f224-pg_partman-en-windows-nativo-binarios-shared_preload_libraries-y-mantenimiento-programado)
  - [Fase 23 — Migraciones Alembic y seed inicial de catálogos](#fase-23-migraciones-alembic-y-seed-inicial-de-catálogos)
    - [Objetivo](#objetivo-2)
    - [Tablas ER relevantes](#tablas-er-relevantes-2)
    - [HU-F23.1 — Ejecución de `alembic upgrade head` con conexión de migración](#hu-f231-ejecución-de-alembic-upgrade-head-con-conexión-de-migración)
    - [HU-F23.2 — Seed idempotente de catálogos operativos base](#hu-f232-seed-idempotente-de-catálogos-operativos-base)
    - [HU-F23.3 — Seed de `impuestos` (IVA) y `config_caja` (base de caja) — corrección de un hueco real](#hu-f233-seed-de-impuestos-iva-y-config_caja-base-de-caja-corrección-de-un-hueco-real)
  - [Fase 24 — Servicios NSSM, instalación de la app Electron y verificación post-instalación](#fase-24-servicios-nssm-instalación-de-la-app-electron-y-verificación-post-instalación)
    - [Objetivo](#objetivo-3)
    - [Tablas ER relevantes](#tablas-er-relevantes-3)
    - [Endpoints relevantes](#endpoints-relevantes)
    - [HU-F24.1 — Registro de `ParkosApiSucursal` vía NSSM](#hu-f241-registro-de-parkosapisucursal-vía-nssm)
    - [HU-F24.2 — Registro de `ParkosJobSyncSucursal` vía NSSM](#hu-f242-registro-de-parkosjobsyncsucursal-vía-nssm)
    - [HU-F24.3 — Instalación silenciosa del MSI de `web_sucursal`](#hu-f243-instalación-silenciosa-del-msi-de-web_sucursal)
    - [HU-F24.4 — Verificación post-instalación integral (el *gate* final)](#hu-f244-verificación-post-instalación-integral-el-gate-final)
  - [Fase 25 — Actualización del stack completo (`Update-ParkosStack`)](#fase-25-actualización-del-stack-completo-update-parkosstack)
    - [Objetivo](#objetivo-4)
    - [Diagrama de estados del ciclo de vida completo](#diagrama-de-estados-del-ciclo-de-vida-completo)
    - [HU-F25.1 — Pre-check de salud y backup obligatorio antes de tocar nada](#hu-f251-pre-check-de-salud-y-backup-obligatorio-antes-de-tocar-nada)
    - [HU-F25.2 — Detención ordenada y reemplazo de binarios con verificación de firma](#hu-f252-detención-ordenada-y-reemplazo-de-binarios-con-verificación-de-firma)
    - [HU-F25.3 — Migración de esquema sobre datos reales de cliente](#hu-f253-migración-de-esquema-sobre-datos-reales-de-cliente)
    - [HU-F25.4 — Reinicio ordenado y smoke test post-actualización](#hu-f254-reinicio-ordenado-y-smoke-test-post-actualización)
  - [Fase 26 — Reparación, diagnóstico y desinstalación](#fase-26-reparación-diagnóstico-y-desinstalación)
    - [Objetivo](#objetivo-5)
    - [HU-F26.1 — `Repair-ParkosInstall`: reparación sin tocar datos](#hu-f261-repair-parkosinstall-reparación-sin-tocar-datos)
    - [HU-F26.2 — `Get-ParkosHealth`: diagnóstico de 4 verificaciones reutilizando `doctor`](#hu-f262-get-parkoshealth-diagnóstico-de-4-verificaciones-reutilizando-doctor)
    - [HU-F26.3 — `Export-ParkosDiagnostics`: paquete unificado para soporte](#hu-f263-export-parkosdiagnostics-paquete-unificado-para-soporte)
    - [HU-F26.4 — `Uninstall-Parkos`: política explícita de preservación](#hu-f264-uninstall-parkos-política-explícita-de-preservación)
  - [Fase 27 — Seguridad desktop: secretos, cuenta de servicio, ACL y hardening de Electron](#fase-27-seguridad-desktop-secretos-cuenta-de-servicio-acl-y-hardening-de-electron)
    - [Objetivo](#objetivo-6)
    - [HU-F27.1 — Cuenta de servicio dedicada `svc-parkos` y ACL restrictiva](#hu-f271-cuenta-de-servicio-dedicada-svc-parkos-y-acl-restrictiva)
    - [HU-F27.2 — Cifrado adicional del `.env` con DPAPI (capa complementaria, no sustituta)](#hu-f272-cifrado-adicional-del-env-con-dpapi-capa-complementaria-no-sustituta)
    - [HU-F27.3 — *Gate* de instalación: rechazo si el secreto JWT cae al fallback de desarrollo](#hu-f273-gate-de-instalación-rechazo-si-el-secreto-jwt-cae-al-fallback-de-desarrollo)
    - [HU-F27.4 — Hardening del proceso Electron: `contextIsolation`, `sandbox`, CSP](#hu-f274-hardening-del-proceso-electron-contextisolation-sandbox-csp)
  - [Fase 28 — Firma de código y distribución](#fase-28-firma-de-código-y-distribución)
    - [Objetivo](#objetivo-7)
    - [HU-F28.1 — Firma de código con Azure Trusted Signing](#hu-f281-firma-de-código-con-azure-trusted-signing)
    - [HU-F28.2 — Canal único de actualización (`latest`), sin contradicción entre documentos](#hu-f282-canal-único-de-actualización-latest-sin-contradicción-entre-documentos)
    - [HU-F28.3 — Rollback manual de versión en producción de cliente](#hu-f283-rollback-manual-de-versión-en-producción-de-cliente)
  - [Fase 29 — Operación en campo: backups, recuperación ante fallos, monitoreo y sincronización](#fase-29-operación-en-campo-backups-recuperación-ante-fallos-monitoreo-y-sincronización)
    - [Objetivo](#objetivo-8)
    - [Tablas ER relevantes](#tablas-er-relevantes-4)
    - [HU-F29.1 — Resiliencia ante corte de energía: `fsync`, `full_page_writes` y prueba de humo de *crash recovery*](#hu-f291-resiliencia-ante-corte-de-energía-fsync-full_page_writes-y-prueba-de-humo-de-crash-recovery)
    - [HU-F29.2 — Backups automáticos con `pg_dump` y política de retención](#hu-f292-backups-automáticos-con-pg_dump-y-política-de-retención)
    - [HU-F29.3 — Monitoreo/heartbeat proactivo reutilizando el canal de sincronización](#hu-f293-monitoreoheartbeat-proactivo-reutilizando-el-canal-de-sincronización)
    - [HU-F29.4 — Sincronización offline-first: outbox, idempotencia y backoff (CU-07)](#hu-f294-sincronización-offline-first-outbox-idempotencia-y-backoff-cu-07)
    - [HU-F29.5 — `sync_queue_lw_buffer`: buffer de dependencias entre padres e hijos aún no resueltos](#hu-f295-sync_queue_lw_buffer-buffer-de-dependencias-entre-padres-e-hijos-aún-no-resueltos)
  - [Fase 30 — Impresión térmica, entorno de desarrollo local, testing del instalador y CI/CD de empaquetado](#fase-30-impresión-térmica-entorno-de-desarrollo-local-testing-del-instalador-y-cicd-de-empaquetado)
    - [Objetivo](#objetivo-9)
    - [HU-F30.1 — Matriz de compatibilidad de impresoras térmicas ESC/POS](#hu-f301-matriz-de-compatibilidad-de-impresoras-térmicas-escpos)
    - [HU-F30.2 — Entorno de desarrollo local sin instalar el producto completo](#hu-f302-entorno-de-desarrollo-local-sin-instalar-el-producto-completo)
    - [HU-F30.3 — Testing del instalador: Pester (unit + integración) y VM de Windows](#hu-f303-testing-del-instalador-pester-unit-integración-y-vm-de-windows)
    - [HU-F30.4 — Testing de la app Electron empaquetada (`_electron.launch` + axe) y CI/CD de empaquetado y firma](#hu-f304-testing-de-la-app-electron-empaquetada-_electronlaunch-axe-y-cicd-de-empaquetado-y-firma)
  - [Sección final — Riesgos y decisiones abiertas](#sección-final-riesgos-y-decisiones-abiertas)
    - [Riesgos (RIESGO-INST-01…16)](#riesgos-riesgo-inst-0116)
    - [Decisiones abiertas (ABIERTO-100…109)](#decisiones-abiertas-abierto-100109)
  - [PARTE IV — AJUSTES DE BACKEND TRANSVERSALES](#parte-iv-ajustes-de-backend-transversales)
    - [0. Alcance de esta Parte](#0-alcance-de-esta-parte)
    - [1.1 GAP-BE-01 — Login por `cedula` vs `email`](#11-gap-be-01-login-por-cedula-vs-email)
    - [1.2 GAP-BE-02 — Bug de `router_factory.py`: orden por `vigente_desde` sin `hasattr`](#12-gap-be-02-bug-de-router_factorypy-orden-por-vigente_desde-sin-hasattr)
    - [1.3 GAP-BE-03 y GAP-BE-04 — Códigos de permiso nunca sembrados (consolidado en una sola migración)](#13-gap-be-03-y-gap-be-04-códigos-de-permiso-nunca-sembrados-consolidado-en-una-sola-migración)
    - [1.4 GAP-BE-05 — Permiso `emitir_factura` mal asignado en `caja.py`/`caja_sesion.py` (abierto, sin dueño)](#14-gap-be-05-permiso-emitir_factura-mal-asignado-en-cajapycaja_sesionpy-abierto-sin-dueño)
    - [1.5 GAP-BE-06 — Rol `parkos_app` y migración `0021` (mínimo privilegio)](#15-gap-be-06-rol-parkos_app-y-migración-0021-mínimo-privilegio)
    - [1.6 GAP-BE-07 — Conteo de tablas del ER: "54" es incorrecto, son 51](#16-gap-be-07-conteo-de-tablas-del-er-54-es-incorrecto-son-51)
    - [1.7 GAP-BE-08 — `config_caja`/`configuracion_caja`: tabla fantasma y desacuerdo de nombre/ruta entre las 3 partes](#17-gap-be-08-config_cajaconfiguracion_caja-tabla-fantasma-y-desacuerdo-de-nombreruta-entre-las-3-partes)
    - [1.8 GAP-BE-09 — Contrato consolidado del motor de tarifa/cotizar/salida](#18-gap-be-09-contrato-consolidado-del-motor-de-tarifacotizarsalida)
    - [2. Orden de despliegue de esta Parte IV](#2-orden-de-despliegue-de-esta-parte-iv)
  - [ANEXOS](#anexos)
    - [A. Catálogo consolidado de endpoints](#a-catálogo-consolidado-de-endpoints)
    - [B. Matriz CU → tablas ER](#b-matriz-cu-tablas-er)
    - [C. Matriz CU → HU](#c-matriz-cu-hu)
    - [D. Riesgos consolidados](#d-riesgos-consolidados)
    - [E. Decisiones abiertas consolidadas](#e-decisiones-abiertas-consolidadas)
    - [F. Glosario extendido](#f-glosario-extendido)
## PARTE I — CONSTRUCCIÓN DE WEB_SUCURSAL

> Esta parte es autocontenida: todo dato, regla de negocio, nombre de tabla/columna, endpoint y decisión que aparece aquí ya incorpora las correcciones verificadas contra los 19 casos de uso originales, el modelo de datos canónico (`modelo_datos_er.mmd`, 51 tablas) y el backend real (`parkos_core`). No hace falta consultar ningún otro documento para ejecutar esta parte.

### Sección 0 — Visión y arquitectura de `web_sucursal`

#### 0.1 Qué es y para quién

`web_sucursal` es el terminal operativo de una sede de parqueadero: la aplicación de escritorio que usa el operador de caja (rol `operador-` del JWT) durante su turno para registrar ingresos y salidas de vehículos, cobrar, emitir la representación local de la factura electrónica, vender y consultar mensualidades, hacer arqueos de caja, y ver el estado de sincronización y las alertas operativas de su sede. Es una aplicación **Electron de escritorio** (no un sitio web ni una PWA), fijada a una sola sucursal por instalación (branch-pinned) y diseñada para seguir operando con normalidad aunque el enlace a internet de la sede caiga.

Alcance de esta parte: la construcción completa de la aplicación `apps/electron-sucursal` — capas main/preload/renderer, todos los flujos operativos de caja, impresión térmica, y los ajustes de backend compartido (`parkos_core`) que esta aplicación necesita para funcionar de verdad, no solo su interfaz. Quedan fuera de esta parte (se tratan en otras partes del plan maestro): la consola de administración multi-sucursal (parametrización de tarifas, catálogos, usuarios, reportería agregada), y el instalador de campo que provisiona PostgreSQL, los servicios de Windows y la propia app en el equipo del cliente — aquí se los menciona solo cuando una decisión de esta parte los toca directamente (por ejemplo, qué necesita el instalador para que el login nunca use el secreto JWT de desarrollo).

Casos de uso que esta parte realiza (numeración y nombres tal como los define el corpus de requisitos): **CU-01** (Registrar ingreso vehicular), **CU-02** (Calcular tarifa en salida), **CU-03** (Registrar salida vehicular), **CU-03M** (Registrar salida vehicular con mensualidad), **CU-04** (Procesar pago efectivo o datáfono), **CU-05** (Gestionar factura electrónica TopPoint — la parte que corre en sucursal: numeración y cola local; el monitoreo multi-sucursal es de administración), **CU-06** (Gestionar suscripciones/mensualidades — la parte operativa: consumo automático en caja y venta en sucursal; el CRUD administrativo completo es de administración), **CU-07** (Sincronizar datos offline-first — la parte que ve el operador: banner de estado; el motor de sincronización en sí es transversal y no se reconstruye aquí), **CU-10** (Realizar arqueos de caja y cierre diario), **CU-14** (Monitorear y alertar sobre eventos operacionales — la parte que ve el operador: panel de alertas locales), **CU-15E/15S/15SM** (Imprimir tiquetes de entrada, salida y salida con mensualidad).

#### 0.2 Arquitectura completa

```mermaid
flowchart LR
    ELEC["electron-sucursal<br/>Electron 30+ · main + preload + renderer"]
    APIS["api-sucursal<br/>servicio Windows (NSSM)<br/>parkos_core · 127.0.0.1:8000"]
    JSS["job-sync-sucursal<br/>servicio Windows (NSSM)<br/>worker de sincronización"]
    BDB[(PostgreSQL 16 + pg_partman<br/>servicio Windows nativo)]
    PRN[("Impresora térmica USB ESC/POS")]
    CLOUD[("api-cloud + TopPoint (DIAN)")]
    ELEC -. "http://127.0.0.1:8000/api/v1" .-> APIS
    APIS --> BDB
    JSS --> BDB
    JSS -. "sync cada 60s" .-> CLOUD
    ELEC -. "escpos-usb / @thiagoelg/node-printer" .-> PRN
```

**Decisión arquitectónica fundamental (DEC-SUC-01)**: cada sucursal corre su **propio PostgreSQL 16 + pg_partman como servicio nativo de Windows**, no una base embebida tipo SQLite. Esta decisión corrige una premisa del corpus de casos de uso original: el diagrama de arquitectura de CU-07 describe la base local como "MÓDULO LOCAL (SQLite)". Verificado contra el CU-07 original paso a paso: ninguno de sus 6 pasos de flujo, ninguna de sus reglas de negocio ni criterios de aceptación dependen de una característica específica de SQLite — todo está descrito en términos de patrón (outbox, idempotencia por UUID, "última escritura gana" por timestamp UTC, backoff exponencial), agnóstico de motor. El pivote a Postgres nativo es seguro y no obliga a ajustar ninguna regla de negocio de CU-07; solo hay que declararlo explícitamente como sustitución de arquitectura. `electron-store` (archivo JSON en `app.getPath('userData')`) es exclusivamente cache de UI y cola de reintentos del lado del renderer — nunca la base de datos de negocio, que vive siempre en el Postgres local de la sede.

La sede se comunica con la nube a través de dos servicios Windows independientes: `api-sucursal` (expone `parkos_core` en `127.0.0.1:8000`, es lo único que consume el Electron) y `job-sync-sucursal` (worker de sincronización, sondeo cada 60 segundos, sin relación directa con el renderer). El aprovisionamiento de estos servicios, de Postgres y de la propia app en el equipo del cliente es responsabilidad del instalador de campo (fuera de esta parte); lo único que esta parte necesita saber es que `api-sucursal` **siempre** está disponible en `127.0.0.1:8000` — nunca se lanza como proceso hijo del Electron.

**Capas de la aplicación**:

```
MAIN PROCESS (Node.js)
  electron/main.ts        — ciclo de vida, BrowserWindow, IPC, auto-updater, kiosko, single-instance
  electron/services/      — printer.ts (escpos-usb), updater.ts (electron-updater), api-status.ts
  electron/preload.ts     — contextBridge.exposeInMainWorld('bridge', { imprimir, usb, app, kiosk, api-status })
  electron/ipc/           — handlers (imprimir.ts, etc.), cada uno valida el payload con Zod antes de usarlo
                             (defensa en profundidad: nunca confiar solo en los tipos TypeScript del renderer)

RENDERER (React 18 + Vite 5 + TypeScript strict)
  src/features/{auth,operacion,caja,facturacion,suscripciones,sync,reimpresion}/
  src/components/ui/      — atomic design: primitivas shadcn/ui (Button, Dialog, Form, Input, Toast,
                             Table, Badge, Sheet, Select, Tabs, Popover, Tooltip, DropdownMenu, Skeleton)
  src/components/         — moleculas/organismos propios (OcupacionStrip, AlertasPanel)
  src/lib/{parkosFetch,bridge,electron-store,validation,fechas,print}/
  src/i18n/               — namespaces: common, auth, operacion, caja, facturacion, sync, errors
```

Patrón de capas por *feature*: cada carpeta de `src/features/<dominio>/` separa **pages** (contenedores: obtienen datos vía hooks SWR, manejan el estado del flujo, no dibujan UI de detalle), **components** (presentacionales: reciben props y renderizan, sin llamadas HTTP propias) y **hooks** (acceso a datos y lógica reusable). Esto es container/presentational aplicado consistentemente: un desarrollador que abre `pages/Principal.tsx` ve orquestación, no marcado; un desarrollador que abre `components/PlacaInput.tsx` ve una presentación pura y testeable con Testing Library sin mockear red. Atomic design vive únicamente dentro de `components/ui/` (átomos y moléculas genéricos, sin conocimiento de dominio); los componentes de dominio (`OcupacionStrip`, `CotizacionPanel`, `AlertasPanel`) son organismos que sí conocen el dominio y se ubican en `src/components/` (compartidos entre features) o dentro de la feature que los usa en exclusiva.

**Stack de versiones exacto**: Electron 30+, React 18, Vite 5 (bundler del renderer; el main+preload se compilan con esbuild), TypeScript 5 en modo `strict`. Estado: **Zustand** solo para estado de UI local efímero (sesión de formulario, banners, contadores) — nunca como cache de datos de servidor. Datos de servidor: **SWR** como único data-fetcher (`dedupingInterval`, `refreshInterval` y `fallbackData` por hook, ver cada Fase). Formularios: **react-hook-form + Zod** (resolver `zodResolver`) en todo formulario de escritura, sin excepción. Cliente HTTP: un único wrapper `parkosFetch` (no `fetch` disperso) que centraliza base URL, reintentos, refresh de sesión, envío de `Idempotency-Key` y de la cabecera de tenant. i18n: `i18next` + `react-i18next`, locale por defecto `es-CO`, namespaces `common`, `auth`, `operacion`, `caja`, `facturacion`, `sync`, `errors` (siete, no cinco — la ausencia de `common`/`errors` en versiones previas de este plan generaba textos hardcodeados fuera de cualquier namespace). Impresión térmica: `escpos-usb` (o `@thiagoelg/node-printer` como alternativa de driver) ejecutado en el **main process**, nunca en el renderer, expuesto vía IPC. Offline/degradado: no hay modo PWA ni Service Worker — el "offline-first" real de esta app es que su propio backend (`api-sucursal` + Postgres local) sigue respondiendo aunque la sede no tenga internet; lo único que se degrada sin internet es la sincronización hacia la nube (CU-07), nunca la operación de caja.

**Convenciones del backend real que condicionan toda la UI** (verificadas directamente contra el código, no asumidas):

1. **Nunca hay `UPDATE` libre en tablas `[V]` (catálogos versionados)** ni en la mayoría de tablas de evento: la única vía de escritura es *close-and-insert* (cerrar la versión vigente, insertar una nueva fila) para catálogos, o *insert-only* puro para tablas de evento (`ingreso`, `salidas`, `facturas`, etc.). Las tablas `[L-W]` (workflow: `anulaciones`, `reclamos`, `alerta`, `envio_dian`, `reimpresion_ticket`, `revocacion_factura`) tampoco se editan nunca: cada transición de estado es una **fila nueva** que referencia a la anterior por un campo `uuid_*_padre`. Solo dos tablas admiten un `UPDATE` real y acotado, con log obligatorio: `sesion` (columna `timestamp_cierre`/`uuid_usuario_cierre` al cerrar turno) y `login` (columna `timestamp_cierre` al cerrar sesión).
2. **Listados paginados por cursor**: contrato uniforme `{items, next_cursor}`, cursor codificado en base64url, `limit` entre 1 y 200.
3. **Errores**: `HTTPException(detail={"error": "<codigo>", ...})`, validación 422 estándar de FastAPI/Pydantic con `extra="forbid"` (un campo no declarado en el schema rechaza la petición completa, no lo ignora en silencio).
4. **Idempotencia**: cabecera `Idempotency-Key` con caché de 24 horas en el servidor. El frontend la envía **siempre** en toda mutación (POST/PUT), calculada como hash SHA-256 de `(método + ruta + cuerpo)` — así una reenvío idéntico produce la misma clave, no un UUID aleatorio que rompería la idempotencia ante un reintento automático.
5. **Tenant fijo por token**: el JWT de rol `operador-` trae `uuid_sucursal` en el claim; no existe selector de sucursal en esta app (una sola sede por instalación/token). Toda petición mutante incluye además la cabecera `X-Sucursal-Context` con ese mismo `uuid_sucursal`, como defensa adicional en profundidad del lado del servidor.
6. **Bug real confirmado en `router_factory.py` (fábrica genérica de routers CRUD)**: su endpoint de listado (`GET` de colección, usado por todo router construido con `make_router`) protege la condición `vigente_hasta IS NULL` con un `hasattr(model_cls, "vigente_hasta")`, pero **ordena incondicionalmente** por `model_cls.vigente_desde` sin la misma guarda (`stmt.order_by(model_cls.vigente_desde.desc(), model_cls.uuid.asc())`), y la paginación por cursor también asume `vigente_desde` sin condición. Esto rompe en tiempo de ejecución el listado de **cualquier tabla de workflow `[L-W]` montada con este factory** (`alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket` — ninguna tiene columna `vigente_desde` en el ER real) apenas se le pide la colección completa. Impacto directo en esta parte: bloquea `GET /workflows/alerta` (necesario para el panel de alertas de Fase 11) y `GET /workflows/reimpresion-ticket`/`GET /workflows/anulaciones`. Se corrige en Fase 1 (HU-F1.1).

Estado derivado (nunca almacenado) de un ingreso a lo largo de su ciclo de vida — clave para entender por qué ninguna HU de esta parte hace `UPDATE` sobre `ingreso`:

```mermaid
stateDiagram-v2
    [*] --> Activo: INSERT ingreso (CU-01)
    Activo --> Finalizado: INSERT salidas sin anular (CU-03/CU-03M)
    Activo --> Anulado: INSERT anulaciones (tipo_anulable='ingreso', estado='ejecutada')
    Finalizado --> Activo: INSERT anulaciones (tipo_anulable='salida', estado='ejecutada') — reactiva el ingreso
    note right of Activo
        Ningún estado es una columna de `ingreso`.
        Se deriva SIEMPRE por consulta contra
        `salidas` + `anulaciones` (DEC-SUC-21).
    end note
```

#### 0.3 Decisiones de arquitectura (DEC-SUC-01 … DEC-SUC-29)

| ID | Decisión |
|---|---|
| **DEC-SUC-01** | Arquitectura branch-pinned: una sola sucursal por instalación/token (`uuid_sucursal` viene del claim JWT `operador-`); sin selector de sucursal en la UI. Base de datos local: PostgreSQL 16 + pg_partman como servicio Windows nativo (nunca SQLite embebido — corrige la premisa del diagrama original de CU-07, verificado sin dependencia real de ese motor). `electron-store` es solo cache de UI, nunca el almacén de negocio. |
| **DEC-SUC-02** | Autenticación por **`email` + `password`** contra `POST /auth/login` (backend real verificado en `api/v1/auth.py`/`schemas/auth.py`). Ningún formulario de esta app pide cédula como credencial de acceso — la cédula es un dato del perfil del usuario (`usuarios.cedula`), no la llave de login. |
| **DEC-SUC-03** | Sesión vía cookie `httpOnly` (`parkos_session`) como mecanismo primario; Bearer token como fallback transitorio mientras se completa el corte. Refresh transparente cada 50 minutos y antes de escrituras críticas (pago, arqueo). |
| **DEC-SUC-04** | Cliente HTTP único `parkosFetch`: retry en 5xx/`NetworkError` con backoff 300/600/1200 ms (3 intentos, nunca en 4xx), un solo refresh automático ante 401 (un segundo 401 consecutivo cierra sesión y redirige a login), `Idempotency-Key` = SHA-256(método+ruta+cuerpo) en toda mutación, `X-Sucursal-Context` siempre presente. |
| **DEC-SUC-05** | SWR como único *data fetcher* de lectura; Zustand exclusivamente para estado de UI local (nunca cache de servidor); `electron-store` para cache persistente entre reinicios de catálogos y cola de reintentos de impresión. |
| **DEC-SUC-06** | react-hook-form + Zod (`zodResolver`) en todo formulario de escritura, sin excepción; schemas de validación colocados junto al formulario que los usa. |
| **DEC-SUC-07** | i18n con `i18next`/`react-i18next`, 7 namespaces (`common`, `auth`, `operacion`, `caja`, `facturacion`, `sync`, `errors`), locale `es-CO` por defecto, formato de moneda vía `Intl.NumberFormat('es-CO', {style:'currency', currency:'COP', minimumFractionDigits:0})`. |
| **DEC-SUC-08** | Impresión térmica nativa vía `escpos-usb` (o `@thiagoelg/node-printer`) en el main process, expuesta por IPC tipado (`bridge.imprimir`); fallback a `window.print()` con plantilla `@page{size:80mm auto;margin:2mm}` si la térmica no responde. Cola de reintento con backoff (5s/15s/60s, 5 intentos) persistida en `electron-store`, para no bloquear la caja mientras la impresora está desconectada. |
| **DEC-SUC-09** | Modo degradado: banner visible si `parkosFetch` falla repetidamente contra `api-sucursal` local (no confundir con degradación de sync hacia la nube, que es un banner distinto); la cola de reintento hacia la nube es responsabilidad del backend (`sync_queue`/`job-sync-sucursal`), nunca del cliente Electron. |
| **DEC-SUC-10** | WCAG 2.1 AA verificado con `@axe-core/playwright` en CI, 0 violaciones como gate de build. |
| **DEC-SUC-11** | Ocupación en vivo vía vista materializada `mv_ocupacion_diaria` con *polling* cada 10 s desde el cliente (no vía websocket); el cupo real se recalcula siempre por comparación entre `cantidad_vehiculos_sucursal.cantidad` (cupo máximo configurado) e ingresos activos — **nunca** por una columna mutable `disponible` (un trigger que mantuviera esa columna fue explícitamente descartado: la tabla no la tiene y añadirla violaría la restricción de no modificar el ER). |
| **DEC-SUC-12** | El cálculo de tarifa (CU-02) es **siempre server-side** (función `calcular_cotizacion` en PL/pgSQL) — el cliente nunca calcula el monto a cobrar, solo lo muestra. |
| **DEC-SUC-13** | Catálogo `tipo_arqueo` (dominio real: `cierre_turno | auditoria | cierre_sesion`) se extiende con un 4º valor `cierre_dia`, declarado explícitamente como **adaptación del ER** (nunca como siembra de rutina) porque el modelo canónico no lo documenta. El valor `cierre_sesion` no tiene flujo correspondiente en el CU-10 original: se documenta como ABIERTO-04 (hipótesis: cierre ejecutado por un supervisor distinto del titular del turno, coherente con `sesion.uuid_usuario_cierre`). |
| **DEC-SUC-14** | `alert_types` se siembra con el catálogo completo de 11 códigos que CU-14 exige literalmente para el operador (`descuadre_critico`, `sync_fallida`, `capacidad_agotada`, `capacidad_agotada_forzado`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, `cache_desactualizado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`), que **coexisten** (no reemplazan) con los 8 códigos técnicos ya sembrados en producción (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) — los 8 existentes son granularidad técnica interna; los 11 nuevos son la capa de negocio que ve el operador. Total real tras esta fase: 19 tipos sembrados, no 11 ni 14. |
| **DEC-SUC-15** | `X-Sucursal-Context` presente en toda petición, como defensa en profundidad adicional al claim del JWT. |
| **DEC-SUC-16** | Electron 30+ empaquetado con `electron-builder` (targets Windows nsis+msi, Linux AppImage+deb, macOS dmg+zip); `api-sucursal` corre siempre como servicio Windows vía NSSM, nunca como proceso hijo del Electron (sobrevive a que el usuario cierre sesión de Windows). |
| **DEC-SUC-17** | Renderer hardenizado: `contextIsolation:true`, `sandbox:true`, `nodeIntegration:false`, CSP estricto, whitelist explícita de métodos en `contextBridge.exposeInMainWorld`. JWT nunca se persiste en el renderer (vive solo en cookie `httpOnly`, DEC-SUC-03). |
| **DEC-SUC-18** | Auto-actualización con `electron-updater`, `autoDownload:true`, `autoInstallOnAppQuit:true`, `allowDowngrade:false`, verificación de firma de código obligatoria, un solo canal de distribución (`latest`, sin canal `beta` paralelo). |
| **DEC-SUC-19** | Single-instance lock (`app.requestSingleInstanceLock()`) + modo kiosko opcional (`PARKOS_KIOSK_MODE=1`): pantalla completa, `Menu.setApplicationMenu(null)`, bloqueo de `Ctrl+W`/`Alt+F4`, salida solo con `Ctrl+Shift+K` + PIN (`bcrypt`, factor ≥12, comparación en tiempo constante, nunca logueado). |
| **DEC-SUC-20** | `NSSM` como envoltorio estándar para los servicios Windows del stack (detalle operativo de despliegue, tratado en la parte del instalador). |
| **DEC-SUC-21** | `tipo_entrada` (mensualidad/rotación) **no es columna de ninguna tabla**: `ingreso` es insert-only y no la persiste en ningún punto verificado del corpus. Siempre se deriva en cada respuesta a partir de `ingreso.uuid_subscripcion_cliente IS NOT NULL` (mensualidad) o de la detección de "otra placa de la misma mensualidad ya en el patio" (rotación) — este segundo caso tampoco se persiste, es un cálculo de consulta. |
| **DEC-SUC-22** | Detección de placa en **ingreso** (CU-01) usa una función estricta y **sin tolerancia** de tipeo (`detectarTipoVehiculo`, solo regex exacta: Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`) — "única fuente válida, sin override manual del cajero; si falla, se corrige como bug" (CU-01 BR2, literal). La tolerancia de tipeo O↔0, I↔1, B↔8 existe **solo** en la *búsqueda* de un ingreso ya existente al iniciar una salida (CU-02, paso 3) y vive en una función distinta (`buscarIngresoTolerante`) que nunca se reusa para detectar el tipo en el ingreso. Compartir una sola función para ambos casos es un error de diseño explícitamente descartado. |
| **DEC-SUC-23** | El monto de una operación de salida **no se persiste en `salidas`** (esa tabla no tiene columna `valor` en el ER real): el "total a pagar" calculado por CU-02 viaja en estado de UI (con vigencia de 15 minutos) hasta que CU-04 lo persiste como `facturas.subtotal`/`facturas.total`, `factura_detalle` (línea) y `factura_impuestos` (snapshot de IVA). `salidas` solo se actualiza una vez en todo el ciclo: `UPDATE salidas SET estado='PAGADO'` al completar el pago (única excepción documentada al patrón insert-only de esta tabla). |
| **DEC-SUC-24** | Fórmula fiscal de IVA tal como la define CU-02 AC7, literal y sin "corregir" la aparente inconsistencia fiscal: `total_a_pagar` es el valor tarifado (tiempo × tarifa, o tarifa plena); `iva = total_a_pagar * porcentaje_impuesto`; `subtotal = total_a_pagar - iva`. Es una decisión de negocio explícita del corpus (no un error de transcripción) y se documenta como tal, no se reemplaza por un cálculo de IVA "sobre base neta". |
| **DEC-SUC-25** | Estado de `alerta`: modelo **append-only** del ER real (`[L-W]`, dominio `abierta \| en_revision \| resuelta`, cada transición es fila nueva enlazada por `uuid_alerta_padre`). CU-14 BR1 describe literalmente un flag booleano `revisada` — como el ER es inmutable y manda sobre la redacción del CU en caso de conflicto de implementación, se reinterpreta BR1 como "la fila original nunca se edita; marcar como revisada es insertar una fila hija con `estado='resuelta'`", no un `UPDATE` de columna. |
| **DEC-SUC-26** | Tiquetes de entrada/salida/salida-mensualidad incluyen **QR y logo** además de los campos que cada CU-15x lista literalmente (15, 19 y 15 campos respectivamente, ninguno de los tres incluye QR ni logo en su propio listado) — se añaden porque CU-01 exige QR en su postcondición de éxito y la política transversal de identidad de marca exige logo en todo tiquete. El contenido exacto del QR queda como ABIERTO-01 (recomendación: folio del ingreso/salida + placa, ambos ya disponibles al imprimir). |
| **DEC-SUC-27** | Impresión de tiquetes: el ingreso (CU-15E) se imprime **automáticamente** al confirmar (con botón manual siempre disponible para reimpresión inmediata sin costo, distinta del workflow pago de reimpresión de Fase 8). El tiquete de salida (CU-15S) se imprime **después** de confirmado el pago (CU-04), no inmediatamente al registrar la salida (CU-03) — se reordena así porque el propio CU-15S exige el campo "medio de pago" (que solo existe tras CU-04) y CU-03 lo manda a imprimir antes de tiempo; es una corrección de secuencia sobre el propio corpus, no una interpretación libre. El de mensualidad (CU-15SM) se imprime al confirmar la salida sin mensualidad, ya que no depende de ningún pago. |
| **DEC-SUC-28** | Numeración de factura electrónica: `prefijo` + `consecutivo` de `resolucion_facturacion`, asignados **en la sucursal** mediante `assign_consecutivo` (lock `SELECT...FOR UPDATE`, ya implementado en el backend real) — nunca numeración simulada `SIM-YYYY-MM-DD-NNNNNN`: esa rama del CU-05 original era un *fallback* explícito "mientras no haya integración real", condición que ya no aplica porque la numeración real ya está resuelta. El envío del documento a TopPoint (proveedor DIAN) es lo único cloud-only (tabla `envio_dian`); la sucursal nunca escribe esa tabla directamente. |
| **DEC-SUC-29** | Tres tablas de backoff **separadas y no unificadas**, cada una con su propia semántica de cola: sincronización general (`sync_queue`, exponencial en segundos: 1-2-4-8-16-32-64-128-256-300s, tope 5 min; evento sin procesar 24h → fallo permanente + alerta `evento_no_procesado`), reintento de envío de FE al usuario (minutos/horas: 1min-5min-15min-1h-6h-24h, 6 reintentos → `estado=ERROR` + alerta), y despacho interno DIAN (administrativo, fuera de esta parte). No se fusionan porque cada una responde a una obligación distinta (disponibilidad operativa vs. plazo legal DIAN). |

#### 0.4 Restricciones del ER y adaptaciones (sin modificar el modelo)

`modelo_datos_er.mmd` es canónico e intocable (51 tablas verificadas, no 54). Toda necesidad no cubierta se resuelve con columnas/tablas existentes, JSONB ya presente o `log_transaccional` como bitácora universal — nunca agregando una columna o tabla nueva sin marcarla explícitamente como excepción documentada.

| Adaptación | Detalle |
|---|---|
| **A-01 — Póliza RC en tiquetes** | El ER no tiene columna para la póliza de responsabilidad civil de la sede. Se almacena como fila en `documentos` (`tipo='certificado'`, `formato='text/plain'`, contenido en `documento_b64`); el builder de tiquetes la lee vía `GET /documentos?uuid_sucursal=X&tipo=certificado`. |
| **A-02 — Tiempo de tarifa plena** | `tarifas_sucursal` tiene `valor` y `valor_plena` pero no un tiempo explícito de corte. Se computa en `calcular_cotizacion`: `tiempo_tar_plena = (valor_plena / valor) * unidad_minutos`. Ejemplo: unidad=minuto, valor=100, valor_plena=10000 → `tiempo_tar_plena=100` minutos. |
| **A-03 — Regex de placa** | `tipos_vehiculo` no tiene columna de regex. Se mantiene **hardcoded** en `src/lib/validation/placa.ts` del cliente: Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`. (Nota de alcance: no hay respaldo en el corpus de CU para un tercer patrón de "Bicicleta" — si el negocio lo requiere, se agrega como decisión de producto explícita, no como dato ya validado por CU-01/CU-12.) |
| **A-04 — Ingreso forzado con cupo agotado** | `ingreso` no tiene columnas `forzado`/`motivo_forzado`. Se usa `observaciones text` con prefijo estructurado `[FORZADO: <motivo>]` (motivo con mínimo 10 caracteres en el formulario). El backend detecta el prefijo y emite la alerta `capacidad_agotada_forzado`. |
| **A-05 — Estado de impresión de tiquetes** | Ni `ingreso` ni `salidas` tienen columnas de estado de impresión. Se inserta una fila en `log_transaccional` (`tabla_afectada`, `uuid_registro_afectado`, `accion='impreso'`, `datos_nuevos={estado:'impresa'}` o `{estado:'pendiente de impresión'}`); el estado actual se lee como la última fila con `accion='impreso'` para ese registro. |
| **A-06 — `tipo_entrada` (mensualidad/rotación)** | Ver DEC-SUC-21: nunca columna, siempre derivado de `uuid_subscripcion_cliente`. |
| **A-07 — `cierre_dia` en `tipo_arqueo`** | Ver DEC-SUC-13: 4º valor del catálogo, declarado como adaptación explícita, no como siembra de rutina. |
| **A-08 — Severidad de alerta** | `alerta` no tiene columna `severidad`: vive en `alert_types.severity`, se obtiene por `JOIN alerta a ON a.tipo_alerta = at.tipo_alerta`. |
| **A-09 — Prorrateo de suscripción tras el día 15** | No hay columna para el monto prorrateado en `subscripciones_cliente`. Se calcula al momento de la venta (`valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`) y el resultado **sí queda persistido**, pero en `factura_detalle.valor_unitario`/`subtotal` de la factura que se emite al vender la suscripción — no en la tabla de suscripción misma, que no necesita columna nueva. |
| **A-10 — Base del arqueo** | El ER no tiene tabla `config_caja`. La "base de caja" que usa el arqueo es siempre `sesion.valor_inicial_efectivo`/`valor_inicial_datafono` del turno vigente en el momento del arqueo (no un catálogo aparte). |

#### 0.5 Glosario reconciliado

| Término | Definición única (ya reconciliada) |
|---|---|
| **Sucursal / branch-pinned** | Sede fija de la instalación: `uuid_sucursal` viene del claim del JWT `operador-`. Sin selector en la UI. |
| **Ingreso / salida** | Eventos inmutables (`ingreso` `[L-E]`, `salidas` `[A]`), UUID v4, insert-only; su estado (activo/finalizado, pagada/pendiente) siempre se deriva por consulta, nunca se persiste como columna. |
| **Tipo entrada** | `MENSUALIDAD` si `ingreso.uuid_subscripcion_cliente IS NOT NULL`; `ROTACION` en otro caso. Siempre calculado (DEC-SUC-21). |
| **Cotización** | Cálculo puro de CU-02 (sin escritura); válido 15 minutos; server-side siempre (DEC-SUC-12). |
| **Tarifa vigente** | Fila de `tarifas_sucursal` con `estado='activo'`, `vigente_desde <= NOW()` y (`vigente_hasta IS NULL` o `vigente_hasta > NOW()`). |
| **FE / factura electrónica DIAN** | Numerada en la sucursal con su propia resolución (`resolucion_facturacion`), enviada a TopPoint (proveedor DIAN) por el lado cloud. Estado real persistido en `envio_dian.estado` (`pendiente\|enviado\|aceptado\|rechazado`); `factura_electronica` no tiene columna de estado propia, se deriva. |
| **Recibo de pago** | Documento distinto de la FE, numeración propia `sucursal-YYYYMMDD-NNNNNN` (sin relación declarada con el consecutivo DIAN — ver ABIERTO-02). |
| **Turno / sesión** | `sesion`, `valor_inicial_efectivo`/`valor_inicial_datafono`, `estado ∈ {abierta, cerrada}`; solo se actualiza al cerrar (`timestamp_cierre`, `uuid_usuario_cierre`). |
| **Arqueo** | `arqueo` (insert-only), `valor_*_esperado` vs `valor_*_reportado`; diferencia evaluada contra `configuracion_tolerancias` (montos absolutos, no porcentaje — ver Fase 10). Tres tipos reales: `auditoria` (parcial, no cierra nada), `cierre_turno` (cierra la sesión), `cierre_dia` (adaptación A-07, cierra todas las sesiones del día). |
| **Suscripción / mensualidad** | `subscripciones_cliente` + `subscripcion_vehiculos` (hasta 2 placas por defecto según el plan); aplica por placa, no por cliente (una persona puede tener varias mensualidades independientes). |
| **Ocupación** | Derivada: ingresos activos vs `cantidad_vehiculos_sucursal.cantidad`, vía `mv_ocupacion_diaria` con *polling* de 10 s. |
| **Impreso / pendiente de impresión** | Estado leído de la última fila de `log_transaccional` con `accion='impreso'` para el registro (A-05). No confundir con el workflow de reimpresión con costo (`reimpresion_ticket`), que es un caso de uso distinto para tiquetes perdidos o dañados días después. |
| **Reimpresión gratuita vs. reimpresión con costo** | La reimpresión inmediata desde el propio flujo de CU-15x (excepción E3: "operación ya impresa") es gratuita, sin relación con `reimpresion_ticket`. La reimpresión con costo (Fase 8) crea una fila en `reimpresion_ticket`, cobra `costos_servicios` y la carga a una factura. |

#### 0.6 Estrategia de pruebas y CI

| Capa | Herramienta | Cobertura exigida |
|---|---|---|
| Unit (backend) | `pytest` + `pytest-asyncio` + `factory-boy` + `testcontainers` (Postgres real, nunca SQLite en memoria) | ≥90% líneas en módulos de negocio nuevos |
| Unit (frontend) | Vitest | ≥90% líneas / 80% branches en `src/lib/` |
| Integración (frontend) | Vitest + Testing Library + MSW | ≥80% de los hooks de datos |
| E2E | Playwright + `_electron.launch` + `@axe-core/playwright` | 100% de los flujos críticos listados por HU |
| Contrato | Schemathesis contra el OpenAPI real de `parkos_core` | 100% de los endpoints que esta parte consume |
| Visual | Playwright `toHaveScreenshot` | tiquetes (los 4 tipos) + dashboard principal |
| Accesibilidad | `@axe-core/playwright` | 0 violaciones WCAG 2.1 AA en cada pantalla nueva |

CI de esta parte, en orden de ejecución (falla rápido primero): `ruff check` + `ruff format --check` + `mypy --strict` (backend) → `eslint . --max-warnings 0` + `tsc --noEmit` (frontend) → `pytest -q --cov` (backend) → `vitest run --coverage` (frontend) → 5 specs Playwright críticos por PR (login, ingreso, salida+pago, arqueo, impresión) → `vite build` con verificación de bundle <500 KB gzipped por chunk. Ninguna migración Alembic se aplica a `main` sin pasar antes por `alembic upgrade --sql` (dry-run revisado) y sin probar su `downgrade` en un entorno de desarrollo.

#### 0.7 Matriz de fases × CU

| Fase | CU que cubre | Qué desbloquea |
|---|---|---|
| F1 — Prerrequisitos de backend | transversal (prerequisito de F3–F12) | Todas las fases siguientes |
| F2 — Andamiaje Electron | transversal | F3–F12 |
| F3 — Autenticación y turno | transversal (base de todo CU operativo) | F4–F12 |
| F4 — Catálogos y ocupación | CU-01 (parametrización local), CU-02 (lectura), CU-11/CU-12 (solo lectura) | F6, F7 |
| F5 — Impresión térmica | transversal, habilita CU-15E/S/SM | F6, F7, F8 |
| F6 — Ingreso vehicular | **CU-01**, **CU-15E** | F7 (deriva a salida) |
| F7 — Salida y tarifa | **CU-02**, **CU-03**, **CU-03M**, **CU-15S**, **CU-15SM** | F8 |
| F8 — Cobro y FE | **CU-04**, **CU-05**, reimpresión con costo | F9 (venta con cobro reutiliza el mismo patrón) |
| F9 — Suscripciones | **CU-06** (operativo: consumo + venta) | — |
| F10 — Arqueos | **CU-10** | — |
| F11 — Sync y alertas | **CU-07** (vista operador), **CU-14** (vista operador) | — |
| F12 — Reportería local | **CU-09** (subset "Mi turno") | — |

#### 0.8 Datos de prueba de referencia

Valores concretos, reutilizables en fixtures de test y demos, para no inventar datos distintos en cada fase (evita fixtures inconsistentes entre HUs que en teoría comparten el mismo dato de dominio):

| Dato | Valor de referencia | Uso |
|---|---|---|
| Placa válida — Auto | `ABC123` | Fase 4, 6, 7 |
| Placa válida — Moto | `ABC12D` | Fase 4, 6, 7 |
| Placa con formato inválido | `AB1234` (4 dígitos, no matchea ningún regex) | Fase 6 (error de formato) |
| Placa con error de tipeo tolerado | `AB0123` (debería leerse `ABC123` con O→0 revertido) | Fase 7 (búsqueda tolerante) |
| NIT válido (módulo 11) | `800.123.456-7` | Fase 8 (validación positiva) |
| NIT inválido (módulo 11) | `800.123.456-1` (DV incorrecto) | Fase 8 (validación negativa) |
| NIT de consumidor final | `222222222222222` | Fase 8 (FE por defecto) |
| Email válido | `cliente@ejemplo.com` | Fase 8, 9 |
| Email inválido | `cliente@` | Fase 8 (validación negativa) |
| Motivo de forzado (≥10 caracteres) | `Cliente frecuente, autorizado por supervisor` | Fase 6 |
| Motivo de reimpresión (≥10 caracteres) | `Tiquete original mojado, ilegible` | Fase 8 |
| Monto de tarifa por minuto (ejemplo) | `valor=100`, `valor_plena=10000` → `tiempo_tar_plena=100 min` | Fase 4, 7 (adaptación A-02) |
| Porcentaje de IVA | `19%` (valor de referencia colombiano, se lee siempre de `impuestos`, nunca hardcoded) | Fase 7, 8 |

#### 0.9 Convenciones de nombres de archivo

- Componentes React: `PascalCase.tsx` (`PlacaInput.tsx`), un componente por archivo.
- Hooks: `camelCase` con prefijo `use` (`useCotizacion.ts`).
- Tests: mismo nombre del archivo bajo prueba + `.test.ts(x)`, en `__tests__/` junto al código; e2e en `e2e/<flujo>.spec.ts` a nivel de proyecto.
- Migraciones Alembic: `YYYY_MM_DD_NNNN_slug.py` (fecha + contador de 4 dígitos + slug en snake_case), consistente con la convención ya usada en las migraciones reales del repo (`0001` a `0021`).
- Schemas Pydantic: `<Recurso><Acción>` (`IngresoCreate`, `ArqueoRead`, `FacturaElectronicaReintentar`).

#### 0.10 Ejemplo de claves i18n por namespace

Muestra representativa (no exhaustiva) de los 7 namespaces, para fijar la convención de nombres de clave antes de que cada fase agregue las suyas:

| Namespace | Clave | Texto es-CO |
|---|---|---|
| `common` | `common.confirmar` | "Confirmar" |
| `common` | `common.cancelar` | "Cancelar" |
| `auth` | `auth.login.title` | "Iniciar sesión" |
| `auth` | `auth.login.email` | "Correo electrónico" |
| `operacion` | `operacion.placa_formato_invalido` | "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" |
| `operacion` | `operacion.mensualidad_activa` | "Mensualidad activa: {{cliente}}" |
| `caja` | `caja.turno_abierto` | "Turno abierto desde {{hora}}" |
| `caja` | `caja.diferencia_justificacion` | "Justificá la diferencia antes de confirmar" |
| `facturacion` | `facturacion.fe_pendiente` | "Factura electrónica pendiente de envío" |
| `sync` | `sync.sin_conexion_local` | "Sin conexión con API local" |
| `errors` | `errors.network` | "Sin conexión. Reintentaremos en cuanto vuelvas a estar en línea." |
| `errors` | `errors.invalid_credentials` | "Correo o contraseña incorrectos" |

---

## Fase 1 — Prerrequisitos de backend

**Objetivo**: cerrar, en `parkos_core`, todos los bugs y endpoints faltantes que `web_sucursal` necesita antes de poder construir UI real sobre datos verdaderos. Esta fase no tiene pantalla propia: es la condición de entrada de todas las demás. Cubre transversalmente CU-01 a CU-10 y desbloquea el resto de fases (marcado en cada HU con qué Fase queda desbloqueada).

Todas las tareas de esta fase siguen las convenciones del backend real: SQLAlchemy 2.0 async, Pydantic v2, migraciones Alembic con `include_schemas=True`, `ruff`/`mypy --strict`, tests con `pytest-asyncio`. Ninguna migración de esta fase modifica una columna existente del ER — todas son `CREATE`/`ADD COLUMN NULL`/siembra de filas de catálogo, consistentes con la restricción dura de no tocar el modelo.

### HU-F1.1 — Corregir el bug de ordenamiento en `router_factory` para tablas sin `vigente_desde`

Desbloquea: Fase 11 (Alertas), y cualquier lectura futura de `anulaciones`/`reclamos`/`reimpresion_ticket`.

**Historia**: Como desarrollador de backend, quiero que el listado genérico (`GET` de colección) de `make_router` no asuma la columna `vigente_desde` en tablas que no la tienen, para que los endpoints de tablas de workflow (`alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket`) no fallen en tiempo de ejecución al pedir la colección completa.

**Criterios de aceptación**:
- Given una tabla de workflow sin columna `vigente_desde` montada con `make_router`, When se llama `GET /workflows/alerta` (colección, sin filtros), Then responde `200` con `{items, next_cursor}` en vez de lanzar `AttributeError`/error de SQL.
- Given la misma tabla, When se pagina con `cursor`, Then el cursor usa `timestamp_evento` (o `created_at` si la tabla no tiene `timestamp_evento`) + `uuid` como clave de orden, nunca `vigente_desde`.
- Given una tabla `[V]` normal (con `vigente_desde`), When se lista, Then el comportamiento actual (orden por `vigente_desde desc, uuid asc`) no cambia — regresión cero.

**Regla de negocio**: el propio código de `router_factory.py` ya guarda la condición `vigente_hasta IS NULL` tras `hasattr(model_cls, "vigente_hasta")`, pero el `order_by` y la comparación de cursor no llevan la misma guarda — es una inconsistencia interna del archivo, confirmada leyendo el código real (`api/router_factory.py`, función `make_router`, bloque `list_endpoint`).

**Tablas ER tocadas**: ninguna migración; cambio de código puro sobre `alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket` (lectura, sin escritura nueva).

**Endpoints**: `GET /workflows/alerta`, `GET /workflows/anulaciones`, `GET /workflows/reclamos`, `GET /workflows/reimpresion-ticket` (corregidos, no nuevos).

**Manejo de errores**: sin cambio de contrato de error; el fix elimina un 500 no controlado, no introduce un nuevo código de error.

**Pruebas**: `backend/tests/unit/test_router_factory_no_vigente_desde.py` — 4 casos (listar `alerta` vacío, listar con datos, paginar con cursor, listar una tabla `[V]` de control para confirmar que no hay regresión).

**Tamaño estimado**: 60 LOC.

**Tareas atómicas**:
- **HU-F1.1-T1**: en `backend/packages/parkos_core/src/parkos_core/api/router_factory.py`, función `list_endpoint`, condicionar el `order_by`/comparación de cursor a `hasattr(model_cls, "vigente_desde")`; para el caso `False`, ordenar por `getattr(model_cls, "timestamp_evento", model_cls.created_at)` desc + `uuid` asc, y construir el cursor con esos mismos campos.
- **HU-F1.1-T2**: extraer la clave de orden a una función `_order_key(model_cls)` reutilizada tanto en `list_endpoint` como en la construcción del cursor, para no duplicar la rama condicional.
- **HU-F1.1-T3**: escribir `test_router_factory_no_vigente_desde.py` con los 4 casos descritos arriba, usando `AlertaFactory`/`AnulacionesFactory` de `pytest-asyncio` + `testcontainers`.

---

### HU-F1.2 — `GET /auth/me`, cookie `httpOnly` y lockout real

Desbloquea: Fase 3 (Autenticación y turno).

**Historia**: Como operador, quiero que al iniciar sesión el servidor me identifique de forma segura (cookie, no solo Bearer) y me bloquee tras varios intentos fallidos, para que mi sesión sea robusta ante errores de tipeo repetidos y ataques de fuerza bruta.

**Criterios de aceptación**:
- Given credenciales válidas (`email`+`password`), When `POST /auth/login`, Then responde `200`, setea cookie `parkos_session` (`httponly=True, secure=True, samesite=Lax`) y el cuerpo trae `access_token` (Bearer, fallback transitorio).
- Given una cookie o Bearer válidos, When `GET /auth/me`, Then responde `200` con `{user, permisos, sucursal, sucursales_permitidas, expires_at}`.
- Given 5 intentos fallidos consecutivos para el mismo usuario, When se intenta un 6º login, Then responde `429` con cabecera `Retry-After` (segundos) calculada desde `configuracion_seguridad.minutos_bloqueo_login`.
- Given un usuario bloqueado, When el tiempo de bloqueo expira, Then el siguiente intento válido limpia el contador de intentos fallidos.

**Regla de negocio**: umbral y duración salen de `configuracion_seguridad` (override por sucursal o default global); valores de siembra recomendados si la sucursal no tiene override: 5 intentos, 15 minutos de bloqueo, 90 días de expiración de password — se documentan como decisión de producto, sin respaldo literal en ningún CU, no como requisito citado.

**Tablas ER tocadas**: `usuarios` (SELECT por `email`), `login` (INSERT en cada intento, `estado ∈ {exitoso, fallido, cerrado}`), `configuracion_seguridad` (SELECT, resolución override-o-global ya implementada en `repo/config_override.py`).

**Endpoints**: `GET /auth/me` (nuevo), `POST /auth/login` (modificado: setea cookie + enforcement real de lockout), `GET /usuarios/{uuid}/login?limit=10&cursor=...` (nuevo — ver HU-F1.15, comparten migración de índice).

Ejemplo de contrato de `GET /auth/me`:

```jsonc
// 200 OK
{
  "user": { "uuid": "…", "nombre": "…", "apellido": "…", "email": "…" },
  "sucursal": { "uuid": "…", "nombre": "…", "prefijo_nombre": "…" },
  "sucursales_permitidas": ["…"],
  "permisos": ["realizar_arqueo", "anular_ingreso", "config_catalogo"],
  "expires_at": "2026-09-11T20:00:00Z"
}
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo | Mensaje mostrado al operador |
|---|---|---|---|
| 401 | `invalid_credentials` | Email inexistente o password incorrecta (mismo mensaje en ambos casos, anti-enumeración) | "Correo o contraseña incorrectos" |
| 429 | `account_locked` | 5 intentos fallidos consecutivos dentro de la ventana configurada | "Cuenta bloqueada temporalmente. Reintentá en {retry_after_seconds}s" |
| 404 | `not_found` | `GET /auth/me` sin sesión válida | redirige a `/login` |

**Pruebas**:

`backend/tests/unit/test_auth_me.py` — 2 casos: sesión válida devuelve el perfil completo; sesión inválida/expirada devuelve `404`.

`backend/tests/unit/test_auth_lockout.py` — 4 casos:
1. 5 intentos fallidos consecutivos → `429` con `Retry-After` correcto.
2. El bloqueo expira tras los minutos configurados y el siguiente intento se procesa normalmente.
3. Un login exitoso limpia el contador de intentos fallidos.
4. `Retry-After` refleja exactamente `configuracion_seguridad.minutos_bloqueo_login` (override de sucursal si existe, default global si no).

**Tamaño estimado**: 210 LOC.

**Tareas atómicas**:
- **HU-F1.2-T1**: en `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py`, agregar `GET /me` que arma la respuesta desde `TenantContext` + `permisos_usuario` + `usuarios_sucursal`.
- **HU-F1.2-T2**: modificar `POST /login` para `response.set_cookie("parkos_session", jwt, httponly=True, secure=True, samesite="lax")` además del cuerpo con `access_token`.
- **HU-F1.2-T3**: implementar enforcement de lockout en el mismo endpoint: contar filas `login` con `estado='fallido'` y `timestamp_evento` dentro de la ventana de `configuracion_seguridad`, comparar contra `max_intentos_login`.
- **HU-F1.2-T4**: escribir las migraciones/tests indicados arriba.

---

### HU-F1.3 — Constraint de sesión única y `GET /caja-sesion/sesion/me`

Desbloquea: Fase 3 (turno).

**Historia**: Como operador, no quiero poder abrir dos turnos a la vez, y quiero que la app sepa de inmediato si ya tengo uno abierto.

**Criterios de aceptación**:
- Given un usuario con sesión `abierta`, When `POST /caja-sesion/sesiones` de nuevo, Then responde `409 {"error":"sesion_ya_abierta"}`.
- Given una sesión ya `cerrada`, When `PUT /caja-sesion/sesion/{uuid}/cerrar` de nuevo, Then responde `409 {"error":"sesion_ya_cerrada"}`.
- Given un usuario con sesión abierta, When `GET /caja-sesion/sesion/me`, Then responde `200` con la fila; sin sesión abierta, responde `404`.

**Tablas ER tocadas**: `sesion` — índice único parcial `CREATE UNIQUE INDEX one_open_session_per_user ON sesion (uuid_usuario) WHERE estado='abierta'` (migración Alembic, `ADD COLUMN`/`CREATE INDEX`, sin tocar columnas existentes).

**Endpoints**: `GET /caja-sesion/sesion/me` (nuevo), `POST /caja-sesion/sesiones` y `PUT /caja-sesion/sesion/{uuid}/cerrar` (agregan manejo de `409`).

**Manejo de errores**: `409 {"error":"sesion_ya_abierta"}`, `409 {"error":"sesion_ya_cerrada"}`, `404 {"error":"not_found"}` en `/me` sin sesión abierta.

**Pruebas**: `backend/tests/unit/test_caja_sesion_constraint.py` (3 casos).

**Tamaño estimado**: 110 LOC.

**Tareas atómicas**:
- **HU-F1.3-T1**: migración `migrations/versions/2026_09_11_0022_add_one_open_session_index.py` con el índice único parcial.
- **HU-F1.3-T2**: capturar `IntegrityError` del índice en `POST /sesiones` y traducirlo a `409`.
- **HU-F1.3-T3**: agregar chequeo de `estado='cerrada'` previo en `PUT /cerrar` → `409` explícito antes de tocar la fila.
- **HU-F1.3-T4**: agregar `GET /sesion/me` (`WHERE uuid_usuario=:actor AND estado='abierta' LIMIT 1`).

---

### HU-F1.4 — Filtro `vigente_en` en tarifas

Desbloquea: Fase 4 (catálogos y ocupación).

**Historia**: Como operador, quiero que la tarifa que veo sea siempre la vigente en el momento exacto de la consulta, no solo la última fila devuelta sin filtrar.

**Criterios de aceptación**: Given `GET /empresa/tarifas-sucursal?uuid_tipo_vehiculo=X&vigente_en=<ISO8601>`, When se omite `vigente_en`, Then se usa `NOW()` por defecto; Then el filtro real aplicado es `vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en)`.

**Tablas ER tocadas**: `tarifas_sucursal` (SELECT).

**Endpoints**: `GET /empresa/tarifas-sucursal` (modificado, parámetro nuevo opcional).

**Pruebas**: `backend/tests/unit/test_tarifas_vigente_en.py` (3 casos: sin parámetro, con fecha pasada, con fecha futura sobre tarifa programada).

**Tamaño estimado**: 60 LOC.

**Tareas atómicas**:
- **HU-F1.4-T1**: agregar `Query(None)` `vigente_en: datetime | None` al endpoint, con default `datetime.now(UTC)`.
- **HU-F1.4-T2**: aplicar el filtro bitemporal descrito arriba en la consulta SQLAlchemy existente.

---

### HU-F1.5 — Vista materializada de ocupación + endpoint

Desbloquea: Fase 4 (ocupación en vivo).

**Historia**: Como operador, quiero ver cuántos cupos quedan disponibles por tipo de vehículo en tiempo casi real, sin que el servidor recalcule sobre toda la tabla `ingreso` en cada petición.

**Criterios de aceptación**: Given `GET /operacion/ocupacion?uuid_sucursal=X`, Then responde `200` con `[{uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible}]`, calculado desde `mv_ocupacion_diaria` (no una columna mutable); Given un ingreso o salida nuevos, When pasan 10 s (intervalo de refresh), Then la vista refleja el cambio.

**Regla de negocio**: la disponibilidad **nunca** se mantiene por trigger sobre una columna mutable `disponible` en `cantidad_vehiculos_sucursal` — esa tabla solo tiene `cantidad` (cupo máximo configurado); el descarte explícito de un trigger de ese tipo (propuesto en una versión anterior del backlog) es intencional: el cálculo siempre compara contra ingresos activos vía la vista.

**Tablas ER tocadas**: `cantidad_vehiculos_sucursal` (SELECT `cantidad`), `ingreso`/`salidas`/`anulaciones` (fuente de la vista, SELECT).

**Endpoints**: `GET /operacion/ocupacion?uuid_sucursal=X` (nuevo).

**Pruebas**: `backend/tests/integration/test_ocupacion_view.py` (3 casos: cupo lleno, cupo parcial, refresh tras nuevo ingreso).

**Tamaño estimado**: 160 LOC.

**Tareas atómicas**:
- **HU-F1.5-T1**: migración `migrations/versions/2026_09_11_0023_add_mv_ocupacion_diaria.py` — `CREATE MATERIALIZED VIEW mv_ocupacion_diaria AS SELECT ... GROUP BY uuid_sucursal, uuid_tipo_vehiculo` (activos = ingresos sin salida no anulada).
- **HU-F1.5-T2**: job de refresco (`REFRESH MATERIALIZED VIEW CONCURRENTLY mv_ocupacion_diaria`) cada 10 s desde `job-sync-sucursal` o un scheduler ligero del propio `api-sucursal`.
- **HU-F1.5-T3**: endpoint `GET /operacion/ocupacion` que hace `JOIN` de la vista con `cantidad_vehiculos_sucursal` para exponer `cupo_maximo` y `disponible = cupo_maximo - activos`.

---

### HU-F1.6 — Validaciones reales en `POST /operacion/ingresos`

Desbloquea: Fase 6 (ingreso vehicular, CU-01).

**Historia**: Como operador, quiero que el servidor rechace placas con formato inválido, detecte automáticamente mensualidad/rotación, valide cupo y exija motivo cuando fuerzo un ingreso sin cupo — para no depender de que el cliente sea el único lugar donde se aplican estas reglas.

**Criterios de aceptación**:
- Given una placa que no matchea ningún regex activo, When `POST /operacion/ingresos`, Then `422 {"error":"placa_formato_invalido", "formatos_aceptados":[...]}`.
- Given una placa con mensualidad vigente, When se registra el ingreso, Then la respuesta expone el tipo derivado `MENSUALIDAD` (sin persistir columna, DEC-SUC-21).
- Given otra placa de la misma mensualidad ya en el patio, When se registra la nueva placa, Then el tipo derivado es `ROTACION`.
- Given cupo agotado para el tipo detectado y `forzado=true` sin `observaciones` con prefijo `[FORZADO:`, When se envía, Then `422 {"error":"motivo_forzado_requerido"}` (mínimo 10 caracteres en el motivo).
- Given una placa con ingreso activo ya existente en la sucursal, When se reintenta el ingreso, Then `409 {"error":"ingreso_activo_existente"}`.

**Regla de negocio**: BR2 de CU-01, literal: la autodetección por regex es la única fuente válida, sin override manual — si el regex falla, es un bug a corregir, nunca una excepción de negocio.

**Tablas ER tocadas**: `ingreso` (INSERT), `subscripcion_vehiculos`/`subscripciones_cliente` (SELECT, vigencia y 2ª placa), `tipos_vehiculo` (SELECT, regex), `cantidad_vehiculos_sucursal` (SELECT, cupo vía `mv_ocupacion_diaria`).

**Endpoints**: `POST /operacion/ingresos` (modificado, agrega las 4 validaciones).

Ejemplo de contrato:

```jsonc
// Request
{
  "placa": "ABC123",
  "observaciones": "[FORZADO: cliente frecuente, autorizado por supervisor]", // solo si forzado
  "forzado": false
}
// 201 Created
{
  "uuid": "…", "placa": "ABC123", "uuid_tipo_vehiculo": "…",
  "tipo_entrada": "rotacion", // MENSUALIDAD | ROTACION — SIEMPRE calculado, nunca columna (DEC-SUC-21)
  "fecha_ingreso": "2026-09-11T14:32:00Z"
}
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo | Detalle adicional |
|---|---|---|---|
| 422 | `placa_formato_invalido` | La placa no matchea ningún regex activo | `formatos_aceptados: ["^[A-Z]{3}[0-9]{3}$", "^[A-Z]{3}[0-9]{2}[A-Z]$"]` |
| 422 | `motivo_forzado_requerido` | `forzado=true` sin prefijo `[FORZADO:` de ≥10 caracteres en `observaciones` | — |
| 409 | `ingreso_activo_existente` | Ya existe un ingreso activo para esa placa en la sucursal | El cliente debe derivar a `SalidaFlow` (Fase 7), no mostrarlo como error bloqueante al operador |

**Pruebas**: `backend/tests/unit/test_operacion_ingresos_validaciones.py` — 8 casos:

1. Placa con formato válido de Auto → `201`.
2. Placa con formato inválido → `422 placa_formato_invalido`.
3. Placa con mensualidad vigente → `tipo_entrada` derivado `MENSUALIDAD` en la respuesta.
4. Segunda placa de la misma mensualidad ya en el patio → `tipo_entrada` derivado `ROTACION`.
5. Cupo agotado sin `forzado` → `422 motivo_forzado_requerido`.
6. Cupo agotado con `forzado=true` y motivo válido (≥10 caracteres tras el prefijo) → `201`, alerta `capacidad_agotada_forzado` generada.
7. Placa ya con ingreso activo → `409 ingreso_activo_existente`.
8. Orden de validación correcto: el regex se valida antes que la mensualidad (verificado explícitamente, no solo el resultado final).

**Tamaño estimado**: 260 LOC.

**Tareas atómicas**:
- **HU-F1.6-T1**: validar regex contra `tipos_vehiculo` activos en `operacion.py`, antes de cualquier otra validación (orden correcto: normalizar → validar formato → validar ingreso activo → recién ahí evaluar mensualidad/rotación, invirtiendo el orden ambiguo del CU original donde se evalúa mensualidad antes que el formato).
- **HU-F1.6-T2**: detectar suscripción vigente (`JOIN subscripcion_vehiculos + subscripciones_cliente`) y calcular el tipo derivado en la respuesta, sin persistirlo.
- **HU-F1.6-T3**: validar cupo vía `mv_ocupacion_diaria`; si `disponible=0` exigir `forzado=true` + `observaciones` con prefijo `[FORZADO: <motivo>]` de ≥10 caracteres tras el prefijo.
- **HU-F1.6-T4**: validar no-duplicado (`EXISTS` de ingreso activo para la placa+sucursal) → `409`.
- **HU-F1.6-T5**: los 8 tests unitarios descritos.

---

### HU-F1.7 — Endpoints de escritura de salida (rotación y mensualidad)

Desbloquea: Fase 7 (CU-02/03/03M).

**Historia**: Como operador, quiero poder registrar la salida de un vehículo (con o sin mensualidad), liberando el cupo y dejando la operación lista para el cobro (si aplica).

**Criterios de aceptación**:
- Given un `uuid_ingreso` con cotización vigente (≤15 min) y sin salida no anulada previa, When `POST /operacion/salidas`, Then `201` con `uuid_salida`, `estado='PENDIENTE_PAGO'`, cupo devuelto.
- Given un `uuid_ingreso` ya con salida no anulada, When se reintenta, Then `409 {"error":"salida_duplicada"}`.
- Given una placa con mensualidad vigente, When `POST /operacion/salidas/mensualidad`, Then `201` con `estado='MENSUALIDAD_PAGO'`, sin ningún monto asociado a `salidas` (sigue sin columna de monto). *(Corrección 2026-09-24: el endpoint real es un único `POST /operacion/salidas` que deriva `tipo_salida='MENSUALIDAD'|'ROTACION'` server-side según `cobrar` — no existe un segundo endpoint `/salidas/mensualidad` en el código, DEC-MONO-01. Además, desde migration `0050_cotizar_mensualidad_factura_descuento`, "sin ningún monto asociado" aplica solo a `salidas`: el operador SÍ debe registrar una factura completa con descuento a $0 después — ver "Factura por mensualidad ($0)" en el glosario y HU-F7.2/HU-F7.3.)*
- Given una placa **sin** mensualidad vigente enviada a este segundo endpoint, When se llama, Then `400 {"error":"mensualidad_no_vigente"}` (el cliente debe derivar a `POST /operacion/salidas` normal). *(Ver corrección anterior — en el código real esto es simplemente la derivación `tipo_salida='ROTACION'` del único endpoint, no un código de error distinto.)*

**Regla de negocio**: ninguno de los dos endpoints modifica `ingreso` (insert-only); ninguno persiste un monto en `salidas` (esa tabla no tiene columna `valor`, DEC-SUC-23) — el monto viaja en memoria de UI hasta CU-04.

**Tablas ER tocadas**: `salidas` (INSERT: `uuid`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, sin columna de monto), `cantidad_vehiculos_sucursal` (recalculado vía vista, sin `UPDATE` de columna mutable), `anulaciones` (SELECT, validar que el ingreso no esté anulado), `subscripciones_cliente`/`subscripcion_vehiculos` (SELECT, solo en el endpoint de mensualidad).

**Endpoints**: `POST /operacion/salidas` (nuevo), `POST /operacion/salidas/mensualidad` (nuevo).

Ejemplo de contrato de `POST /operacion/salidas`:

```jsonc
// Request
{ "uuid_ingreso": "…", "uuid_cotizacion_ref": "…" } // referencia opaca al cálculo de HU-F1.8, valida vigencia server-side
// 201 Created
{ "uuid": "…", "uuid_ingreso": "…", "estado": "PENDIENTE_PAGO", "fecha_salida": "2026-09-11T16:05:00Z" }
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo |
|---|---|---|
| 409 | `salida_duplicada` | El ingreso ya tiene una salida no anulada |
| 400 | `mensualidad_no_vigente` | `POST /salidas/mensualidad` llamado sobre una placa sin mensualidad vigente — el cliente debe derivar a `POST /salidas` normal |
| 410 | `cotizacion_expirada` | La cotización referenciada tiene más de 15 minutos — recalcular vía `GET /operacion/cotizar` antes de reintentar |

**Pruebas**: `backend/tests/unit/test_operacion_salidas.py` (4 casos), `backend/tests/unit/test_operacion_salidas_mensualidad.py` (3 casos).

**Tamaño estimado**: 220 LOC.

**Tareas atómicas**:
- **HU-F1.7-T1**: índice único parcial `one_exit_per_ingreso` sobre `salidas` (`WHERE NOT EXISTS` de anulación ejecutada, mismo patrón que `sesion`).
- **HU-F1.7-T2**: `POST /operacion/salidas` — valida cotización vigente (recibe `uuid_ingreso` + timestamp de cálculo del cliente, o revalida server-side contra `calcular_cotizacion`), inserta la fila, no toca `ingreso`.
- **HU-F1.7-T3**: `POST /operacion/salidas/mensualidad` — valida mensualidad vigente vía `subscripcion_vehiculos`/`subscripciones_cliente` (`fecha_vencimiento > NOW() AND estado='activo'`), inserta con `estado` conceptual de mensualidad (ver nota de HU-F1.9 sobre dónde vive ese estado).
- **HU-F1.7-T4**: los 7 tests unitarios descritos.

---

### HU-F1.8 — Función `calcular_cotizacion` + `GET /operacion/cotizar`

Desbloquea: Fase 7 (CU-02).

**Historia**: Como operador, quiero pedir la cotización de una salida y recibir siempre el mismo resultado (idempotente) mientras la tarifa no cambie, calculado enteramente en el servidor.

**Criterios de aceptación**:
- Given un `uuid_ingreso` con ingreso activo, When `GET /operacion/cotizar?uuid_ingreso=X`, Then responde `200` con `{uuid_ingreso, tiempo_minutos, total_a_pagar, iva, subtotal, vigente_hasta}` en ≤5 s (timeout de cliente).
- Given `valor_plena>0` y `tiempo>=tiempo_tar_plena`, Then `total_a_pagar=valor_plena`; en cualquier otro caso, `total_a_pagar=valor*tiempo_redondeado` (`Math.ceil`).
- Given una placa con mensualidad vigente, Then la respuesta trae `{cobrar:false, motivo:'mensualidad_vigente', ...}`. *(Corrección 2026-09-24, migration 0050: desde esta migración la respuesta SÍ incluye el desglose fiscal completo — `subtotal`, `iva`, `total`, `tiempo_minutos`, `tarifa_uuid`, `vigente_hasta` — más `uuid_subscripcion_cliente` y `concepto_descuento` (nombre del plan). El criterio original ["sin desglose de IVA"] queda obsoleto: el desglose ahora se calcula SIEMPRE, incluso cuando `cobrar=false`, para que la salida-mensualidad pueda armar la factura con descuento — ver "Factura por mensualidad ($0)" en el glosario. También se agregó el motivo `'multiple_vehiculos_plan_empresa'` para planes de flota (`cantidad_maxima_vehiculos > 2`) con varios vehículos simultáneos en patio.)*
- Given que no existe una fila de `impuestos` vigente con `codigo='IVA'`, Then `500 {"error":"iva_no_configurado"}` (error de configuración, nunca un cálculo silencioso sin IVA). *(Corrección 2026-09-24, migration 0049: el criterio original decía `nombre='IVA'`; `nombre` es una etiqueta cosmética sin restricción de unicidad — `codigo` es el UK01 real del catálogo, `modelo_datos_er.mmd:192`, y coincide con el `natural_key` de sync y con `repo/impuestos.py`/`repo/factura.py`, que ya resolvían por `codigo`. Bug real reproducido dos veces por esta fuente de verdad partida — ver docstring de la migración 0049.)*

**Regla de negocio (DEC-SUC-24, literal de CU-02 AC7)**: `iva = total_a_pagar * porcentaje_impuesto`; `subtotal = total_a_pagar - iva` — se implementa tal cual, sin "corregir" la base del cálculo.

**Tablas ER tocadas**: `ingreso`/`salidas`/`anulaciones` (SELECT, resolver ingreso activo), `tarifas_sucursal` (SELECT), `impuestos` (SELECT, IVA vigente), `subscripciones_cliente` (SELECT).

**Endpoints**: `GET /operacion/cotizar?uuid_ingreso=X` (nuevo).

Ejemplo de contrato:

```jsonc
// 200 OK — rotación normal
{ "uuid_ingreso": "…", "cobrar": true, "tiempo_minutos": 135, "tarifa_valor": 100,
  "subtotal": 11345, "iva": 2155, "total": 13500, "vigente_hasta": "2026-09-11T16:20:00Z" }
// 200 OK — mensualidad vigente (migration 0050: desglose completo + descuento, ver corrección arriba)
{ "uuid_ingreso": "…", "cobrar": false, "motivo": "mensualidad_vigente",
  "subtotal": 11345, "iva": 2155, "total": 13500, "tiempo_minutos": 135,
  "tarifa_uuid": "…", "vigente_hasta": "2026-09-11T16:20:00Z",
  "uuid_subscripcion_cliente": "…", "concepto_descuento": "Plan Oro" }
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo |
|---|---|---|
| 404 | `ingreso_no_encontrado` | El `uuid_ingreso` no existe o no está activo en la sucursal |
| 500 | `iva_no_configurado` | No existe fila de `impuestos` vigente con `codigo='IVA'` — error de configuración, nunca se calcula sin IVA |

**Pruebas**: `backend/tests/unit/test_calcular_cotizacion.py` — 3 escenarios (rotación, mensualidad, tiempo ≥ tiempo de tarifa plena).

**Tamaño estimado**: 200 LOC.

**Tareas atómicas**:
- **HU-F1.8-T1**: migración con función PL/pgSQL `calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb`, implementando la fórmula exacta de arriba.
- **HU-F1.8-T2**: endpoint `GET /operacion/cotizar` que invoca la función y mapea la respuesta al schema Pydantic de salida.
- **HU-F1.8-T3**: los 3 tests unitarios.

---

### HU-F1.9 — Facturación transaccional: factura, pagos, validación de NIT

Desbloquea: Fase 8 (CU-04).

**Historia**: Como operador, quiero que al cobrar se registren en una sola transacción la factura, sus líneas, el IVA y el pago — de forma que si algo falla, no quede una factura sin pago ni un pago sin factura.

**Criterios de aceptación**:
- Given un cobro válido, When `POST /facturacion/factura`, Then en una sola transacción (`BEGIN`/`COMMIT`/`ROLLBACK` explícitos) se crean `facturas` + `factura_detalle` + `factura_impuestos`, y `salidas.estado` pasa a `'PAGADO'` (única excepción al patrón insert-only de `salidas`, ver DEC-SUC-23).
- Given el medio de pago, When `POST /facturacion/factura-pagos`, Then se exige `referencia` (voucher) no vacía si el medio es datáfono.
- Given una FE con datos propios del cliente (no consumidor final), When se valida el NIT, Then se aplica el algoritmo de módulo 11 real (`validar_nit_modulo11`, caso de referencia `800.123.456-7`) tanto en el schema de creación de cliente como en el de creación de factura.
- Given un email inválido en los datos del cliente, Then `422` con detalle RFC 5322.

**Tablas ER tocadas**: `facturas` (INSERT), `factura_detalle` (INSERT, concepto="Estacionamiento"), `factura_impuestos` (INSERT, snapshot de IVA), `factura_pagos` (INSERT, `medio_pago`, `valor`, `referencia`, `uuid_sesion`, `tipo_movimiento='pago'`), `salidas` (`UPDATE estado='PAGADO'`), `clientes` (SELECT/INSERT condicional si hay datos propios del cliente).

**Endpoints**: `POST /facturacion/factura` (nuevo, transaccional), `POST /facturacion/factura-pagos` (nuevo).

Ejemplo de contrato de `POST /facturacion/factura`:

```jsonc
// Request
{ "uuid_ingreso": "…", "uuid_salida": "…", "subtotal": 11345, "iva": 2155, "total": 13500,
  "medio_pago": "efectivo", "monto_recibido": 15000, "uuid_sesion": "…",
  "fe_con_datos": false } // true exige nit/dv/nombre/email
// 201 Created
{ "uuid_factura": "…", "uuid_factura_electronica": "…", "estado_fe": "pendiente" }
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo |
|---|---|---|
| 422 | `nit_invalido` | Falla la validación de módulo 11; el detalle incluye el DV esperado |
| 422 | `email_invalido` | Email no cumple RFC 5322 (solo si `fe_con_datos=true`) |
| 400 | `voucher_requerido` | Medio `datafono` sin `referencia` (voucher) |
| 400 | `monto_insuficiente` | Medio `efectivo` con `monto_recibido < total` |

**Pruebas**: `backend/tests/unit/test_facturacion_factura.py` (transacción atómica, rollback ante fallo de una de las 3 tablas), `backend/tests/unit/test_validar_nit_modulo11.py` (casos válido/inválido con `800.123.456-7`).

**Tamaño estimado**: 330 LOC.

**Tareas atómicas**:
- **HU-F1.9-T1**: `POST /facturacion/factura` con bloque transaccional explícito (no depender del autocommit implícito del ORM).
- **HU-F1.9-T2**: `POST /facturacion/factura-pagos` con validación de voucher no vacío en datáfono.
- **HU-F1.9-T3**: helper `validar_nit_modulo11(nit, dv)` en Pydantic, aplicado en `ClienteCreate` y en el schema de creación de factura con datos propios.
- **HU-F1.9-T4**: los tests descritos.

---

### HU-F1.10 — Numeración de factura electrónica y estado DIAN

Desbloquea: Fase 8 (CU-05).

**Historia**: Como operador, quiero que al generar la FE se le asigne automáticamente el consecutivo de la resolución vigente de mi sucursal, y poder ver/reintentar su estado si queda pendiente o falla.

**Criterios de aceptación**:
- Given una factura pagada, When `POST /facturacion/factura-electronica`, Then se asigna `prefijo`+`consecutivo` vía `assign_consecutivo` (`SELECT...FOR UPDATE` sobre `resolucion_facturacion`, ya implementado) y se crea la fila inicial de `envio_dian` con `estado='pendiente'`.
- Given una FE existente, When `GET /facturacion/factura-electronica/{uuid}`, Then responde con `estado` crudo (`pendiente|enviado|aceptado|rechazado`) y `cufe` (si `aceptado`) — nunca un booleano `reportado_dian` inexistente.
- Given una FE en `rechazado`, When `POST /facturacion/factura-electronica/{uuid}/reintentar`, Then se inserta una **nueva fila** en `envio_dian` con `uuid_envio_padre` apuntando a la anterior (cadena de reintentos, nunca `UPDATE`).
- Given que el rango de la resolución vigente está agotado, When se intenta asignar consecutivo, Then `409 {"error":"numeracion_agotada"}` y se dispara la alerta ya sembrada `fe_numbering_exhausted`.

**Regla de negocio**: la numeración simulada `SIM-YYYY-MM-DD-NNNNNN` que CU-05 contempla como *fallback* "mientras no haya integración real" **no se implementa** en esta fase: la condición que la activaría ya no existe porque `assign_consecutivo` (numeración real) está construido y en uso.

**Tablas ER tocadas**: `resolucion_facturacion` (SELECT/lock), `factura_electronica` (INSERT), `envio_dian` (INSERT por transición, nunca UPDATE).

**Endpoints**: `POST /facturacion/factura-electronica` (nuevo), `GET /facturacion/factura-electronica/{uuid}` (nuevo, con join a la vista real `v_factura_electronica_acuse` que expone solo `(uuid_factura_electronica, cufe, estado, timestamp_evento)`), `POST /facturacion/factura-electronica/{uuid}/reintentar` (nuevo).

Ejemplo de contrato de `GET /facturacion/factura-electronica/{uuid}`:

```jsonc
// 200 OK
{ "uuid": "…", "prefijo": "SETP", "consecutivo": 4521, "estado": "aceptado", "cufe": "9a3f…", "timestamp_evento": "2026-09-11T16:10:00Z" }
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo |
|---|---|---|
| 409 | `numeracion_agotada` | El rango de la resolución vigente está agotado; dispara la alerta ya sembrada `fe_numbering_exhausted` |
| 409 | `reintento_no_permitido` | Se intenta reintentar una FE que no está en `rechazado` |

**Pruebas**: `backend/tests/unit/test_factura_electronica_numeracion.py` (3 casos: asignación normal, rango agotado, reintento encadenado).

**Tamaño estimado**: 230 LOC.

**Tareas atómicas**:
- **HU-F1.10-T1**: `POST /facturacion/factura-electronica` invocando `assign_consecutivo` + creación de `envio_dian` inicial.
- **HU-F1.10-T2**: `GET /facturacion/factura-electronica/{uuid}` con `JOIN` a `v_factura_electronica_acuse`.
- **HU-F1.10-T3**: `POST .../reintentar` insertando fila nueva de `envio_dian` con `uuid_envio_padre`.
- **HU-F1.10-T4**: los 3 tests.

---

### HU-F1.11 — Workflow de reimpresión de tiquete (crear y anular)

Desbloquea: Fase 8 (reimpresión con costo).

**Historia**: Como operador, quiero poder reimprimir un tiquete perdido cobrando el servicio correspondiente, y poder anular ese cobro si me equivoqué de ingreso/motivo.

**Criterios de aceptación**:
- Given un ingreso existente y un motivo de ≥10 caracteres, When `POST /workflows/reimpresion-ticket`, Then se cobra el costo vigente de `costos_servicios` (concepto de reimpresión), se carga a una factura (nueva o existente) y se crea la fila con `estado='cobrada'`.
- Given una reimpresión ya cobrada por error, When `POST /workflows/reimpresion-ticket/{uuid}/anular`, Then se inserta una **fila nueva** con `uuid_reimpresion_padre` apuntando a la original y `estado='anulada'` (nunca `UPDATE` sobre la fila original).

**Nota de alcance (gap huérfano detectado)**: el endpoint de anulación no aparecía en ningún documento previo — sin él, un cobro de reimpresión mal hecho no tiene camino de reversa. Se incluye aquí como parte obligatoria de esta HU, no como extensión futura.

**Tablas ER tocadas**: `reimpresion_ticket` (INSERT en ambos casos, workflow `[L-W]`), `costos_servicios` (SELECT, snapshot del costo vigente), `facturas`/`factura_detalle` (carga del cobro).

**Endpoints**: `POST /workflows/reimpresion-ticket` (nuevo), `POST /workflows/reimpresion-ticket/{uuid}/anular` (nuevo).

**Pruebas**: `backend/tests/unit/test_reimpresion_ticket.py` (3 casos: cobro normal, anulación, motivo <10 caracteres → 422).

**Tamaño estimado**: 170 LOC.

**Tareas atómicas**:
- **HU-F1.11-T1**: `POST /workflows/reimpresion-ticket` — snapshot de `costos_servicios.costo` en `reimpresion_ticket.costo_aplicado`, carga a `uuid_factura`.
- **HU-F1.11-T2**: `POST .../{uuid}/anular` — INSERT con `uuid_reimpresion_padre`, mismo patrón de cadena que `anulaciones`/`alerta`.
- **HU-F1.11-T3**: los 3 tests.

---

### HU-F1.12 — Venta atómica de suscripción (decisión de producto, no requisito literal del CU)

Desbloquea: Fase 9 (CU-06).

**Historia**: Como operador, quiero poder vender una mensualidad nueva desde caja (cliente + vehículos + suscripción + cobro + FE) en un solo paso, sin que un fallo a mitad de camino deje datos inconsistentes.

**Nota de fidelidad obligatoria**: el CU-06 original solo describe la creación de una suscripción por un **Administrador**, sin mencionar cobro, factura ni FE en su flujo de 7 pasos — la venta atómica en caja por parte del operador es una **ampliación de producto**, justificada operativamente (un parqueadero necesita vender mensualidades en el mismo mostrador) pero sin respaldo literal en el corpus de casos de uso. Se construye igual porque es una necesidad real declarada por el negocio, pero se documenta aquí sin narrarla como si el CU ya la exigiera.

**Criterios de aceptación**:
- Given datos de cliente (nuevo o existente), 1-2 placas (mismo tipo de vehículo si el plan lo exige) y un plan vigente, When `POST /clientes/venta-suscripcion`, Then en una transacción se crean/actualizan `clientes`, `vehiculos` (si son placas nuevas), `subscripciones_cliente`, `subscripcion_vehiculos`, y opcionalmente `facturas`/`factura_pagos`/`factura_electronica` si la venta incluye cobro.
- Given una placa que ya tiene una suscripción vigente, When se intenta vender otra, Then `422 {"error":"suscripcion_duplicada_placa"}`.
- Given un plan con `mismo_tipo_vehiculo=true` y placas de tipos distintos, Then `422 {"error":"tipo_vehiculo_incompatible"}`.

**Tablas ER tocadas**: `clientes` (SELECT/INSERT), `vehiculos` (SELECT/INSERT condicional), `subscripciones_cliente` (INSERT), `subscripcion_vehiculos` (INSERT, hasta `cantidad_maxima_vehiculos` del plan), `tipo_subscripciones` (SELECT), `facturas`/`factura_pagos`/`factura_electronica` (INSERT condicional si la venta cobra).

**Endpoints**: `POST /clientes/venta-suscripcion` (nuevo, transaccional).

Ejemplo de contrato:

```jsonc
// Request
{ "cliente": { "nit": "…", "nombre": "…", "email": "…" },
  "placas": ["ABC123", "XYZ789"], "uuid_tipo_subscripcion": "…",
  "fecha_inicio_cobertura": "2026-09-12", "cobrar_ahora": true,
  "medio_pago": "efectivo" }
// 201 Created
{ "uuid_subscripcion": "…", "fecha_vencimiento": "2026-12-12", "monto_prorrateado": 45000, "uuid_factura": "…" }
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo |
|---|---|---|
| 422 | `suscripcion_duplicada_placa` | Una de las placas ya tiene una suscripción vigente |
| 422 | `tipo_vehiculo_incompatible` | El plan exige `mismo_tipo_vehiculo=true` y las placas son de tipos distintos |
| 422 | `cantidad_maxima_excedida` | Se envían más placas que `cantidad_maxima_vehiculos` del plan |

**Pruebas**: `backend/tests/unit/test_venta_suscripcion.py` (4 casos: cliente nuevo, cliente existente, plan `mismo_tipo_vehiculo=true`, placa duplicada).

**Tamaño estimado**: 260 LOC.

**Tareas atómicas**:
- **HU-F1.12-T1**: endpoint transaccional con las validaciones de duplicado y compatibilidad de tipo en el mismo handler (no en un paso separado).
- **HU-F1.12-T2**: cálculo de prorrateo si la venta ocurre después del día 15 (adaptación A-09: el monto prorrateado se persiste en `factura_detalle`, no en `subscripciones_cliente`).
- **HU-F1.12-T3**: los 4 tests.

---

### HU-F1.13 — Endpoints de arqueo y siembra de `cierre_dia`

Desbloquea: Fase 10 (CU-10).

**Historia**: Como operador/supervisor, quiero poder registrar un arqueo (parcial, de cierre de turno, o de cierre de día) y ver el resumen de un día completo.

**Criterios de aceptación**:
- Given los pagos de un turno o de un día, When `POST /caja/arqueo`, Then se calcula `valor_efectivo_esperado`/`valor_datafono_esperado` desde `sesion` + `factura_pagos` (sin modificar `factura_pagos`, que es inmutable) y se compara contra lo reportado; si `|diferencia| > tolerancia` (monto absoluto de `configuracion_tolerancias`, no porcentaje — ver Fase 10 para la reconciliación de esta fórmula), se crea una fila de `alerta` con `tipo_alerta='descuadre_critico'`.
- Given `uuid_tipo_arqueo` con `codigo='cierre_dia'`, When se registra, Then `uuid_sesion=NULL` y se cierran todas las sesiones abiertas del día (`UPDATE sesion SET estado='cerrada', timestamp_cierre=..., uuid_usuario_cierre=...`).
- Given `GET /caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD`, Then responde con el resumen por sesión (cajero, apertura/cierre, base, esperado, reportado, diferencia, justificado).

**Tablas ER tocadas**: `arqueo` (INSERT), `sesion` (SELECT y, solo en cierre de día, `UPDATE` de cierre masivo), `factura_pagos` (SELECT, suma por `medio_pago`), `configuracion_tolerancias` (SELECT), `tipo_arqueo` (siembra de `cierre_dia`), `alerta` (INSERT condicional).

**Endpoints**: `POST /caja/arqueo` (nuevo), `GET /caja/arqueo/resumen` (nuevo).

Ejemplo de contrato de `POST /caja/arqueo`:

```jsonc
// Request
{ "uuid_tipo_arqueo": "…", // resuelve a codigo='auditoria' | 'cierre_turno' | 'cierre_dia'
  "uuid_sesion": "…", // NULL si codigo='cierre_dia'
  "valor_efectivo_reportado": 148000, "valor_datafono_reportado": 320000,
  "justificacion": "Faltante por vueltos mal calculados en 2 operaciones" }
// 201 Created
{ "uuid": "…", "valor_efectivo_esperado": 150000, "diferencia_efectivo": -2000,
  "descuadre_pct": -1.33, "alerta_generada": false } // alerta_generada evalúa SIEMPRE contra el monto absoluto, no el %
```

**Manejo de errores**:

| Código HTTP | `error` | Cuándo |
|---|---|---|
| 409 | `sesion_ya_cerrada` | Se intenta un `cierre_turno` sobre una sesión ya cerrada |
| 400 | `justificacion_requerida` | Diferencia distinta de cero en `cierre_turno` sin `justificacion` (obligatoria en cierre; solo advertencia en `auditoria`) |

**Pruebas**: `backend/tests/unit/test_caja_arqueo.py` (3 casos: sin diferencia, con diferencia justificada, con descuadre → alerta), `backend/tests/unit/test_cierre_dia.py` (1 caso, 3 sesiones: 2 cerradas + 1 abierta).

**Tamaño estimado**: 240 LOC.

**Tareas atómicas**:
- **HU-F1.13-T1**: migración de siembra `migrations/versions/2026_09_11_0024_seed_tipo_arqueo_cierre_dia.py` (INSERT idempotente `ON CONFLICT DO NOTHING` del 4º valor).
- **HU-F1.13-T2**: `POST /caja/arqueo` con cálculo de esperado/diferencia y alerta condicional.
- **HU-F1.13-T3**: `GET /caja/arqueo/resumen` con `JOIN` a `sesion` + agregación de `factura_pagos`.
- **HU-F1.13-T4**: los 4 tests.

---

### HU-F1.14 — `GET /sync/estado` y siembra completa de `alert_types`

Desbloquea: Fase 11 (sync banner + alertas).

**Historia**: Como operador, quiero ver el estado real de sincronización de mi sucursal y que las alertas que el sistema puede generar ya existan en el catálogo antes de que ocurran.

**Criterios de aceptación**:
- Given `GET /sync/estado?uuid_sucursal=X`, Then responde `{ultima_sync_at, lag_seg, pendientes}`.
- Given el catálogo `alert_types`, Then contiene los 8 códigos técnicos ya existentes (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) **más** los 11 códigos de negocio que CU-14 exige literalmente (`descuadre_critico`, `sync_fallida`, `capacidad_agotada`, `capacidad_agotada_forzado`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, `cache_desactualizado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`) — 19 en total, sembrados de forma idempotente tanto en cloud como en cada sucursal.

**Tablas ER tocadas**: `sync_log`/`sync_queue` (SELECT, para `lag_seg`/`pendientes`), `alert_types` (siembra).

**Endpoints**: `GET /sync/estado` (nuevo).

Ejemplo de contrato:

```jsonc
// 200 OK
{ "uuid_sucursal": "…", "ultima_sync_at": "2026-09-11T15:58:00Z", "lag_seg": 120, "pendientes": 3 }
```

**Pruebas**: `backend/tests/unit/test_sync_estado.py` (2 casos), `backend/tests/unit/test_alert_types_seed.py` (verifica los 19 códigos presentes, sin duplicados).

**Tamaño estimado**: 120 LOC.

**Tareas atómicas**:
- **HU-F1.14-T1**: migración `migrations/versions/2026_09_11_0025_seed_alert_types_operativos.py` con INSERT idempotente de los 11 códigos de negocio (severidad: alta para `descuadre_critico`/`sync_fallida`/`evento_no_procesado`/`impresora_caida`/`fe_error_toppoint`/`numeracion_toppoint_agotada`; media para `capacidad_agotada`/`capacidad_agotada_forzado`/`arqueo_pendiente_24h`/`suscripcion_proxima_vencer`; baja para `cache_desactualizado`).
- **HU-F1.14-T2**: `GET /sync/estado` calculando `lag_seg` desde la última fila de `sync_log` y `pendientes` desde `sync_queue WHERE estado='pendiente'`.
- **HU-F1.14-T3**: los tests descritos.

---

### HU-F1.15 — Histórico de intentos de login (gap huérfano)

Desbloquea: ninguna pantalla obligatoria de esta parte, pero cierra un hueco de auditoría de seguridad detectado sin ID de gap en ningún documento previo.

**Historia**: Como operador o supervisor, quiero poder ver los últimos intentos de acceso de un usuario (exitosos, fallidos, cerrados) para diagnosticar bloqueos o accesos sospechosos.

**Criterios de aceptación**: Given `GET /usuarios/{uuid}/login?limit=10&cursor=...`, Then responde `{items, next_cursor}` con los intentos más recientes primero, cada uno con su `estado` real (`exitoso|fallido|cerrado`) — nunca un campo booleano `activo`, que no existe en el dominio real de `login.estado`.

**Tablas ER tocadas**: `login` (SELECT, paginado por cursor).

**Endpoints**: `GET /usuarios/{uuid}/login` (nuevo).

**Pruebas**: `backend/tests/unit/test_login_historico.py` (2 casos).

**Tamaño estimado**: 70 LOC.

**Tareas atómicas**:
- **HU-F1.15-T1**: endpoint de solo lectura con el contrato estándar de listado paginado (`{items, next_cursor}`).
- **HU-F1.15-T2**: los 2 tests.

---

## Fase 2 — Andamiaje Electron

**Objetivo**: crear `apps/electron-sucursal` desde cero (no existe aún) con todo lo transversal que las fases operativas van a necesitar: scaffold, cliente HTTP, bridge IPC, estado de autenticación, auto-actualización, kiosko y logging. No cubre ningún CU directamente; desbloquea todas las fases siguientes.

### HU-F2.1 — Scaffold del proyecto + `ui-kit` compartido + shadcn/ui

**Historia**: Como desarrollador, quiero un scaffold Electron+Vite+React+TS funcional desde el primer commit, con el set de componentes base ya generado, para empezar a construir features sin resolver configuración de build cada vez.

**Criterios de aceptación**:
- Given el repo, When `npm run dev` en `apps/electron-sucursal`, Then arranca Vite en `:5173` (renderer) + esbuild en modo watch (main+preload).
- Given `npm run build`, Then produce `dist/` (renderer) + `out/main` + `out/preload.js` sin errores de tipos (`tsc --noEmit` limpio en los 3 tsconfigs: base, main, renderer).
- Given `npx shadcn@latest add`, Then existen en `src/components/ui/` los 14 componentes base: Button, Dialog, Form, Input, Toast, Table, Badge, Sheet, Select, Tabs, Popover, Tooltip, DropdownMenu, Skeleton.
- Given `apps/ui-kit` (compartido con el hermano de administración), Then expone `Button`, `cn()` y tokens de diseño, importable desde `electron-sucursal` con su propio `package.json`.

**Reglas de negocio**: ninguna (tarea de infraestructura pura).

**Componentes UI**: `apps/ui-kit/{Button,cn,tokens}` (presentacional, compartido); `src/App.tsx` (contenedor raíz, solo router placeholder en esta fase).

**Validaciones Zod**: N/A en esta HU.

**Manejo de errores**: N/A.

**Pruebas**: `e2e/scaffold.spec.ts` — smoke test: la app abre, muestra un placeholder, 0 violaciones de axe-core.

**Tamaño estimado**: 700 LOC.

**Tareas atómicas**:
- **HU-F2.1-T1**: `package.json` del workspace `@parkos/electron-sucursal`. Dependencias de producción: `react@^18`, `react-dom@^18`, `react-router-dom@^6`, `zustand@^4`, `swr@^2`, `react-hook-form@^7`, `@hookform/resolvers@^3`, `zod@^3`, `i18next@^23`, `react-i18next@^15`, `electron-updater@^6`, `electron-log@^5`, `electron-store@^8`, `escpos-usb@^3`, `class-variance-authority@^0.7`, `clsx@^2`, `tailwind-merge@^2`, `lucide-react@^0.4`. Dependencias de desarrollo: `electron@^30`, `vite@^5`, `typescript@^5`, `electron-builder@^24`, `vitest@^2`, `@vitest/coverage-v8@^2`, `@testing-library/react@^16`, `msw@^2`, `playwright@^1.48`, `@axe-core/playwright@^4`, `eslint@^9`, `@typescript-eslint/*@^8`, `prettier@^3`.
- **HU-F2.1-T2**: 3 tsconfigs (`tsconfig.json` base, `tsconfig.main.json` target Node, `tsconfig.renderer.json` target ESNext+DOM), los 3 con `strict: true`, `noUncheckedIndexedAccess: true`.
- **HU-F2.1-T3**: `vite.config.ts` (renderer, HMR) + `vite.main.config.ts` (esbuild, target `node20`, main+preload).
- **HU-F2.1-T4**: `electron-builder.yml` con `appId: co.parkos.electron-sucursal`, `productName: Parkos Sucursal`, targets Windows/Linux/macOS, íconos placeholder.
- **HU-F2.1-T5**: `apps/ui-kit/package.json` + `Button` + `cn()` (usa `clsx`+`tailwind-merge`) + `tokens`.
- **HU-F2.1-T6**: `npx shadcn@latest init` (`rsc:false`, `cssVariables:true`) + `add` de los 14 componentes listados arriba.
- **HU-F2.1-T7**: `src/i18n/` con los 7 namespaces (`common`, `auth`, `operacion`, `caja`, `facturacion`, `sync`, `errors`).
- **HU-F2.1-T8**: `e2e/` con Playwright + `_electron.launch`, axe-core integrado desde este mismo scaffold (no como fase separada).
- **HU-F2.1-T9**: `src/main.tsx` + `src/App.tsx` con router placeholder.

---

### HU-F2.2 — Cliente HTTP `parkosFetch`, bridge IPC y `authStore`

**Historia**: Como desarrollador, quiero un único punto de entrada HTTP con reintentos, refresh e idempotencia, y un bridge IPC tipado, para que ninguna feature reinvente estas reglas.

**Criterios de aceptación**:
- Given `baseURL=http://127.0.0.1:8000/api/v1` (default; configurable por `PARKOS_API_BASE`), When cualquier request de mutación, Then lleva `Idempotency-Key` = SHA-256(método+ruta+cuerpo) y `X-Sucursal-Context`.
- Given un 5xx o `NetworkError`, When `parkosFetch` reintenta, Then lo hace hasta 3 veces con backoff 300/600/1200 ms, nunca en 4xx.
- Given un 401, When ocurre, Then se intenta un refresh único (`POST /auth/refresh`); un segundo 401 consecutivo limpia `authStore` y redirige a `/login?next=<path>`.
- Given `window.bridge`, Then expone `imprimir`, `usb.list`, `kiosk.toggle`, `app.quit`, `api-status`, cada uno tipado en `electron/types/bridge.d.ts` y filtrado por whitelist en `preload.ts`.

**Componentes UI**: N/A (capa de infraestructura); `useAuth()` (hook, no componente) con SWR a `/auth/me`, `refreshInterval: 5*60*1000`.

**Manejo de errores**: `errors.network` (i18n) al agotar reintentos; redirect a login tras doble 401.

**Pruebas**: `src/lib/__tests__/parkosFetch.test.ts` — 14 escenarios con MSW (`vi.useFakeTimers()` para los backoffs, cobertura exigida >90% en `parkosFetch.ts`):

1. GET exitoso sin cabeceras extra.
2. POST incluye `Idempotency-Key` calculada por SHA-256(método+ruta+cuerpo).
3. Dos POST idénticos producen la misma `Idempotency-Key`.
4. `X-Sucursal-Context` presente en toda mutación.
5. 5xx reintenta con backoff de 300 ms.
6. Segundo reintento a 600 ms.
7. Tercer reintento a 1200 ms.
8. Agotados los 3 reintentos, propaga el error al llamador.
9. 4xx **no** dispara ningún reintento.
10. 401 dispara un refresh único (`POST /auth/refresh`).
11. Refresh exitoso reintenta automáticamente la petición original.
12. Un segundo 401 consecutivo limpia `authStore` y redirige a `/login?next=<path>`.
13. `NetworkError` (sin conexión) se trata igual que un 5xx para efectos de reintento.
14. Timeout de una petición con `timeoutMs` explícito aborta vía `AbortController`.

`src/lib/__tests__/bridge.test.ts` — mock de `window.bridge`, 8 escenarios: imprimir OK, imprimir con `printer_offline`, `usb.list` vacío, `usb.list` con dispositivos, `kiosk.toggle` activa/desactiva, `app.quit`, `api-status` OK, `api-status` caído.

**Tamaño estimado**: 450 LOC.

**Tareas atómicas**:
- **HU-F2.2-T1**: `src/lib/parkosFetch.ts` — `baseURL`, `Idempotency-Key` (SHA-256), retry 5xx (300/600/1200ms), refresh único en 401.
- **HU-F2.2-T2**: `electron/types/bridge.d.ts` con los tipos de `PrintPayload`, `USBDevice`, etc.
- **HU-F2.2-T3**: `electron/preload.ts` con `contextBridge.exposeInMainWorld('bridge', {imprimir, usb, app, kiosk, api-status})`.
- **HU-F2.2-T4**: `src/lib/bridge.ts` (wrapper tipado de `window.bridge`).
- **HU-F2.2-T5**: `src/lib/authStore.ts` (Zustand + middleware `persist` sobre `electron-store`, `partialize` para persistir solo `{user.uuid, expires_at, permisos}` — el JWT nunca se persiste, vive solo en la cookie).
- **HU-F2.2-T6**: `src/lib/hooks/useAuth.ts` con SWR a `/auth/me`.
- **HU-F2.2-T7**: los tests de `parkosFetch` (14 escenarios) y de `bridge` (8 escenarios).

---

### HU-F2.3 — Auto-actualización, single-instance y kiosko

**Historia**: Como operador, quiero que la app se actualice sola y que no pueda abrirse dos veces; como administrador, quiero poder bloquearla en modo kiosko con salida protegida por PIN.

**Criterios de aceptación**:
- Given una nueva versión publicada, When la app detecta el feed, Then descarga automáticamente (`autoDownload:true`) y se instala al cerrar (`autoInstallOnAppQuit:true`); `allowDowngrade:false`.
- Given la app abierta, When se lanza una segunda instancia, Then `app.requestSingleInstanceLock()` hace que la segunda invocación enfoque la primera y termine (`app.quit()`).
- Given `PARKOS_KIOSK_MODE=1`, Then pantalla completa, `Menu.setApplicationMenu(null)`, `Ctrl+W`/`Alt+F4` bloqueados; salida solo con `Ctrl+Shift+K` + PIN (`bcrypt`, factor ≥12, comparación en tiempo constante, nunca logueado).

**Manejo de errores**: fallo de verificación de firma en el update → no se instala, se loguea y se reintenta en el próximo ciclo.

**Pruebas**: `e2e/lifecycle.spec.ts` — segunda instancia enfoca la primera; kiosko bloquea `Ctrl+W`; PIN incorrecto no desbloquea.

**Tamaño estimado**: 450 LOC.

**Tareas atómicas**:
- **HU-F2.3-T1**: `electron/services/updater.ts` con `electron-updater`, feed propio, verificación de firma.
- **HU-F2.3-T2**: `electron/services/api-status.ts` — `fetch('http://127.0.0.1:8000/health')` cada 30 s, IPC `bridge.api-status` con `{ok, latency_ms, code?}`.
- **HU-F2.3-T3**: `app.requestSingleInstanceLock()` + evento `second-instance` → `mainWindow.focus()`.
- **HU-F2.3-T4**: kiosko: `mainWindow.setKiosk(...)`, `Menu.setApplicationMenu(null)`, bloqueo de shortcuts, PIN de salida con `bcrypt.hash(pin, 12)`.
- **HU-F2.3-T5**: `electron-log` con rotación 10 MB × 5 backups, formato JSON, captura de `uncaughtException`/`unhandledRejection`.
- **HU-F2.3-T6**: `<StatusBar>` con texto exacto por estado (`"🟢 API OK"` / `"🟡 API lento"` / `"🔴 Sin API"`, `aria-live="polite"`).
- **HU-F2.3-T7**: los 3 e2e descritos.

---

## Fase 3 — Autenticación y turno de caja

**Objetivo**: login real contra el backend (email+password), lockout visible en UI, y apertura/cierre de turno. Cubre la base transversal de todos los CU operativos (ninguno puede correr sin sesión y turno abiertos).

### HU-F3.1 — Login con `email` + `password`

**Historia**: Como operador, quiero iniciar sesión con mi correo y contraseña, para acceder al terminal con mis permisos y mi sucursal ya resueltos.

**Criterios de aceptación**:
- Given un formulario con `email` (formato válido) y `password` (mínimo 8 caracteres), When se envía, Then `POST /auth/login` con `credentials:'include'`.
- Given credenciales válidas, Then la cookie `httpOnly` queda establecida y `authStore` se hidrata desde `GET /auth/me` (`useAuth().user.sucursal` es el `uuid` de la sede; `permisos` es un array).
- Given credenciales inválidas, Then `401` muestra un mensaje único (`errors.invalid_credentials`), sin distinguir si el email existe o no (anti-enumeración).

**Regla de negocio**: el campo de acceso es `email`, nunca `cedula` (DEC-SUC-02) — corrige explícitamente una versión previa de este mismo plan que asumía `cedula` como credencial, error que no proviene del caso de uso original (CU-01 no menciona cédula como mecanismo de login en ningún punto verificado) sino de una lectura incorrecta del esquema de autenticación real.

**Tablas ER tocadas**: `usuarios` (SELECT vía backend), `login` (INSERT del intento, vía backend).

**Endpoints**: `POST /auth/login`, `GET /auth/me`.

**Componentes UI**: `Login` (page, contenedor: RHF+Zod, llama `parkosFetch`); `LoginForm` (presentacional, dos campos + botón).

**Validaciones Zod**: `z.object({ email: z.string().email(), password: z.string().min(8) })`.

**Manejo de errores**: `401` → `errors.invalid_credentials`; `429` → ver HU-F3.2.

**Pruebas**: `e2e/login.spec.ts` — login OK con cookie, refresh automático, logout.

**Tamaño estimado**: 190 LOC.

**Tareas atómicas**:
- **HU-F3.1-T1**: `src/features/auth/pages/Login.tsx` con RHF+Zod (`email`/`password`).
- **HU-F3.1-T2**: integrar `POST /auth/login` con `credentials:'include'`.
- **HU-F3.1-T3**: `src/features/auth/pages/Login.tsx` redirige a `/` (o a la sesión activa) tras hidratar `authStore` desde `/auth/me`.
- **HU-F3.1-T4**: `e2e/login.spec.ts` (3 casos: login OK, refresh transparente, logout).

---

### HU-F3.2 — Lockout visible y refresh transparente

**Historia**: Como operador, si fallo 5 veces seguidas quiero ver cuánto falta para poder reintentar, sin adivinar.

**Criterios de aceptación**: Given `429` con `Retry-After`, When se recibe, Then el formulario se deshabilita y muestra un contador regresivo exacto (`useCountdown`, `setInterval(1000)`) hasta `secondsLeft=0`; Given `authStore`, When pasan 50 minutos desde el último refresh, Then se refresca sin acción del usuario, y además antes de `POST /facturacion/*` y `POST /caja/arqueo` (refresh pre-flight).

**Componentes UI**: `useCountdown(retryAfter)` (hook) → `{secondsLeft, isExpired}`.

**Pruebas**: `e2e/lockout.spec.ts` — 5 intentos fallidos → 429 + countdown visible y decreciente.

**Tamaño estimado**: 130 LOC.

**Tareas atómicas**:
- **HU-F3.2-T1**: `src/features/auth/hooks/useCountdown.ts`.
- **HU-F3.2-T2**: integrar en `Login.tsx`: 429 → deshabilitar formulario + countdown.
- **HU-F3.2-T3**: refresh pre-flight en `parkosFetch` antes de `POST /facturacion/*` y `POST /caja/arqueo`.
- **HU-F3.2-T4**: `e2e/lockout.spec.ts`.

---

### HU-F3.3 — Abrir y cerrar turno

**Historia**: Como operador, quiero abrir mi turno con la base de caja inicial al empezar mi jornada, y cerrarlo con un arqueo al terminar.

**Criterios de aceptación**:
- Given `valor_inicial_efectivo`/`valor_inicial_datafono` (decimales ≥0), When `POST /caja-sesion/sesiones`, Then `200` con la sesión abierta; si ya hay una abierta para el usuario, `409` con mensaje claro.
- Given una sesión abierta, When se navega a `/`, Then `GET /caja-sesion/sesion/me` resuelve el dashboard con el resumen del turno (sin redirigir a abrir turno de nuevo).
- Given el cierre de turno, When se confirma el arqueo (`tipo_arqueo='cierre_turno'`) y `PUT /caja-sesion/sesion/{uuid}/cerrar`, Then `200` y redirect a login o a "turno cerrado".

**Componentes UI**: `AbrirTurno` (page, `inputMode="decimal"` en los campos numéricos), `CerrarTurno` (page, arqueo inline — ver Fase 10 para el detalle completo de arqueo), `useSesionActiva` (hook, SWR).

**Validaciones Zod**: `z.object({ valor_inicial_efectivo: z.number().min(0), valor_inicial_datafono: z.number().min(0), observaciones: z.string().optional() })`.

**Manejo de errores**: `409 sesion_ya_abierta` → mensaje "ya tenés un turno abierto"; `409 sesion_ya_cerrada` en el cierre.

**Pruebas**: `e2e/turno.spec.ts` — abrir, intentar un segundo → 409, cerrar, ver resumen.

**Tamaño estimado**: 260 LOC.

**Tareas atómicas**:
- **HU-F3.3-T1**: `src/features/caja/pages/AbrirTurno.tsx` con RHF+Zod.
- **HU-F3.3-T2**: `src/features/caja/pages/CerrarTurno.tsx` (arqueo inline placeholder, se completa en Fase 10).
- **HU-F3.3-T3**: `src/features/caja/hooks/useSesionActiva.ts` (SWR a `/caja-sesion/sesion/me`).
- **HU-F3.3-T4**: rutas `/caja/abrir-turno`, `/caja/cerrar-turno` en `App.tsx`; redirect según exista o no sesión activa.
- **HU-F3.3-T5**: `e2e/turno.spec.ts` (3 casos).

---

## Fase 4 — Catálogos y ocupación en vivo

**Objetivo**: consumir (nunca gestionar — eso es de administración) los catálogos que el operador necesita a diario, y mostrar la ocupación de la sede en tiempo casi real. Cubre CU-01 (parametrización local), CU-02 (lectura de tarifas), CU-11/CU-12 (solo lectura del lado sucursal).

### HU-F4.1 — Detección de tipo de vehículo por placa

**Historia**: Como operador, quiero que al digitar una placa el sistema detecte automáticamente el tipo de vehículo, sin que yo tenga que elegirlo.

**Criterios de aceptación**:
- Given una placa `ABC123`, When se normaliza y valida, Then detecta `Auto` (regex `^[A-Z]{3}[0-9]{3}$`).
- Given una placa `ABC12D`, Then detecta `Moto` (regex `^[A-Z]{3}[0-9]{2}[A-Z]$`).
- Given una placa que no matchea ningún regex activo, Then error inline "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)", campo abierto para corrección.
- Given esta misma función, When se usa en el flujo de **ingreso**, Then **nunca** aplica tolerancia de tipeo O↔0/I↔1/B↔8 (DEC-SUC-22) — esa tolerancia es exclusiva de la búsqueda en salida (Fase 7).

**Regla de negocio**: BR2 de CU-01, literal — "autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug".

**Tablas ER tocadas**: `tipos_vehiculo` (SELECT, para nombre/ícono; la regex en sí es hardcoded, adaptación A-03).

**Endpoints**: `GET /catalogos/tipos-vehiculo`.

**Componentes UI**: `useTiposVehiculo` (hook, SWR, `dedupingInterval: 5*60*1000`, con fallback a un catálogo hardcoded de `{auto, moto}` si la API local no responde — degradación explícita, no un crash de pantalla).

**Validaciones Zod**: N/A (validación por regex propia, no Zod, porque la lógica de detección devuelve un tipo, no solo válido/inválido).

**Manejo de errores**: mensaje literal de arriba, i18n `operacion.placa_formato_invalido`.

**Pruebas**: `src/lib/validation/__tests__/placa.test.ts` — 6 casos (Auto, Moto, formato inválido, placa vacía, minúsculas normalizadas a mayúsculas, placa con espacios).

**Tamaño estimado**: 100 LOC.

**Tareas atómicas**:
- **HU-F4.1-T1**: `src/lib/validation/placa.ts` — `detectarTipoVehiculo(placa): TipoVehiculo | null`, función **estricta**, sin tolerancia de tipeo, usada únicamente en el flujo de ingreso.
- **HU-F4.1-T2**: `src/features/catalogos/hooks/useTiposVehiculo.ts` (SWR + fallback hardcoded).
- **HU-F4.1-T3**: los 6 tests unitarios.

---

### HU-F4.2 — Tarifas vigentes

**Historia**: Como operador, quiero ver la tarifa aplicable al tipo de vehículo detectado, siempre la vigente al momento exacto de la consulta.

**Criterios de aceptación**:
- Given un tipo de vehículo detectado, When se pide la tarifa, Then `GET /empresa/tarifas-sucursal?uuid_tipo_vehiculo=X&vigente_en=<ahora>` devuelve el valor actual.
- Given que la API local no responde, Then se usa el último valor cacheado en `electron-store` (nunca una pantalla vacía).
- Given un valor cacheado con más de 1 hora de antigüedad, Then el `TarifaBadge` se marca como "desactualizado" sin dejar de mostrar el valor.
- Given un cambio de tarifa vigente durante el turno (tarifa programada con `vigente_desde` futura que ya llegó), Then el siguiente refresco (`dedupingInterval` de 5 min) trae el nuevo valor sin necesidad de reiniciar la app.

**Tablas ER tocadas**: `tarifas_sucursal` (SELECT).

**Endpoints**: `GET /empresa/tarifas-sucursal` (con filtro `vigente_en`, cerrado en HU-F1.4).

**Componentes UI**: `useTarifasVigentes` (hook, SWR con `dedupingInterval: 5*60*1000` y `fallbackData: electronStore.get('tarifas')`); `TarifaBadge` (presentacional, marca "stale" si `fetchedAt > 1h`, con `aria-describedby`).

**Manejo de errores**: badge "stale" en vez de error duro cuando la API está caída pero hay cache.

**Pruebas**: `src/features/catalogos/hooks/__tests__/useTarifasVigentes.test.ts` — 2 casos (cache válido, invalidación tras cambio de tipo).

**Tamaño estimado**: 160 LOC.

**Tareas atómicas**:
- **HU-F4.2-T1**: `useTarifasVigentes.ts` con SWR + `fallbackData` de `electron-store`.
- **HU-F4.2-T2**: `formatearMonedaCOP()` — `Intl.NumberFormat('es-CO', {style:'currency', currency:'COP', minimumFractionDigits:0})`, con fixtures de test exactos `"$ 8.000"` y `"$ 1.234.567"`.
- **HU-F4.2-T3**: `TarifaBadge.tsx`.
- **HU-F4.2-T4**: los 2 tests de hook + tests de formato de moneda.

---

### HU-F4.3 — Ocupación en vivo

**Historia**: Como operador, quiero ver de un vistazo cuántos cupos quedan por tipo de vehículo, con alerta visual cuando la sede se está llenando.

**Criterios de aceptación**:
- Given `GET /operacion/ocupacion?uuid_sucursal=X` (cerrado en HU-F1.5), When se muestra el strip superior, Then aparece `Auto: 23/50` por tipo, con *polling* cada 10 s.
- Given el porcentaje de ocupación, Then el color es verde (<70%), amarillo (70-90%) o rojo (>90%), con leyenda al pasar el mouse.
- Given que el cupo se agota mientras el strip está abierto, Then el color y el número se actualizan solos en el siguiente ciclo de *polling*, sin recargar la página.

**Componentes UI**: `OcupacionStrip` (organismo, `aria-live="polite"`, `AbortController` explícito con limpieza en `unmount` para no dejar fugas de petición).

**Manejo de errores**: si el *polling* falla, el strip conserva el último valor conocido con indicador visual sutil de "desactualizado", no desaparece.

**Pruebas**: `e2e/ocupacion.spec.ts` — el strip renderiza; el valor cambia al refrescar tras un ingreso simulado.

**Tamaño estimado**: 220 LOC.

**Tareas atómicas**:
- **HU-F4.3-T1**: `src/components/OcupacionStrip.tsx` — grid por tipo, colores por umbral.
- **HU-F4.3-T2**: *polling* SWR `refreshInterval: 10_000` + `AbortController`.
- **HU-F4.3-T3**: `e2e/ocupacion.spec.ts`.

**Addendum — footer `<CuposLibresStrip />` del Dashboard (`apps/electron-sucursal`, mismo dato de `GET /operacion/ocupacion` + mismo umbral de color de esta HU, componente separado de `OcupacionStrip`):**
- Directiva operador (2026-09-24): un tipo de vehículo con `cupo_maximo=0` (no habilitado en la sucursal) NUNCA se muestra en el footer — ni la tarjeta por tipo ni el agregado total lo cuentan.
- Directiva operador (2026-09-24, rediseño — REVERTIDA el 2026-09-25, se deja como historial): se probó sacar el tope de ~80px de alto y usar tarjetas individuales grandes por tipo (ícono + número de cupos libres en `text-3xl`+ color de fondo por umbral) con un bloque de total en `text-4xl`. El operador lo rechazó explícitamente ("rompe totalmente el diseño", "el tamaño es exageradamente grande").
- Directiva operador (2026-09-25, vigente — corrección de escala): el footer vuelve a `max-h-[80px]` con chips compactos en una sola fila (ícono chico + label + cupos libres + ocupados/total como dato secundario), alineados a la misma escala tipográfica del resto del dashboard (botones de sidebar, chip de turno activo, chips de hotkey). Se mantiene el filtro de tipos con `cupo_maximo=0` (nunca se muestran) y que el dato protagonista de cada chip sea `disponible` (cupos libres), no solo ocupados/total. Sigue siendo `sticky bottom-0` dentro del mismo dashboard, nunca modal ni ruta aparte.

---

## Fase 5 — Impresión térmica

**Objetivo**: construir el servicio de impresión (main process) del que dependen los tres tiquetes (Fases 6-8) antes de implementarlos, para no bloquear ese trabajo por un servicio de bajo nivel a medio construir.

### HU-F5.1 — Servicio de impresora en el main process

**Historia**: Como operador, quiero que el tiquete se imprima en menos de 500 ms sin que la app se congele si la impresora se desconecta a mitad de la operación.

**Criterios de aceptación**:
- Given una impresora térmica USB conectada, When se llama `listDevices()`, Then detecta dispositivos de clase USB `0x07` (Printer).
- Given un `Buffer` ESC/POS, When se envía a imprimir, Then el tiempo P95 es <500 ms para un buffer de 1 KB (medido con `performance.now()`).
- Given que la impresora se desconecta a mitad de impresión, Then el main process captura el error (`printer_offline`), lo loguea y avisa al renderer sin crashear el proceso.
- Given un payload recibido por IPC, When llega al handler del main process, Then se valida con Zod **antes** de tocar el hardware — defensa en profundidad contra un renderer comprometido, no confiar solo en los tipos TypeScript.

**Componentes UI**: N/A (main process); `bridge.imprimir` (IPC, consumido por las fases 6-8).

**Manejo de errores**: `printer_offline` (banner en UI, cola de reintento con backoff 5s/15s/60s, 5 intentos, persistida en `electron-store` para sobrevivir a un reinicio de la app).

**Pruebas**: `e2e/printer.spec.ts` — dispositivo detectado, impresión OK, desconexión no crashea (con mock USB, librería `node-usb-mock`); test de performance P95 <500 ms.

**Tamaño estimado**: 420 LOC.

**Tareas atómicas**:
- **HU-F5.1-T1**: `electron/services/printer.ts` con `listDevices()` y `print(buffer, vid, pid)`, usando específicamente `escpos-usb` (no el paquete genérico `escpos`).
- **HU-F5.1-T2**: `electron/ipc/imprimir.ts` con `ipcMain.handle('bridge.imprimir', ...)`, validación Zod del payload antes de imprimir.
- **HU-F5.1-T3**: cola de reintento en `electron-store` con backoff 5s/15s/60s (5 intentos), sin bloquear el flujo de caja mientras espera.
- **HU-F5.1-T4**: `build/entitlements.mac.plist` con `com.apple.security.device.usb = true` + `electron-builder.yml` (`mac.entitlements`, `hardenedRuntime:true`).
- **HU-F5.1-T5**: `e2e/printer.spec.ts` (detección, impresión OK, offline no crashea) + test de performance P95.

---

### HU-F5.2 — `escposBuilder` base y fallback de navegador

**Historia**: Como desarrollador, quiero un builder de tiquetes reutilizable por los 4 tipos de documento (entrada, salida, salida-mensualidad, reimpresión), con un fallback si la térmica no responde.

**Criterios de aceptación**: Given `escposBuilder.build(<tipo>, payload)`, Then produce un `Buffer` con secuencia ESC/POS válida (`0x1B 0x40` init, `0x1D 0x56 0x00` cut, `0x1B 0x61 0x01` centrado, `0x1B 0x45` negrita, `0x1B 0x21 0x30` texto 2x altura para sellos); Given que la impresora no responde, Then cae a `fallbackBrowser.print(payload)` con plantilla `@page{size:80mm auto;margin:2mm}`.

**Componentes UI**: `src/lib/print/escposBuilder.ts`, `escposTemplates.ts`, `fallbackBrowser.ts` (todos lib, no componentes visuales).

**Pruebas**: `src/lib/print/__tests__/escposBuilder.test.ts` — 5+ fixtures byte a byte de los comandos citados arriba.

**Tamaño estimado**: 180 LOC.

**Tareas atómicas**:
- **HU-F5.2-T1**: `escposBuilder.ts` con la firma `build(tipo, payload): Buffer`, tipo genérico reutilizado por las 4 variantes de tiquete.
- **HU-F5.2-T2**: `fallbackBrowser.ts` con la plantilla CSS exacta.
- **HU-F5.2-T3**: los tests de bytes ESC/POS.

---

## Fase 6 — Ingreso vehicular (CU-01) + tiquete de entrada (CU-15E)

**Objetivo**: el flujo completo de registrar la entrada de un vehículo y emitir su tiquete. Cubre CU-01 íntegro y CU-15E íntegro.

### HU-F6.1 — Flujo de ingreso en la pantalla principal

**Historia**: Como operador, quiero digitar una placa en un campo grande y, con una sola confirmación, registrar el ingreso y ver el tiquete impreso.

**Criterios de aceptación** (orden correcto de validación — invertido respecto al orden ambiguo del CU-01 original, que evalúa mensualidad antes de validar formato):
- Given el campo de placa con auto-focus, When se digita y se presiona Enter (o el botón), Then se normaliza a MAYÚSCULAS.
- Given la placa normalizada, When se valida contra el regex del tipo detectado, Then si no matchea ningún formato activo, error inline sin llamar al backend.
- Given formato válido, When se consulta si ya tiene ingreso activo en la sucursal, Then si existe, la app **redirige automáticamente** al flujo de salida (`SalidaFlow`, Fase 7) — nunca permite un doble ingreso.
- Given que no tiene ingreso activo, When se evalúa mensualidad/rotación, Then se muestra un banner: "Mensualidad activa: <cliente>" (si `uuid_subscripcion_cliente` no es nulo) o "Rotación" en cualquier otro caso — **nunca se persiste este valor**, se calcula en cada respuesta (DEC-SUC-21).
- Given cupo disponible para el tipo detectado, When se confirma, Then `POST /operacion/ingresos` con `Idempotency-Key`; al recibir `200`, se dispara automáticamente `bridge.imprimir(escposBuilder.build('entrada', payload))` (impresión **automática**, con botón "Imprimir" siempre disponible después para una reimpresión inmediata sin costo — ver nota de alcance abajo).
- Given cupo agotado, When el operador fuerza el ingreso, Then el modal de forzado exige un motivo de ≥10 caracteres (Zod `min(10)`), enviado como `observaciones` con prefijo `[FORZADO: <motivo>]` (adaptación A-04); el backend genera la alerta `capacidad_agotada_forzado`.

**Nota de alcance obligatoria**: la impresión inmediata que ofrece el botón "Imprimir" tras registrar el ingreso (reimpresión E3 de CU-15E: "operación ya impresa") es **gratuita** y no crea ninguna fila en `reimpresion_ticket` — es un caso distinto del workflow de reimpresión con costo de la Fase 8, que existe para tiquetes perdidos o dañados días después. No confundir ambos en la implementación.

**Reglas de negocio**: BR1 (placa siempre en MAYÚSCULAS, almacenada e impresa), BR2 (autodetección única fuente válida, sin tolerancia de tipeo — DEC-SUC-22), BR3 (UUID del ingreso inmutable, nunca se reutiliza), BR5 (regex Auto/Moto exactos, ver Fase 4), BR6 (las 2 placas de una mensualidad deben ser del mismo tipo de vehículo).

**Tablas ER tocadas**: `ingreso` (INSERT: `uuid`, `uuid_sucursal`, `placa`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente` nullable, `fecha_ingreso`, `observaciones`, `created_by`), `vehiculos` (INSERT condicional, solo si es placa nueva de una suscripción existente), `subscripcion_vehiculos`/`subscripciones_cliente` (SELECT), `cantidad_vehiculos_sucursal` (recalculado vía vista, sin `UPDATE` de columna mutable), `sync_queue` (INSERT `ingreso.creado`, vía backend), `login` (SELECT, sesión activa).

**Endpoints**: `GET /operacion/ingresos?placa=X&activo=true` (para el redirect automático), `POST /operacion/ingresos` (cerrado en HU-F1.6).

**Componentes UI**: `Principal` (page, contenedora: orquesta `PlacaInput` + banners + confirmación); `PlacaInput` (presentacional, `useRef` para auto-focus, normalización, submit por Enter); `ForzarIngresoModal` (presentacional, textarea con Zod `min(10)`); `TiqueteModal` (presentacional, `role="dialog"`, botones "Imprimir" y "Siguiente"); `useIngresoActivo` (hook, SWR).

**Validaciones Zod**: `z.object({ placa: z.string().regex(REGEX_ACTIVO) })` para el campo principal; `z.object({ motivo: z.string().min(10) })` para el modal de forzado.

**Manejo de errores**:

| Código | Origen | Mensaje/acción en UI |
|---|---|---|
| `placa_formato_invalido` | Cliente (antes de llamar API) o `422` del backend | "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)", campo abierto |
| `motivo_forzado_requerido` | `422` | Foco en el textarea del modal de forzado, mensaje "El motivo debe tener al menos 10 caracteres" |
| `ingreso_activo_existente` | `409` | No se muestra como error: redirect automático y transparente a `SalidaFlow` |
| `printer_offline` | IPC (main process) | Banner "Impresora no disponible, reintentando…"; el ingreso ya quedó registrado, solo falla la impresión |

**Componentes UI — props clave**:

| Componente | Tipo | Props clave |
|---|---|---|
| `PlacaInput` | Presentacional | `value`, `onSubmit(placa)`, `autoFocus`, `disabled` |
| `Principal` | Contenedor | (sin props, obtiene todo de hooks: `useIngresoActivo`, `useTiposVehiculo`, `useOcupacion`) |
| `ForzarIngresoModal` | Presentacional | `open`, `onConfirm(motivo)`, `onCancel` |
| `TiqueteModal` | Presentacional | `payload`, `onImprimir`, `onSiguiente` |

**Pruebas**: `e2e/ingreso.spec.ts` — 5 escenarios:

1. Ingreso rotación: placa sin mensualidad, tipo detectado correctamente, tiquete impreso.
2. Ingreso mensualidad: placa con suscripción vigente, banner "Mensualidad activa" visible.
3. Placa con ingreso activo: redirect automático y transparente a `SalidaFlow`.
4. Ingreso forzado: cupo agotado, motivo capturado, alerta `capacidad_agotada_forzado` generada.
5. Fallback térmico: impresora no responde, cae a `window.print()` sin bloquear el registro del ingreso.

**Tamaño estimado**: 480 LOC.

**Tareas atómicas**:
- **HU-F6.1-T1**: `src/features/operacion/components/PlacaInput.tsx` — auto-focus (`useRef`), normalización a mayúsculas, submit por Enter.
- **HU-F6.1-T2**: `src/features/operacion/hooks/useIngresoActivo.ts` (SWR a `/operacion/ingresos?placa=X&activo=true`).
- **HU-F6.1-T3**: `src/features/operacion/pages/Principal.tsx` — orquesta `PlacaInput`, banner de tipo detectado, `OcupacionStrip` (Fase 4).
- **HU-F6.1-T4**: integrar `POST /operacion/ingresos` con `Idempotency-Key`.
- **HU-F6.1-T5**: tras `200`, disparar `bridge.imprimir(escposBuilder.build('entrada', payload))` automáticamente.
- **HU-F6.1-T6**: implementar redirect a `SalidaFlow` cuando `useIngresoActivo` resuelve un ingreso existente.
- **HU-F6.1-T7**: `ForzarIngresoModal.tsx` con Zod `min(10)`.
- **HU-F6.1-T8**: `e2e/ingreso.spec.ts` (5 escenarios).

---

#### Secuencia de flujo — CU-01 Registrar ingreso vehicular

```mermaid
sequenceDiagram
    actor Op as Operador
    participant UI as Principal.tsx
    participant API as api-sucursal
    participant DB as PostgreSQL local
    participant Prn as Impresora térmica

    Op->>UI: digita placa + Enter
    UI->>UI: normaliza MAYÚSCULAS + valida regex (estricta, sin tolerancia)
    alt formato inválido
        UI-->>Op: error inline "Placa no coincide con ningún formato conocido"
    else formato válido
        UI->>API: GET /operacion/ingresos?placa=X&activo=true
        alt ya tiene ingreso activo
            API-->>UI: 200 {items:[…]}
            UI->>UI: redirect automático a SalidaFlow (Fase 7)
        else sin ingreso activo
            API-->>UI: 200 {items:[]}
            UI->>Op: banner "Mensualidad activa" | "Rotación" (calculado, no persistido)
            Op->>UI: confirma ingreso
            UI->>API: POST /operacion/ingresos (Idempotency-Key)
            API->>DB: valida regex + suscripción + cupo (mv_ocupacion_diaria)
            alt cupo agotado sin forzado
                API-->>UI: 422 motivo_forzado_requerido
                UI->>Op: modal forzado (motivo ≥10 chars)
                Op->>UI: confirma motivo
                UI->>API: reintenta con observaciones=[FORZADO: …]
            end
            API->>DB: INSERT ingreso + recalcula ocupación
            API-->>UI: 201 {uuid, tipo_entrada, fecha_ingreso}
            UI->>Prn: bridge.imprimir(escposBuilder.build('entrada', payload))
            Prn-->>UI: ACK impresión (o printer_offline → cola de reintento)
            UI->>Op: "Ingreso registrado. Folio: UUID. Ticket impreso."
        end
    end
```

---

### HU-F6.2 — Tiquete de entrada (CU-15E), con QR y logo añadidos

**Historia**: Como operador, quiero que al confirmar un ingreso se imprima automáticamente un tiquete completo y legible, que el cliente pueda usar para reclamar su vehículo.

**Criterios de aceptación**: Given un ingreso confirmado, Then el tiquete impreso contiene los **15 campos literales** de CU-15E (encabezado, nombre de empresa, dirección, NIT, régimen, operario, "TIQUETE DE ENTRADA", número/folio, tarifa aplicada, fecha, hora de entrada, placa, horario de atención, póliza RC, observaciones) **más QR y logo**, añadidos porque CU-01 exige QR en su postcondición de éxito y la identidad de marca exige logo en todo tiquete (ninguno de los dos aparece en el listado literal de CU-15E, se agregan como extensión documentada, DEC-SUC-26); Given que la impresora no responde, Then cae a `fallbackBrowser.print()`. *(Corrección 2026-09-25, directiva del operador: se agrega un tercer campo añadido, "Tipo de operación" — ver tabla abajo — para que el operador identifique de un vistazo, con solo mirar el tiquete de entrada O el de salida, si ese vehículo se cobra o no. Antes era un tag condicional que solo aparecía para mensualidad; ahora es siempre explícito, ROTACIÓN o MENSUALIDAD.)*

**Contenido del QR (ABIERTO-01, recomendación aplicada por defecto)**: folio (UUID del ingreso) + placa, ambos ya disponibles al momento de imprimir, sin necesidad de tabla ni columna nueva. Si el negocio decide otro contenido, es un cambio acotado al builder, no a datos del ER.

**Los 18 campos exactos del tiquete de entrada (15 literales de CU-15E + 3 añadidos)**:

| # | Campo | Fuente |
|---|---|---|
| 1 | Encabezado | `sucursal` (dato configurado) |
| 2 | Nombre de la empresa | `sucursal.nombre` |
| 3 | Dirección | `sucursal.direccion` |
| 4 | NIT | `empresa.nit` |
| 5 | Régimen | `empresa.regimen` |
| 6 | Operario | `uuid_sucursal` + `uuid_usuario` de la sesión |
| 7 | Tipo de documento | texto fijo "TIQUETE DE ENTRADA" |
| 8 | **Tipo de operación** (añadido) | "ROTACIÓN" / "MENSUALIDAD" — derivado de `ingreso.uuid_subscripcion_cliente IS NOT NULL` al momento del ingreso (DEC-SUC-21) |
| 9 | Número de tiquete (folio) | `ingreso.uuid` |
| 10 | Tarifa aplicada | `tarifas_sucursal` resuelta en CU-01 |
| 11 | Fecha de operación | `ingreso.fecha_ingreso` (fecha) |
| 12 | Hora de entrada | `ingreso.fecha_ingreso` (hora) |
| 13 | Placa del vehículo | `ingreso.placa` |
| 14 | Horario de atención | `sucursal.horario` |
| 15 | Póliza de responsabilidad civil | `documentos` (adaptación A-01) |
| 16 | Observaciones | `sucursal` (dato configurado) |
| 17 | **QR** (añadido, DEC-SUC-26) | folio + placa (ABIERTO-01) |
| 18 | **Logo** (añadido, DEC-SUC-26) | `documentos` (`tipo='logo'`) |

**Nota (2026-09-25)**: el campo "Tipo de operación" del tiquete de ENTRADA refleja el estado de la suscripción al momento de entrar, no necesariamente lo que se termina cobrando en la salida — `calcular_cotizacion` decide el cobro real y puede diferir (ver CU-03M: una 2da placa simultánea de una suscripción **personal** paga rotación aunque haya entrado marcada "MENSUALIDAD"; una suscripción **empresa**, `cantidad_maxima_vehiculos>2`, no tiene esa restricción). No es una inconsistencia — es la naturaleza de un dato resuelto en dos momentos distintos.

**Tablas ER tocadas** (solo lectura, para armar el payload del tiquete): `sucursal` (nombre, dirección, NIT, régimen, horario, mensaje de bienvenida), `documentos` (`tipo='certificado'`, póliza RC — adaptación A-01), `ingreso` (folio, placa, fecha, tipo), `tipos_vehiculo` (nombre del tipo), `tarifas_sucursal` (tarifa aplicada), `usuarios` (nombre del operario).

**Endpoints**: `GET /documentos?uuid_sucursal=X&tipo=certificado` (póliza RC), datos ya disponibles del propio `POST /operacion/ingresos`.

**Componentes UI**: `escposBuilder.build('entrada', payload)` (extiende el builder base de Fase 5); `escposTemplates.ts` (layout de los 15+2 campos).

**Manejo de errores**: A-05 — tras imprimir, se inserta una fila en `log_transaccional` (`accion='impreso'`, `datos_nuevos={estado:'impresa'}` o `{estado:'pendiente de impresión'}` si falla); el estado se lee como la última fila con esa acción para el registro.

**Pruebas**: `src/lib/print/__tests__/escposBuilder.entrada.test.ts` — valida que los 18 campos (15+QR+logo+tipo de operación) están presentes en el buffer generado; `e2e/print.spec.ts` con mock de `bridge.imprimir`.

**Tamaño estimado**: 220 LOC.

**Tareas atómicas**:
- **HU-F6.2-T1**: `escposTemplates.ts` — layout con los 15 campos literales de CU-15E + QR + logo.
- **HU-F6.2-T2**: `TiqueteEntradaPayload` como interfaz con los 17 campos `readonly` (el campo 18, tipo de operación, vive en `esMensualidad` como side-channel — ver `escposTemplates.ts`) — TypeScript da error de compilación si falta uno, garantía de completitud en tiempo de build.
- **HU-F6.2-T3**: integración con `log_transaccional` para el estado de impresión (vía backend, adaptación A-05).
- **HU-F6.2-T4**: los tests de builder + e2e con mock de impresión.

---

## Fase 7 — Salida y cálculo de tarifa (CU-02, CU-03, CU-03M) + tiquetes de salida (CU-15S, CU-15SM)

**Objetivo**: cotizar, registrar la salida (con o sin mensualidad) y emitir su tiquete — con la secuencia de impresión reordenada respecto al corpus original (ver DEC-SUC-27).

### HU-F7.1 — Búsqueda tolerante y cotización (CU-02)

**Historia**: Como operador, quiero buscar un vehículo por placa con tolerancia a errores de tipeo, y ver el desglose de lo que debe pagar antes de confirmar la salida.

**Criterios de aceptación**:
- Given una placa digitada con posible error de tipeo, When se busca el ingreso activo, Then la búsqueda tolera O↔0, I↔1, B↔8 (`buscarIngresoTolerante`, **función distinta** de `detectarTipoVehiculo` de Fase 4 — nunca la misma, DEC-SUC-22).
- Given un ingreso activo encontrado, When `GET /operacion/cotizar?uuid_ingreso=X`, Then se muestra el tiempo transcurrido y el desglose `{tiempo, total_a_pagar, iva, subtotal}`, con countdown de 15 minutos (vigencia del cálculo).
- Given que el vehículo tiene mensualidad vigente, Then la respuesta trae `{cobrar:false}` y el flujo salta directo a CU-03M (HU-F7.2) sin mostrar desglose de cobro.
- Given múltiples candidatos por la búsqueda tolerante, Then se muestra una lista para que el operador elija.
- Given que el cálculo pasa de 15 minutos sin confirmarse, Then se recalcula automáticamente antes de permitir "Confirmar salida".
- Given un vehículo SIN placa (bici/patineta) con ingreso activo identificado solo por `consecutivo` (ej. `PATINETA-000003-34a24bae`), When el operador tipea un fragmento de placa o de consecutivo en el input gigante del dashboard o en el campo de búsqueda del propio panel de Salida (abierto directo con F2 / botón lateral), Then el sistema muestra en vivo hasta 6 sugerencias — match por prefijo en placa normalizada y por substring case-insensitive en consecutivo — en un dropdown accesible (WAI-ARIA "combobox con listbox de autocompletado": input con `role="combobox"`/`aria-expanded`/`aria-controls`/`aria-activedescendant`, listbox con ítems `role="option"`; flechas navegan, Enter/click selecciona, Escape cierra).
- Given que el operador selecciona una sugerencia CON placa, Then el comportamiento es idéntico a tipear esa placa manualmente (abre/cotiza la salida). Given que selecciona una sugerencia SIN placa, Then el sistema resuelve el `uuid_ingreso` directamente y corre la MISMA guarda de estado (`abierto`/`cerrado`/`anulada`) antes de cotizar — sin que el operador tenga que tipear nada más.

**Regla de negocio**: fórmula fiscal literal de CU-02 AC7 (DEC-SUC-24): `iva = total_a_pagar * porcentaje_impuesto`; `subtotal = total_a_pagar - iva` — se muestra tal cual, sin reinterpretar la base del cálculo.

**Tablas ER tocadas** (solo lectura): `ingreso`, `salidas`, `anulaciones` (resolver ingreso activo), `tarifas_sucursal`, `impuestos`, `subscripciones_cliente`.

**Endpoints**: `GET /operacion/cotizar?uuid_ingreso=X` (cerrado en HU-F1.8).

**Componentes UI**: `CotizacionPanel` (presentacional, usa `<dl>` semántico para el desglose, countdown de 15 min visible); `useCotizacion` (hook, SWR con `refreshInterval: 1000` mientras el panel está abierto). Búsqueda sin placa (T5-T8): `useIngresosActivos` (hook compartido, polling 10s de ingresos activos por sucursal); `matchVehiculos` (función pura de ranking placa-prefijo/consecutivo-substring); `VehiculoSuggestions` (dropdown accesible compartido por el input del dashboard y por el campo `salida-placa`).

**Manejo de errores**:

| Código | Mensaje/acción en UI |
|---|---|
| `ingreso_no_encontrado` | "No hay ingreso activo para XYZ999 en esta sucursal", con opciones "Reintentar" o "Crear nuevo ingreso" (deriva a Fase 6) |
| `iva_no_configurado` | Banner de error de configuración, no operable por el operador — requiere intervención de administración |
| timeout (>5s) | "El cálculo está tardando más de lo esperado, reintentando…" con reintento automático único |

**Componentes UI — props clave**: `CotizacionPanel` — `data` (resultado de `useCotizacion`), `secondsLeft` (del countdown de 15 min), `onConfirmar`, `onRecalcular`.

**Pruebas**: `src/features/operacion/hooks/__tests__/useCotizacion.test.ts` — 3 escenarios (rotación, mensualidad, tiempo ≥ tarifa plena). Búsqueda sin placa: `vehiculoMatch.test.ts` (ranking puro), `VehiculoSuggestions.test.tsx` (listbox/option ARIA + navegación), `dashboardDrawerStore.test.ts` (`initialUuidIngreso`), `SalidaSheet.test.tsx` y `SalidaPanel.test.tsx` (guarda de estado + autocompletar in-field), `Dashboard.test.tsx` (autocompletar del hero).

**Tamaño estimado**: 260 LOC (T1-T4). Ampliado en T5-T8 para búsqueda sin placa — ver tareas atómicas.

**Tareas atómicas**:
- **HU-F7.1-T1**: `src/lib/validation/placaTolerante.ts` — `buscarIngresoTolerante(placa)`, función separada de la detección estricta de ingreso.
- **HU-F7.1-T2**: `src/features/operacion/hooks/useCotizacion.ts` (SWR, `refreshInterval:1000`, timeout 5s).
- **HU-F7.1-T3**: `CotizacionPanel.tsx` con `<dl>` semántico + countdown.
- **HU-F7.1-T4**: los 3 tests de hook.
- **HU-F7.1-T5** (búsqueda sin placa): `src/features/operacion/hooks/useIngresosActivos.ts` (extraído de `Dashboard.tsx`, reusado por `<VehiculosDentroList>` y `<SalidaPanel>`) + `src/features/operacion/lib/vehiculoMatch.ts` (`matchVehiculos`, función pura: prefijo en placa normalizada — reusa `normalizarPlaca` de `placaTolerante.ts` — y substring case-insensitive en consecutivo, cap 6 candidatos).
- **HU-F7.1-T6** (búsqueda sin placa): `src/features/operacion/components/VehiculoSuggestions.tsx` — dropdown accesible compartido (WAI-ARIA combobox+listbox), consumido por AMBOS puntos de entrada.
- **HU-F7.1-T7** (búsqueda sin placa): `dashboardDrawerStore.ts` (+`initialUuidIngreso`, mismo patrón que `initialPlaca`) y wiring del `PlacaInputHero` (`Dashboard.tsx`) + `SalidaSheet.tsx` para threadear la selección de una sugerencia sin placa.
- **HU-F7.1-T8** (búsqueda sin placa): wiring del propio campo `salida-placa` en `SalidaPanel.tsx` — autocompletar in-field + guarda de estado (`getIngresoEstado`) factorizada en una sola función interna reusada por la búsqueda tolerante, `initialUuidIngreso`, y la selección de sugerencias.

---

### HU-F7.2 — Registrar salida (rotación y mensualidad)

**Historia**: Como operador, quiero confirmar la salida de un vehículo (con o sin mensualidad) y que el cupo se libere de inmediato.

**Criterios de aceptación**:
- Given un cálculo vigente, When se confirma la salida (rotación), Then `POST /operacion/salidas` → `201` con `uuid_salida`, `estado='PENDIENTE_PAGO'`; el cupo se libera inmediatamente.
- Given una placa con mensualidad vigente, When se confirma, Then `POST /operacion/salidas` (endpoint único, ver corrección de HU-F1.7) → `201` con `tipo_salida='MENSUALIDAD'`, sin ningún monto asociado a `salidas`. *(Corrección 2026-09-24, migration 0050: la salida ya no deriva "directo" al tiquete — primero se registra la factura completa con descuento a $0 (`POST /facturacion/factura`, `medio_pago='suscripcion'`, mismo pipeline DIAN que CU-04/CU-05), se muestra `<FacturaDisplayModal />` con el desglose, y SOLO al cerrar ese modal se imprime el tiquete CU-15SM — ver "Factura por mensualidad ($0)" en el glosario y HU-F7.3.)*
- Given una placa que es la 2da placa simultánea de la misma suscripción en patio, When el plan es personal (`tipo_subscripciones.cantidad_maxima_vehiculos <= 2` o sin configurar), Then la salida cobra como ROTACIÓN normal (`cobrar=true`, motivo informativo `'segunda_placa_misma_mensualidad'`), sin descuento — bugfix 2026-09-24 (migration 0050): esta regla ya estaba en el corpus original (ver glosario) pero se había regresado silenciosamente en migraciones intermedias (0046-0049) al reescribir la función PL/pgSQL completa sin arrastrar el fix de la migration `0038_calcular_cotizacion_2nd_plate_rotation`.
- Given una placa que es la 2da (o 3ra, etc.) placa simultánea de la misma suscripción en patio, When el plan es empresa/flota (`cantidad_maxima_vehiculos > 2`), Then la salida sigue sin cobro (`cobrar=false`, motivo `'multiple_vehiculos_plan_empresa'`), igual que la 1era placa — directiva del operador 2026-09-24, no estaba en el corpus original.
- Given un doble clic en "Confirmar salida", Then la idempotencia por UUID evita duplicar la operación.
- Given un ingreso que ya tiene una salida no anulada, When se reintenta, Then `409 salida_duplicada`.

**Regla de negocio**: ninguno de los dos endpoints modifica `ingreso` (insert-only); ninguno persiste un monto en `salidas` — el "total a pagar" viaja en memoria de UI hasta CU-04 (DEC-SUC-23).

**Tablas ER tocadas**: `salidas` (INSERT, sin columna de monto), `cantidad_vehiculos_sucursal` (recalculado vía vista), `subscripciones_cliente`/`subscripcion_vehiculos` (SELECT, solo mensualidad).

**Endpoints**: `POST /operacion/salidas`, `POST /operacion/salidas/mensualidad` (ambos cerrados en HU-F1.7).

**Componentes UI**: `SalidaFlow` (page, wizard de 2 pasos: confirmación con desglose → tiquete); `SalidaMensualidad` (page, atajo directo desde detección de mensualidad).

**Manejo de errores**:

| Código | Mensaje/acción en UI |
|---|---|
| `salida_duplicada` | "Este ingreso ya tiene una salida registrada" — bloquea el reintento |
| `mensualidad_no_vigente` | Deriva automáticamente a `SalidaFlow` normal (rotación), sin mostrarse como error |
| `cotizacion_expirada` | "El cálculo expiró, recalculando…" — vuelve a `GET /operacion/cotizar` de forma transparente |

**Componentes UI — props clave**: `SalidaFlow` (contenedor, orquesta `CotizacionPanel` + confirmación); `SalidaMensualidad` — `uuidIngreso`, `onConfirmado(uuidSalida)`.

**Pruebas**: `e2e/salida.spec.ts` — 3 escenarios:

1. Salida rotación: cotización vigente, cupo liberado de inmediato, sin impresión aún (diferida a Fase 8).
2. Salida mensualidad: sin cobro (`salidas` sin monto), pero SÍ registra una factura completa con descuento a $0 y muestra `<FacturaDisplayModal />`; el tiquete CU-15SM se imprime al cerrar ese modal (corrección 2026-09-24, migration 0050 — ver HU-F7.3).
3. Doble clic en "Confirmar salida": idempotencia por UUID evita duplicar la operación; segunda salida sobre el mismo ingreso → `409 salida_duplicada`.
4. *(Agregado 2026-09-24)* 2da placa simultánea de un plan personal → cobra rotación completa. 2da+ placa simultánea de un plan empresa (`cantidad_maxima_vehiculos>2`) → sigue sin cobro.

**Tamaño estimado**: 320 LOC.

**Tareas atómicas**:
- **HU-F7.2-T1**: `src/features/operacion/pages/SalidaFlow.tsx` (wizard de 2 pasos, usa `CotizacionPanel` de HU-F7.1).
- **HU-F7.2-T2**: integración de `POST /operacion/salidas` con `Idempotency-Key`.
- **HU-F7.2-T3**: `src/features/operacion/pages/SalidaMensualidad.tsx` (atajo).
- **HU-F7.2-T4**: `e2e/salida.spec.ts` (3 escenarios).

---

#### Secuencia de flujo — CU-02/CU-03/CU-03M Calcular tarifa y registrar salida

```mermaid
sequenceDiagram
    actor Op as Operador
    participant UI as SalidaFlow.tsx
    participant API as api-sucursal
    actor Cl as Cliente

    Op->>UI: digita placa (con tolerancia O/0, I/1, B/8 — solo aquí, nunca en ingreso)
    UI->>API: buscarIngresoTolerante(placa)
    alt múltiples candidatos
        API-->>UI: lista de candidatos
        UI->>Op: elegir el correcto
    end
    UI->>API: GET /operacion/cotizar?uuid_ingreso=X
    alt mensualidad vigente (2026-09-24: desglose completo + concepto_descuento)
        API-->>UI: {cobrar:false, motivo:'mensualidad_vigente', subtotal, iva, total, concepto_descuento, ...}
        UI->>API: POST /operacion/salidas (endpoint único, tipo_salida='MENSUALIDAD')
        API-->>UI: 201 {tipo_salida:'MENSUALIDAD'}
        UI->>API: POST /facturacion/factura (medio_pago='suscripcion', servicio+descuento, total=0)
        API-->>UI: 201 FacturaRead (factura DIAN completa, descuento poblado)
        UI->>Op: <FacturaDisplayModal /> con el desglose
        Op->>UI: cierra el modal
        UI->>Op: imprime CU-15SM (sin cambios de formato)
    else rotación con cobro
        API-->>UI: {tiempo_minutos, total_a_pagar, iva, subtotal, vigente_hasta}
        UI->>Op: muestra desglose (countdown 15 min)
        Op->>UI: "Confirmar salida"
        UI->>API: POST /operacion/salidas
        API-->>UI: 201 {uuid_salida, estado:'PENDIENTE_PAGO'} — cupo liberado de inmediato
        Note over UI: el tiquete CU-15S NO se imprime aquí (DEC-SUC-27)
        UI->>Op: continúa a PagoModal (Fase 8)
    end
```

---

### HU-F7.3 — Tiquetes de salida (CU-15S) y salida-mensualidad (CU-15SM), impresos después del pago

**Historia**: Como operador, quiero que el tiquete de salida se imprima con el desglose completo (incluido el medio de pago), y que el de mensualidad se distinga claramente como "sin cobro".

**Corrección de secuencia obligatoria (DEC-SUC-27)**: el CU-03 original manda a imprimir el tiquete de salida en su propio paso 8, **antes** de que exista ningún pago — pero el propio CU-15S exige el campo "medio de pago" (atribuido por error de cita del corpus a "CU-02", cuando en realidad ese dato solo existe tras CU-04). Esta HU reordena la secuencia: **el tiquete de salida (CU-15S) se imprime después de confirmado el pago** (Fase 8), no al registrar la salida. El tiquete de salida-mensualidad (CU-15SM) sí se imprime de inmediato al confirmar la salida, porque no depende de ningún pago.

**Criterios de aceptación**:
- Given un pago confirmado (Fase 8), Then se imprime el tiquete CU-15S con los **19 campos literales** (encabezado, empresa, dirección, NIT, régimen, operario, "TIQUETE DE SALIDA", folio, tarifa aplicada, fecha, hora de entrada, hora de salida, tiempo total, subtotal, IVA, total a pagar, medio de pago, placa, horario/póliza RC/resolución FE/observaciones) más QR, logo y un campo explícito "Tipo de operación: ROTACIÓN" (misma extensión que CU-15E — directiva del operador 2026-09-25).
- Given una salida con mensualidad confirmada, Then se imprime el tiquete CU-15SM con los **15 campos literales** (mismo patrón que CU-15E, sin desglose de cobro), con el encabezado dinámico de la sucursal (**no** el texto fijo "PARQUEADERO PUBLICO" que trae el CU original — se trata como defecto de copia del corpus, corregido aquí en silencio), un sello "*** PAGO CON MENSUALIDAD ***" (`0x1B 0x21 0x30`, texto 2x altura) que distingue visualmente el documento, y un campo explícito "Tipo de operación: MENSUALIDAD" (directiva del operador 2026-09-25, mismo campo que ahora llevan CU-15E y CU-15S) — el CU original no diferencia el texto de "TIPO DE DOCUMENTO" entre CU-15S y CU-15SM (ambos dicen literalmente "TIQUETE DE SALIDA"); el sello + el campo explícito son la decisión de producto que introduce la distinción visual/textual necesaria para que el cajero no confunda un tiquete sin cobro con uno cobrado. *(Corrección 2026-09-24, migration 0050: "se imprime de inmediato" ya no es exacto — el tiquete se imprime al cerrar `<FacturaDisplayModal />`, que se abre después de registrar la factura completa con descuento a $0. El FORMATO del tiquete NO cambia salvo el nuevo campo explícito de tipo (sigue sin desglose de cobro, mismo sello) — lo que cambia es que ahora existe una factura completa detrás, visible en el modal antes de imprimir. Ver "Factura por mensualidad ($0)" en el glosario.)*

**Los 22 campos exactos del tiquete de salida (19 literales de CU-15S + 3 añadidos)**:

| # | Campo | Fuente |
|---|---|---|
| 1-6 | Encabezado, empresa, dirección, NIT, régimen, operario | `sucursal`/`empresa`/sesión (idéntico a CU-15E) |
| 7 | Tipo de documento | texto fijo "TIQUETE DE SALIDA" |
| 8 | **Tipo de operación** (añadido, directiva 2026-09-25) | texto fijo "ROTACIÓN" — este builder solo se invoca cuando `tipo_salida==='ROTACION'` |
| 9 | Número de tiquete (folio) | `salidas.uuid` |
| 10 | Tarifa aplicada | `tarifas_sucursal` (nota del corpus original: cita "CU-01", corregido aquí a la tarifa real usada en CU-02) |
| 11 | Fecha de operación | `salidas.fecha_salida` (fecha) |
| 12 | Hora de entrada | `ingreso.fecha_ingreso` (hora) |
| 13 | Hora de salida | `salidas.fecha_salida` (hora) |
| 14 | Tiempo total | `fecha_salida - fecha_ingreso` |
| 15 | Subtotal | de la factura (CU-02/CU-04) |
| 16 | IVA | de la factura |
| 17 | Total a pagar | de la factura |
| 18 | Medio de pago | `factura_pagos.medio_pago` (nota: el corpus original lo atribuye por error de cita a "CU-02"; el dato real proviene de CU-04) |
| 19 | Placa del vehículo | `ingreso.placa` |
| 20 | Horario/Póliza RC/Resolución FE/Observaciones | `sucursal`/`documentos`/`resolucion_facturacion` |
| 21 | **QR** (añadido) | folio + placa |
| 22 | **Logo** (añadido) | `documentos` (`tipo='logo'`) |

**Los 16 campos exactos del tiquete de salida-mensualidad (idénticos a CU-15E salvo la fuente)**: encabezado (dinámico de sucursal, no "PARQUEADERO PUBLICO" fijo), empresa, dirección, NIT, régimen, operario, "TIQUETE DE SALIDA" + sello "*** PAGO CON MENSUALIDAD ***", **Tipo de operación: "MENSUALIDAD" (añadido, directiva 2026-09-25)**, folio (`salidas.uuid`), fecha de operación, hora de entrada, hora de salida, tiempo total, placa, horario/póliza RC/resolución FE/observaciones — **sin** subtotal/IVA/total (no hay cobro). *(Nota preexistente, no corregida en este cambio: este listado en prosa tampoco menciona QR/logo, aunque el builder SÍ los emite — ver `escposBuilder.ts::buildSalidaMensualidadBody` — drift de documentación anterior a esta directiva.)*

**Tablas ER tocadas** (solo lectura): `sucursal`, `ingreso`, `salidas`, `facturas`/`factura_pagos` (medio de pago, solo CU-15S), `subscripciones_cliente` (solo CU-15SM), `usuarios`.

**Componentes UI**: `escposBuilder.build('salida', payload)`, `escposBuilder.build('salida-mensualidad', payload)`.

**Pruebas**: `src/lib/print/__tests__/escposBuilder.salida.test.ts` — 2 casos (22 campos de CU-15S, 16 campos + sello de CU-15SM), validando los bytes exactos del sello (`0x1B 0x21 0x30`).

**Tamaño estimado**: 200 LOC.

**Tareas atómicas**:
- **HU-F7.3-T1**: `escposBuilder.build('salida', payload)` — 19 campos + QR + logo; se dispara desde el flujo de pago (Fase 8), no desde `SalidaFlow`.
- **HU-F7.3-T2**: `escposBuilder.build('salida_mensualidad', payload)` — 15 campos + sello, encabezado dinámico corregido (no "PARQUEADERO PUBLICO" fijo).
- **HU-F7.3-T3**: integrar el builder de mensualidad en `SalidaMensualidad.tsx` (inmediato) y el de salida normal en el flujo de pago de Fase 8 (diferido al éxito del cobro).
- **HU-F7.3-T4**: los 2 tests de builder.

---

## Fase 8 — Cobro y Factura Electrónica (CU-04, CU-05) + reimpresión de tiquete

**Objetivo**: procesar el pago de una salida por rotación, emitir la representación local de la FE (TopPoint), y permitir reimprimir un tiquete con costo cuando el cliente lo perdió o dañó.

### HU-F8.1 — Modal de pago (efectivo/datáfono) con FE

**Historia**: Como operador, quiero cobrar una salida (efectivo o datáfono) y generar automáticamente la factura electrónica, sin que el cliente tenga que pedirla explícitamente.

**Criterios de aceptación**:
- Given una salida rotación registrada, When se abre el modal de pago, Then muestra el monto a pagar (de CU-02), opciones Efectivo/Datáfono y un checkbox "¿Desea factura con sus datos?" **no marcado por defecto**.
- Given efectivo, When se ingresa el monto recibido, Then se calculan y muestran los vueltos en vivo antes de confirmar.
- Given datáfono, When se ingresa el voucher, Then no hay integración SDK (MVP): el voucher se guarda para auditoría, sin contacto con ningún proveedor de pago.
- Given el checkbox de FE con datos propios marcado, When se completan NIT/DV/nombre/email, Then se validan **antes** de enviar: NIT por módulo 11 (caso de referencia `800.123.456-7`) y email por RFC 5322.
- **(Ajuste 2026-09-25, directiva del operador — persona natural/empresa)** Given el checkbox de FE marcado, When se completa el bloque de datos del cliente, Then primero se elige **tipo de cliente** (Persona natural | Empresa), independiente del checkbox de FE: Empresa exige NIT+DV (módulo 11) y razón social; Persona natural exige tipo de documento (CC/CE/Pasaporte, sin DV — Colombia no tiene dígito de verificación para cédula), número, nombres y apellidos. El checkbox de FE decide si se envía con datos reales o como cliente genérico; el tipo de cliente decide QUÉ documento pedir cuando sí hay datos reales — son dos decisiones ortogonales.
- **(Ajuste 2026-09-25)** Given el checkbox de FE marcado, Then los inputs de identificación arrancan **vacíos con placeholder de ejemplo** (nunca con un valor precargado) — el sentinel de consumidor final (`222222222222222`) solo se usa para armar el payload cuando el checkbox está **sin marcar**, nunca como contenido visible de un input.
- Given cualquier medio de pago, When se confirma, Then el pago **siempre** se registra, y la FE **siempre** se genera (a consumidor final, NIT `222222222222222`, por defecto) — no existe ningún camino de "sin FE" (regulación DIAN, BR1 de CU-04, literal).
- Given que la FE falla por error técnico del lado de envío, Then el pago ya quedó completo en `factura_pagos` y la FE queda encolada para reintento (nunca se revierte el cobro por un fallo de FE).
- Given el pago confirmado, Then se dispara la impresión del tiquete de salida (CU-15S, HU-F7.3) y del recibo de pago (numeración propia `sucursal-YYYYMMDD-NNNNNN`, sin relación declarada con el consecutivo DIAN — ver ABIERTO-02).

**Nota de copy obligatoria**: el texto del modal debe decir explícitamente "Factura a nombre del cliente (opcional); por defecto, factura a consumidor final" — nunca "FE opcional" a secas, redacción que podría leerse (incorrectamente) como que la factura misma es opcional.

**Reglas de negocio**: BR2 (consumidor final por defecto, NIT `222222222222222`, nombre "Consumidor final"), BR3 (email opcional a consumidor final, obligatorio con datos del cliente), BR4 (numeración TopPoint estrictamente secuencial por sucursal, sin saltos), BR6 (datáfono = voucher manual, sin SDK en MVP).

**Tablas ER tocadas**: `factura_pagos` (INSERT: `medio_pago`, `valor`, `referencia`, `uuid_sesion`, `tipo_movimiento='pago'`), `facturas` (INSERT: `subtotal`, `descuento=0`, `total`), `factura_detalle` (INSERT, línea "Estacionamiento"), `factura_impuestos` (INSERT, snapshot de IVA), `factura_electronica` (INSERT), `salidas` (`UPDATE estado='PAGADO'`, única excepción al insert-only de esta tabla), `clientes` (SELECT/INSERT condicional si hay datos propios).

**Endpoints**: `POST /facturacion/factura`, `POST /facturacion/factura-pagos` (ambos cerrados en HU-F1.9), `POST /facturacion/factura-electronica` (HU-F1.10).

**Componentes UI**: `PagoModal` (contenedora: RHF + vueltos en vivo + voucher + checkbox FE); `useVueltos` (hook, cálculo puro).

**Validaciones Zod**: `z.object({ medio: z.enum(['efectivo','datafono']), monto_recibido: z.number().optional(), voucher: z.string().min(1).optional(), fe_con_datos: z.boolean(), nit: z.string().optional(), dv: z.string().optional(), nombre: z.string().optional(), email: z.string().email().optional() })` con refinamiento condicional: si `fe_con_datos=true`, `nit`/`nombre`/`email` pasan a requeridos.

**Manejo de errores**:

| Código | Origen | Mensaje/acción en UI |
|---|---|---|
| `nit_invalido` | `422` | Muestra el DV esperado junto al campo, no permite enviar |
| `email_invalido` | `422`/cliente | Mensaje inline RFC 5322, foco en el campo |
| `voucher_requerido` | `400`/cliente | Bloquea el submit si datáfono con voucher vacío |
| `monto_insuficiente` | cliente (antes de llamar API) | Bloquea el submit si el efectivo recibido es menor al total |

**Componentes UI — props clave**: `PagoModal` — `total`, `uuidSalida`, `onConfirmado(uuidFactura)`, `onCancelar`.

**Pruebas**: `e2e/pago.spec.ts` — 6 escenarios:

1. Pago en efectivo: vueltos calculados correctamente, FE a consumidor final generada.
2. Pago con datáfono: voucher capturado, guardado sin contacto SDK.
3. FE a consumidor final (checkbox sin marcar): NIT `222222222222222` aplicado automáticamente.
4. FE con datos del cliente: NIT/DV/nombre/email capturados y validados antes de enviar.
5. NIT inválido: `422 nit_invalido` con el DV esperado en el detalle, submit bloqueado.
6. Pago mixto (si el negocio lo permite; documentar como fuera de alcance explícito si no aplica en esta versión).

**Tamaño estimado**: 420 LOC.

**Tareas atómicas**:
- **HU-F8.1-T1**: `src/lib/validation/nit.ts` — `validarNitModulo11(nit, dv): {ok, detalle}`, caso de test `800.123.456-7`.
- **HU-F8.1-T2**: `src/features/facturacion/components/PagoModal.tsx` con RHF + Zod + vueltos en vivo.
- **HU-F8.1-T3**: integrar `POST /facturacion/factura` + `POST /facturacion/factura-pagos` con `Idempotency-Key`.
- **HU-F8.1-T4**: tras `200`, disparar impresión de CU-15S (Fase 7) y del recibo de pago.
- **HU-F8.1-T5**: `e2e/pago.spec.ts` (6 escenarios).
- **HU-F8.1-T6** (Ajuste 2026-09-25, persona natural/empresa): selector "Tipo de cliente" (persona|empresa) dentro del bloque FE de `PagoModal.tsx`, desacoplado del checkbox; `src/lib/validation/identificacion.ts` (`validarIdentificacion(tipo, numero, dv?)`, dispatcher que delega a `validarNitModulo11` para NIT y aplica solo checks de formato para CC/CE/pasaporte); fix del bug de placeholders (`nit`/`nombre_cliente` ya no se precargan con el sentinel de consumidor final). Armado del payload centralizado en `src/features/facturacion/lib/clienteFePayload.ts` (`buildClienteFePayload(values)`, función pura) — `PagoSheet.tsx` y `ReimprimirTiquete.tsx` (ambos consumidores de `<PagoModal>`) ya NO arman `fe_datos_cliente` a mano ni hardcodean `tipo_identificador:'NIT'`, solo llaman la función y spreadean el resultado. Pendiente en Flujo 2 (misma directiva, rama separada): `Venta.tsx` paso 1 (identificación siempre visible, sin checkbox, fuera de `<PagoModal>`) sigue con su input NIT-only propio — cuando se aborde, debe reusar `ClienteIdentificacionFields` + una función pura compartida equivalente para `ClientesCreate`/`VentaSuscripcionCreate.cliente`, no reinventar el mapeo.
  - **Bugs críticos encontrados y corregidos en validación en vivo (Chrome DevTools) de esta misma tarea, no preexistentes al alcance pero sí al código tocado**:
    1. `schemas/facturacion.py::FacturaItemConDatosPropios._validar_nit_modulo11` usaba `@field_validator("numero_identificacion")` leyendo `info.data.get("dv")` — en Pydantic v2 `info.data` solo trae los campos declarados ANTES del campo bajo validación, y `dv` se declara DESPUÉS de `numero_identificacion`, así que `dv` era SIEMPRE `None`: **todo pago con NIT real (datos propios) rechazaba con 422 "dv required" sin importar el DV enviado** — el camino de FE con datos propios nunca pudo completarse en producción hasta este fix. Corregido a `model_validator(mode="after")` (mismo patrón que `ClientesCreate`).
    2. `src/lib/validation/nit.ts` implementaba un algoritmo módulo-11 DISTINTO al del backend (16 pesos incluyendo `31`, aplicado izquierda-a-derecha, `DV=11-mod`) contra el real de la DIAN que usa el backend (15 pesos sin `31`, aplicado derecha-a-izquierda, `DV=mod` directo, Variant A). Coincidían por casualidad solo en el NIT de referencia `800.123.456-7`; cualquier otro NIT real (verificado en vivo con `900123456`: frontend calculaba DV `2`, backend exige `3`) divergía, dando al operador una validación de "DV correcto" que el backend luego rechazaba. Corregido para que `nit.ts` sea un espejo exacto de `repo/nit_modulo11.py`.

---

#### Secuencia de flujo — CU-04/CU-05 Procesar pago y generar Factura Electrónica

```mermaid
sequenceDiagram
    actor Op as Operador
    participant UI as PagoModal.tsx
    participant API as api-sucursal
    participant Cloud as api-cloud
    participant TP as TopPoint (DIAN)
    participant Prn as Impresora

    Op->>UI: elige medio (efectivo/datáfono) + monto o voucher
    opt FE con datos del cliente
        Op->>UI: NIT + DV + nombre + email
        UI->>UI: validarNitModulo11() + email RFC 5322 (client-side, antes de enviar)
    end
    Op->>UI: confirmar
    UI->>API: POST /facturacion/factura (Idempotency-Key)
    API->>API: BEGIN — INSERT facturas + factura_detalle + factura_impuestos
    API->>API: INSERT factura_pagos (medio_pago, valor, referencia, uuid_sesion)
    API->>API: UPDATE salidas SET estado='PAGADO' (única excepción insert-only)
    API->>API: assign_consecutivo (SELECT...FOR UPDATE) → INSERT factura_electronica
    API->>API: COMMIT
    API-->>UI: 201 {uuid_factura, uuid_factura_electronica, estado_fe:'pendiente'}
    UI->>Prn: imprime tiquete CU-15S (recién ahora, DEC-SUC-27) + recibo de pago
    UI->>Op: pantalla de confirmación

    par asíncrono, vía sync_queue
        API->>Cloud: evento factura.creada (sync cada 60s)
        Cloud->>TP: envía documento FE
        TP-->>Cloud: CUFE (aceptado) o error (rechazado)
        Cloud-->>API: ACK → envio_dian.estado actualizado (fila nueva, workflow)
    end
    Note over UI: si TopPoint falla, el pago YA quedó completo — la FE se reintenta sola, nunca revierte el cobro (BR5 CU-04)
```

---

Estado real de `envio_dian` (única fuente de verdad del estado de la FE; `factura_electronica` no tiene columna de estado propia):

```mermaid
stateDiagram-v2
    [*] --> pendiente: INSERT envio_dian (al generar la FE, CU-04)
    pendiente --> enviado: sync hacia cloud (job-sync-sucursal)
    enviado --> aceptado: ACK de TopPoint con CUFE
    enviado --> rechazado: error de TopPoint
    rechazado --> pendiente: POST reintentar (nueva fila, uuid_envio_padre)
    note right of pendiente
        Cada transición es una fila NUEVA
        (workflow [L-W]), nunca un UPDATE.
    end note
```

### HU-F8.2 — Estado de la Factura Electrónica y reintento

**Historia**: Como operador, quiero ver si la factura electrónica de una venta fue aceptada por TopPoint o quedó pendiente/rechazada, y poder reintentarla si falló.

**Criterios de aceptación**:
- Given `GET /facturacion/factura-electronica/{uuid}`, Then muestra el estado real (`pendiente|enviado|aceptado|rechazado`) y el CUFE si está `aceptado`.
- Given `pendiente` o `enviado`, Then hay *polling* cada 30 s mientras el estado no sea terminal.
- Given `rechazado`, When se presiona "Reintentar", Then `POST /facturacion/factura-electronica/{uuid}/reintentar` — nueva fila encadenada, no un `UPDATE`.

**Tablas ER tocadas** (solo lectura, salvo el reintento): `factura_electronica`, `envio_dian`.

**Endpoints**: `GET /facturacion/factura-electronica/{uuid}`, `POST .../reintentar` (ambos de HU-F1.10).

**Componentes UI**: `FacturaDetalle` (page, bloque de estado FE + botón reintentar).

**Manejo de errores**: `409 numeracion_agotada` → alerta visible "Numeración agotada. Contactar proveedor." (mapea a la alerta ya sembrada `fe_numbering_exhausted`).

**Pruebas**: `e2e/fe.spec.ts` — FE generada, estado visible, reintentar.

**Tamaño estimado**: 180 LOC.

**Tareas atómicas**:
- **HU-F8.2-T1**: `src/features/facturacion/pages/FacturaDetalle.tsx` con bloque de estado FE + botón reintentar.
- **HU-F8.2-T2**: *polling* SWR `refreshInterval: 30_000`, activo solo mientras no sea estado terminal.
- **HU-F8.2-T3**: `e2e/fe.spec.ts` (3 escenarios).

---

### HU-F8.3 — Reimpresión de tiquete con costo (crear y anular)

**Historia**: Como operador, quiero reimprimir un tiquete perdido o dañado cobrando el servicio correspondiente, y poder anular ese cobro si me equivoqué.

**Criterios de aceptación**:
- Given un ingreso identificado por placa **o por cupo/consecutivo (vehículo sin placa, REQ-OPS-197)** y un motivo de ≥10 caracteres, When el operador confirma el cobro vía `<PagoModal>` (monto → método de pago), Then se crea una factura real (`POST /facturacion/factura-servicio`, monto = `costos_servicios` vigente del concepto de reimpresión) y luego `POST /workflows/reimpresion-ticket` con ese `uuid_factura`, y se reimprime el tiquete de entrada con el mismo formato del original.
- Given una reimpresión mal cobrada, When se anula, Then se inserta una fila nueva con `uuid_reimpresion_padre` (nunca `UPDATE` sobre la original) — la anulación afecta solo el registro de workflow, no reversa la factura/pago (ver Ajuste 2026-09-25-c).

**Ajuste 2026-09-25 (directiva del operador)**: la búsqueda no puede exigir el `uuid_ingreso` a mano — debe reutilizar el mismo patrón de resolución placa/consecutivo→`uuid_ingreso` que ya usa `SalidaPanel` (`matchVehiculos` + `VehiculoSuggestions` + `useIngresosActivos`/`getIngresosByPlaca`), para soportar tanto placa como cupo de vehículos sin placa.

**Ajuste 2026-09-25-b (directiva del operador)**: el flujo entero (búsqueda, motivo, cobro, anulación, impresión) vive DENTRO de un drawer/sheet del dashboard (`<ReimprimirTiqueteSheet />`, hotkey **F8** + botón "Facturas" del sidebar) — **no** es una ruta aparte (`/facturacion/reimprimir` se retiró de `App.tsx`). Mismo patrón "thin shell" que `<ArqueoSheet />` envolviendo `pages/ArqueoParcial.tsx`: el shell resuelve open/close/focus-restore vía `useDashboardDrawerStore`, la forma (`pages/ReimprimirTiquete.tsx`) no sabe que está en un Sheet.

**Ajuste 2026-09-25-c (directiva del operador — corrección de alcance)**: snapshotear un costo dentro de `reimpresion_ticket` NO alcanza — la reimpresión tiene que disparar el MISMO flujo de cobro real que la salida de vehículo (monto → método de pago → factura → tiquete de factura), reusando `<PagoModal>` sin fork. Esto reemplaza el diseño anterior (DEC-TKT-04, "uuid_factura opcional, sin crear prod.facturas") por uno que SÍ crea la factura:
  - `useCostoServicioVigente('reimpresion')` (nuevo hook) — preview del costo vigente ANTES de mostrar `<PagoModal>` (`GET /catalogos/costos-servicios?concepto=reimpresion&estado=activo`, filtra `vigente_hasta IS NULL` client-side).
  - `POST /api/v1/facturacion/factura-servicio` (endpoint NUEVO, **no** modifica `POST /facturacion/factura` que ya está en producción con DIAN/FE encima) — factura un servicio suelto ANCLADO a `uuid_ingreso` (no requiere `prod.salidas`; `Facturas.uuid_salida`/`uuid_ingreso` ya son nullable en el modelo). Reusa verbatim el motor de 4-table insert (`crear_factura_evento`/`crear_factura_detalle_bulk`/`crear_factura_impuesto_iva`/`crear_factura_pago`/`build_display_factura`) con `uuid_salida=None`.
  - El `POST /workflows/reimpresion-ticket` ya existente ahora recibe el `uuid_factura` real de la factura recién creada (el campo ya era opcional en el schema, solo no se usaba).
  - `<FacturaDisplayModal>` (reusado tal cual, sin fork) muestra el desglose completo post-cobro, igual que `<PagoSheet>`.
  - **Fuera de alcance, documentado**: no hay plantilla ESC/POS dedicada para el recibo térmico de esta factura de servicio todavía (`ReciboPagoPayload` extiende `SalidaPayload` con campos de vehículo/tiempo parqueado que no aplican a un servicio suelto — fabricarlos imprimiría datos incorrectos). El tiquete de entrada SÍ se reimprime (buffer real). Follow-up: plantilla `'factura_servicio'` dedicada.
  - **Fuera de alcance, decisión explícita**: anular una reimpresión NO reversa el pago/factura (eso es `factura_pagos.reverse_payment`, un flujo aparte).

**Nota de alcance**: este workflow (con costo, tabla `reimpresion_ticket`) es **distinto** de la reimpresión gratuita inmediata de las Fases 6/7 (excepción E3 de CU-15x, "operación ya impresa") — no comparten código ni tabla.

**Tablas ER tocadas**: `reimpresion_ticket` (INSERT en ambos casos), `costos_servicios` (SELECT, snapshot del costo), `facturas`/`factura_detalle`/`factura_impuestos`/`factura_pagos` (carga real del cobro, sin `uuid_salida`).

**Endpoints**: `POST /workflows/reimpresion-ticket`, `POST .../{uuid}/anular` (ambos de HU-F1.11), `POST /facturacion/factura-servicio` (**nuevo**, Ajuste 2026-09-25-c), `GET /catalogos/costos-servicios` (ya existente, reusado para el preview del monto).

**Componentes UI**: `ReimprimirTiqueteSheet` (drawer, thin shell) envolviendo `ReimprimirTiquete` (form con búsqueda por placa o cupo/consecutivo + motivo + `<PagoModal>` reusado + `<FacturaDisplayModal>` reusado); `role="alertdialog"` en el dialog de anulación (consecuencia de cobro).

**Validaciones Zod**: `z.object({ termino: z.string().min(1), motivo: z.string().min(10) })` — `termino` acepta placa o consecutivo, resuelto a `uuid_ingreso` client-side antes de mostrar `<PagoModal>`.

**Manejo de errores**:

| Código | Mensaje/acción en UI |
|---|---|
| validación cliente (Zod `min(10)`) | motivo <10 caracteres → error inline antes de enviar, sin llamar al backend |
| `costo_servicio_no_configurado` | Sin fila vigente en `costos_servicios` para el concepto de reimpresión — el preview client-side ya lo detecta antes de mostrar `<PagoModal>` (banner de error de configuración) |
| `ingreso_no_encontrado` (V1 de `factura-servicio`) | 404 — no debería ocurrir en el flujo normal (el ingreso ya se resolvió en la búsqueda) |
| `voucher_requerido` | datáfono sin referencia — mismo V6 que `create_factura` |

**Componentes UI — props clave**: `ReimprimirTiquete` — `onBuscar(termino)` resuelve `uuid_ingreso`; motivo confirmado abre `<PagoModal uuid_ingreso total_cop={costoVigente} onSubmit={handlePago}>`.

**Pruebas**: `e2e/reimpresion.spec.ts` (stub, `test.skip` — sin backend real en CI) + `tests/unit/test_factura_servicio_create_handler.py` (backend, mock-everything) + `ReimprimirTiquete.test.tsx` (9 casos, incluye el submit real de `<PagoModal>` sin mockear).

**Tamaño estimado**: 210 LOC (original) + ~450 LOC (Ajuste 2026-09-25-c: endpoint nuevo + schema + 2 hooks + 1 api client + rewiring de la página).

**Tareas atómicas**:
- **HU-F8.3-T1**: `src/features/facturacion/pages/ReimprimirTiquete.tsx` (form, búsqueda por placa o cupo/consecutivo vía reuso de `matchVehiculos`/`VehiculoSuggestions` + motivo + `<PagoModal>`) envuelto por `src/features/facturacion/components/ReimprimirTiqueteSheet.tsx` (drawer, hotkey F8).
- **HU-F8.3-T2**: `escposBuilder.build('reimpresion', payload)` (literal verificado en `escposBuilder.ts` — la prosa vieja decía `'reimprimir'`, drift anchor REQ-OPS-175) — mismo formato del tiquete original, con marca visual `0x1B 0x45` (negrita) y etiqueta "REIMPRESIÓN".
- **HU-F8.3-T3**: acción de anulación (llama a `POST .../anular`).
- **HU-F8.3-T4**: `e2e/reimpresion.spec.ts` (stub) + tests unitarios backend/frontend.
- **HU-F8.3-T5** (Ajuste 2026-09-25-c): `POST /facturacion/factura-servicio` (`backend/.../api/v1/facturacion.py::create_factura_servicio` + `schemas/facturacion.py::FacturaServicioCreate`) + `useCostoServicioVigente`/`useRegistrarPagoServicio` (frontend).

### HU-F8.4 — Mostrar factura post-pago con desglose (operador-ve la factura en la UI)

**Historia**: Como operador, después de confirmar un pago (efectivo o datáfono) quiero ver la factura con el desglose completo — placa + minutos, segregación de valores (subtotal + descuento + impuestos + total), datos del cliente, número de recibo, medio de pago — para poder verificar visualmente que el cobro quedó correcto antes de cerrar el drawer.

**Contexto crítico**: este HU cierra el bug silencioso del pago (F8.1-b). Pre-HU-F8.4, `PagoSheet.handleSubmit` mandaba `uuid_ingreso` + `monto_recibido_cents` + `total_cents` + `cliente` al BE, pero `FacturaCreate` (backend `schemas/facturacion.py:578-592`) exige `uuid_salida` + `items[1-50]` + `subtotal` + `total` + `medio_pago` + `referencia` + `fe_con_datos` + `fe_datos_cliente`. El POST debería haber sido 422 — pago "silencioso" sin persistencia. HU-F8.4 corrige el contrato FE→BE (mandar `uuid_salida`) Y enriquece el response con los campos de display (HU-F8.4) para que el modal pueda mostrar el desglose.

**Criterios de aceptación**:
- Given un pago confirmado (rotación o mensualidad), When el BE responde 201, Then se monta `<FacturaDisplayModal />` con el desglose completo y el drawer queda abierto detrás del modal hasta que el operador cierre.
- Given la respuesta del BE, Then el modal muestra: header (número de recibo + fecha/hora), datos de la sucursal (razón social + NIT + dirección + régimen + teléfono), datos del cliente (o "Consumidor final" cuando NULL), placa + minutos parqueados (cuando hay `datos_vehiculo`), líneas de la factura (`items[]`), segregación de valores (`subtotal + descuento + impuestos[] + total`), medio de pago (con vuelto cuando es efectivo + voucher cuando es datáfono), estado DIAN cuando hay `factura_electronica`.
- Given el operador cierra el modal, Then el drawer también se cierra (single close path).
- Given que el POST falla (V4 validaciones, NIT inválido, monto insuficiente), Then el modal NO se monta y el form queda abierto con error inline (comportamiento pre-HU-F8.4 preservado).
- Given que el FE manda `uuid_salida` en el POST body, When el BE valida V1 (salida existe + es facturable), Then el POST 201 persiste con KD-FACT-01 single-commit.

**Tablas ER tocadas** (solo lectura en el modal): `facturas` (subtotal, descuento, total), `factura_detalle` (items), `factura_impuestos` (snapshot + nombre desde `impuestos`), `salidas` (fecha_salida), `ingreso` (placa, fecha_ingreso), `sucursal` + `empresa` (datos emisor), `clientes` (datos cliente), `factura_pagos` (init pago, medio_pago), `factura_electronica` (prefijo, consecutivo, estado_dian, cufe).

**Endpoints**: `POST /api/v1/facturacion/factura` (modificado — response enriquecido con 11 campos nuevos: `medio_pago`, `monto_recibido_cents`, `vuelto_cents`, `voucher`, `numero_recibo`, `cliente`, `datos_sucursal`, `datos_vehiculo`, `impuestos`, `pagos`, `factura_electronica`).

**Componentes UI**: `<FacturaDisplayModal />` (nuevo, `apps/electron-sucursal/src/features/facturacion/components/FacturaDisplayModal.tsx`).

**Validaciones Zod**: `FacturaReadSchema` Zod mirror extendido de 11 → 22 campos en `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts`. `PostFacturaPayload` ahora incluye `uuid_salida` (no `uuid_ingreso`).

**Manejo de errores**:
- 422 (V4 detalle_invalido / V6 total_no_coherente) → form queda abierto con error inline
- 500 (iva_no_configurado) → solo en BE; FE re-lanza el error

**Tests**:
- `apps/electron-sucursal/src/features/facturacion/components/FacturaDisplayModal.test.tsx` (nuevo): render con `factura` null → no muestra, con `factura` populado → muestra todas las secciones
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.test.tsx` (modificado): mock trigger resolve con `FacturaRead` enriquecido → verifica que `setFacturaDisplay` se llama con el resultado

**Pruebas manuales (Chrome DevTools MCP)**:
- Login → ingreso ABC123 → confirmar salida → PagoSheet efectivo → confirmar pago → modal aparece con número de recibo, placa, minutos, subtotal, IVA 19%, total, vuelto. Cerrar modal → drawer cierra también. Verificar consola sin errors/warnings.
- Repetir con datafono (voucher) → modal muestra voucher en lugar de vuelto.
- Repetir con FE activa → modal muestra prefijo+consecutivo, estado_dian='pendiente', cufe NULL.

**Decisiones arquitectónicas**:
- **`numero_recibo` derivado server-side** (no columna nueva). Formato `sucursal-YYYYMMDD-NNNNNN` per plan.md:473. O(N) per emission (COUNT facturas WHERE uuid_sucursal=X AND DATE(created_at)=today()); aceptable para MVP. Column promotion deferred post-MVP si throughput se vuelve bottleneck.
- **`datos_sucursal` requerido** (no nullable) — el modal SIEMPRE muestra datos del emisor (no es opcional). Si falta, BE levanta `RuntimeError` (defensa en profundidad, debería ser imposible).
- **`factura_electronica` nullable** — NULL hasta que cloud-side dispatcher asigne prefijo+consecutivo (HU-F8.2 + cloud-only dispatch). Estado `pendiente` cuando hay fila sin `envio_dian`; `aceptado|rechazado` después.
- **`cliente` nullable** — NULL para consumidor final (NIT `222222222222222` default, DEC-SUC-04). El modal muestra "Consumidor final" cuando NULL.
- **Pagos[] vacío en MVP** — el FE lee `medio_pago` + form values (vueltos/voucher) del PagoModal state. Round-trip extra al BE para los pagos sería over-fetch.
- **`monto_recibido_cents` / `vuelto_cents` NULL en MVP** — el FE ya computa vueltos en `PagoModal.tsx:191-198`. Backend no captura `monto_recibido_cents` del payload todavía (FIX-OPEN: capturar en PR futuro).
- **`tipo='servicio'` hard-coded en `items[]`** (bug pre-existente): `prod.factura_detalle` no tiene columna `tipo` en la DB (verificado con `\d+`); el repo silently dropea el kwarg en `crear_factura_detalle_bulk`. FIX-OPEN: migración Alembic que agregue la columna (out of MVP scope per AGENTS.md §8.2 step 4 — corregir en su propia rama `fix/`).

**Tareas atómicas** (4 work-unit commits en 1 PR):
- **HU-F8.4-T1** (`feat(backend)`): `schemas/facturacion.py` extiende `FacturaRead` con 11 campos nuevos + 6 sub-schemas. `__all__` actualizado.
- **HU-F8.4-T2** (`feat(backend)`): `api/v1/_factura_display.py` nuevo — helper `build_display_factura` joinea 6 queries post-commit. `api/v1/facturacion.py` delega al helper.
- **HU-F8.4-T3** (`feat(apps)`): `facturaApi.ts` Zod mirror extendido (11→22 campos). `PostFacturaPayload` ahora con `uuid_salida`.
- **HU-F8.4-T4** (`feat(apps)`): `<FacturaDisplayModal />` nuevo (8 secciones: emisor, cliente, vehículo, items, totales+impuestos, medio de pago, FE). `PagoSheet.handleSubmit` envía `uuid_salida` + abre el modal post-success.

**Notas de especificación**:
- Migración Alembic: ZERO (FIX-OPEN de columna `tipo` se maneja en cambio separado).
- Sin `size:exception` — estimado total ~700 LOC, dentro del budget de 800 por PR (overrides del operador para F8.x).
- Cierre con merge `--no-ff` a `dev`, push, borrar rama.
- Verificar en DB que la factura persiste con impuestos snapshot + sucursal/cliente/vehículo display.

---

## Fase 9 — Suscripciones y mensualidades operativas (CU-06)

**Objetivo**: el consumo automático de mensualidades en caja (ya cubierto por las Fases 6-7) más la venta y consulta operativa desde sucursal. La gestión CRUD completa de planes/convenios es de administración, no de esta parte.

**Nota de alcance obligatoria**: el CU-06 original describe la creación de una suscripción como una acción de **Administrador** (paso 3 del flujo: "El administrador selecciona 'Nueva suscripción'"), en un flujo de 7 pasos que **no menciona cobro, factura ni FE en ningún punto**. La venta atómica en caja (cliente + vehículos + suscripción + cobro + FE en una sola transacción) que esta fase construye es, por tanto, una **ampliación de producto**, no un requisito literal del corpus — se construye porque es una necesidad operativa real de un parqueadero (vender la mensualidad en el mismo mostrador), pero se declara aquí sin narrarla como si el CU ya la exigiera. Explícitamente **fuera de alcance** de esta fase (y de esta parte): los convenios corporativos B2B (múltiples vehículos, facturación a un tercero, tabla `clientes_b2b`) — el propio CU-06 (BR5, literal) dice que son "un caso de uso aparte que se abordará en una fase posterior".

### HU-F9.1 — Venta de suscripción desde caja

**Historia**: Como operador, quiero vender una mensualidad nueva (cliente + hasta 2 placas + plan + cobro) en un solo flujo guiado, sin dejar datos a medias si algo falla.

**Criterios de aceptación**:
- Given un wizard de 4 pasos (cliente → vehículos → plan → pago), When se completa cada paso, Then se valida antes de avanzar (RHF + Zod por paso).
- Given los datos completos, When se confirma, Then `POST /clientes/venta-suscripcion` crea en una transacción cliente (nuevo o existente) + vehículos (si son placas nuevas) + suscripción + cobertura +, si aplica, factura/pago/FE.
- Given una placa que ya tiene una suscripción vigente, Then `422 suscripcion_duplicada_placa`.
- Given un plan con `mismo_tipo_vehiculo=true`, When las placas son de tipos distintos, Then `422 tipo_vehiculo_incompatible`.
- Given una venta después del día 15 del mes, Then el monto cobrado se prorratea (`valor_dia = plan.valor/duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`), persistido en `factura_detalle` de la factura emitida (adaptación A-09) — no en la fila de suscripción, que no tiene columna para eso.
- **(Ajuste 2026-09-25, identificación persona natural/empresa)** Given el paso 1 (Cliente), When el operador elige "Persona natural", Then se pide tipo de documento (CC/CE/Pasaporte) + número + nombres + apellidos; When elige "Empresa", Then se pide NIT (+DV opcional, validado por módulo 11 si se ingresa) + razón social — a diferencia del checkbox de FE de `PagoModal` (HU-F8.1), este paso NO tiene opción de "cliente genérico": una venta de suscripción siempre exige un cliente real identificado.

**Tablas ER tocadas**: `clientes` (SELECT/INSERT), `vehiculos` (SELECT/INSERT condicional), `subscripciones_cliente` (INSERT), `subscripcion_vehiculos` (INSERT, hasta `cantidad_maxima_vehiculos` del plan), `tipo_subscripciones` (SELECT), `facturas`/`factura_detalle`/`factura_pagos`/`factura_electronica` (INSERT condicional si la venta cobra en el acto).

**Endpoints**: `POST /clientes/venta-suscripcion` (cerrado en HU-F1.12).

**Componentes UI**: `Venta` (page, wizard 4 pasos); `ClienteIdentificacionFields` (Ajuste 2026-09-25, componente compartido con `PagoModal` — Flujo 1 de la directiva de identificación persona/empresa).

**Validaciones Zod**: por paso — `z.object({cliente: {tipo_persona, tipo_identificador, numero_identificacion, dv?, nombre, apellido?}})` (Ajuste 2026-09-25: reemplaza el `{nit, nombre, email}` original — `tipo_identificador` ya no es literal `'NIT'`), `z.object({placas: z.array(z.string()).min(1).max(2)})`, `z.object({uuid_tipo_subscripcion})`, `z.object({medio_pago})`.

**Manejo de errores**:

| Código | Mensaje/acción en UI |
|---|---|
| `suscripcion_duplicada_placa` | Paso 2 del wizard: "Esta placa ya tiene una suscripción vigente", no permite avanzar |
| `tipo_vehiculo_incompatible` | Paso 2: "Este plan exige que todas las placas sean del mismo tipo de vehículo" |
| `cantidad_maxima_excedida` | Paso 2: bloquea agregar más placas de las que el plan permite |

**Componentes UI — props clave**: `Venta` (contenedor, wizard 4 pasos: `paso`, `onAvanzar`, `onConfirmar`).

**Pruebas**: `e2e/suscripcion-venta.spec.ts` — 4 escenarios:

1. Cliente nuevo: se crea `clientes` + `vehiculos` + `subscripciones_cliente` en una sola transacción.
2. Cliente existente: reutiliza la fila de `clientes`, solo agrega la nueva suscripción.
3. Plan con `mismo_tipo_vehiculo=true`: placas de tipos distintos → `422 tipo_vehiculo_incompatible`.
4. Placa ya con suscripción vigente → `422 suscripcion_duplicada_placa`.

**Tamaño estimado**: 400 LOC.

**Tareas atómicas**:
- **HU-F9.1-T1**: `src/features/suscripciones/pages/Venta.tsx` — wizard de 4 pasos con validación por paso.
- **HU-F9.1-T2**: integración de `POST /clientes/venta-suscripcion` con `Idempotency-Key`.
- **HU-F9.1-T3**: mostrar el monto prorrateado en el paso de pago cuando la fecha de venta sea posterior al día 15.
- **HU-F9.1-T4**: `e2e/suscripcion-venta.spec.ts` (4 escenarios).
- **HU-F9.1-T5** (Ajuste 2026-09-25, Flujo 2 de la directiva de identificación persona/empresa — depende de HU-F8.1-T6): paso 1 de `Venta.tsx` reemplaza el input NIT-only por `<ClienteIdentificacionFields>` (componente compartido con `PagoModal`, `src/features/facturacion/components/ClienteIdentificacionFields.tsx`); armado del payload centralizado en `src/features/suscripciones/lib/clienteVentaPayload.ts` (`buildClienteVentaPayload`, función pura — ya no hardcodea `tipo_identificador:'NIT'`); `ventaSuscripcionApi.ts` cambia `tipo_identificador: z.literal('NIT')` por el enum completo. Backend: `uuid_tipo_persona` se resuelve server-side desde `tipo_identificador` vía `repo/tipo_persona.py::resolve_uuid_tipo_persona` (NIT→jurídica, CC/CE/pasaporte→natural), invocado desde `repo/venta_suscripcion.py::buscar_cliente_por_uuid_o_crear_nuevo` — reutilizable por futuros call-sites (ej. cuando `factura.py` empiece a auto-crear clientes) sin duplicar el mapeo.
  - **Bug preexistente encontrado, NO relacionado con este ajuste (no corregido acá, requiere su propia rama)**: `backend/tests/unit/test_venta_suscripcion_handler.py::test_venta_suscripcion_v8_cobro_subchain_calls_helpers_when_cobrar_ahora` falla en `dev` limpio (confirmado con `git stash` antes de tocar código) porque el mock de `session` no expone `refresh`/las queries que consume `_factura_display.py::build_display_factura` (HU-F8.4) — el subchain de cobro V8 en `venta_suscripcion` llega hasta ese helper y el test nunca actualizó su mock cuando F8.4 se integró ahí. Requiere mockear las ~6 queries que `build_display_factura` ejecuta, no es un fix de una línea.
  - **Hallazgo de diseño preexistente (NO introducido por este ajuste, requiere decisión del operador antes de corregir)**: validando en vivo (Chrome DevTools) se confirmó que `buildVentaPayload` (`Venta.tsx`) arma el campo `cliente` del `POST /clientes/venta-suscripcion` **exclusivamente** desde `state.cliente` (los datos del paso 1) — los campos NIT/DV/tipo de documento/nombre/apellido que `<PagoModal>` muestra en el paso 5 (vía `clientePrefill`) son **puramente decorativos** en este flujo: editarlos ahí no cambia el cliente creado ni los datos de la FE (`emitir_factura_electronica` solo viaja como booleano). Verificado reproduciendo con NIT distinto en paso 1 (`901234567`) vs. paso 5 (`800123456`+DV `7`): el cliente persistido en `prod.clientes` quedó con `901234567` (el del paso 1), no con el valor editado en paso 5. La validación de DV módulo 11 del paso 5 SÍ bloquea el submit (`dv debe ser 0-9` / `DV inválido`) sobre un valor que después se descarta — confunde al operador y puede bloquear una venta válida por un DV que no importa. Esto es preexistente (misma arquitectura desde que `<Venta>` empezó a reusar `<PagoModal>`, antes de este ajuste) y su corrección correcta depende de una decisión de producto: (a) ocultar/deshabilitar esos campos en el paso 5 cuando `<PagoModal>` se monta desde `<Venta>` (dejarlos solo de lectura, ya que el cliente real ya quedó fijado en el paso 1), o (b) hacer que `buildVentaPayload` use los valores editados en el paso 5 como fuente de verdad para la FE (requeriría separar "cliente de la suscripción" de "titular de la FE", que hoy el `.mmd`/backend no distinguen — `VentaSuscripcionCreate` solo acepta un `cliente`). Queda ABIERTO para que el operador decida antes de tocarlo.

---

#### Secuencia de flujo — CU-06 Venta de suscripción en caja (ampliación de producto)

```mermaid
sequenceDiagram
    actor Op as Operador
    participant UI as Venta.tsx (wizard 4 pasos)
    participant API as api-sucursal

    Op->>UI: paso 1 — datos de cliente (nuevo o existente)
    UI->>UI: valida Zod (persona/empresa + documento + nombre) antes de avanzar
    Op->>UI: paso 2 — 1 o 2 placas
    Op->>UI: paso 3 — elige plan (tipo_subscripciones vigente)
    Op->>UI: paso 4 — medio de pago
    UI->>API: POST /clientes/venta-suscripcion (Idempotency-Key)
    API->>API: BEGIN — INSERT/UPDATE clientes, INSERT vehiculos (si placa nueva)
    API->>API: valida: placa duplicada, mismo_tipo_vehiculo, cantidad_maxima
    API->>API: INSERT subscripciones_cliente + subscripcion_vehiculos (1-2 filas)
    alt venta después del día 15
        API->>API: calcula monto_proporcional → persiste en factura_detalle
    end
    opt cobrar_ahora=true
        API->>API: INSERT facturas/factura_pagos/factura_electronica (mismo patrón de CU-04)
    end
    API->>API: COMMIT
    API-->>UI: 201 {uuid_subscripcion, fecha_vencimiento, monto_prorrateado?}
    UI->>Op: confirmación + (opcional) tiquete/recibo de la venta
```

---

### HU-F9.2 — Listado, búsqueda por identificación y gestión de cupos (Sheet de sucursal)

**Historia**: Como operador, quiero ver de un vistazo las suscripciones activas de mi sede y, sobre una en particular, poder agregar o quitar vehículos inscritos sin salir del panel de suscripciones.

**Realineado 2026-09-24** (directiva del operador): el diseño original de esta HU vivía en una página aparte (`/suscripciones`, `Listado.tsx` + DataTable) con búsqueda por placa/cliente, y no cubría gestión de cupos post-venta (esa gestión no estaba cubierta en ninguna HU de sucursal — HU-F20.2 en `web_admin` solo cubre validaciones al CREAR la suscripción y el campo `dias_alerta_pre_vencimiento`, no el alta/baja de vehículos de una suscripción ya vendida). Por directiva del operador, el listado + gestión ahora viven DENTRO de `<SuscripcionesSheet />` (ya usado para el flujo de venta, HU-F9.1) como pasos adicionales, y el buscador cambia de placa/cliente a **número de identificación del cliente** — el dato con el que el operador atiende en mostrador. El panel de "por vencer" (top-5 + banner inline) fue relocalizado fuera del kiosko en `feat/ux-remover-suscripciones-vencer` (2026-09-22) y queda fuera del alcance de esta HU.

**Criterios de aceptación**:
- Given el operador abre `<SuscripcionesSheet />` (botón "Suscripción" del Dashboard), Then el paso inicial (`mode='list'`) muestra el listado de suscripciones **activas** de la sucursal actual (`estado='activo' AND fecha_vencimiento >= hoy`), con cliente, plan y fecha de vencimiento.
- Given un campo de búsqueda por número de identificación en ese mismo paso, When el operador escribe un número de identificación y confirma, Then el Sheet avanza a un paso de detalle (`mode='cupos'`) con la suscripción de ese cliente: plan contratado, cupo máximo (`tipo_subscripciones.cantidad_maxima_vehiculos`), vehículos inscritos actualmente y cupos libres.
- Given cupos libres > 0, When el operador agrega una placa nueva, Then el vehículo queda inscrito (INSERT en `subscripcion_vehiculos`) respetando `mismo_tipo_vehiculo` si el plan lo exige — sin cupos libres, la acción se bloquea con 422 antes de tocar la base.
- Given un vehículo ya inscrito, When el operador lo quita, Then se cierra su versión vigente e inserta una nueva con `estado='inactivo'` (bi-temporal, `close_and_insert` — nunca DELETE), liberando un cupo de inmediato en la misma pantalla.
- Given ningún resultado para el número de identificación buscado, Then el Sheet muestra un estado vacío explícito, sin error de red.
- Todo el flujo (listado → búsqueda → cupos) ocurre DENTRO del mismo `<SuscripcionesSheet />`, sin navegar a otra ruta.

**ABIERTO relevante (no resuelto en esta fase, ver cierre de Parte I)**: CU-06 BR4 exige que `dias_alerta_pre_vencimiento` sea editable **por suscripción individual** al crearla; el ER no tiene columna para eso en `subscripciones_cliente` (solo `tipo_sucursal.caracteristicas` admite un default global vía JSON). Esta fase implementa el default global (adaptación A-06 bis / §0.4); el override por suscripción queda como ABIERTO-05.

**Tablas ER tocadas**: `subscripciones_cliente` (R), `subscripcion_vehiculos` (R + INSERT para agregar + `close_and_insert` para quitar), `clientes` (R, búsqueda por `numero_identificacion`), `tipo_subscripciones` (R, `cantidad_maxima_vehiculos`/`mismo_tipo_vehiculo`).

**Endpoints**:
- `GET /clientes/subscripciones-activas` (nuevo, dedicado) — listado branch-scoped de suscripciones activas con plan + cliente + conteo de vehículos inscritos.
- `GET /clientes/subscripciones-activas/buscar?numero_identificacion=X` (nuevo, dedicado — anidado bajo `subscripciones-activas` y no bajo `subscripciones-cliente` a propósito: esa última ya tiene el CRUD genérico montado con `GET /{uuid}`, y `/subscripciones-cliente/buscar` habría colisionado con ese patrón de un solo segmento) — detalle de la suscripción de un cliente con sus vehículos inscritos.
- `POST /clientes/subscripcion-vehiculos/agregar` (nuevo, dedicado) — agrega un vehículo validando cupo y `mismo_tipo_vehiculo` (reutiliza `validar_cantidad_maxima_vehiculos`/`validar_placas_mismo_tipo_vehiculo`/`crear_subscripcion_vehiculos_bulk` de `repo/venta_suscripcion.py`).
- `PUT /clientes/subscripcion-vehiculos/{uuid}/quitar` (nuevo, dedicado) — **no** se puede reutilizar el PUT genérico de `router_factory`: `SubscripcionVehiculosUpdate` (schemas/clientes.py) no expone `estado` como campo, así que nunca podría viajar `estado="inactivo"` en el payload. El endpoint dedicado llama `versioned.close_and_insert(session, SubscripcionVehiculos, current_uuid=uuid, new_attrs={"estado": "inactivo"}, actor_uuid=...)` directamente — `close_and_insert` carga el resto de columnas desde la fila vigente (confirmado en `repo/versioned.py`), así que solo `estado` cambia.

**Componentes UI**: `SuscripcionesSheet` (agrega `mode: 'buscar' | 'cupos'` a los existentes `'list' | 'venta'`), `useSuscripcionesActivas` (hook, reemplaza el roto `useSuscripcionesList` — pegaba a `/clientes/suscripciones`, endpoint inexistente), `useBuscarSuscripcionPorIdentificacion`, `useAgregarVehiculoSuscripcion`, `useQuitarVehiculoSuscripcion`.

**Manejo de errores**: 422 `cantidad_maxima_excedida`; 422 `tipo_vehiculo_incompatible`; sin resultados de búsqueda → estado vacío explícito (no es error).

**Pruebas**: unit (vitest) por hook + componente nuevo/tocado; validación funcional con Chrome DevTools contra la API real (login operador, agregar/quitar vehículo, confirmar en Postgres). e2e Playwright queda fuera de esta iteración.

**Tamaño estimado**: ~320 LOC (backend + frontend).

**Tareas atómicas**:
- **HU-F9.2-T1**: Backend — router dedicado `clientes_cupos.py` con los 4 endpoints nuevos (mirror de `clientes_venta.py`).
- **HU-F9.2-T2**: Backend — tests de integración (pytest) para cupo excedido, tipo mixto, agregar y quitar.
- **HU-F9.2-T3**: `useSuscripcionesActivas` (reemplaza `useSuscripcionesList`).
- **HU-F9.2-T4**: `useBuscarSuscripcionPorIdentificacion`, `useAgregarVehiculoSuscripcion`, `useQuitarVehiculoSuscripcion`.
- **HU-F9.2-T5**: `SuscripcionesSheet.tsx` — pasos `buscar`/`cupos`.

---

## Fase 10 — Arqueos de caja y cierre diario (CU-10)

**Objetivo**: los 3 flujos reales que CU-10 describe, mapeados al dominio real del catálogo `tipo_arqueo` (no a los nombres en mayúsculas del corpus de flujo, que no son los valores sembrados en base de datos).

**Mapeo de nomenclatura obligatorio** (dominio real del catálogo `tipo_arqueo`, no los nombres en mayúsculas del corpus de flujo):

| Flujo del CU-10 original | `tipo_arqueo.codigo` real | Cierra sesión | HU que lo implementa |
|---|---|---|---|
| "Arqueo Parcial (Auditoría)" | `auditoria` | No | HU-F10.1 |
| "Cierre Parcial (TURNO)" | `cierre_turno` | Sí, la sesión del turno | HU-F10.2 |
| "Cierre Total (Diario)" | `cierre_dia` (adaptación A-07, 4º valor sembrado en HU-F1.13) | Sí, todas las sesiones del día | HU-F10.3 |
| *(sin flujo en el CU-10 original)* | `cierre_sesion` | — | Sin implementar (ABIERTO-04: hipótesis — cierre ejecutado por un supervisor distinto del titular del turno, coherente con `sesion.uuid_usuario_cierre`) |

### HU-F10.1 — Arqueo parcial (auditoría, sin cierre)

**Historia**: Como operador o supervisor, quiero contar la caja en cualquier momento del turno sin cerrarlo, y que el sistema me diga si hay diferencia.

**Criterios de aceptación**:
- Given `/caja/arqueo-parcial`, Then muestra la base configurada al inicio del **arqueo** (no necesariamente `sesion.valor_inicial_efectivo` fijo — la base pudo reconfigurarse entre la apertura del turno y este momento, BR1 literal de CU-10) más los pagos del período, agrupados por `medio_pago`.
- Given el conteo físico ingresado, Then se muestra la diferencia en vivo; si `|diferencia| > 0`, se **advierte** (no bloquea) y pide justificación.
- Given la confirmación, When `POST /caja/arqueo` con `uuid_tipo_arqueo` de `codigo='auditoria'`, Then `200` y el arqueo queda registrado sin cerrar ninguna sesión.
- Given `|diferencia| > tolerancia`, Then se crea una alerta `descuadre_critico`.

**Regla de negocio — reconciliación obligatoria de fórmula**: CU-10 BR2 define `descuadre_pct = ((reportado - esperado) / esperado) * 100` (fórmula porcentual), pero el ER real (`configuracion_tolerancias.tolerancia_efectivo`/`tolerancia_datafono`) define la tolerancia como **monto absoluto**, no porcentaje. Se resuelve así: el porcentaje se muestra en la UI como dato informativo adicional junto al monto, pero la decisión de disparar o no la alerta se basa **siempre** en el monto absoluto contra `configuracion_tolerancias` — nunca en el porcentaje.

**Tablas ER tocadas**: `sesion` (SELECT, base vigente), `factura_pagos` (SELECT, suma por medio de pago — nunca `UPDATE`, los pagos son inmutables), `configuracion_tolerancias` (SELECT), `arqueo` (INSERT), `alerta` (INSERT condicional).

**Endpoints**: `POST /caja/arqueo` (cerrado en HU-F1.13).

**Componentes UI**: `ArqueoParcial` (page, form + diferencia en vivo).

**Validaciones Zod**: `z.object({ valor_efectivo_reportado: z.number(), valor_datafono_reportado: z.number(), justificacion: z.string().optional() })`, con refinamiento: si `|diferencia| > 0`, `justificacion` se vuelve requerida en el envío final (aunque el CU la trata como opcional, la UI la exige cuando hay diferencia, coherente con la advertencia).

**Manejo de errores**:

| Situación | Comportamiento |
|---|---|
| `|diferencia| > 0` sin justificación | **Advertencia**, no bloqueo — CU-10 E2 literal: "el sistema advierte antes de confirmar, no bloquea" |
| `sesion_ya_cerrada` (`409`) | No aplica a este arqueo (parcial no cierra sesión); solo relevante en HU-F10.2 |

**Componentes UI — props clave**: `ArqueoParcial` — `sesionActual`, `esperado`, `onConfirmar(reportado, justificacion?)`.

**Pruebas**: `e2e/arqueo.spec.ts` — 3 escenarios:

1. Arqueo sin diferencia: `reportado == esperado`, sin justificación, sin alerta.
2. Arqueo con diferencia dentro de tolerancia: justificación opcional, advertencia visible pero no bloqueante.
3. Arqueo con descuadre mayor a la tolerancia absoluta configurada: alerta `descuadre_critico` generada.

**Tamaño estimado**: 260 LOC.

**Tareas atómicas**:
- **HU-F10.1-T1**: `src/features/caja/pages/ArqueoParcial.tsx` con form + diferencia en vivo (informativa en % y determinante en monto absoluto).
- **HU-F10.1-T2**: integración `POST /caja/arqueo` con `uuid_tipo_arqueo` de código `auditoria`.
- **HU-F10.1-T3**: `bridge.imprimir(escposBuilder.build('arqueo', payload))` — tiquete de arqueo con totales.
- **HU-F10.1-T4**: `e2e/arqueo.spec.ts` (3 escenarios).

---

### HU-F10.2 — Cierre de turno

**Historia**: Como operador, quiero cerrar mi turno con un arqueo obligatorio, dejando mi sesión formalmente cerrada.

**Criterios de aceptación**: Given el arqueo con `codigo='cierre_turno'`, When se confirma (justificación **obligatoria** si hay diferencia — a diferencia del arqueo parcial, aquí no es solo advertencia), Then `sesion.timestamp_cierre`/`uuid_usuario_cierre` se completan y `estado='cerrada'`; `factura_pagos` no se modifica en ningún momento (los pagos son inmutables, confirmado literal por CU-10).

**Tablas ER tocadas**: `arqueo` (INSERT), `sesion` (`UPDATE` de cierre — una de las dos únicas tablas con `UPDATE` real permitido en todo el sistema).

**Endpoints**: `POST /caja/arqueo` (con `codigo='cierre_turno'`), `PUT /caja-sesion/sesion/{uuid}/cerrar`.

**Componentes UI**: `CerrarTurno` (page, arqueo inline + cierre; completa el placeholder de HU-F3.3).

**Manejo de errores**: `409 sesion_ya_cerrada` (de HU-F1.3).

**Pruebas**: incluido en `e2e/turno.spec.ts` (Fase 3) y `e2e/arqueo.spec.ts`.

**Tamaño estimado**: 160 LOC.

**Tareas atómicas**:
- **HU-F10.2-T1**: completar `CerrarTurno.tsx` con el arqueo real (`codigo='cierre_turno'`, justificación obligatoria si hay diferencia).
- **HU-F10.2-T2**: encadenar `POST /caja/arqueo` → `PUT /sesion/{uuid}/cerrar` en una sola confirmación de UI.

---

#### Secuencia de flujo — CU-10 Arqueo y cierre (los 3 flujos reales, mapeados al dominio real)

```mermaid
sequenceDiagram
    actor Op as Operador/Supervisor
    participant UI as ArqueoParcial / CerrarTurno / CierreDiario
    participant API as api-sucursal

    Op->>UI: abre arqueo (parcial, cierre de turno o cierre de día)
    UI->>API: GET base vigente + pagos del período (por sesión o por día)
    API-->>UI: valor_esperado por medio de pago
    Op->>UI: ingresa conteo físico reportado
    UI->>UI: calcula diferencia (monto absoluto Y % informativo)
    alt diferencia ≠ 0
        alt codigo='auditoria' (parcial)
            UI->>Op: advierte, justificación opcional
        else codigo='cierre_turno' | 'cierre_dia'
            UI->>Op: exige justificación (obligatoria)
        end
    end
    Op->>UI: confirma
    UI->>API: POST /caja/arqueo {uuid_tipo_arqueo, valor_*_reportado, justificacion}
    API->>API: INSERT arqueo (nunca UPDATE; factura_pagos permanece inmutable)
    alt |diferencia| > configuracion_tolerancias (monto absoluto)
        API->>API: INSERT alerta (tipo_alerta='descuadre_critico')
    end
    alt codigo='cierre_turno'
        API->>API: UPDATE sesion SET estado='cerrada', timestamp_cierre, uuid_usuario_cierre
    else codigo='cierre_dia'
        API->>API: UPDATE sesion (todas las abiertas del día) SET estado='cerrada'
    end
    API-->>UI: 201 {uuid_arqueo, diferencia, alerta_generada}
    UI->>Op: confirmación + tiquete de arqueo
```

---

### HU-F10.3 — Cierre diario

**Historia**: Como operador o supervisor, quiero cerrar todas las sesiones del día de una vez, con el resumen agregado de la jornada.

**Criterios de aceptación**: Given el sheet de cierre diario (ver ajuste 2026-09-25 abajo), Then `GET /caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD` muestra el resumen por sesión (cajero, apertura/cierre, base, esperado, reportado, diferencia, justificado); When se confirma, Then `POST /caja/arqueo` con `codigo='cierre_dia'` y `uuid_sesion=NULL`, y se cierran todas las sesiones abiertas del día.

**Ajuste 2026-09-25 (directiva del operador)**: "cierre diario no debe estar en una ruta aparte, debe estar en un sheet dentro de `/` como todas las demás funcionalidades". Se retira la ruta `/caja/cierre-diario` de `App.tsx`; `CierreDiario` (el form real, sin cambios de contenido) ahora se monta dentro de `<CierreDiarioSheet />` (thin shell, mismo patrón que `<ArqueoSheet />`/`<CerrarTurnoSheet />`), abierta desde el mismo botón del sidebar vía `useDashboardDrawerStore.open('cierre-diario-multi', ...)`. Ancho del sheet: 50% del viewport (`md:w-1/2` default), contenido centrado en `max-w-xl`.

**Ajuste 2026-09-25-b (directiva del operador)**: se unificó el hotkey F6 con este mismo sheet. Existía un kind viejo `'cierre-diario'` (`<CierreDiarioDialog />`) — cierre rápido per-session — CONFIRMADO como código muerto (`DrawerHost` lo montaba con `uuid_sucursal`/`uuid_sesion` siempre `null`, su submit nunca hacía nada); era la implementación vieja de este mismo "cierre diario". Se retiró por completo (componente borrado) y F6 ahora abre `'cierre-diario-multi'`, igual que el botón del sidebar.

**Tablas ER tocadas**: `arqueo` (INSERT, `uuid_sesion=NULL`), `sesion` (`UPDATE` masivo de cierre, filtrado por sucursal + rango del día).

**Endpoints**: `GET /caja/arqueo/resumen`, `POST /caja/arqueo` (ambos de HU-F1.13).

**Componentes UI**: `CierreDiarioSheet` (drawer, thin shell) envolviendo `CierreDiario` (form, resumen + totales).

**Pruebas**: `e2e/cierre-diario.spec.ts` — cierre con 3 sesiones (2 ya cerradas + 1 abierta).

**Tamaño estimado**: 200 LOC.

**Tareas atómicas**:
- **HU-F10.3-T1**: `src/features/caja/pages/CierreDiario.tsx` con resumen + form.
- **HU-F10.3-T2**: `e2e/cierre-diario.spec.ts`.

---

## Fase 11 — Estado de sincronización y alertas operativas (CU-07 vista del operador, CU-14)

**Objetivo**: lo que el operador ve y hace respecto a la sincronización (nunca el motor de sincronización en sí, que es transversal y corre en `job-sync-sucursal`, fuera de esta app) y el panel de alertas operativas.

### HU-F11.1 — Indicador de estado de sincronización (navbar)

**Historia**: Como operador, quiero ver de un vistazo si mi sede está sincronizando bien con la nube, sin tener que interpretar logs.

**Realineado 2026-09-24** (REQ-OPS-171, AD-3/AD-4/AD-5): esta funcionalidad vivió primero como un banner fijo arriba de toda la página (por encima incluso del navbar del Dashboard) — el operador reportó que esa franja tapaba contenido sin aportar valor en ese lugar. Por su directiva, la misma funcionalidad ahora vive integrada en el badge "Online" del header del Dashboard (`SyncStatusBadge`), con el detalle real en un tooltip. No es una sección nueva: es la realineación de esta misma HU.

**Criterios de aceptación**:
- Given `GET /sync/estado?uuid_sucursal=X` (cada 30 s), Then el indicador del navbar cambia de color (verde = sync al día en la última hora, amarillo = retrasos menores, rojo = sync fallida o más de 1 hora sin sincronizar, gris neutro = sucursal sin sincronizar nunca) — mismos umbrales que usa CU-14 para clasificar el estado por sucursal — y el tooltip al pasar el mouse/enfocar muestra el detalle (`lag_seg`/`pendientes`).
- Given que `api-status` (Fase 2) falla 3 veces consecutivas, Then un banner **distinto** y persistente (`<LocalApiDownBanner />`) indica "Sin conexión con API local" — no debe confundirse con el indicador de sincronización hacia la nube (son dos problemas distintos: uno es la API local de la propia sede, otro es el enlace de esa sede hacia la nube).

**Tablas ER tocadas** (solo lectura): `sync_log`, `sync_queue`.

**Endpoints**: `GET /sync/estado` (cerrado en HU-F1.14).

**Componentes UI**: `SyncStatusBadge` (badge + tooltip Radix dentro del header de `<Dashboard />`; anuncio a lectores de pantalla vía `role="status"` + `aria-live="polite"` en un `span` `sr-only` separado, *polling* cada 30 s propio del componente, no solo del hook).

**Pruebas**: `e2e/sync-status-badge.spec.ts` — 4 escenarios:

1. Verde: `lag_seg` bajo, sync dentro de la última hora.
2. Amarillo: retrasos menores (lag por encima del umbral, pero sin fallos consecutivos).
3. Rojo: sync fallida o más de 1 hora sin sincronizar.
4. "Sin conexión con API local": `api-status` falla 3 veces consecutivas, banner persistente distinto del indicador de sync hacia la nube.

**Tamaño estimado**: 190 LOC.

**Tareas atómicas**:
- **HU-F11.1-T1**: `src/features/sync/components/SyncStatusBadge.tsx` con color por `lag_seg` y `pendientes`.
- **HU-F11.1-T2**: *polling* SWR `refreshInterval: 30_000`.
- **HU-F11.1-T3**: indicador separado de "Sin conexión con API local" (Zustand, contador de fallos consecutivos de `api-status`).
- **HU-F11.1-T4**: `e2e/sync-status-badge.spec.ts` (4 escenarios).

---

### HU-F11.2 — Panel de alertas locales

**Historia**: Como operador, quiero ver las alertas activas de mi sede, entender de qué se trata cada una y marcarlas como revisadas cuando corresponda.

**Criterios de aceptación**:
- Given `GET /workflows/alerta?uuid_sucursal=X&estado=abierta` (endpoint corregido en HU-F1.1), Then el panel lateral muestra las alertas activas con `JOIN` a `alert_types` (código, descripción, severidad).
- Given las 11 alertas de negocio sembradas (HU-F1.14), Then todas son visibles y filtrables por tipo/severidad, con el detalle exacto de la siguiente tabla:

| Código | Descripción | Severidad | Disparador |
|---|---|---|---|
| `descuadre_critico` | Descuadre en arqueo mayor al umbral configurado | alta | CU-10 al cerrar arqueo |
| `sync_fallida` | 3 o más intentos de sync fallidos en 30 minutos | alta | CU-07 |
| `capacidad_agotada` | Sucursal con `disponible=0` por más de 30 minutos | media | Job cada 5 min |
| `capacidad_agotada_forzado` | Operador forzó un ingreso con capacidad en 0 | media | CU-01 |
| `evento_no_procesado` | Evento en `sync_queue` por más de 24 horas sin ACK | alta | Job cada 1h |
| `impresora_caida` | Impresora no responde en 3 o más intentos | alta | Job local cada 5 min |
| `fe_error_toppoint` | FE en estado rechazado por timeout del proveedor TopPoint | alta | CU-05 |
| `numeracion_toppoint_agotada` | Consecutivo de la resolución vigente agotado | alta | CU-05 |
| `cache_desactualizado` | Cache local con más de 1 hora sin sync | baja | CU-07 |
| `arqueo_pendiente_24h` | Salida `PENDIENTE_PAGO` por más de 24 horas | media | Job cada 1h |
| `suscripcion_proxima_vencer` | Suscripción vigente vence en ≤ `dias_alerta_pre_vencimiento` días | media | Job diario + verificación en CU-01/02/03 |

Los 8 códigos técnicos ya sembrados (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) **no** se muestran en este panel de sucursal (ABIERTO-06): son monitoreo técnico interno/administración.
- Given una alerta, When se expande, Then hace drill-down al objeto origen (arqueo, FE, suscripción, etc., vía `uuid_arqueo` u otro dato disponible en la fila).
- Given que el operador marca una alerta como revisada, Then se inserta una **fila nueva** con `uuid_alerta_padre` apuntando a la original y `estado='resuelta'` (modelo append-only del ER real, DEC-SUC-25) — nunca un `UPDATE` de un campo booleano `revisada`, pese a que CU-14 BR1 lo describa en esos términos: el ER es la fuente de verdad de implementación en caso de conflicto.

**Tablas ER tocadas**: `alerta` (SELECT + INSERT de la fila de transición), `alert_types` (JOIN).

**Endpoints**: `GET /workflows/alerta?uuid_sucursal=X&estado=abierta` (corregido en HU-F1.1).

**Componentes UI**: `AlertasPanel` (lista de alertas activas, drill-down por click).

**Manejo de errores**: N/A directo (el 500 que este endpoint producía antes de HU-F1.1 queda cerrado en Fase 1; esta HU asume el endpoint ya corregido).

**Pruebas**: `e2e/alertas-panel.spec.ts` — las 11 alertas de negocio visibles y filtrables; click hace drill-down; marcar como revisada inserta fila nueva (verificado contra el backend, no solo contra el estado local de UI).

**Tamaño estimado**: 210 LOC.

**Tareas atómicas**:
- **HU-F11.2-T1**: `src/components/AlertasPanel.tsx` con lista + filtros (tipo/severidad).
- **HU-F11.2-T2**: acción "marcar como revisada" que llama al endpoint de transición (nunca un `PUT`/`PATCH` sobre la fila original).
- **HU-F11.2-T3**: `e2e/alertas-panel.spec.ts` (2 escenarios).

---

## Fase 12 — Reportería local mínima ("Mi turno", subset de CU-09)

**Objetivo**: el subconjunto de reportería que el operador necesita ver de su propio turno, sin construir el módulo completo de reportería/analítica (CU-09 completo es de administración).

### HU-F12.1 — Panel "Mi turno"

**Historia**: Como operador, quiero ver un resumen de mi turno actual (ingresos, salidas, total cobrado por medio de pago) sin salir de la pantalla principal.

**Criterios de aceptación**:
- Given una sesión abierta, When se muestra el panel, Then aparecen KPIs: cantidad de ingresos, cantidad de salidas, total cobrado, desglose por medio de pago (efectivo/datáfono).
- Given el botón "Cerrar turno", When se presiona, Then navega a `/caja/cerrar-turno` (Fase 10).
- Given que el turno lleva 0 operaciones, Then los KPIs muestran 0 en vez de ocultarse o mostrar un estado de error.
- Given una nueva operación (ingreso, salida o pago) durante el turno, Then los KPIs se actualizan sin necesidad de recargar la pantalla (mismo patrón de *polling*/SWR que el resto de la app).

**Tablas ER tocadas** (solo lectura): `ingreso`, `salidas`, `factura_pagos` (agregado por `uuid_sesion`).

**Endpoints**: `GET /operacion/mi-turno?uuid_sesion=X` (nuevo, backend agrega esta suma).

**Componentes UI**: `MiTurnoPanel` (cards de KPI).

**Pruebas**: `e2e/mi-turno.spec.ts` — KPIs visibles, cierre desde el panel.

**Tamaño estimado**: 180 LOC.

**Tareas atómicas**:
- **HU-F12.1-T1**: **Backend**: `GET /operacion/mi-turno?uuid_sesion=X` con las sumas por medio de pago.
- **HU-F12.1-T2**: `src/features/operacion/components/MiTurnoPanel.tsx` con las KPIs.
- **HU-F12.1-T3**: `e2e/mi-turno.spec.ts` (2 escenarios).

---

## Anexos de referencia rápida

### Anexo A — Endpoints consolidados de esta parte

| Método | Ruta | Estado | Fase que lo cierra | Fase(s) que lo consumen |
|---|---|---|---|---|
| GET | `/workflows/alerta` | Corregido (bug `vigente_desde`) | F1 (HU-F1.1) | F11 |
| GET | `/workflows/anulaciones` | Corregido | F1 (HU-F1.1) | — |
| GET | `/workflows/reclamos` | Corregido | F1 (HU-F1.1) | — |
| GET | `/workflows/reimpresion-ticket` | Corregido | F1 (HU-F1.1) | F8 |
| GET | `/auth/me` | Nuevo | F1 (HU-F1.2) | F3 |
| POST | `/auth/login` | Modificado (cookie + lockout) | F1 (HU-F1.2) | F3 |
| GET | `/usuarios/{uuid}/login` | Nuevo | F1 (HU-F1.2/F1.15) | — |
| GET | `/caja-sesion/sesion/me` | Nuevo | F1 (HU-F1.3) | F3 |
| POST | `/caja-sesion/sesiones` | Modificado (409) | F1 (HU-F1.3) | F3 |
| PUT | `/caja-sesion/sesion/{uuid}/cerrar` | Modificado (409) | F1 (HU-F1.3) | F3, F10 |
| GET | `/empresa/tarifas-sucursal` | Modificado (`vigente_en`) | F1 (HU-F1.4) | F4 |
| GET | `/operacion/ocupacion` | Nuevo | F1 (HU-F1.5) | F4 |
| GET | `/catalogos/tipos-vehiculo` | Existente | — | F4 |
| POST | `/operacion/ingresos` | Modificado (validaciones) | F1 (HU-F1.6) | F6 |
| GET | `/operacion/ingresos?placa=X&activo=true` | Existente | — | F6 |
| POST | `/operacion/salidas` | Nuevo | F1 (HU-F1.7) | F7 |
| POST | `/operacion/salidas/mensualidad` | Nuevo | F1 (HU-F1.7) | F7 |
| GET | `/operacion/cotizar` | Nuevo | F1 (HU-F1.8) | F7 |
| POST | `/facturacion/factura` | Nuevo | F1 (HU-F1.9) | F8 |
| POST | `/facturacion/factura-pagos` | Nuevo | F1 (HU-F1.9) | F8 |
| POST | `/facturacion/factura-electronica` | Nuevo | F1 (HU-F1.10) | F8 |
| GET | `/facturacion/factura-electronica/{uuid}` | Nuevo | F1 (HU-F1.10) | F8 |
| POST | `/facturacion/factura-electronica/{uuid}/reintentar` | Nuevo | F1 (HU-F1.10) | F8 |
| GET | `/documentos?uuid_sucursal=X&tipo=certificado` | Existente | — | F6 (póliza RC en tiquete) |
| POST | `/workflows/reimpresion-ticket` | Nuevo | F1 (HU-F1.11) | F8 |
| POST | `/workflows/reimpresion-ticket/{uuid}/anular` | Nuevo | F1 (HU-F1.11) | F8 |
| POST | `/facturacion/factura-servicio` | Nuevo (ajuste 2026-09-25-c) | — | F8 (HU-F8.3 consume) |
| POST | `/clientes/venta-suscripcion` | Nuevo | F1 (HU-F1.12) | F9 |
| POST | `/caja/arqueo` | Nuevo | F1 (HU-F1.13) | F10 |
| GET | `/caja/arqueo/resumen` | Nuevo | F1 (HU-F1.13) | F10 |
| GET | `/sync/estado` | Nuevo | F1 (HU-F1.14) | F11 |
| GET | `/operacion/mi-turno` | Nuevo | F12 (HU-F12.1) | F12 |

### Anexo B — Inventario de páginas y organismos por fase

| Fase | Páginas (contenedoras) | Organismos/moléculas propios |
|---|---|---|
| F3 | `Login`, `AbrirTurno`, `CerrarTurno` | `LoginForm`, `Topbar` |
| F4 | — | `OcupacionStrip`, `TarifaBadge` |
| F6 | `Principal` | `PlacaInput`, `ForzarIngresoModal`, `TiqueteModal` |
| F7 | `SalidaFlow`, `SalidaMensualidad` | `CotizacionPanel` |
| F8 | `FacturaDetalle`, `ReimprimirTiquete` | `PagoModal` |
| F9 | `Venta`, `Listado` (suscripciones) | banner de vencimiento próximo (inline en `Principal`) |
| F10 | `ArqueoParcial`, `CierreDiario` (completa `CerrarTurno` de F3) | — |
| F11 | — | `SyncStatusBadge`, `AlertasPanel` |
| F12 | — | `MiTurnoPanel` |

### Anexo C — Mapa de fases, historias y tareas atómicas (resumen)

| Fase | HUs | Tareas atómicas | LOC estimado |
|---|---|---|---|
| F1 — Prerrequisitos de backend | 15 | 47 | ~3.170 |
| F2 — Andamiaje Electron | 3 | 22 | ~1.600 |
| F3 — Autenticación y turno | 3 | 12 | ~580 |
| F4 — Catálogos y ocupación | 3 | 9 | ~480 |
| F5 — Impresión térmica | 2 | 8 | ~600 |
| F6 — Ingreso vehicular + CU-15E | 2 | 12 | ~700 |
| F7 — Salida y tarifa + CU-15S/SM | 3 | 12 | ~780 |
| F8 — Cobro, FE y reimpresión | 3 | 12 | ~810 |
| F9 — Suscripciones | 2 | 7 | ~620 |
| F10 — Arqueos y cierre diario | 3 | 8 | ~620 |
| F11 — Sync y alertas | 2 | 7 | ~400 |
| F12 — Reportería local | 1 | 3 | ~180 |
| **Total** | **42 HU** | **~159 tareas atómicas** | **~10.540 LOC** |

### Anexo D — Catálogo consolidado de códigos de error

Todo error de esta parte sigue el contrato estándar del backend: `HTTPException(detail={"error": "<codigo>", ...})`. Este anexo reúne, en un solo lugar, los códigos que aparecen repartidos en las fases anteriores, para que un desarrollador no tenga que buscarlos HU por HU al implementar el manejo global de errores del cliente (`parkosFetch`).

| Código | HTTP | Fase de origen | Significado |
|---|---|---|---|
| `invalid_credentials` | 401 | F1/F3 | Email o contraseña incorrectos (mensaje único, anti-enumeración) |
| `account_locked` | 429 | F1/F3 | Bloqueo por intentos fallidos, con `retry_after_seconds` |
| `sesion_ya_abierta` | 409 | F1/F3 | El usuario ya tiene un turno abierto |
| `sesion_ya_cerrada` | 409 | F1/F3/F10 | Se intenta cerrar o arquear una sesión ya cerrada |
| `placa_formato_invalido` | 422 | F1/F6 | La placa no matchea ningún regex de tipo activo |
| `motivo_forzado_requerido` | 422 | F1/F6 | Ingreso forzado sin motivo de ≥10 caracteres |
| `ingreso_activo_existente` | 409 | F1/F6 | Ya existe un ingreso activo para la placa (deriva a salida, no es error visible) |
| `salida_duplicada` | 409 | F1/F7 | El ingreso ya tiene una salida no anulada |
| `mensualidad_no_vigente` | 400 | F1/F7 | Se llamó al endpoint de salida-mensualidad sin mensualidad vigente |
| `cotizacion_expirada` | 410 | F1/F7 | El cálculo de CU-02 superó los 15 minutos de vigencia |
| `ingreso_no_encontrado` | 404 | F1/F7 | No hay ingreso activo para la placa buscada |
| `iva_no_configurado` | 500 | F1/F7 | No existe IVA vigente en `impuestos` — error de configuración |
| `nit_invalido` | 422 | F1/F8 | Falla la validación de módulo 11 |
| `email_invalido` | 422 | F1/F8 | Email no cumple RFC 5322 (solo con datos propios del cliente) |
| `voucher_requerido` | 400 | F1/F8 | Datáfono sin referencia de voucher |
| `monto_insuficiente` | 400 | F1/F8 | Efectivo recibido menor al total a pagar |
| `numeracion_agotada` | 409 | F1/F8 | Rango de la resolución de facturación agotado |
| `reintento_no_permitido` | 409 | F1/F8 | Se intenta reintentar una FE que no está en `rechazado` |
| `suscripcion_duplicada_placa` | 422 | F1/F9 | La placa ya tiene una suscripción vigente |
| `tipo_vehiculo_incompatible` | 422 | F1/F9 | El plan exige mismo tipo de vehículo y las placas difieren |
| `cantidad_maxima_excedida` | 422 | F1/F9 | Se envían más placas que las que el plan permite |
| `justificacion_requerida` | 400 | F1/F10 | Diferencia de arqueo sin justificación en un cierre (obligatoria, a diferencia del parcial) |
| `costo_servicio_no_configurado` | 500 | F1/F8 | No hay costo vigente en `costos_servicios` para el concepto de reimpresión |
| `not_found` | 404 | transversal | Recurso inexistente (contrato genérico de FastAPI) |
| `printer_offline` | — (IPC, no HTTP) | F5 | La impresora térmica no responde; dispara la cola de reintento local |

### Anexo E — Rutas de la aplicación

| Ruta | Página | Protegida por permiso | Fase |
|---|---|---|---|
| `/login` | `Login` | — (pública) | F3 |
| `/` | `Principal` | `operador-` autenticado | F6 |
| `/caja/abrir-turno` | `AbrirTurno` | `operador-` autenticado | F3 |
| `/caja/cerrar-turno` | `CerrarTurno` | `operador-` autenticado | F3/F10 |
| `/caja/arqueo-parcial` | `ArqueoParcial` | `realizar_arqueo` | F10 |
| `/` (sheet `cierre-diario-multi`) | `CierreDiarioSheet` → `CierreDiario` | `realizar_arqueo` | F10 (ruta retirada 2026-09-25, directiva del operador) |
| `/salida/:uuidIngreso` | `SalidaFlow` | `operador-` autenticado | F7 |
| `/salida-mensualidad/:uuidIngreso` | `SalidaMensualidad` | `operador-` autenticado | F7 |
| `/facturacion/factura/:uuid` | `FacturaDetalle` | `operador-` autenticado | F8 |
| `/facturacion/reimprimir` | `ReimprimirTiquete` | `emitir_reimpresion` | F8 |
| `/suscripciones` | `Listado` | `operador-` autenticado | F9 |
| `/suscripciones/nueva` | `Venta` | `operador-` autenticado | F9 |

### Anexo F — Definición de Hecho (DoD) por fase

| Fase | DoD |
|---|---|
| F1 | Los 18 gaps + el bug de `router_factory` cerrados; `alembic check` sin drift; `pytest` verde en los módulos tocados. |
| F2 | `npm run dev`/`build` sin errores; `tsc --noEmit` limpio en los 3 tsconfigs; smoke e2e con 0 violaciones axe-core. |
| F3 | Login, lockout y turno funcionales de punta a punta contra el backend real (no mocks) en al menos un entorno de desarrollo. |
| F4 | Detección de placa, tarifas y ocupación consumibles con datos reales de al menos una sucursal de prueba. |
| F5 | Impresión física verificada contra al menos un modelo de impresora térmica real (no solo mock USB). |
| F6 | Flujo de ingreso completo, incluida la impresión automática del tiquete con QR, verificado en papel. |
| F7 | Flujo de salida (rotación y mensualidad) completo; tiquete de salida impreso después del pago, verificado en papel. |
| F8 | Pago + FE + reimpresión funcionando contra el backend real; al menos una FE aceptada de punta a punta en un entorno de pruebas de TopPoint. |
| F9 | Venta de suscripción atómica probada con cliente nuevo y existente; alerta de vencimiento visible. |
| F10 | Los 3 flujos de arqueo (parcial, cierre de turno, cierre de día) probados con al menos un caso de descuadre real. |
| F11 | Banner de sync y panel de alertas mostrando datos reales de al menos una sucursal con historial de eventos. |
| F12 | Panel "Mi turno" verificado con datos de un turno real completo (apertura, operaciones, cierre). |

### Anexo G — Checklist maestro de aceptación (una fila por HU)

Lista de verificación para que quien coordine la ejecución de esta parte pueda marcar el avance HU por HU, sin tener que releer cada sección para saber si "está listo":

- [ ] HU-F1.1 — `router_factory` corregido; `GET /workflows/alerta` responde 200 sin `AttributeError`.
- [ ] HU-F1.2 — `/auth/me`, cookie `httpOnly` y lockout real funcionando contra el backend.
- [ ] HU-F1.3 — constraint de sesión única + `/sesion/me` con los 3 casos de prueba en verde.
- [ ] HU-F1.4 — `vigente_en` filtrando tarifas correctamente en fechas pasadas/futuras.
- [ ] HU-F1.5 — `mv_ocupacion_diaria` refrescando cada 10s y endpoint de ocupación exponiéndola.
- [ ] HU-F1.6 — las 4 validaciones de ingreso (regex, suscripción, cupo, duplicado) con los 8 tests en verde.
- [ ] HU-F1.7 — `POST /operacion/salidas` y `.../mensualidad` con índice único parcial funcionando.
- [ ] HU-F1.8 — `calcular_cotizacion` con los 3 escenarios fiscales correctos.
- [ ] HU-F1.9 — factura transaccional con rollback verificado ante fallo simulado.
- [ ] HU-F1.10 — numeración FE + reintento encadenado verificado.
- [ ] HU-F1.11 — reimpresión con costo + anulación (cadena `uuid_reimpresion_padre`).
- [ ] HU-F1.12 — venta de suscripción atómica con los 4 casos de prueba en verde.
- [ ] HU-F1.13 — arqueo + `cierre_dia` sembrado + resumen diario.
- [ ] HU-F1.14 — `/sync/estado` + 19 tipos de `alert_types` sembrados (8 técnicos + 11 de negocio).
- [ ] HU-F1.15 — histórico de login paginado.
- [ ] HU-F2.1 — scaffold compila, `npm run dev`/`build` sin errores, 14 componentes shadcn generados.
- [ ] HU-F2.2 — `parkosFetch` con los 14 escenarios MSW en verde; `authStore` persistiendo solo lo permitido.
- [ ] HU-F2.3 — auto-update, single-instance y kiosko probados manualmente al menos una vez.
- [ ] HU-F3.1 — login real con `email`+`password` contra el backend, sin ningún rastro de `cedula` como credencial.
- [ ] HU-F3.2 — countdown de lockout visible y decreciente en pantalla.
- [ ] HU-F3.3 — abrir/cerrar turno con constraint de sesión única verificado en UI.
- [ ] HU-F4.1 — detección de placa sin tolerancia de tipeo, 6 tests unitarios en verde.
- [ ] HU-F4.2 — tarifas vigentes con fallback a cache cuando la API local falla.
- [ ] HU-F4.3 — strip de ocupación con colores correctos y sin fugas de `AbortController`.
- [ ] HU-F5.1 — impresión física verificada, P95 <500ms medido, offline no crashea.
- [ ] HU-F5.2 — `escposBuilder` con los 5+ fixtures de bytes ESC/POS correctos.
- [ ] HU-F6.1 — flujo de ingreso íntegro con los 5 escenarios e2e en verde.
- [ ] HU-F6.2 — tiquete de entrada con los 17 campos (15+QR+logo) impreso en papel real.
- [ ] HU-F7.1 — búsqueda tolerante y cotización con countdown de 15 min funcionando.
- [ ] HU-F7.2 — salida rotación y mensualidad con idempotencia verificada.
- [ ] HU-F7.3 — tiquete de salida impreso **después** del pago (no antes), verificado en papel.
- [ ] HU-F8.1 — pago con los 6 escenarios e2e en verde, incluida validación de NIT real.
- [ ] HU-F8.2 — estado de FE visible con *polling* y reintento funcional.
- [ ] HU-F8.3 — reimpresión con costo + anulación probadas de punta a punta.
- [ ] HU-F9.1 — venta de suscripción atómica con prorrateo correcto tras el día 15.
- [ ] HU-F9.2 — banner de vencimiento con el texto literal exacto visible.
- [ ] HU-F10.1 — arqueo parcial con tolerancia por monto absoluto (no porcentaje) verificada.
- [ ] HU-F10.2 — cierre de turno con justificación obligatoria si hay diferencia.
- [ ] HU-F10.3 — cierre diario cerrando todas las sesiones abiertas del día.
- [ ] HU-F11.1 — banner de sync con los 4 estados (verde/amarillo/rojo/sin conexión local).
- [ ] HU-F11.2 — panel de alertas con los 11 códigos de negocio visibles y filtrables.
- [ ] HU-F12.1 — panel "Mi turno" con KPIs correctos verificados contra un turno real.

### Anexo H — Reglas de negocio citadas por CU (referencia rápida, ya reconciliadas)

| CU | Regla | Valor/enunciado exacto |
|---|---|---|
| CU-01 | BR1 | Placa siempre en MAYÚSCULAS (almacenada e impresa) |
| CU-01 | BR2 | Autodetección por regex es la única fuente válida; sin override manual; sin tolerancia de tipeo (DEC-SUC-22) |
| CU-01 | BR3 | UUID del ingreso inmutable, nunca se reutiliza ni tras anular |
| CU-01 | BR4 | La anulación no elimina el ingreso; se registra en `anulaciones` (`tipo_anulable='ingreso'`) |
| CU-01 | BR5 | Auto `^[A-Z]{3}[0-9]{3}$`; Moto `^[A-Z]{3}[0-9]{2}[A-Z]$` |
| CU-01 | BR6 | Las 2 placas de una mensualidad deben ser del mismo tipo de vehículo |
| CU-02 | BR1 | Tiempo = `(fecha_salida - fecha_ingreso)`, redondeado hacia arriba |
| CU-02 | BR2 | Tarifa vigente al momento del cobro, no del ingreso |
| CU-02 | BR3 | El cálculo es idempotente |
| CU-02 | BR4 | Tarifa plena máxima por día aplica entre las 00:00 y las 23:59 hora local Colombia |
| CU-02 | BR5 | IVA se consulta de `impuestos` vigente; sin IVA vigente, error de configuración |
| CU-03 | BR1 (corregido) | El monto **no** se persiste en `salidas` (sin columna `valor`); viaja en memoria de UI hasta que CU-04 lo persiste en `facturas`/`factura_detalle`/`factura_impuestos` (DEC-SUC-23) |
| CU-03 | BR2 | Si la salida se anula sin pagar, se reactiva el ingreso y se vuelve a descontar el cupo |
| CU-03M | BR1 | Solo vehículos con mensualidad activa y vigente |
| CU-03M | BR2 (2026-09-24) | 2da placa simultánea de la MISMA suscripción en patio: plan personal (`cantidad_maxima_vehiculos<=2` o sin configurar) → paga como ROTACIÓN completa (bugfix, restaura la intención de migration 0038, regresada silenciosamente por 0046-0049); plan empresa/flota (`cantidad_maxima_vehiculos>2`) → sigue sin cobro, igual que la 1era placa (directiva del operador, no estaba en el corpus original) |
| CU-03M | BR3 (2026-09-24) | Toda salida sin cobro por mensualidad (BR1 o el brazo "empresa" de BR2) genera de todas formas una factura completa (interna + FE DIAN) mostrando el desglose fiscal íntegro + una línea de descuento por el mismo valor, netando `total=0` (`medio_pago='suscripcion'`) — directiva del operador, ver "Factura por mensualidad ($0)" en el glosario |
| CU-04 | BR1 | SIEMPRE se genera FE; no existe camino "sin FE" |
| CU-04 | BR2 | FE a consumidor final por defecto, NIT `222222222222222` |
| CU-04 | BR3 | Email opcional a consumidor final, obligatorio con datos propios del cliente |
| CU-04 | BR4 | Numeración estrictamente secuencial por sucursal, sin saltos |
| CU-04 | BR5 | El pago se completa aunque la FE falle técnicamente; la FE se reintenta después |
| CU-04 | BR6 | Datáfono = voucher manual, sin integración SDK en MVP |
| CU-05 | BR1 (reconciliado) | Numeración real vía `assign_consecutivo`; la rama `SIM-YYYY-MM-DD-NNNNNN` no se implementa (condición de fallback ya superada) |
| CU-05 | BR2 | FE `aceptado` no se edita ni anula; corrección solo vía nota crédito (diferido a fase 2) |
| CU-05 | BR3 | Nunca se omite la FE; cada pago genera una |
| CU-05 | BR4 | Cola de envío FIFO estricto |
| CU-06 | BR1 | La mensualidad aplica por placa, no por cliente |
| CU-06 | BR2 | Duración = `fecha_vencimiento - fecha_inicio_cobertura` |
| CU-06 | BR3 | Prorrateo tras el día 15, persistido en `factura_detalle` de la venta (adaptación A-09) |
| CU-06 | BR4 | `dias_alerta_pre_vencimiento` editable por suscripción individual — solo parcialmente resuelto (ABIERTO-05: esta parte implementa un default global) |
| CU-06 | BR5 | Convenios B2B fuera de alcance de esta parte (fase posterior) |
| CU-07 | BR1 | Idempotencia garantizada por UUID v4 en cada evento |
| CU-07 | BR2 | Backoff exponencial 1-2-4-8-16-32-64-128-256-300s (tope 5 min) |
| CU-07 | BR3 | Evento sin procesar 24h → fallo permanente + alerta `evento_no_procesado` |
| CU-10 | BR1 | La base usada es la configurada al inicio del **arqueo**, no necesariamente `sesion.valor_inicial_efectivo` fijo |
| CU-10 | BR2 (reconciliado) | El % de descuadre se muestra informativo; la alerta se decide siempre por monto absoluto contra `configuracion_tolerancias` |
| CU-10 | BR3 | Un cambio de base durante la jornada no afecta arqueos ya cerrados |
| CU-10 | BR4 | El cierre no modifica `factura_pagos`; los pagos son inmutables |
| CU-14 | BR1 (reconciliado) | Modelo append-only del ER (nunca `UPDATE` de un flag `revisada`); "marcar revisada" inserta fila hija con `estado='resuelta'` |
| CU-14 | BR2 | Una alerta revisada se mantiene en histórico, pero se filtra del badge activo |
| CU-14 | BR3 | El estado de sync (verde/amarillo/rojo) se calcula en tiempo de consulta, nunca se persiste |
| CU-15E/S/SM | BR1 | Datos de encabezado fijos desde configuración de sucursal (nombre, NIT, régimen, póliza RC, horario) |
| CU-15E/S/SM | BR2 | La tarifa aplicada depende de sucursal + tipo de vehículo, resuelta en CU-01/CU-02 |

### Anexo I — Tablas del ER tocadas por esta parte (impacto por tabla)

Referencia inversa a las tablas de cada HU: útil para saber, ante un cambio futuro de una tabla del ER, qué fases de esta parte se verían afectadas.

| Tabla ER | Operación principal | HU(s) que la tocan |
|---|---|---|
| `ingreso` | INSERT (insert-only) | F1.6, F6.1 |
| `salidas` | INSERT + único `UPDATE estado='PAGADO'` | F1.7, F1.9, F7.2, F8.1 |
| `vehiculos` | INSERT condicional | F1.6, F1.12, F6.1, F9.1 |
| `subscripciones_cliente` | INSERT | F1.12, F9.1 |
| `subscripcion_vehiculos` | INSERT | F1.12, F9.1 |
| `cantidad_vehiculos_sucursal` | SELECT (vía vista, nunca `UPDATE` de columna mutable) | F1.5, F1.6, F1.7, F4.3 |
| `tarifas_sucursal` | SELECT | F1.4, F1.8, F4.2, F6.2, F7.3 |
| `impuestos` | SELECT | F1.8, F7.1 |
| `tipos_vehiculo` | SELECT | F1.6, F4.1, F6.1 |
| `sucursal` | SELECT | F6.2, F7.3 |
| `documentos` | SELECT (póliza RC, logo) | F6.2, F7.3 |
| `usuarios` | SELECT | F1.2, F6.2, F7.3 |
| `login` | INSERT (cada intento) + SELECT (histórico) | F1.2, F1.15 |
| `sesion` | INSERT + `UPDATE` de cierre (una de las 2 tablas con `UPDATE` real permitido) | F1.3, F3.3, F10.2, F10.3 |
| `configuracion_seguridad` | SELECT | F1.2 |
| `configuracion_tolerancias` | SELECT | F1.13, F10.1 |
| `facturas` | INSERT | F1.9, F8.1 |
| `factura_detalle` | INSERT | F1.9, F1.12, F8.1, F9.1 |
| `factura_impuestos` | INSERT | F1.9, F8.1 |
| `factura_pagos` | INSERT + SELECT (arqueo, nunca `UPDATE`) | F1.9, F1.13, F8.1, F10.1 |
| `factura_electronica` | INSERT | F1.10, F1.12, F8.1, F8.2 |
| `envio_dian` | INSERT (cloud-only, nunca escrita directamente por sucursal) | F1.10 (lectura vía vista) |
| `resolucion_facturacion` | SELECT (lock `FOR UPDATE` en `assign_consecutivo`) | F1.10 |
| `clientes` | SELECT/INSERT condicional | F1.9, F1.12, F8.1, F9.1 |
| `reimpresion_ticket` | INSERT (workflow) | F1.11, F8.3 |
| `costos_servicios` | SELECT | F1.11, F8.3 |
| `arqueo` | INSERT (insert-only) | F1.13, F10.1, F10.2, F10.3 |
| `tipo_arqueo` | SELECT + siembra de `cierre_dia` | F1.13, F10.1-F10.3 |
| `alerta` | SELECT + INSERT (workflow append-only) | F1.6, F1.13, F11.2 |
| `alert_types` | siembra (19 tipos) | F1.14 |
| `sync_queue` | SELECT | F1.14, F11.1 |
| `sync_log` | SELECT | F1.14, F11.1 |
| `mv_ocupacion_diaria` (vista) | SELECT | F1.5, F4.3 |
| `anulaciones` | SELECT | F1.1, F1.7, F7.1, F7.2 |
| `reclamos` | SELECT (lectura corregida por HU-F1.1) | F1.1 |
| `tipo_subscripciones` | SELECT | F1.12, F9.1 |

### Anexo J — Comandos de desarrollo de referencia

| Comando | Dónde | Qué hace |
|---|---|---|
| `npm run dev` | `apps/electron-sucursal` | Levanta Vite (renderer) + esbuild watch (main/preload) |
| `npm run build` | `apps/electron-sucursal` | Compila `dist/`, `out/main`, `out/preload.js` |
| `npm run package` | `apps/electron-sucursal` | Empaqueta binarios con `electron-builder` |
| `npm run test` | `apps/electron-sucursal` | Corre Vitest (unit + integración) |
| `npx playwright test` | `apps/electron-sucursal` | Corre los specs e2e (incluye axe-core) |
| `npm run lint` / `npm run typecheck` | `apps/electron-sucursal` | ESLint / `tsc --noEmit` |
| `uv run uvicorn parkos_core.main:app --reload` | `backend/packages/parkos_core` | Levanta `api-sucursal` local en `:8000` |
| `uv run alembic upgrade head` | `backend/packages/parkos_core` | Aplica migraciones pendientes |
| `uv run alembic upgrade --sql <revision>` | `backend/packages/parkos_core` | Dry-run de una migración (revisar antes de aplicar) |
| `uv run pytest -q --cov` | `backend/packages/parkos_core` | Corre la suite de tests backend con cobertura |
| `uv run ruff check . && uv run mypy src/` | `backend/packages/parkos_core` | Lint + chequeo de tipos estricto |
| `docker compose -f infra/deploy/docker-compose.branch.yml up -d` | raíz del repo | Levanta Postgres + servicios de sucursal en modo desarrollo local |

---

## Riesgos y decisiones abiertas de Sucursal

### Riesgos

| ID | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| **RIESGO-SUC-01** | Si Fase 1 (lockout real) se retrasa, la app quedaría expuesta a fuerza bruta de login sin bloqueo efectivo. | Media | Alto | No exponer `web_sucursal` en producción hasta que HU-F1.2 esté cerrada y probada. |
| **RIESGO-SUC-02** | La vista materializada de ocupación (*polling* 10 s) puede mostrar cupo desactualizado en momentos de alta rotación simultánea (varios ingresos/salidas en el mismo segundo). | Media | Medio | Monitorear el lag real de refresh en campo; reducir el intervalo si la sede tiene alta rotación. |
| **RIESGO-SUC-03** | Confusión operativa entre la reimpresión gratuita inmediata (E3 de CU-15x) y el workflow de reimpresión con costo (Fase 8) — un operador podría usar el botón equivocado. | Media | Bajo | Etiquetado visual claro y distinto entre ambos botones/flujos; capacitación breve. |
| **RIESGO-SUC-04** | Un bug en la validación de NIT módulo 11 bloquearía la emisión de FE con datos del cliente. | Baja | Alto | Suite de tests con NIT reales colombianos (incluido el caso de referencia `800.123.456-7`) antes de habilitar el checkbox de FE con datos propios en producción. |
| **RIESGO-SUC-05** | Un antivirus de Windows marca el instalador/binario Electron como sospechoso por falta de firma reconocida. | Media | Medio | Firma de código (Azure Trusted Signing) + empaquetado NSIS `perMachine` — tratado en la parte del instalador, pero condiciona cuándo esta app puede distribuirse. |
| **RIESGO-SUC-06** | `api-sucursal` cae por ser un servicio Windows sujeto a fallos de infraestructura de la sede. | Baja | Crítico | NSSM con auto-restart (parte del instalador); del lado de esta app, el banner "Sin conexión con API local" (Fase 11) avisa de inmediato al operador en vez de dejarlo operar a ciegas. |
| **RIESGO-SUC-07** | Certificado de firma de código (EV/Trusted Signing) no está listo antes del primer despliegue real. | Alta | Alto | Iniciar el trámite de Azure Trusted Signing con antelación (semanas, no días) — condición de bloqueo para el primer release de producción. |
| **RIESGO-SUC-08** | Impresoras térmicas económicas (clones Xprinter) con dialectos ESC/POS incompletos (fuentes/códigos de barra limitados) fallan con el builder genérico. | Media | Medio | Tabla `printer_profiles` (excepción explícita y documentada al ER, no tabla oculta) con matriz de compatibilidad inicial: Epson TM-T20/TM-T88 (referencia), Xprinter XP-58/80 (validar), Star TSP100/143 (puede requerir driver StarPRNT propio, no ESC/POS puro). |
| **RIESGO-SUC-09** | En macOS, la impresora USB requiere entitlements específicos que si faltan bloquean el acceso al dispositivo. | Alta (solo macOS) | Alto | `entitlements.mac.plist` + `hardenedRuntime:true` (HU-F5.1). |
| **RIESGO-SUC-10** | El lock de single-instance queda huérfano tras un crash, impidiendo reabrir la app. | Baja | Bajo | Verificar proceso vivo asociado al lock en `userData` al arrancar, no solo la existencia del archivo. |
| **RIESGO-SUC-11** | El modo kiosko puede evadirse con conocimiento técnico suficiente (task manager, combinaciones no cubiertas). | Baja | Bajo | Aceptado como *best effort*; un MDM completo queda fuera de alcance de esta parte. |
| **RIESGO-SUC-12** | El backend cae al secreto JWT de desarrollo hardcodeado si el instalador no provisiona `PARKOS_JWT_KEY_PATH` correctamente, comprometiendo la seguridad del login de esta app. | Media | Crítico | Gate de instalación (parte del instalador) que rechaza continuar si detecta el fallback de desarrollo; esta app no puede detectar esto por sí sola, pero depende de que ese gate exista antes de ir a producción. |
| **RIESGO-SUC-13** | Sin gate de compatibilidad, el auto-update de Electron (independiente) podría dejar al renderer llamando a una versión de `api-sucursal` incompatible tras una actualización parcial. | Media | Alto | Ver ABIERTO-08 — candidato de decisión para verificar `api_contract_version` en `GET /health` antes de habilitar funciones nuevas. |
| **RIESGO-SUC-14** | Reordenar la impresión del tiquete de salida para después del pago (DEC-SUC-27) cambia un hábito operativo previo (imprimir antes de cobrar). | Baja | Bajo | Mensaje visible en pantalla ("el tiquete se imprime al confirmar el pago") + capacitación breve al desplegar. |

### Decisiones abiertas

| ID | Decisión pendiente | Recomendación |
|---|---|---|
| **ABIERTO-01** | Contenido exacto del QR del tiquete de entrada — CU-01 exige QR en su postcondición de éxito, ningún CU-15x lo especifica. | Folio (UUID del ingreso) + placa, ambos ya disponibles al imprimir, sin tabla ni columna nueva. |
| **ABIERTO-02** | Relación entre la numeración del recibo de pago (`sucursal-YYYYMMDD-NNNNNN`) y el consecutivo DIAN de la FE (`prefijo`+`consecutivo`) — el corpus las usa como si fueran independientes sin decirlo explícitamente. | Mantenerlas independientes: el recibo es un documento interno de caja, la FE es el documento fiscal; no hay obligación DIAN de que coincidan. |
| **ABIERTO-03** | Un solo canal de auto-actualización (`latest`, DEC-SUC-18) vs. canal `beta` para clientes piloto, mencionado en documentos hermanos del instalador sin reconciliar. | Mantener un solo canal en esta primera versión (ya decidido); revisar junto con la parte del instalador si el negocio necesita pilotos controlados. |
| **ABIERTO-04** | El valor real `cierre_sesion` de `tipo_arqueo` no tiene flujo correspondiente en el CU-10 original. Hipótesis: cierre ejecutado por un supervisor distinto del titular del turno (coherente con `sesion.uuid_usuario_cierre`). | Confirmar la hipótesis con negocio antes de construir cualquier UI específica para ese valor; hasta entonces, queda sembrado en el catálogo pero sin flujo propio. |
| **ABIERTO-05** | CU-06 BR4 exige `dias_alerta_pre_vencimiento` editable por suscripción individual; el ER solo admite un default global (`tipo_sucursal.caracteristicas`), sin columna por fila en `subscripciones_cliente`. | Aceptar el default global en esta parte (documentado como desviación explícita del BR4); si el negocio insiste en el override por suscripción, requiere una excepción de ER (columna nueva) aprobada explícitamente por el dueño del modelo. |
| **ABIERTO-06** | Coexistencia de los 8 códigos técnicos de `alert_types` ya sembrados con los 11 códigos de negocio que exige CU-14 — ¿se muestran juntos al operador o se separan por audiencia? | Mostrar en el panel de sucursal (Fase 11) solo los 11 códigos de negocio; los 8 técnicos quedan para monitoreo interno/administración. |
| **ABIERTO-07** | CU-06 BR3 (prorrateo tras el día 15) no aclara si aplica también a renovaciones de una suscripción existente o solo a altas nuevas. | Aplicar solo a altas nuevas hasta que el negocio confirme el tratamiento de renovaciones. |
| **ABIERTO-08** | Sin gate de compatibilidad de versión entre el auto-update de Electron (independiente) y la actualización del backend (vía instalador), puede haber una ventana de incompatibilidad tras una actualización parcial de la sede. | Candidato de decisión: Electron valida un campo `api_contract_version` en `GET /health` y pausa la habilitación de funciones nuevas hasta confirmar compatibilidad — a coordinar con la parte del instalador. |


## PARTE II — CONSTRUCCIÓN DE WEB_ADMIN

### Sección 0 — Visión y arquitectura de `web_admin`

#### 0.1 Qué es y para quién

`web_admin` es la consola cloud multi-sucursal del sistema de parqueaderos. Es una PWA (React + Vite) que corre contra `api-admin` (despliegue cloud de `parkos_core`, `PARKOS_DEPLOY=cloud`) y PostgreSQL como fuente de verdad. A diferencia de la terminal de sucursal (Electron, offline-first, una sola sede por instalación), `web_admin` siempre tiene conectividad, opera sobre datos ya sincronizados desde todas las sedes, y su unidad de navegación es "selecciona una sucursal en el selector superior" en vez de "esta terminal ES la sucursal".

Para quién: el administrador de la operación (parametriza sucursales, tarifas, catálogos, usuarios), el supervisor/auditor (audita arqueos, bitácora, cadena de hashes), y cualquier actor con rol de negocio que el catálogo de `usuarios.rol` acepte (Usuario, Facturador, Supervisor, Administrador, Auditor, Desarrollo — ver §0.3, DEC-ADM-03). No hay "cajero" en `web_admin`: la venta puntual, el cobro y la impresión de tiquetes ocurren en `web_sucursal`; aquí solo se configura lo que la sucursal consume y se audita lo que la sucursal produjo.

Alcance de esta Parte II: 8 casos de uso —CU-06 (mantenimiento, no venta puntual), CU-07 (lado admin: monitoreo + pairing), CU-08, CU-09, CU-10 (lado admin: solo auditoría), CU-11, CU-12, CU-13, CU-14 (lado admin: reglas + vista consolidada)— más las brechas de backend que el admin necesita para funcionar de verdad.

#### 0.2 Arquitectura

**Stack verificado contra el repositorio real** (`apps/web_admin/package.json`, leído directo, no asumido de ningún plan previo):

| Pieza | Versión real | Nota |
|---|---|---|
| React | 18.3.1 | — |
| Vite | 5.4.8 | — |
| TypeScript | 5.6.2 | strict |
| Tailwind CSS | 3.4.13 | — |
| react-router-dom | 6.27.0 | — |
| SWR | 2.2.5 | **es el fetcher realmente usado** (`Dashboard.tsx` lo importa y lo consume; `swr-mutate-on-switch.ts` también) |
| @tanstack/react-query | 5.59.0 | presente en `package.json`, **0 imports en `src/`** (verificado con grep). Dependencia muerta. |
| zustand | 5.0.0 | presente en `package.json`, **0 imports en `src/`** (verificado con grep). Dependencia sin usar todavía — no muerta: se activa en esta Parte II para `authStore`/`tenantStore`. |
| react-hook-form | 7.53.0 | sin uso aún; se activa en Fase 14+ para formularios |
| zod | 3.23.8 | idem |
| @radix-ui/react-select, class-variance-authority, tailwind-merge, tailwindcss-animate | — | base de un patrón shadcn/ui ya iniciado (`components/ui/button.tsx`, `BranchSelector.tsx` usa Radix Select directo) |
| i18next / react-i18next | 23.15.2 / 15.0.2 | ya configurado (`src/i18n/index.ts`), un solo locale `es-CO`, un solo namespace `translation` |
| lucide-react | 0.453.0 | iconos, ya usado en `BranchSelector` |
| vite-plugin-pwa | 0.20.5 | presente pero sin configurar en `vite.config.ts` (no verificado uso real) |
| @axe-core/playwright, @playwright/test | 4.10.0 / 1.48.0 | devDependencies, e2e + accesibilidad ya en el toolchain |

**Decisión**: se descarta cualquier plan que hable de "SWR2 vs react-query" como debate abierto — SWR ya es la librería en producción del código real. `@tanstack/react-query` se elimina de `package.json` por dependencia muerta (DEC-ADM-01).

**Topología real** (verificada contra los routers montados en `api/v1/__init__.py` y contra `dian/cloud_router.py`, no asumida):

```mermaid
flowchart LR
    subgraph Cloud
        WA["web_admin (PWA)"]
        APIA["api-admin\nparkos_core, PARKOS_DEPLOY=cloud"]
        PG[("PostgreSQL\nfuente de verdad")]
        DIAN["proveedor DIAN\n(URL única por env var)"]
        WA -->|"/api/v1, Bearer admin-"| APIA
        APIA --> PG
        APIA -->|"envio_dian"| DIAN
    end
    subgraph Sucursal["Cada sucursal (N instancias)"]
        WS["web_sucursal (Electron)"]
        APIS["api-sucursal\nparkos_core, PARKOS_DEPLOY=branch"]
        WS --> APIS
    end
    APIS <-->|"/sync/pull, /sync/push,\n/sync/heartbeat, /sync/pair"| APIA
    WA -.->|"emite pairing token"| APIS
```

**Qué ya existe y se reutiliza tal cual (verificado archivo por archivo, no por lo que dice ningún plan anterior):**

| Archivo | Estado real verificado | Reutilización |
|---|---|---|
| `src/lib/fetch.ts` (`parkosFetch`) | Envía `Authorization: Bearer <token>` (leído de `localStorage['parkos.auth.token']`) + `X-Sucursal-Context` (de `sucursal-context.tsx`). **Sin** retry, **sin** refresh en 401, **sin** `Idempotency-Key`. | Se extiende (Fase 13), no se reescribe desde cero. |
| `src/lib/sucursal-context.tsx` (`SucursalProvider`/`useSucursal`) | Context de React (no Zustand) con `selected: string \| null` persistido en `localStorage['parkos.lastSelectedSucursal']`. `getSucursalHeader()` es un reader no-React ya usado por `parkosFetch`. | Se mantiene como está para el MVP; no hace falta reescribirlo a Zustand ni a una cascada empresa→sucursal (ver DEC-ADM-02: no existe multiempresa real en el backend hoy). |
| `src/lib/swr-mutate-on-switch.ts` (`useInvalidateOnBranchSwitch`) | Invalida las claves SWR del dashboard de la sucursal anterior y la nueva al cambiar selección. Funciona. | Se generaliza a cualquier clave dependiente de sucursal (Fase 13). |
| `src/components/branch-selector/BranchSelector.tsx` | Radix UI `Select` real, con `data-testid`, WCAG (`aria-label`, foco visible), alimentado por `GET /api/v1/sucursales`. Funciona correctamente hoy — **no tiene el bug de cascada que un plan previo alegó** (no existe cascada empresa→sucursal en absoluto, ni falta: hoy hay una sola empresa). | Se reutiliza sin cambios en Fase 13; se le añade solo lo que falta (loading state, empty state ya cubierto). |
| `src/pages/Dashboard.tsx` | Ya consume `GET /api/v1/admin/me` y `GET /api/v1/admin/sucursales/{uuid}/dashboard` reales con SWR, con 3 `MetricCard` (ingresos, facturas, alertas abiertas) y selección de sucursal persistida. Es un dashboard real y funcional, no un placeholder vacío. | Se extiende con más KPIs y gráficas (Fase 17), no se descarta. |
| `src/pages/Login.tsx` | **Sí es un placeholder real** (sin formulario, solo texto). | Se reemplaza (Fase 13). |
| `src/App.tsx` | 2 rutas (`/login`, `/dashboard`), sin `ProtectedRoute`, cualquiera puede navegar a `/dashboard` sin sesión. | Se reescribe (Fase 13). |

**Qué falta de verdad (confirmado por lectura directa del código, no por suposición):**

1. **`authStore`**: no existe ningún store de autenticación. El token vive en funciones sueltas (`setAuthToken`/`getAuthToken` en `fetch.ts`). No hay noción de "usuario actual" en memoria ni de permisos cargados.
2. **Refresh transparente en 401**: `parkosFetch` no intercepta 401 ni llama a `POST /auth/refresh` (que sí existe en el backend).
3. **Guard de rutas**: no hay `ProtectedRoute`; cualquiera con la URL entra a `/dashboard`.
4. **Docker/serving para cloud**: no existe ningún `Dockerfile` ni configuración de despliegue para `apps/web_admin` en `infra/` (verificado con búsqueda exhaustiva). El único `docker-compose.branch.yml` real en el repo es de la terminal de sucursal.

**Capas (mismo principio que `web_sucursal`, adaptado a que aquí no hay Electron ni SQLite):**

```
apps/web_admin/src/
├── features/{auth,parametrizacion,usuarios,reporteria,arqueos,alertas,sync,pairing,workflows,clientes,auditoria}/
│   ├── pages/          # contenedores: hooks de datos + composición
│   ├── components/     # presentacional puro, recibe props, sin fetch
│   └── hooks/          # useXxxData con SWR
├── components/          # compartido entre features (DataTable, TimelineVersiones, KpiCard, charts/)
├── components/ui/       # primitivos shadcn (ya iniciado: button.tsx)
├── lib/
│   ├── fetch.ts         # parkosFetch (se extiende)
│   ├── authStore.ts     # NUEVO — Zustand
│   ├── sucursal-context.tsx  # se mantiene
│   ├── schemas/         # Zod espejo de los schemas Pydantic reales
│   ├── validation/      # NIT módulo 11, email, etc.
│   └── export/          # csv.ts, pdf.ts
├── routes/              # ProtectedRoute
└── i18n/locales/es-CO/{common,auth,dashboard,parametrizacion,...}.json
```

Principios: **feature-first** (una carpeta por dominio, no por tipo de archivo salvo lo verdaderamente compartido), **container/presentational** (`pages/` hacen fetch y orquestan estado, `components/` solo reciben props), **atomic design** aplicado de forma pragmática (átomos = `components/ui`, moléculas = `components/` compartidos como `DataTable`/`KpiCard`, organismos = `features/*/components`, páginas = `features/*/pages`). Formularios: React Hook Form + Zod, con los mismos criterios de validación que el backend (para no duplicar reglas divergentes: NIT módulo 11, email RFC 5322). Data fetching: SWR, una clave por recurso + contexto de sucursal cuando aplica, invalidación explícita al cambiar de sucursal (patrón ya iniciado en `swr-mutate-on-switch.ts`). Seguridad: Bearer JWT en `localStorage` (no hay cookie httpOnly en el backend real; no se inventa una migración a cookies que el backend no soporta — ver DEC-ADM-06), refresh transparente en 401, rutas protegidas, permisos verificados en cliente solo para UX (el backend es la autoridad real vía `require_permission`).

#### 0.3 Decisiones de arquitectura (`DEC-ADM-01` a `DEC-ADM-20`)

> Numeración propia de esta Parte II, arrancando en 1. Varias corrigen explícitamente decisiones erróneas que circulaban en el material previo (marcado "corrige" cuando aplica).

| ID | Decisión | Motivo |
|---|---|---|
| **DEC-ADM-01** | Fetcher único: **SWR** (ya en producción). Se elimina `@tanstack/react-query` de `package.json` por dependencia muerta (0 imports verificados). Se activa `zustand` (ya en `package.json`, sin uso) para `authStore`. | Evitar dos librerías de datos remotos conviviendo sin motivo; aprovechar una dependencia ya instalada en vez de sumar otra. |
| **DEC-ADM-02** *(corrige)* | **No existe** un modelo de tenancy de 4 niveles (`global/empresa/sucursal/auditor`) ni un rol Postgres `rol_admin_auditor` con BYPASSRLS. No se encontró ninguna referencia a esto en el backend real, y el commit reciente de esta misma rama (`fix(db): la app deja de conectarse como superusuario, ahora usa un rol de mínimo privilegio real`) confirma que la aplicación usa **un único rol de aplicación de mínimo privilegio** para todas las conexiones — no hay bypass de RLS por actor. El scope real de un token `admin-` es `claims.sucursales_permitidas` (lista de UUIDs en el JWT), ya resuelto en servidor por `apply_admin_scope()` (`db/tenancy.py`, usado en `admin_views.py::list_sucursales`). Todo el diseño de tenancy de esta Parte II se apoya en ese mecanismo real, no en una jerarquía empresa→sucursal inexistente (hoy hay una sola empresa en el ER: `empresa` 1—N `sucursal`, sin necesidad de cascada). | Diseñar sobre lo que el backend realmente aplica, no sobre claims que el JWT nunca emite. |
| **DEC-ADM-03** *(corrige)* | Los 6 roles de negocio de CU-08 (`Usuario, Facturador, Supervisor, Administrador, Auditor, Desarrollo`) son **valores libres** de la columna `usuarios.rol` (`String`, sin `CHECK` en el ER ni en el modelo SQLAlchemy) — se pueden almacenar sin tocar el ER. Pero **no** determinan por sí solos el emisor JWT: `POST /auth/login` hoy solo distingue `rol == 'operador'` (emite `operador-`) de todo lo demás (emite `admin-`). Como CU-08 usa la etiqueta `"Usuario"` (no `"operador"`) para el rol operativo de línea, la condición actual clasificaría por error a un `"Usuario"` como `admin-`. Fase 13 corrige `auth.py` para que el emisor dependa de una lista explícita de roles operativos (`{"Usuario", "operador"}` → `operador-`), y documenta que la autorización fina real vive en `permisos_usuario` (RBAC atómico por código), no en `usuarios.rol` (que queda como metadato descriptivo/reporting). | El rol de negocio es para mostrar y filtrar en pantalla; el permiso atómico es lo que el backend efectivamente verifica en cada escritura. |
| **DEC-ADM-04** *(corrige)* | Login: **email + password** (bcrypt), nunca `cedula`. Confirmado en `api/v1/auth.py:45-79` y `schemas/auth.py::LoginRequest` (`email: EmailStr`). Este era el error transversal más grave detectado por la auditoría de fidelidad ER/backend (se repetía en los tres documentos previos de front, admin y tareas). | Un formulario con `cedula` fallaría en runtime contra el backend real. |
| **DEC-ADM-05** | `BranchSelector.tsx`, `sucursal-context.tsx`, `swr-mutate-on-switch.ts` y `Dashboard.tsx` se **reutilizan y extienden**, no se reescriben. Los cuatro ya funcionan contra endpoints reales (`/admin/me`, `/sucursales`, `/admin/sucursales/{uuid}/dashboard`). | Evitar reconstruir funcionalidad ya construida y probada. |
| **DEC-ADM-06** *(corrige)* | Se descarta la migración a cookie httpOnly para el JWT: el backend no emite cookies de sesión en ningún endpoint real (`TokenPair` en `schemas/auth.py` solo define `access_token`/`refresh_token`/`token_type`/`expires_in`, cuerpo JSON). Se mantiene Bearer en `localStorage`, con **refresh transparente en 401** vía `POST /auth/refresh` (sí existe y funciona) como mitigación real de XSS-persistencia (ventana de vida corta del access token, 1h, `ACCESS_TOKEN_TTL` en `auth.py`). | No diseñar sobre un mecanismo de sesión que el backend no implementa; usar el que sí existe correctamente. |
| **DEC-ADM-07** | Tablas grandes: **TanStack Table** (`@tanstack/react-table`, se añade como dependencia nueva — no confundir con `@tanstack/react-query`, que se elimina). Gráficas: **Recharts**. Ambas declarativas, livianas, con buen soporte de i18n. | Encaja con lo ya usado (Radix, shadcn) sin sumar una librería de UI pesada tipo AG Grid. |
| **DEC-ADM-08** | Arquitectura de capas: feature-first + container/presentational + atomic design pragmático (ver §0.2). | Mismo lenguaje arquitectónico que `web_sucursal`, facilita mover devs entre ambos frontends. |
| **DEC-ADM-09** | Formularios: React Hook Form + Zod. Validadores de dominio compartidos (NIT módulo 11, regex de placa **solo para mostrar/entender**, nunca para persistir — ver DEC-ADM-13) viven en `src/lib/validation/`. | Simetría cliente/servidor: los mismos criterios que valida Pydantic en el backend. |
| **DEC-ADM-10** | El versionado bi-temporal (`vigente_desde`/`vigente_hasta`/`estado`) de toda tabla `[V]` se visualiza con un componente único `TimelineVersiones`, reutilizado en cada pantalla de parametrización y en la bitácora. La escritura de una edición SIEMPRE es un `PUT` que dispara `close_and_insert` en el backend (cierra la versión vigente, inserta una nueva) — la UI nunca ofrece "editar in place". | Un solo patrón mental para todo el admin: "toda edición es una versión nueva". |
| **DEC-ADM-11** | Los códigos de permiso que los routers ya exigen pero que nunca fueron sembrados (`config_empresa`, `admin_documentos`, `admin_resolucion_facturacion`, `config_tarifas`, `config_cupos`, `config_tolerancias`, `config_seguridad`) se resuelven **sembrándolos** en una migración nueva (Fase 13) — no reescribiendo los routers para usar códigos ya existentes, porque no hay un código genérico equivalente que no sobre-otorgue permisos entre recursos distintos. Es el mismo patrón de defecto y de arreglo que ya se aplicó realmente en `api/v1/clientes.py` (comentario explícito en el código: "estos 5 recursos exigían códigos nunca sembrados... se consolidó en `gestionar_clientes`, el único código canónico real"). Para el caso distinto de `workflows.py` (que exige `anular_ingreso_salida`, `registrar_reclamo`, `registrar_alerta`, `emitir_reimpresion` — ninguno sembrado, pero el catálogo real YA tiene equivalentes sembrados: `aprobar_anulacion`+`ejecutar_anulacion`, `descartar_alerta`, `reimprimir_ticket`), la resolución es **reconciliar** `_ROUTER_CONFIG` a los códigos ya sembrados, no sembrar 4 más (ver Fase 13, tarea de reconciliación). Solo `registrar_reclamo` no tiene equivalente real y sí requiere siembra nueva. | Minimizar la superficie de códigos de permiso; seguir el patrón de corrección que el propio código ya demuestra que el equipo prefiere. |
| **DEC-ADM-12** | CU-13 (base de caja parametrizable) no tiene tabla en el ER canónico (`config_caja` existe solo en el corpus de CU original / `FLUJO_CUS_ER.md`, nunca en `modelo_datos_er.mmd` — confirmado: 51 tablas en el `.mmd`, `config_caja` no es una de ellas). Se declara una tabla nueva `configuracion_caja` ([V], versionada, patrón idéntico a `configuracion_tolerancias`/`configuracion_seguridad` ya reales: `uuid_sucursal` FK nullable = default global vs. override por sucursal), con columnas `base_inicial_sugerida` (decimal), `redondeo` (string: `ninguno\|100\|500\|1000`), `denominaciones_permitidas` (JSON, array de enteros). El "umbral de alerta por descuadre" de CU-13 **no** duplica una columna nueva: se resuelve reutilizando `configuracion_tolerancias.tolerancia_efectivo`/`tolerancia_datafono`, que ya existen y ya cubren exactamente ese propósito (una sola fuente de verdad de tolerancia, no dos). Esta es una extensión de backend explícitamente declarada como tal — no se modifica `modelo_datos_er.mmd` y se documenta como excepción, exactamente como ya son excepción real (no en el `.mmd`, sí en el backend) `pairing_tokens` y `revoked_sync_jwts`. | Dar a CU-13 una pantalla real sin inventar un nombre de columna en una tabla que no lo tiene, y sin fabricar una segunda fuente de verdad de tolerancia. |
| **DEC-ADM-13** *(corrige)* | `tipos_vehiculo` no tiene columna de regex, prioridad ni orden en el ER (`.mmd` línea 87-103: solo `uuid`, `tipo`, columnas de auditoría/versión/sync). El admin **no** construye un CRUD que persista una regex — construye una pantalla de **catálogo simple** (`tipo`, alta/baja, con timeline), y muestra en modo **solo lectura** el mapeo `tipo → regex` que hoy vive hardcodeado en el frontend de sucursal (`Auto: ^[A-Z]{3}[0-9]{3}$`, `Moto: ^[A-Z]{3}[0-9]{2}[A-Z]$`), con una nota explícita: "este valor no se persiste desde aquí; cambiarlo requiere un release de `web_sucursal`". | Un plan previo construía un CRUD bi-temporal completo para un campo que el propio documento admitía (en otra sección) que no se persiste — contradicción interna real, corregida aquí de raíz. |
| **DEC-ADM-14** | `alerta.estado` usa exactamente los 3 valores que el ER define (`.mmd` línea 750): `abierta \| en_revision \| resuelta`. `alerta` es `[L-W]` (workflow: cada transición es fila nueva, con `uuid_alerta_padre`), igual que `anulaciones`/`reclamos`. No se usa `'ACTIVA'/'REVISADA'` (así aparece en `FLUJO_CUS_ER.md`, un documento de corpus más antiguo que el `.mmd`) ni un booleano `revisada=true` (así lo redacta el CU-14 original) — el `.mmd` es el que manda sobre nombres de columna y valores. | Reconciliar 3 modelos de estado de alerta distintos que circulaban (CU-14 original, `FLUJO_CUS_ER.md`, y el material de plan previo) en el único que el ER canónico realmente soporta. |
| **DEC-ADM-15** | El proveedor de facturación electrónica DIAN es, en el backend real, **una URL única configurada por variable de entorno** (`PARKOS_DIAN_PROVIDER_URL`) y un token en archivo (`PARKOS_DIAN_PROVIDER_TOKEN_PATH`) — no existe (ni se construye en esta Parte II) una tabla `dian_proveedor_config` ni una UI para alternar entre "Factus" y "TopPoint" en caliente. Cambiar de proveedor es un cambio de configuración de despliegue, no una pantalla de admin. | No inventar una capacidad de multi-proveedor que el dispatcher real no tiene. |
| **DEC-ADM-16** | El "reintento" de un envío DIAN rechazado o en error se hace con el endpoint que **ya existe**: `POST /api/v1/envio-dian` (`dian/cloud_router.py`), pasando `uuid_envio_padre` con el `uuid` del envío anterior — es una transición de workflow más, no un endpoint nuevo. | Reutilizar el mecanismo de cadena de transiciones (`uuid_envio_padre`) que el backend ya implementa, en vez de proponer `POST /cloud/envio-dian/:uuid/reintentar` (que no existe ni hace falta). |
| **DEC-ADM-17** | i18n: un solo locale (`es-CO`), namespaces por feature dentro del mismo árbol de traducciones ya iniciado (`src/i18n/locales/es-CO/*.json`), sin librería de detección de idioma adicional (no hace falta: no hay multi-idioma en el alcance). | Extender lo ya configurado, no reintroducir `i18next-browser-languagedetector` para un caso de un solo locale. |
| **DEC-ADM-18** | WCAG 2.1 AA verificado con `@axe-core/playwright` en cada spec e2e (ya es devDependency). | Ya está en el toolchain; solo falta usarlo sistemáticamente. |
| **DEC-ADM-19** | ~~Modo oscuro: fuera de alcance v1~~ — **superada por `Fase 31`** (2026-09-25): el operador lo solicitó explícitamente como requisito no negociable del rediseño visual, cumpliendo la condición de reapertura que la propia decisión exigía. Ver `ABIERTO-53` y `HU-F31.1`. | Evitar trabajo no solicitado por ningún caso de uso — condición que dejó de aplicar al llegar el pedido explícito. |
| **DEC-ADM-20** | Despliegue/serving de `web_admin`: **no existe** ningún `Dockerfile` ni configuración de servido para el cloud hoy (confirmado por búsqueda exhaustiva en `infra/`). Fase 13 decide y construye el mecanismo mínimo real (build estático de Vite servido por un contenedor Nginx, con las mismas variables de entorno de proxy `/api` que ya usa `vite.config.ts` en desarrollo). | Sin este trabajo, `web_admin` no tiene forma de desplegarse aunque todas las fases de negocio estén completas. |

#### 0.4 Glosario (reconciliado con Sucursal)

| Término | Definición | Tabla(s) ER |
|---|---|---|
| **Turno / sesión de caja** | Periodo de trabajo de un operador en una sucursal, desde apertura hasta cierre. Mismo concepto que usa `web_sucursal`; en el ER es la tabla `sesion` ([L-S]). | `sesion` |
| **Arqueo** | Conteo físico de caja contra lo esperado (`factura_pagos` sumado por sesión), clasificado por `tipo_arqueo` (`cierre_turno \| auditoria \| cierre_sesion`, valores reales del catálogo — CU-10/13 hablan de "parcial"/"cierre de turno"/"cierre diario", que se mapean a estos 3 códigos reales). Corrección de una sesión no se hace con `UPDATE`: un arqueo nuevo referencia al anterior. | `arqueo`, `tipo_arqueo` |
| **Tarifa vigente** | La fila de `tarifas_sucursal` cuya ventana `[vigente_desde, vigente_hasta)` contiene la fecha de consulta. "Parametrización efectiva" en `web_admin` es exactamente esta consulta, expuesta con un selector de fecha. | `tarifas_sucursal` |
| **Configuración efectiva** | Patrón default-global + override-por-sucursal: una fila con `uuid_sucursal IS NULL` es el default; una fila con `uuid_sucursal` no nulo es el override de esa sucursal. Ya implementado y real para `configuracion_tolerancias` y `configuracion_seguridad` (`GET .../efectiva?uuid_sucursal=X`); se extiende al mismo patrón para `configuracion_caja` (DEC-ADM-12). | `configuracion_tolerancias`, `configuracion_seguridad`, `configuracion_caja` |
| **Versionado bi-temporal / timeline** | Cada fila `[V]` tiene `vigente_desde`/`vigente_hasta`/`estado`; una "edición" es un `close_and_insert` (cierra la vigente, inserta una nueva). El admin muestra esto como una línea de tiempo con diff entre versiones. | todas las `[V]` |
| **Alcance de sucursales permitidas** | `claims.sucursales_permitidas` del JWT — la lista de UUIDs de sucursal que un actor `admin-` puede ver/operar. Resuelto en servidor por `apply_admin_scope()`. No hay "modo auditor" con bypass; un auditor es un actor con el permiso `audit_read` y normalmente sin permisos de escritura. | — (claim JWT, no tabla) |
| **Permiso atómico** | Código de cadena en `permisos.permiso` (p.ej. `config_tarifas`), asignado a un usuario vía `permisos_usuario`. El backend lo verifica en vivo (join a la BD) en cada escritura — nunca se cachea en el JWT. Las lecturas (`GET`) solo verifican el prefijo de emisor (`admin-`/`operador-`), no el permiso. | `permisos`, `permisos_usuario` |
| **Workflow (`[L-W]`)** | Tabla donde cada transición de estado es una fila nueva que referencia a la anterior (`uuid_*_padre`), nunca un `UPDATE`. `anulaciones`, `reclamos`, `alerta`, `envio_dian`, `validacion_evento` son `[L-W]`. | ver ANEXO de tablas |
| **Bitácora probatoria** | `log_transaccional`, cadena de hashes SHA-256 por `uuid_sucursal`, insert-only. El admin la muestra por registro afectado (`tabla_afectada` + `uuid_registro_afectado`) y ofrece verificación de integridad de la cadena. | `log_transaccional` |
| **Pairing** | Emparejamiento de una sucursal nueva con el cloud: el admin emite un token de un solo uso (24h por defecto, hasta 168h configurable), la sucursal lo canjea por un JWT `sync-agent-` de larga duración. Revocar un pairing token o un JWT de sync es un `INSERT` en `revoked_sync_jwts` (nunca `UPDATE`/`DELETE`, por el trigger de inmutabilidad de `pairing_tokens`). | `pairing_tokens`, `revoked_sync_jwts` (ambas cloud-only, no están en el `.mmd` — ver DEC-ADM-12 para el criterio de excepción) |

#### 0.5 Catálogo de componentes compartidos

> Cada componente se construye **una sola vez** (en la fase que primero lo necesita) y se reutiliza en todas las demás — evita que Fase 15 reinvente el `DataTable` de Fase 14, o que Fase 20 reinvente el `WorkflowChain` de Fase 19. Esta tabla es la referencia única de props/responsabilidad de cada uno; las HU de cada fase solo indican en qué pantalla se usa, no repiten su contrato.

| Componente | Se construye en | Responsabilidad | Props principales |
|---|---|---|---|
| `DataTable.tsx` | Fase 14 (primer catálogo) | Envoltorio de TanStack Table sobre cualquier `ReadList` `{items, next_cursor}`: paginación cursor, ordenamiento de columnas, selección de fila, slot de acciones por fila. | `columns`, `data`, `nextCursor`, `onLoadMore`, `onRowClick?`, `renderActions?` |
| `TimelineVersiones.tsx` | Fase 14 (`CatalogosTiposVehiculo.tsx`) | Muestra el histórico bi-temporal de un registro `[V]` (`GET .../{uuid}/history`, ya real en todo router versionado): línea de tiempo con `vigente_desde`/`vigente_hasta`, diff campo a campo entre versión N y N-1, marca la vigente actual. | `historial: T[]`, `campoLabel: (campo) => string`, `highlightFecha?` (Fase 15, para parametrización efectiva) |
| `ParametrizacionEfectivaSelector.tsx` | Fase 15 | Datepicker + llamado a `?vigente_en=YYYY-MM-DD`; delega el resaltado al `TimelineVersiones` que envuelve. | `tipo`, `uuidSucursal`, `onFechaChange` |
| `KpiCard.tsx` | Fase 17 (dashboard) | Tarjeta con label + valor + skeleton mientras `SWR` carga + estado de error (`—`). | `label`, `value`, `suffix?`, `loading`, `error` |
| `charts/ChartLine.tsx`, `ChartBar.tsx`, `ChartPie.tsx`, `HeatmapOcupacion.tsx` | Fase 17 | Envoltorios declarativos de Recharts + un heatmap SVG custom; todos con `React.lazy`/`import()` dinámico (DEC-ADM-07, RIESGO-ADM-12). `HeatmapOcupacion` se reutiliza en Fase 19 para lag de sync (mismo componente, distinta métrica de color). | `data`, `xKey`, `yKey`, `formatY?` |
| `export/csv.ts`, `export/pdf.ts` | Fase 17 (CSV), Fase 18 (PDF firmado) | `exportToCSV(data, columns, filename)` (RFC 4180 + BOM); `exportToPdf(data, columns, { hashFooter: true })` (hash SHA256 embebido, DEC de HU-F18.4). | — (funciones puras, sin componente visual propio) |
| `WorkflowChain.tsx` | Fase 19 (`AlertaDetalle.tsx`) | Visualiza cualquier cadena `[L-W]` (`uuid_*_padre`) como una lista vertical de transiciones con actor, fecha y `motivo`/`observaciones`. Es el único componente que las 3 tablas `[L-W]` de esta Parte II (`alerta`, `anulaciones`, `reclamos`) comparten — nunca se reescribe por tabla. | `cadena: T[]`, `campoMotivo`, `campoActor`, `campoFecha` |
| `HashChainStatus.tsx` | Fase 15 (`EmpresaDetalle.tsx`, bitácora) | Badge verde/rojo derivado del resultado de `verify_chain()` (Fase 20) para el `uuid_sucursal` en contexto. | `ok: boolean`, `anomalias?: ChainAnomaly[]` |
| `PermisosTree.tsx` | Fase 16 | Árbol de checkboxes agrupado por prefijo semántico del código de permiso (`config_*`, `admin_*`, `gestionar_*`, operativos sin prefijo). | `permisosVigentes: string[]`, `onOtorgar`, `onRevocar` |
| `AlertasBadge.tsx` | Fase 19 | Contador de alertas `estado='abierta'` de las sucursales permitidas del actor, en la barra lateral; se actualiza al cambiar filtro o al transicionar una alerta. | — (lee de un store liviano compartido) |

#### 0.6 Convenciones de UI compartidas

Cada pantalla construida en las fases 14-20 sigue las mismas 4 convenciones, para que el admin nunca tenga que reaprender el comportamiento de una pantalla nueva:

1. **Estados de carga**: `SWR` con `isLoading` → skeleton (nunca un spinner de página completa); `error` → mensaje inline con botón "Reintentar" (nunca una pantalla en blanco).
2. **Confirmación de acciones destructivas o irreversibles** (deshabilitar sucursal, revocar pairing token, descartar alerta, ejecutar anulación): siempre un `AlertDialog` (shadcn) con el detalle exacto de la consecuencia — nunca un `window.confirm()` nativo (falla WCAG y no es consistente visualmente).
3. **Notificación de resultado de una mutación**: `toast` (shadcn) — éxito en verde con el nombre del recurso afectado, error en rojo con el código de error real devuelto por el backend (`detail.error`), nunca un mensaje genérico "algo salió mal".
4. **Formularios con versión bi-temporal**: todo formulario que edita un recurso `[V]` muestra, debajo del botón "Guardar", el texto "Esto creará una nueva versión vigente desde hoy; la versión anterior queda en el histórico" — la misma frase, palabra por palabra, en las 12+ pantallas de parametrización de esta Parte II, para que el patrón de versionado nunca sea una sorpresa.

**Wireframe conceptual — Dashboard ejecutivo (Fase 17, sobre el ya real de hoy):**

```
┌──────────────────────────────────────────────────────────────────────┐
│  Panel de administración               [Sucursal: Sede Norte ▾]  👤  │
├──────────────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐  ┌─────────┐ ┌─────────┐ ┌─────┐│
│  │Ingresos │ │Facturas │ │Alertas  │  │Ocupación│ │Suscrip. │ │Sync ││
│  │  hoy    │ │emitidas │ │abiertas │  │  actual │ │ activas │ │ lag ││
│  └─────────┘ └─────────┘ └─────────┘  └─────────┘ └─────────┘ └─────┘│
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                                 │
│  │Medios de│ │Top 5    │ │Estado FE│                                 │
│  │ pago hoy│ │sucursal │ │  24h    │                                 │
│  └─────────┘ └─────────┘ └─────────┘                                 │
│  ┌────────────────────────────┐ ┌────────────────────────────────┐   │
│  │ Ingresos últimos 30 días   │ │ Heatmap ocupación 24h×N sedes   │   │
│  │  (ChartLine)                │ │  (HeatmapOcupacion)             │   │
│  └────────────────────────────┘ └────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**Wireframe conceptual — Detalle de sucursal (Fase 15, 7 pestañas):**

```
┌──────────────────────────────────────────────────────────────────────┐
│  Sucursales > Sede Norte                                              │
│  [General] [Tarifas] [Capacidad] [Resoluciones] [Caja] [Documentos]   │
│  [Bitácora]                                                            │
├──────────────────────────────────────────────────────────────────────┤
│  Vigente desde 2026-08-01                    [Ver línea de tiempo ▾]  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Nombre:        [Sede Norte                                   ] │  │
│  │ Dirección:     [Cra 45 # 10-20                                ] │  │
│  │ Teléfono:      [601 555 0000                                  ] │  │
│  │ Tipo sucursal: [Parqueadero techado                        ▾ ] │  │
│  │ Estado:        (•) Activa   ( ) Inactiva                       │  │
│  │                                                                  │  │
│  │  Esto creará una nueva versión vigente desde hoy; la versión   │  │
│  │  anterior queda en el histórico.                                │  │
│  │                                          [Cancelar] [Guardar]  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

**`apps/ui-kit` (decisión, no construida en esta Parte II)**: un plan previo proponía un paquete de workspace `apps/ui-kit` compartido entre `web_admin` y `web_sucursal` (Button, `cn`, tokens de diseño). Esta Parte II **no lo construye**: cada app ya tiene su propio `components/ui/` iniciado de forma independiente (`web_admin` tiene `button.tsx` propio), y no hay evidencia de duplicación de esfuerzo real todavía — 2 componentes (`Button`, `cn`) no justifican el costo de mantenimiento de un paquete de workspace compartido (versionado, publicación interna, sincronización de cambios entre 2 apps con ciclos de release distintos). Se documenta como `ABIERTO-60`: evaluar la extracción a un paquete compartido si el catálogo de componentes de UI puramente visuales (sin lógica de negocio) crece más allá de 8-10 componentes duplicados verificados entre ambas apps.

#### 0.7 Anexo — mapeo de términos del corpus de CU original a nombres reales

> Referencia rápida para quien lea el corpus de casos de uso original y necesite ubicar el equivalente real antes de escribir código. Cada fila ya está aplicada en silencio en las secciones anteriores; esta tabla solo la hace buscable en un solo lugar.

| Término del corpus de CU original / de un plan previo | Equivalente real | Dónde se aplica |
|---|---|---|
| `config_caja` (tabla) | `configuracion_caja` (tabla **nueva**, declarada explícitamente fuera del `.mmd`) | DEC-ADM-12, HU-F13.3 |
| `username` (CU-08) | `usuarios.cedula` (UK, identificador de negocio) — el login usa `email`, no `username` ni `cedula` | DEC-ADM-03/04, HU-F16.1 |
| Login por `cedula` (CU original, y varios planes previos) | Login por `email` + `password` (bcrypt) | DEC-ADM-04 |
| "Cajero" / "Operario" / "Operador" (varios CU) | Rol de negocio `"Usuario"` (uno de los 6 de CU-08) para el operativo de línea | DEC-ADM-03 |
| "tipo entrada" (Mensualidad / Rotación) | Derivado, no es columna: `ingreso.uuid_subscripcion_cliente` nullable | (referencia, sin HU propia en esta Parte II — es responsabilidad de `web_sucursal`) |
| `disponible[tipo]` | Derivado en vivo comparando `cantidad_vehiculos_sucursal.cantidad` contra ingresos activos — nunca una columna mutable | HU-F14.4 |
| Numeración simulada `SIM-YYYY-MM-DD-NNNNNN` (FE) | Fuera de alcance v1: el consecutivo real ya usa `resolucion_facturacion` + `SELECT FOR UPDATE` | DEC-ADM-15 |
| `alerta.estado = 'ACTIVA'/'REVISADA'` (FLUJO_CUS_ER.md) o `revisada=true` (CU-14 original) | `alerta.estado ∈ {abierta, en_revision, resuelta}` (valores reales del `.mmd`) | DEC-ADM-14 |
| `tipo_arqueo = 'cierre_dia'` (un plan previo, sin respaldo) | No existe un 4º valor: "cierre de todo el día" = `tipo_arqueo='auditoria'` con `uuid_sesion IS NULL` | HU-F18.3 |
| Recibo de pago `sucursal-YYYYMMDD-NNNNNN` vs. consecutivo de FE | Son dos numeraciones distintas — el recibo es de `web_sucursal`, el consecutivo de FE es `prefijo`+`consecutivo` de `resolucion_facturacion` | HU-F17.3 |
| "Título Ticket" (sucursal) | Sin columna en el ER; decisión pendiente | `ABIERTO-50` |
| "Póliza RC" (sucursal) | `documentos` con `tipo='certificado'` | HU-F15.4 |
| `config_tarifas` / `config_cupos` / `config_empresa` / `admin_documentos` / `config_tolerancias` / `config_seguridad` / `admin_resolucion_facturacion` (permisos) | Códigos reales que los routers ya exigían, nunca sembrados hasta esta Parte II | HU-F13.1 |
| "BYPASSRLS" / rol Postgres `admin_auditor` (un plan previo) | No existe en el backend real; el scope es `claims.sucursales_permitidas` | DEC-ADM-02 |
| `dias_alerta_pre_vencimiento` como default global en `tipo_sucursal.caracteristicas` (un plan previo) | Columna nueva por suscripción individual en `subscripciones_cliente` (CU-06 BR4 lo exige así) | HU-F20.2 |
| `V_FACTURA_ESTADO` (comentario del `.mmd`) | No existe ni como vista ni como endpoint; se calcula ad-hoc (`EXISTS anulaciones ejecutada`) | HU-F17.3 |
| `V_FE_ESTADO_DIAN` (comentario del `.mmd`) | Existe una vista real más angosta: `v_factura_electronica_acuse` (sin `reportado_dian`) | HU-F17.3 |
| "TopPoint" / "Factus" como proveedores conmutables desde UI | El backend real usa una única URL de proveedor por variable de entorno | DEC-ADM-15 |
| `GET /auth/me` (varios planes previos, "no existe, hay que construirlo") | Ya existe con otro nombre y forma equivalente: `GET /admin/me` | DEC-ADM-06, HU-F13.5 |
| `POST /cloud/pairing/*`, `POST /cloud/envio-dian/:uuid/reintentar` (un plan previo, endpoints inventados) | Ya existen con otro path: `/admin/pairing-tokens/*`, `POST /envio-dian` (reintento vía `uuid_envio_padre`) | DEC-ADM-16, HU-F19.3, HU-F20.5 |

---

## Fase 13 — Fundamentos: backend admin, autenticación y despliegue

**Objetivo**: cerrar las brechas de backend que bloquean CUALQUIER pantalla de negocio (permisos que nunca fueron sembrados, emisor JWT que clasifica mal los roles de CU-08, lecturas que faltan para DIAN) y construir el cimiento de frontend (auth, rutas protegidas, sesión) sobre el que se apoyan todas las fases siguientes. Ninguna fase de negocio (14 a 20) puede completarse sin esta.

**CUs cubiertos**: transversal (habilita CU-06, CU-07, CU-08, CU-09, CU-10, CU-11, CU-12, CU-13, CU-14).
**Prereq**: ninguno — es la fase de arranque de Parte II.

### HU-F13.1 — Sembrar los permisos faltantes y reconciliar los códigos de `workflows.py`

**Given** que `api/v1/empresa.py` y `api/v1/configuracion.py` ya exigen los códigos `config_empresa`, `admin_documentos`, `admin_resolucion_facturacion`, `config_tarifas`, `config_cupos`, `config_tolerancias`, `config_seguridad` en sus escrituras (`permission_required=` en cada `_ROUTER_CONFIG`),
**When** se intenta crear o editar cualquiera de esos 7 recursos (empresa, documentos, resolución de facturación, tarifas por sucursal, cupos por sucursal, tolerancias de arqueo, política de seguridad) con cualquier actor, incluido un `admin-` con todos los permisos de negocio que existen hoy,
**Then** el backend responde **403 `permission_denied`** siempre, porque `require_permission()` hace `JOIN` en vivo contra `prod.permisos` y no existe ninguna fila con ese código — es estructuralmente imposible otorgar el permiso hasta sembrarlo.

**Reglas de negocio**
- BR1. `require_permission(codigo)` (`auth/permissions.py`) no cachea nada en el JWT: en cada request hace `SELECT ... FROM permisos_usuario JOIN permisos ON ... WHERE permiso = :codigo AND ambas vigentes`. Si `permisos` no tiene esa fila, ningún `permisos_usuario` puede apuntar a ella (FK), así que el 403 es permanente, no un bug de asignación.
- BR2. Las lecturas (`GET`) de estos mismos recursos **sí funcionan hoy** — el gate de permiso solo se aplica al `POST`/`PUT` en `router_factory.py` (`extra_deps` solo se agrega en la rama de escritura). Esto significa: hoy se puede ver empresa/documentos/tarifas/cupos/tolerancias/seguridad/resolución, pero no crearlos ni editarlos.
- BR3. El patrón de arreglo correcto ya existe en el propio código: `api/v1/clientes.py` documenta (en un comentario real, no hipotético) que sus 5 recursos tenían exactamente este defecto y se corrigió consolidando en un único código canónico ya sembrado (`gestionar_clientes`). Para los 7 códigos de esta HU no hay un equivalente ya sembrado que no sobre-otorgue entre recursos distintos (p. ej. no se puede usar `config_sucursal` para `config_tarifas`: un editor de tarifas no debería poder editar el NIT de la empresa), así que la corrección correcta aquí es **sembrar los 7**, no reconciliar.
- BR4. Distinto es el caso de `workflows.py`: exige `anular_ingreso_salida`, `registrar_reclamo`, `registrar_alerta`, `emitir_reimpresion`, ninguno sembrado — pero el catálogo real ya sembró equivalentes utilizables: `aprobar_anulacion` + `ejecutar_anulacion` (más finos que un solo `anular_ingreso_salida`), `descartar_alerta`, `reimprimir_ticket`. Aquí la corrección es **reconciliar** `_ROUTER_CONFIG` a los códigos ya sembrados (usar `ejecutar_anulacion` para el POST de transición de `anulaciones`, `descartar_alerta` para `alerta`, `reimprimir_ticket` para `reimpresion-ticket`), y sembrar únicamente `registrar_reclamo`, que no tiene equivalente real.
- BR5. Se agrega además `config_caja`, permiso nuevo para el endpoint de `configuracion_caja` que crea la HU-F13.3.

**Tablas ER**: `permisos` ([V], INSERT de 9 filas nuevas: los 7 + `config_caja` + `registrar_reclamo`), `permisos_usuario` (sin cambio de esquema).

**Endpoints**: ninguno nuevo; esta HU solo habilita los `PUT`/`POST` que ya existen en `empresa.py`, `configuracion.py` y `workflows.py`.

**Componentes**: ninguno (backend puro).

**Validaciones**: la migración usa `ON CONFLICT (permiso, vigente_desde) DO NOTHING` (mismo patrón idempotente que `0002_seed_permisos_canonicos.py`), así que es segura de re-ejecutar.

**Errores**: ninguno nuevo; se elimina el 403 estructural descrito arriba.

**Pruebas**: test de integración que crea un usuario con `permisos_usuario` apuntando a cada uno de los 9 códigos nuevos y verifica que el `PUT`/`POST` correspondiente ya no devuelve 403; test unitario que verifica que `workflows.py::_ROUTER_CONFIG` usa exclusivamente códigos presentes en el catálogo sembrado (test de "no-permiso-huérfano", análogo a como se detectó el defecto en `clientes.py`).

**Tamaño**: ~90 LOC (migración + 4 líneas de reconciliación en `workflows.py`).

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.1-T1 | Migración `NNNN_seed_permisos_admin_faltantes.py`: INSERT de `config_empresa`, `admin_documentos`, `admin_resolucion_facturacion`, `config_tarifas`, `config_cupos`, `config_tolerancias`, `config_seguridad`, `config_caja`, `registrar_reclamo` | `backend/packages/parkos_core/migrations/versions/` |
| HU-F13.1-T2 | Reconciliar `_ROUTER_CONFIG` de `workflows.py`: `anulaciones`→`ejecutar_anulacion`, `alerta`→`descartar_alerta`, `reimpresion-ticket`→`reimprimir_ticket`, `reclamos`→`registrar_reclamo` | `backend/.../api/v1/workflows.py` |
| HU-F13.1-T3 | Test de integración de los 9 permisos nuevos + test de "no-permiso-huérfano" | `backend/tests/integration/`, `backend/tests/static/` |

---

### HU-F13.2 — Corregir el emisor JWT para los 6 roles de negocio de CU-08

**Given** que `POST /auth/login` emite `issuer = "operador-" if user.rol == "operador" else "admin-"`,
**When** un usuario tiene `rol = "Usuario"` (la etiqueta que CU-08 define para el rol operativo de línea, distinta de la cadena literal `"operador"`),
**Then** hoy recibe un token `admin-` en vez de `operador-` — un error de clasificación real que ningún documento previo había detectado, porque nadie cruzó la lista de 6 roles de CU-08 contra la condición literal de `auth.py`.

**Reglas de negocio**
- BR1. El emisor JWT (`operador-` vs `admin-`) determina qué routers puede tocar el token (`requires_issuer(...)` en cada router) — es el límite arquitectónico grueso; el permiso atómico es el fino (DEC-ADM-03).
- BR2. Los roles que deben emitir `operador-`: `"Usuario"` (y se mantiene compatibilidad retro con la cadena `"operador"` ya usada en datos existentes/tests). Los que emiten `admin-`: `"Facturador"`, `"Supervisor"`, `"Administrador"`, `"Auditor"`, `"Desarrollo"`.
- BR3. Esta corrección es puramente de clasificación de emisor; no cambia el modelo de permisos atómicos, que sigue siendo la autoridad real de qué puede escribir cada actor.

**Tablas ER**: `usuarios.rol` (sin cambio de esquema — sigue siendo `String` libre).

**Endpoints**: `POST /auth/login` (modificado, mismo contrato de respuesta `TokenPair`).

**Componentes**: ninguno (backend).

**Validaciones**: lista explícita `ROLES_OPERADOR = {"operador", "Usuario"}` en `auth.py`, resto → `admin-`.

**Errores**: sin cambio de forma de error.

**Pruebas**: test unitario parametrizado con los 6 roles verificando el emisor esperado para cada uno.

**Tamaño**: ~20 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.2-T1 | Reemplazar la condición binaria por `ROLES_OPERADOR` explícita | `backend/.../api/v1/auth.py` |
| HU-F13.2-T2 | Test parametrizado de los 6 roles | `backend/tests/unit/test_auth_login_password.py` (extender el ya existente en la rama) |

---

### HU-F13.3 — Tabla `configuracion_caja` (backend real para CU-13)

**Given** que CU-13 pide "base inicial, umbral de alerta y redondeo por sucursal" y que el ER canónico no tiene tabla para eso (ver DEC-ADM-12),
**When** se necesita dar a CU-13 una pantalla de administración real (no una que solo reordena `configuracion_tolerancias`, que es lo que hacía un plan previo),
**Then** se crea `configuracion_caja` con el mismo patrón exacto que `configuracion_tolerancias`/`configuracion_seguridad` (override por sucursal vs. default global, bi-temporal, endpoint `.../efectiva`).

**Reglas de negocio**
- BR1 (CU-13 BR1, real). El arqueo usa la base configurada al **inicio del arqueo**, no la del inicio del turno — `base_inicial_sugerida` es un valor de referencia que la UI de sucursal pre-llena; no reemplaza `sesion.valor_inicial_efectivo`/`valor_inicial_datafono` (que siguen siendo lo que efectivamente se contó al abrir el turno, tabla real ya existente).
- BR2. El "umbral de alerta por descuadre" de CU-13 **no** se modela con una columna nueva: es exactamente `configuracion_tolerancias.tolerancia_efectivo`/`tolerancia_datafono`, ya reales. La pantalla de CU-13 en `web_admin` muestra y edita ambas tablas juntas en una sola vista ("Caja" con dos secciones: Base y redondeo / Tolerancias"), pero son dos tablas distintas por debajo — no se duplica la fuente de verdad.
- BR3. `redondeo` acepta `ninguno | 100 | 500 | 1000` (el múltiplo al que se redondea el vuelto en efectivo). `denominaciones_permitidas` es un array JSON de enteros (p. ej. `[1000, 2000, 5000, 10000, 20000, 50000]`) usado por la sucursal para validar que el efectivo contado se pueda componer con esas denominaciones — validación de UI en sucursal, no constraint de base de datos.
- BR4 (CU-13 E1, real). Cambiar la base durante una jornada activa está permitido; los arqueos ya cerrados conservan su histórico (patrón bi-temporal estándar: no se reescribe nada, se cierra la versión vigente y se inserta la nueva).

**Tablas ER**: `configuracion_caja` (**tabla nueva**, no en `modelo_datos_er.mmd` — declarada como excepción explícita, mismo criterio que `pairing_tokens`/`revoked_sync_jwts`): `uuid` PK, `uuid_sucursal` FK nullable (NULL = default global), `base_inicial_sugerida` decimal(18,4), `redondeo` string, `denominaciones_permitidas` JSON, más las columnas estándar de auditoría/versión/sync que toda `[V]` ya tiene. `configuracion_tolerancias` (existente, reutilizada sin cambios).

**Endpoints**: `GET/POST/PUT /api/v1/configuracion/configuracion-caja` (mismo factory `make_router`, `repo_kind="versioned"`, `issuer_required="admin-,operador-"`, `permission_required="config_caja"`); `GET /api/v1/configuracion/configuracion-caja/efectiva?uuid_sucursal=X` (mismo patrón que `configuracion-seguridad/efectiva`).

**Componentes**: `SucursalCaja.tsx` (Fase 15, no aquí — esta HU es backend puro).

**Validaciones**: Pydantic `redondeo: Literal["ninguno", "100", "500", "1000"]`; `denominaciones_permitidas: list[int]`.

**Errores**: 404 si no hay override ni default global en `.../efectiva` (mismo contrato que las dos tablas hermanas).

**Pruebas**: test de integración espejo de `test_config_override_resolution.py` (que ya cubre tolerancias/seguridad), extendido a `configuracion_caja`.

**Tamaño**: ~180 LOC (modelo + schema + router + migración + test), calcado del patrón real de las dos tablas hermanas.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.3-T1 | Migración: tabla `configuracion_caja` + UK `(uuid_sucursal, vigente_desde)` | `backend/.../migrations/versions/` |
| HU-F13.3-T2 | Modelo `ConfiguracionCaja` (calco de `ConfiguracionTolerancias`) | `backend/.../models/V/configuracion_caja.py` |
| HU-F13.3-T3 | Schemas `ConfiguracionCajaCreate/Read/Update/Filter/ReadList` | `backend/.../schemas/configuracion.py` |
| HU-F13.3-T4 | Montar router + endpoint `.../efectiva` | `backend/.../api/v1/configuracion.py` |
| HU-F13.3-T5 | Test de integración de resolución efectiva | `backend/tests/unit/test_config_override_resolution.py` |

---

### HU-F13.4 — Lecturas para `envio_dian` y `validacion_evento` (no existen hoy)

**Given** que `dian/cloud_router.py` solo expone `POST /envio-dian` y `POST /validacion-evento` (transiciones de escritura) y que `workflows.py` documenta explícitamente que **no debe** montar estas dos tablas de solo lectura junto a `anulaciones`/`reclamos`/`alerta` (están reservadas al módulo cloud-only),
**When** el admin necesita un monitor de cola DIAN (CU-05/CU-14) o una bandeja de validación de eventos (CU-07 lado admin),
**Then** no hay ningún endpoint que liste o lea estas dos tablas — es una brecha real y confirmada, no una suposición.

**Reglas de negocio**
- BR1. Se agregan solo lecturas (`GET`, cursor-paginado, mismo contrato `{items, next_cursor}` que el resto del sistema); ninguna escritura nueva — las escrituras ya existen (`POST /envio-dian`, `POST /validacion-evento`) y se reutilizan tal cual (DEC-ADM-16).
- BR2. `envio_dian` filtra por `estado` (`pendiente|enviado|aceptado|rechazado`, los 4 valores reales del ER) y por `uuid_sucursal`. `validacion_evento` filtra por `estado` (`recibido|validado|observado|rechazado`).
- BR3. Ambos endpoints viven en `cloud_router.py` (mismo archivo, mismo guard de `PARKOS_DEPLOY=branch` que ya bloquea el módulo entero en despliegues de sucursal).

**Tablas ER**: `envio_dian` ([L-W], solo lectura), `validacion_evento` ([L-W], solo lectura).

**Endpoints**: `GET /api/v1/envio-dian?uuid_sucursal=&estado=&cursor=&limit=`; `GET /api/v1/validacion-evento?uuid_sucursal=&estado=&cursor=&limit=`.

**Componentes**: consumidos en Fase 19 (`DianCola.tsx`, `ValidacionEventos.tsx`), no en esta HU.

**Validaciones**: `estado` restringido a los valores reales del ER (422 si no matchea).

**Errores**: 400 si `cursor` es inválido (mismo `InvalidCursorError` que el resto del sistema).

**Pruebas**: test de integración de paginación cursor + filtro por estado para ambos endpoints.

**Tamaño**: ~120 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.4-T1 | `GET /envio-dian` con filtros + cursor | `backend/.../dian/cloud_router.py` |
| HU-F13.4-T2 | `GET /validacion-evento` con filtros + cursor | `backend/.../dian/cloud_router.py` |
| HU-F13.4-T3 | Tests de integración de ambos | `backend/tests/integration/` |

---

### HU-F13.5 — `authStore` + `useAuth` + refresh transparente en 401

**Given** que hoy `parkosFetch` no reintenta en 401 ni existe ningún store de identidad en memoria,
**When** el access token expira a la hora (`ACCESS_TOKEN_TTL=3600`) mientras el admin sigue trabajando,
**Then** debe renovarse solo, sin que el admin note la expiración, usando `POST /auth/refresh` (real, ya implementado).

**Reglas de negocio**
- BR1. Un único reintento de refresh por request fallida en 401; si el segundo intento también da 401, se limpia el `authStore`, se borra el token de `localStorage` y se redirige a `/login?next=<ruta actual>`.
- BR2. `authStore` se hidrata con `GET /api/v1/admin/me` (real, ya construido — no `/auth/me`, que nunca existió y no hace falta inventar: `/admin/me` ya devuelve `actor_uuid, email, rol, sucursales_permitidas, permissions`).
- BR3. `hasPermission(codigo)` en el hook es una ayuda de UX (ocultar/deshabilitar botones); el backend sigue siendo la única autoridad real — un botón visible no implica que el `POST` vaya a aceptar.

```mermaid
sequenceDiagram
    participant UI as web_admin (parkosFetch)
    participant API as api-admin
    UI->>API: GET /recurso (Bearer access_token)
    API-->>UI: 401 (token expirado)
    UI->>API: POST /auth/refresh (refresh_token)
    alt refresh válido
        API-->>UI: 200 TokenPair (nuevo access_token)
        UI->>API: GET /recurso (Bearer nuevo access_token)
        API-->>UI: 200 OK
    else refresh también inválido
        API-->>UI: 401
        UI->>UI: authStore.clear() + setAuthToken(null)
        UI->>UI: redirect /login?next=<ruta actual>
    end
```

**Tablas ER**: ninguna directa (consume `permisos`/`permisos_usuario` indirectamente vía `/admin/me`).

**Endpoints**: `GET /api/v1/admin/me` (ya existe), `POST /api/v1/auth/refresh` (ya existe).

**Componentes**: `src/lib/authStore.ts` (Zustand: `{ user: AdminMeResponse | null, isLoading, setUser, clear }`), `src/lib/hooks/useAuth.ts` (SWR sobre `/admin/me` + `hasPermission`).

**Validaciones**: ninguna de formulario en esta HU.

**Errores**: 401 doble → logout + redirect; red caída → SWR reintenta con backoff propio de SWR (no se reinventa un backoff manual).

**Pruebas**: unit con MSW cubriendo: hidratación exitosa, 401 único con refresh exitoso, 401 doble con logout, permiso presente/ausente en `hasPermission`.

**Tamaño**: ~180 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.5-T1 | `authStore.ts` (Zustand) | `src/lib/authStore.ts` |
| HU-F13.5-T2 | Extender `parkosFetch` con retry de 401 (un solo intento de refresh) | `src/lib/fetch.ts` |
| HU-F13.5-T3 | `useAuth.ts` con SWR sobre `/admin/me` + `hasPermission` | `src/lib/hooks/useAuth.ts` |
| HU-F13.5-T4 | Tests MSW (4 escenarios) | `src/lib/hooks/__tests__/useAuth.test.ts` |

---

### HU-F13.6 — Login real (email + password), `ProtectedRoute` y `App.tsx`

**Given** que `Login.tsx` es un placeholder sin formulario y `App.tsx` no protege ninguna ruta,
**When** un admin visita `/parametrizacion` (o cualquier ruta de negocio) sin sesión,
**Then** debe rebotar a `/login?next=/parametrizacion`; y al iniciar sesión con `email`+`password` válidos, debe volver exactamente a esa ruta.

**Reglas de negocio**
- BR1. El formulario valida `email` (RFC 5322, mismo criterio que `EmailStr` de Pydantic) y `password` (mínimo 8 caracteres, mismo mínimo que `LoginRequest`). **Nunca** `cedula` (DEC-ADM-04).
- BR2. 401 del backend (`invalid_credentials`, respuesta anti-enumeración: mismo mensaje para email inexistente o password incorrecta) se muestra como un único mensaje genérico "Credenciales inválidas", sin distinguir causa (coherente con el diseño anti-enumeración real del backend).
- BR3. Tras login exitoso, el token se persiste (`setAuthToken`, ya existente) y se navega a `next` si es una ruta interna válida, o a `/dashboard` si no hay `next`.
- BR4. `ProtectedRoute` verifica `authStore.user` (vía `useAuth`); si además se pasa `permiso`, verifica `hasPermission(permiso)` y redirige a `/403` si falta.

**Tablas ER**: `usuarios` (vía `POST /auth/login`, ya real).

**Endpoints**: `POST /api/v1/auth/login` (ya existe).

**Componentes**: `src/features/auth/pages/Login.tsx` (reemplazo del placeholder), `src/routes/ProtectedRoute.tsx`, `src/pages/Forbidden.tsx` (403), `src/pages/NotFound.tsx` (404), `App.tsx` reescrito con las rutas reales que las fases 14-20 van agregando (esta HU deja el esqueleto: `/login`, `/dashboard`, `/403`, `/404`, con placeholder de las demás secciones que cada fase completa).

**Validaciones**: Zod `{ email: z.string().email(), password: z.string().min(8) }`.

**Errores**: 401 → toast "Credenciales inválidas"; red caída → toast "No se pudo conectar, reintentá".

**Pruebas**: e2e Playwright: login exitoso con `next`, login fallido (permanece en form), ruta protegida sin sesión rebota, ruta con permiso insuficiente rebota a `/403`. Axe-core en la página de login (WCAG 2.1 AA: `aria-invalid`, `aria-describedby`, foco visible, navegación por teclado).

**Tamaño**: ~230 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.6-T1 | `Login.tsx` con RHF + Zod (`email`/`password`) | `src/features/auth/pages/Login.tsx` |
| HU-F13.6-T2 | Integración `POST /auth/login` + `setAuthToken` + `authStore.setUser` | `src/features/auth/pages/Login.tsx` |
| HU-F13.6-T3 | `ProtectedRoute.tsx` (auth + permiso opcional) | `src/routes/ProtectedRoute.tsx` |
| HU-F13.6-T4 | `Forbidden.tsx`, `NotFound.tsx` | `src/pages/` |
| HU-F13.6-T5 | Reescribir `App.tsx` con el esqueleto de rutas protegidas | `src/App.tsx` |
| HU-F13.6-T6 | i18n `auth.json` (`login.title`, `login.error.credenciales`, etc.) | `src/i18n/locales/es-CO/auth.json` |
| HU-F13.6-T7 | e2e (4 escenarios) + axe | `e2e/login.spec.ts`, `e2e/routing.spec.ts` |

---

### HU-F13.7 — Despliegue: `Dockerfile` + servido de `web_admin`

**Given** que no existe ningún mecanismo de despliegue para `apps/web_admin` (confirmado: 0 archivos `Dockerfile`/`docker-compose` bajo `apps/web_admin` o `infra/` que lo mencionen),
**When** el resto de las fases de negocio estén completas,
**Then** igual no habría forma de desplegar `web_admin` — este es un bloqueante independiente del contenido funcional.

**Reglas de negocio**
- BR1. Build estático (`vite build`) servido por un contenedor Nginx liviano (multi-stage: build en `node:20-alpine`, servido en `nginx:alpine`), coherente con que es una PWA sin SSR.
- BR2. El proxy `/api` que hoy solo existe en `vite.config.ts` para desarrollo (`server.proxy`) se resuelve en producción con la configuración real de Nginx (`location /api/ { proxy_pass ... }`) apuntando a `api-admin`.
- BR3. Variables de entorno de build (`VITE_API_BASE_URL` si aplica) documentadas en un `.env.example` nuevo.

**Tablas ER**: ninguna (infraestructura pura).

**Endpoints**: ninguno nuevo.

**Componentes**: ninguno de UI.

**Validaciones**: healthcheck HTTP del contenedor (`GET /` → 200).

**Errores**: build que falla en CI bloquea el merge (ya cubierto por el pipeline existente de lint/typecheck/build).

**Pruebas**: smoke test de `docker build` + `docker run` + `curl localhost:PORT/` en CI.

**Tamaño**: ~80 LOC (Dockerfile + nginx.conf + smoke test).

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F13.7-T1 | `Dockerfile` multi-stage (build Vite + serve Nginx) | `apps/web_admin/Dockerfile` |
| HU-F13.7-T2 | `nginx.conf` con proxy `/api` → `api-admin` | `apps/web_admin/nginx.conf` |
| HU-F13.7-T3 | Smoke test de build+run en CI | `.github/workflows/` o equivalente del repo |

---

## Fase 14 — Parametrización: catálogos, tipos de vehículo, tarifas y capacidad

**Objetivo**: dar a CU-12 (tipos de vehículo) y CU-11 (tarifas y capacidad, parte 1 de 2 — la parte 2 sigue en Fase 15 con sucursal/empresa/resoluciones) sus pantallas reales de administración, apoyadas en endpoints que ya existen y funcionan hoy (catálogos, tarifas, cupos) una vez sembrado el permiso que falta (`config_tarifas`/`config_cupos`, Fase 13).

**CUs cubiertos**: CU-12 (completo), CU-11 (tarifas + capacidad).
**Prereq**: Fase 13 completa (permisos sembrados, auth funcionando).

### HU-F14.1 — Catálogo `tipos_vehiculo` (solo lo que persiste de verdad)

**Given** que `tipos_vehiculo` en el ER solo tiene `uuid` y `tipo` como columnas de negocio (`.mmd` línea 87-103),
**When** el admin abre `/catalogos/tipos-vehiculo`,
**Then** ve un CRUD simple de esa única columna de negocio (alta, edición con timeline, baja lógica por cierre de vigencia) — **no** un formulario de regex/prioridad/orden que no tiene dónde persistirse (DEC-ADM-13).

**Reglas de negocio**
- BR1 (CU-12 real, adaptada). El formato de placa esperado por tipo (`Auto: ^[A-Z]{3}[0-9]{3}$`, `Moto: ^[A-Z]{3}[0-9]{2}[A-Z]$`, más los que agregue `web_sucursal`) se muestra en modo **solo lectura**, leído de una constante compartida documentada (no de la base de datos), con el aviso explícito de que cambiarlo requiere un release de `web_sucursal`, no una edición aquí.
- BR2 (CU-12 BR2, real). Un tipo deshabilitado (`vigente_hasta` cerrado) no debe aparecer en los dropdowns operativos de sucursal, pero sus ingresos históricos (`ingreso.uuid_tipo_vehiculo`) se mantienen intactos — el cierre de vigencia nunca borra ni reescribe filas relacionadas.
- BR3 (CU-12 E3, real). No se permite cerrar la vigencia de un tipo con suscripciones activas que lo referencian (`subscripciones_cliente` vía `vehiculos.uuid_tipo_vehiculo`) — el backend ya rechaza escrituras de `[V]` con relaciones vigentes dependientes en otros flujos similares; esta HU agrega la validación específica para este caso en el endpoint de `PUT`.

**Tablas ER**: `tipos_vehiculo` ([V]).

**Endpoints**: `GET/POST/PUT /api/v1/catalogos/tipos-vehiculo` (ya existen, `permission_required="config_catalogo"`, ya sembrado — funciona hoy).

**Componentes**: `CatalogosTiposVehiculo.tsx` (página, DataTable + timeline), `TipoVehiculoForm.tsx` (RHF + Zod, un solo campo `tipo`), `RegexReferencia.tsx` (panel de solo lectura con el mapeo tipo→regex documentado).

**Validaciones**: `tipo` no vacío, único entre las versiones vigentes (backend ya lo garantiza por UK `(tipo, vigente_desde)`).

**Errores**: 422 `tipo_duplicado_vigente` si ya existe una versión vigente con el mismo `tipo`; 409 si se intenta deshabilitar con suscripciones vigentes dependientes (nuevo, ver BR3).

**Pruebas**: e2e: crear tipo, editar (nueva versión, timeline muestra 2 filas), intentar deshabilitar uno con suscripciones activas → 409.

**Tamaño**: ~220 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F14.1-T1 | Zod schema `tiposVehiculo.ts` (solo `tipo`) | `src/lib/schemas/tiposVehiculo.ts` |
| HU-F14.1-T2 | `CatalogosTiposVehiculo.tsx` con `TimelineVersiones` | `src/features/parametrizacion/pages/` |
| HU-F14.1-T3 | `TipoVehiculoForm.tsx` | `src/features/parametrizacion/components/` |
| HU-F14.1-T4 | `RegexReferencia.tsx` (solo lectura, constante compartida documentada) | `src/features/parametrizacion/components/` |
| HU-F14.1-T5 | **Backend**: validación 409 al deshabilitar tipo con suscripciones vigentes | `backend/.../api/v1/catalogos.py` |
| HU-F14.1-T6 | e2e (3 escenarios) | `e2e/catalogos-tipos-vehiculo.spec.ts` |

---

### HU-F14.2 — Catálogos simples restantes (`tipo_persona`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `tipo_subscripciones`, `impuestos`, `otros_cobros`, `costos_servicios`)

**Given** que las 8 tablas de catálogo restantes ya tienen router real y funcional (`GET/POST/PUT`, `permission_required="config_catalogo"`, ya sembrado),
**When** el admin necesita mantenerlas,
**Then** una sola pantalla genérica con pestañas cubre las 8, cada una con su propio formulario según sus columnas reales (no un formulario genérico que finja columnas iguales).

**Reglas de negocio**
- BR1. `tipo_arqueo.codigo` acepta exactamente `cierre_turno | auditoria | cierre_sesion` (3 valores reales del ER, `.mmd` línea 171) — la UI no ofrece un cuarto valor "cierre_dia" inventado por material previo sin respaldo en el ER ni en el catálogo real.
- BR2. `impuestos` y `otros_cobros` son catálogos con **patrón snapshot**: al emitir una factura, el valor vigente se copia a `factura_impuestos`/`factura_otros_cobros` (tablas `[A]`, ya reales) — cambiar el IVA de 19% a otro valor cierra la versión vigente y abre una nueva, pero las facturas ya emitidas mantienen su snapshot histórico intacto. La UI debe comunicar esto explícitamente ("las facturas emitidas no cambian retroactivamente").
- BR3. `tipo_subscripciones` expone `valor`, `duracion_dias`, `cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo` (bool), `tipo_cliente_permitido` — son las columnas reales que CU-06 (Fase 20) necesita para vender planes; esta HU solo las hace administrables, el consumo queda en Fase 20.

**Tablas ER**: `tipo_persona`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `tipo_subscripciones`, `impuestos`, `otros_cobros`, `costos_servicios` (todas [V], ya reales).

**Endpoints**: `GET/POST/PUT /api/v1/catalogos/{tipo-persona,tipo-tarifa,tipo-sucursal,tipo-arqueo,tipo-subscripciones,impuestos,otros-cobros,costos-servicios}` (ya existen y funcionan).

**Componentes**: `CatalogosTipos.tsx` (8 pestañas), `GenericoCatalogo.tsx` (tabla + timeline reutilizable), un formulario específico por catálogo (`ImpuestoForm.tsx`, `TipoSubscripcionForm.tsx`, etc. — no un formulario 100% genérico, porque las columnas difieren).

**Validaciones**: `impuestos.porcentaje` decimal 0-100; `tipo_subscripciones.duracion_dias` entero > 0; `tipo_arqueo.codigo` restringido a los 3 valores reales.

**Errores**: 422 `codigo_duplicado_vigente` por catálogo (mismo patrón UK que el resto).

**Pruebas**: e2e de navegación entre las 8 pestañas + CRUD en al menos 3 representativas (`impuestos`, `tipo_subscripciones`, `tipo_arqueo`).

**Tamaño**: ~380 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F14.2-T1 | Zod schemas de los 8 catálogos | `src/lib/schemas/catalogos.ts` |
| HU-F14.2-T2 | `CatalogosTipos.tsx` con 8 pestañas | `src/features/parametrizacion/pages/` |
| HU-F14.2-T3 | `GenericoCatalogo.tsx` (tabla+timeline reutilizable) | `src/features/parametrizacion/components/` |
| HU-F14.2-T4 | Formularios específicos (impuestos, otros_cobros, tipo_subscripciones, resto) | `src/features/parametrizacion/components/` |
| HU-F14.2-T5 | e2e (navegación + 3 CRUD) | `e2e/catalogos-tipos.spec.ts` |

---

### HU-F14.3 — Matriz de tarifas por sucursal (CU-11, parte tarifas)

**Given** que `tarifas_sucursal` es real y funcional en lectura pero su escritura está bloqueada hasta sembrar `config_tarifas` (Fase 13),
**When** el admin edita la matriz `tipo_vehiculo × tipo_tarifa` de una sucursal,
**Then** puede crear/editar `valor`, `valor_plena` (tope diario opcional) con vigencia futura programable, sin poder tener dos modalidades vigentes simultáneas para la misma combinación (`sucursal, tipo_vehiculo, tipo_tarifa`).

**Reglas de negocio**
- BR1 (CU-11 BR7, real). La unidad de tarifa es excluyente por `(sucursal, tipo_vehiculo)`: solo una de `hora|fraccion|plena` puede estar vigente a la vez para esa combinación — se aplica leyendo `tipo_tarifa` (catálogo real de modalidades) y validando en el formulario que no se dupliquen modalidades activas para el mismo par.
- BR2 (CU-11 BR8, real). `valor_plena` es opcional; si está definida, es el tope máximo aplicado entre las 00:00 y las 23:59 hora local Colombia (UTC-5). El "tiempo de tarifa plena" (`tiempo_tar_plena`) **no** es una columna del ER: se computa en pantalla como `(valor_plena / valor) * unidad_minutos` — valor puramente informativo (solo lectura), nunca se envía al backend.
- BR3 (CU-11, real — programación futura). Una tarifa con `vigente_desde` en el futuro queda "programada": no aplica hasta esa fecha, pero ya es visible en el timeline con una marca "programada" distinta de "vigente".
- BR4. Corrección de estilo (hallazgo de la auditoría de fidelidad, aplicado en silencio): el slug de URL usa "suscripcion" con S en cualquier parte visible de esta pantalla (no aplica aquí directamente, pero se deja como convención para toda la Parte II — ver Fase 20).

**Tablas ER**: `tarifas_sucursal` ([V], real), `tipos_vehiculo` (R), `tipo_tarifa` (R).

**Endpoints**: `GET/POST/PUT /api/v1/empresa/tarifas-sucursal?uuid_sucursal=X` (ya existe; el filtro `vigente_en` para "parametrización efectiva" se agrega en Fase 15 junto con la vista de parametrización efectiva general, para no duplicar el mismo trabajo en dos fases).

**Componentes**: `SucursalTarifas.tsx` (matriz `tipo_vehiculo × tipo_tarifa`), `TarifaForm.tsx` (RHF + Zod: `valor` decimal > 0, `valor_plena` decimal opcional ≥ 0, `vigente_desde` fecha).

**Validaciones**: `valor > 0`; si `valor_plena` está presente, `valor_plena >= valor` (un tope diario menor que la tarifa por unidad no tiene sentido de negocio — validación de cliente, el backend valida solo tipos).

**Errores**: 422 `tarifa_duplicada_vigente` si ya existe una modalidad vigente para esa combinación exacta.

**Pruebas**: e2e: crear tarifa, editar con fecha futura (se muestra "programada"), intentar duplicar modalidad vigente → 422.

**Tamaño**: ~230 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F14.3-T1 | `SucursalTarifas.tsx` (matriz agrupada) | `src/features/parametrizacion/components/` |
| HU-F14.3-T2 | `TarifaForm.tsx` | `src/features/parametrizacion/components/` |
| HU-F14.3-T3 | Cálculo de `tiempo_tar_plena` (solo lectura, cliente) | `src/lib/tarifas.ts` |
| HU-F14.3-T4 | Integración SWR con `uuid_sucursal` | `src/features/parametrizacion/hooks/` |
| HU-F14.3-T5 | e2e (3 escenarios) | `e2e/sucursal-tarifas.spec.ts` |

---

### HU-F14.4 — Capacidad por tipo de vehículo (CU-11, parte capacidad)

**Given** que `cantidad_vehiculos_sucursal` es real y funcional en lectura, bloqueada en escritura hasta sembrar `config_cupos` (Fase 13),
**When** el admin reduce la capacidad de un tipo por debajo de lo actualmente ocupado,
**Then** el backend rechaza con 422 y detalle — nunca se permite una capacidad negativa implícita.

**Reglas de negocio**
- BR1 (CU-11 BR5, real). La capacidad es **estricta por tipo**, sin compartir cupos entre tipos: 0 cupos de Auto bloquea ingresos de Auto aunque haya cupos de Moto libres. Esto se valida en `web_sucursal` (CU-01); aquí solo se configura el número total.
- BR2 (CU-11 AC7, real). `nuevo_total >= vehiculos_adentro[tipo]` — el "ocupado actual" no es una columna, se deriva comparando contra `ingreso` sin `salidas` asociada no anulada (mismo patrón `V_INGRESO_ESTADO` que usa sucursal). El backend calcula esto en el momento de la validación del `PUT`, no se persiste un contador mutable (evita repetir el error, ya detectado en la auditoría, de un trigger que mantendría una columna `disponible` que el ER no tiene).
- BR3 (CU-11 BR6, real). Reducir la capacidad no afecta ingresos ya activos: un vehículo que entró cuando había cupo se mantiene adentro aunque el nuevo total sea menor a la ocupación — solo se bloquean ingresos *nuevos* de ese tipo hasta que la ocupación baje del nuevo total.

**Tablas ER**: `cantidad_vehiculos_sucursal` ([V], real), `ingreso`/`salidas` (R, para calcular ocupación).

**Endpoints**: `GET/POST/PUT /api/v1/empresa/cantidad-vehiculos-sucursal?uuid_sucursal=X` (ya existe).

**Componentes**: `SucursalCapacidad.tsx` (matriz por tipo, con validación local antes de enviar y mensaje de error del backend si de todos modos se rechaza).

**Validaciones**: `cantidad >= 0` entero; validación local "no reducir por debajo de lo ocupado" como aviso previo (UX), con el backend como autoridad final.

**Errores**: 422 `capacidad_insuficiente` con detalle `{tipo, ocupado_actual, solicitado}`.

**Pruebas**: e2e: aumentar capacidad, reducir por encima de lo ocupado (éxito), reducir por debajo de lo ocupado (422 con detalle visible).

**Tamaño**: ~150 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F14.4-T1 | `SucursalCapacidad.tsx` | `src/features/parametrizacion/components/` |
| HU-F14.4-T2 | **Backend**: validar `nuevo_total >= ocupado` calculado en vivo contra `ingreso`/`salidas` en el `PUT` | `backend/.../api/v1/empresa.py` |
| HU-F14.4-T3 | e2e (3 escenarios) | `e2e/sucursal-capacidad.spec.ts` |

---

## Fase 15 — Empresa, sucursal, resoluciones DIAN, documentos y caja

**Objetivo**: completar CU-11 (datos generales de sucursal, resoluciones DIAN) y dar a CU-13 su pantalla real apoyada en `configuracion_caja` (Fase 13). Cierra la matriz CU-11 junto con Fase 14.

**CUs cubiertos**: CU-11 (completo), CU-13 (completo).
**Prereq**: Fase 13 (permisos `config_empresa`, `admin_documentos`, `admin_resolucion_facturacion`, `config_caja`, `config_tolerancias`, `config_seguridad` sembrados), Fase 14 (tabs de sucursal ya iniciados si se comparte shell).

### HU-F15.1 — Detalle de sucursal: datos generales + parametrización efectiva

**Given** que `sucursal` es real y funcional en lectura, bloqueada en escritura hasta sembrar `config_sucursal` (**ya sembrado desde 2026-09-03, migración 0002** — este recurso funciona en escritura desde antes de esta Parte II, no es un gap),
**When** el admin abre `/sucursales/:uuid`,
**Then** ve una vista con pestañas (General, Tarifas, Capacidad, Resoluciones, Caja, Documentos, Bitácora) y puede editar los datos generales con versionado.

**Reglas de negocio**
- BR1 (CU-11 real). Campos editables: `nombre`, `direccion`, `telefono`, `prefijo_nombre`, `ciudad`, `horario`, `uuid_tipo_sucursal`, `uuid_empresa` — exactamente las columnas reales de `sucursal` (`.mmd` línea 341-364). El corpus de CU original menciona además "Título Ticket", "Mensaje Salida", "Mensaje bienvenida" como si fueran de `sucursal`: **mensaje_bienvenida y mensaje_salida son columnas de `empresa`, no de `sucursal`** (`.mmd` línea 291-312) — se editan en la pantalla de Empresa (HU-F15.2), no aquí. No existe columna "Título Ticket" en ningún lado del ER; se documenta como `ABIERTO-50`.
- BR2 (CU-11 BR1, real). Una sucursal deshabilitada (`vigente_hasta` cerrado / `estado='inactivo'`) no acepta nuevos ingresos, pero sí permite registrar salidas — esto lo aplica `web_sucursal`; aquí solo se ofrece el botón "Deshabilitar" con el aviso de la consecuencia.
- BR3 (CU-11 E3, real). No se permite deshabilitar una sucursal con vehículos adentro (ingresos activos) o suscripciones vigentes que la referencian — 409 desde backend.
- BR4 (parametrización efectiva, DEC-ADM-10). Un selector de fecha (`?vigente_en=YYYY-MM-DD`) muestra qué tarifa/capacidad/resolución estaba vigente en esa fecha exacta, reutilizando el mismo filtro `vigente_en` en `tarifas_sucursal`, `cantidad_vehiculos_sucursal` y `resolucion_facturacion` (se agrega el filtro a los tres endpoints en esta HU, una sola vez, para no repetirlo en cada pestaña).

**Tablas ER**: `sucursal` ([V], real), `tipo_sucursal` (R), `empresa` (R, para el selector de empresa).

**Endpoints**: `GET/POST/PUT /api/v1/empresa/sucursal` (ya existe y ya funciona en escritura); **nuevo**: filtro `vigente_en` en `GET /empresa/tarifas-sucursal`, `GET /empresa/cantidad-vehiculos-sucursal`, `GET /empresa/resolucion-facturacion` (mismo patrón: `WHERE vigente_desde <= :fecha AND (vigente_hasta IS NULL OR :fecha < vigente_hasta)`).

**Componentes**: `SucursalDetalle.tsx` (shell de pestañas), `SucursalGeneralForm.tsx`, `ParametrizacionEfectivaSelector.tsx` (datepicker compartido por las 3 pestañas que lo usan).

**Validaciones**: `nombre` no vacío y único entre vigentes; `telefono` formato colombiano básico (no crítico, aviso no bloqueante).

**Errores**: 422 `nombre_duplicado`; 409 `sucursal_con_ocupacion` o `sucursal_con_suscripciones_vigentes` al deshabilitar.

**Pruebas**: e2e: editar datos generales (nueva versión, timeline), deshabilitar sucursal vacía (éxito), intentar deshabilitar una con ingresos activos (409), consultar parametrización efectiva en 3 fechas distintas.

**Tamaño**: ~320 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F15.1-T1 | `SucursalDetalle.tsx` con 7 pestañas (General/Tarifas/Capacidad/Resoluciones/Caja/Documentos/Bitácora) | `src/features/parametrizacion/pages/` |
| HU-F15.1-T2 | `SucursalGeneralForm.tsx` | `src/features/parametrizacion/components/` |
| HU-F15.1-T3 | **Backend**: filtro `vigente_en` en tarifas/capacidad/resolución | `backend/.../api/v1/empresa.py` |
| HU-F15.1-T4 | `ParametrizacionEfectivaSelector.tsx` + hook `useParametrizacionEfectiva` | `src/features/parametrizacion/` |
| HU-F15.1-T5 | e2e (4 escenarios) | `e2e/sucursal-general.spec.ts` |

---

### HU-F15.2 — Empresa: datos generales, mensajes de ticket, bitácora

**Given** que `empresa` es real y funcional en lectura, bloqueada en escritura hasta sembrar `config_empresa` (Fase 13),
**When** el admin edita razón social, NIT, régimen o los mensajes de bienvenida/salida del ticket,
**Then** el NIT se valida con módulo 11 antes de aceptar, y el cambio queda en la bitácora con hash chain.

**Reglas de negocio**
- BR1 (CU-11 BR2, real). El NIT de la empresa se imprime en tickets y FE (encabezado) — validación módulo 11 obligatoria antes de guardar.
- BR2 (real, `empresa` ER). Columnas editables: `nombre`, `nit`, `mensaje_bienvenida`, `mensaje_salida`, `regimen`. La numeración DIAN **no** vive aquí (se movió a `resolucion_facturacion`, una por sucursal — HU-F15.3).
- BR3 (CU-11 BR4, real). El `regimen` determina si se aplica IVA en el recibo — la UI solo lo captura; la lógica de aplicación vive en `web_sucursal`/backend de facturación, fuera de esta Parte II.

**Tablas ER**: `empresa` ([V], real), `log_transaccional` (R, para bitácora).

**Endpoints**: `GET/POST/PUT /api/v1/empresa/empresa` (ya existe, escritura habilitada por Fase 13).

**Componentes**: `EmpresaDetalle.tsx` (tabs General + Bitácora), `HashChainStatus.tsx` (badge verde/rojo, reutilizado también en Fase 20).

**Validaciones**: `src/lib/validation/nit.ts::validarNitModulo11(nit, dv)` — mismo algoritmo que valida el backend (módulo 11 sobre el NIT colombiano), para no aceptar en cliente lo que el servidor va a rechazar.

**Errores**: 422 `nit_invalido` con detalle del cálculo del dígito verificador (mismo formato que exige CU-11 E1).

**Pruebas**: e2e: editar empresa, NIT inválido → error inline con detalle, ver bitácora con al menos un cambio.

**Tamaño**: ~230 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F15.2-T1 | `src/lib/validation/nit.ts` | `src/lib/validation/nit.ts` |
| HU-F15.2-T2 | `EmpresaDetalle.tsx` (tabs) | `src/features/parametrizacion/pages/` |
| HU-F15.2-T3 | `HashChainStatus.tsx` | `src/components/` |
| HU-F15.2-T4 | Integración `GET/PUT /empresa/empresa` | `src/features/parametrizacion/` |
| HU-F15.2-T5 | e2e (2 escenarios) | `e2e/empresa.spec.ts` |

---

### HU-F15.3 — Resoluciones de facturación DIAN por sucursal

**Given** que `resolucion_facturacion` es real y funcional en lectura, bloqueada en escritura hasta sembrar `admin_resolucion_facturacion` (Fase 13, permiso **admin-only**: a diferencia de los demás recursos de `empresa.py`, este exige `issuer_required="admin-"` sin `operador-`, coherente con que la numeración DIAN es una decisión exclusivamente administrativa),
**When** el admin crea una resolución nueva para una sucursal,
**Then** valida `rango_hasta > rango_desde` y `fecha_fin_vigencia > fecha_inicio_vigencia`, y no permite dos resoluciones vigentes con el mismo `prefijo` para la misma sucursal.

**Reglas de negocio**
- BR1 (real, ER). El consecutivo actual **no** es una columna (eliminado por 4FN): se deriva como `MAX(factura_electronica.consecutivo)` por resolución, ya resuelto en el backend real con `SELECT ... FOR UPDATE` (`atomic_next_consecutivo.py`, verificado) — la UI solo lee ese máximo para mostrar cuánto rango queda, nunca lo calcula ni lo envía.
- BR2. Si el consecutivo más reciente está a menos de 100 números del `rango_hasta`, se muestra un banner amarillo "Rango por agotarse" — cálculo hecho en servidor (nuevo endpoint de solo lectura), no en cliente, para no depender de traer todo el historial de `factura_electronica`.
- BR3. No hay UI de "cambiar de proveedor DIAN" (DEC-ADM-15): el proveedor es configuración de despliegue, no de esta pantalla.

**Tablas ER**: `resolucion_facturacion` ([V], real), `factura_electronica` (R, para el consecutivo).

**Endpoints**: `GET/POST/PUT /api/v1/empresa/resolucion-facturacion` (ya existe, issuer `admin-` estricto); **nuevo**: `GET /api/v1/empresa/resolucion-facturacion/:uuid/consecutivo-actual` (devuelve `{ consecutivo_actual, rango_hasta, restantes, agotandose: bool }`).

**Componentes**: `ResolucionesDIAN.tsx` (árbol por sucursal), `ResolucionForm.tsx` (con los dos validadores de rango/fecha), banner de agotamiento inline en el árbol.

**Validaciones**: `rango_hasta > rango_desde`; `fecha_fin_vigencia > fecha_inicio_vigencia`; unicidad `(uuid_sucursal, prefijo)` entre vigentes.

**Errores**: 422 en cualquiera de las 3 validaciones anteriores.

**Pruebas**: e2e: crear resolución válida, rango inválido → 422, prefijo duplicado vigente → 422, banner de agotamiento visible cuando quedan <100 consecutivos (fixture con datos cercanos al límite).

**Tamaño**: ~260 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F15.3-T1 | Zod `resolucionFacturacion.ts` | `src/lib/schemas/` |
| HU-F15.3-T2 | `ResolucionesDIAN.tsx` + `ResolucionForm.tsx` | `src/features/parametrizacion/components/` |
| HU-F15.3-T3 | **Backend**: endpoint `consecutivo-actual` | `backend/.../api/v1/empresa.py` |
| HU-F15.3-T4 | Banner de agotamiento | `src/features/parametrizacion/` |
| HU-F15.3-T5 | e2e (4 escenarios) | `e2e/resoluciones-dian.spec.ts` |

---

### HU-F15.4 — Documentos de sucursal (logo, póliza RC, plantillas)

**Given** que `documentos` es real y funcional en lectura, bloqueada en escritura hasta sembrar `admin_documentos` (Fase 13),
**When** el admin sube un logo o una póliza de responsabilidad civil,
**Then** el archivo se guarda como base64 inline en `documento_b64`, con un límite de 1MB validado en el cliente antes de enviar (el backend también lo valida — doble defensa).

**Reglas de negocio**
- BR1 (CU-11 BR3, real). El logo se imprime en todos los tickets y en la FE — se sube una vez por sucursal, `documentos.tipo='logo'`.
- BR2 (adaptación documentada, no un hueco). El ER no tiene columna para "póliza de responsabilidad civil": se almacena como `documentos` con `tipo='certificado'`, `formato` describiendo el tipo MIME real del archivo subido (no fijo a `text/plain`: puede ser un PDF o imagen escaneada, y el `formato` debe reflejar el tipo real).
- BR3. El campo "Observaciones" que la auditoría de fidelidad detectó como ausente en los 3 documentos previos (INC-28/DEC-19 del digest) se agrega aquí como un cuarto tipo de documento, `tipo='observaciones'`, contenido de texto plano codificado en base64 — no requiere columna nueva, mismo patrón `documentos`.

**Tablas ER**: `documentos` ([V], real).

**Endpoints**: `GET/POST/PUT /api/v1/empresa/documentos?uuid_sucursal=X&tipo=` (ya existe).

**Componentes**: `SucursalDocumentos.tsx` (upload + preview + lista de 4 tipos: logo, certificado, plantilla_ticket, observaciones).

**Validaciones**: tamaño ≤ 1MB (verificado en cliente antes del base64 y de nuevo esperado del backend); `formato` coherente con el contenido real del archivo (no confiar en la extensión del nombre).

**Errores**: 422 `documento_demasiado_pesado`; 422 `formato_invalido`.

**Pruebas**: e2e: subir logo (preview visible), subir archivo >1MB (rechazado), ver los 4 tipos en la lista.

**Tamaño**: ~200 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F15.4-T1 | `SucursalDocumentos.tsx` (upload→base64→POST) | `src/features/parametrizacion/components/` |
| HU-F15.4-T2 | Validación de tamaño/formato en cliente | `src/lib/validation/documentos.ts` |
| HU-F15.4-T3 | e2e (3 escenarios) | `e2e/sucursal-documentos.spec.ts` |

---

### HU-F15.5 — Caja: base inicial, redondeo y tolerancias (CU-13 completo)

**Given** que `configuracion_caja` (nueva, Fase 13) y `configuracion_tolerancias` (real, escritura bloqueada hasta sembrar `config_tolerancias`, Fase 13) cubren juntas todo lo que CU-13 pide,
**When** el admin abre la pestaña "Caja" de una sucursal,
**Then** ve y edita en una sola pantalla: base inicial sugerida, redondeo, denominaciones permitidas (de `configuracion_caja`) y tolerancia de efectivo/datáfono (de `configuracion_tolerancias`) — dos tablas, una experiencia.

**Reglas de negocio**
- BR1 (CU-13 BR1, real, ver DEC-ADM-12). "Base inicial sugerida" pre-llena el formulario de apertura de turno en `web_sucursal`; el valor real contado en cada turno sigue siendo `sesion.valor_inicial_efectivo`/`valor_inicial_datafono`, que esta pantalla no toca.
- BR2 (CU-13 E1, real). Cambiar la base durante una jornada activa está permitido; los arqueos ya cerrados no se recalculan retroactivamente (versión bi-temporal estándar).
- BR3 (CU-13 E2, real). Un umbral de tolerancia inválido (negativo, o `tolerancia_efectivo`/`tolerancia_datafono` no numérico) se rechaza con 422.
- BR4 (patrón default+override, real). Ambas tablas soportan `uuid_sucursal IS NULL` como default global; la pantalla de sucursal edita el override específico, con un enlace a "ver/editar el default global" para el caso en que la sucursal no tenga override propio todavía.

**Tablas ER**: `configuracion_caja` (nueva, Fase 13), `configuracion_tolerancias` ([V], real).

**Endpoints**: `GET/POST/PUT /api/v1/configuracion/configuracion-caja` y `.../efectiva` (nuevos, Fase 13); `GET/POST/PUT /api/v1/configuracion/configuracion-tolerancias` y `.../efectiva` (ya existen).

**Componentes**: `SucursalCaja.tsx` (una pantalla, dos secciones/formularios: "Base y redondeo" + "Tolerancias de arqueo").

**Validaciones**: `base_inicial_sugerida >= 0`; `redondeo ∈ {ninguno, 100, 500, 1000}`; `denominaciones_permitidas` array de enteros positivos; `tolerancia_efectivo/datafono >= 0`.

**Errores**: 422 en cualquiera de las validaciones anteriores; 404 en `.../efectiva` si no hay override ni default global (mensaje explícito invitando a configurar el default global primero).

**Pruebas**: e2e: editar base+redondeo, editar tolerancias, consultar efectiva sin override (cae al default), consultar efectiva con override (lo prioriza).

**Tamaño**: ~210 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F15.5-T1 | `SucursalCaja.tsx` (dos secciones) | `src/features/parametrizacion/components/` |
| HU-F15.5-T2 | Zod `configuracionCaja.ts` + `configuracionTolerancias.ts` | `src/lib/schemas/` |
| HU-F15.5-T3 | Integración SWR + close+insert en ambas tablas | `src/features/parametrizacion/` |
| HU-F15.5-T4 | e2e (4 escenarios) | `e2e/sucursal-caja.spec.ts` |

---

## Fase 16 — Usuarios, perfiles y permisos (CU-08)

**Objetivo**: CU-08 es el único CU de esta Parte II sin ningún router backend hoy (confirmado: no existe `api/v1/usuarios.py` en el árbol real de 14 routers montados). Esta fase construye el CRUD completo, de cero, siguiendo el mismo patrón (`make_router`, versionado bi-temporal, permiso `admin_usuarios` — **ya sembrado** desde la migración 0002, no hace falta sembrarlo) que el resto del sistema.

**CUs cubiertos**: CU-08 (completo).
**Prereq**: Fase 13 (auth, permisos).

### HU-F16.1 — Backend: router `usuarios.py` completo

**Given** que `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal` y `login` son tablas reales del ER sin ningún endpoint HTTP propio hoy,
**When** se necesita cualquier operación de CU-08,
**Then** hace falta construir el router completo desde cero — a diferencia de casi todas las demás brechas de esta Parte II (que son "sembrar un permiso" o "agregar un filtro"), esta es la única brecha de tamaño comparable a un router nuevo completo.

**Reglas de negocio**
- BR1 (CU-08 BR1, real). `password_hash` con bcrypt cost 12 — mismo costo que ya usa `POST /auth/login` para verificar (`bcrypt.checkpw`), por consistencia.
- BR2 (reconciliación). CU-08 BR2 dice "username único (case-insensitive)" — el ER no tiene columna `username`: el identificador único real de negocio es `cedula` (UK, `.mmd` línea 13) y el identificador de login es `email`. Se reconcilia como: `cedula` única (case-sensitive, es un número de documento, no aplica case-insensitive), `email` único por construcción de uso (login), ambos validados en el formulario de creación.
- BR3 (CU-08 BR3, real, sin cambio de ER — ver DEC-ADM-03). 6 roles como valores libres de `usuarios.rol`: `Usuario, Facturador, Supervisor, Administrador, Auditor, Desarrollo`.
- BR4 (CU-08 BR4, real). `usuarios_sucursal` vacío = sin acceso a ninguna sucursal (no "todas") — se valida explícitamente al crear: si el wizard llega al paso de sucursales sin marcar ninguna, se advierte antes de confirmar (no se bloquea: puede ser intencional para un rol de solo-catálogo global).
- BR5 (CU-08 E3, real). No se permite desactivar al último usuario con permiso `admin_usuarios` activo — el backend cuenta cuántos `permisos_usuario` vigentes apuntan a ese código antes de cerrar la vigencia del usuario objetivo.
- BR6. Reset de password genera una temporal de 12 caracteres (mezcla de mayúsculas/minúsculas/dígitos/símbolos), fuerza cambio en el próximo login usando `configuracion_seguridad.dias_expiracion_password` (real, ya existe) — no se inventa una columna `debe_cambiar_password`: se compara `NOW() - usuarios.fecha_cambio_password > dias_expiracion_password` en el momento del login (mismo patrón "calculado, no almacenado" que el resto del sistema usa para estado derivado).

**Tablas ER**: `usuarios` ([V], real, INSERT/UPDATE vía close+insert), `permisos` (R, catálogo), `permisos_usuario` ([V], INSERT al otorgar / cierre de vigencia al revocar), `usuarios_sucursal` ([V], idem), `login` ([L-S], R/W para sesiones + historial).

**Endpoints (todos nuevos)**:
- `GET/POST /api/v1/usuarios` (mismo `make_router`, `permission_required="admin_usuarios"`)
- `GET /api/v1/usuarios/:uuid`
- `PUT /api/v1/usuarios/:uuid` (close+insert; incluye validación BR5 al pasar a `estado='inactivo'`)
- `GET/POST /api/v1/usuarios/:uuid/permisos` (lista permisos vigentes del usuario / otorga uno nuevo)
- `POST /api/v1/usuarios/:uuid/permisos/:uuid_permiso/revocar` (cierra vigencia — POST-shaped, nunca DELETE, mismo canon que todo el sistema)
- `POST /api/v1/usuarios/:uuid/reset-password`
- `GET/POST /api/v1/usuarios/:uuid/sucursales`
- `GET /api/v1/usuarios/:uuid/login?activo=&cursor=&limit=` (historial; `activo` se traduce a `timestamp_cierre IS NULL`, valor real de la columna, no un booleano nuevo)
- `POST /api/v1/usuarios/:uuid/login/:login_uuid/cerrar` (cierre forzado de sesión por un admin)

**Componentes**: ninguno en esta HU (backend puro); consumidos en HU-F16.2 a HU-F16.5.

**Validaciones**: Pydantic — `cedula` string 6-15 dígitos; `email: EmailStr`; `password` (creación) min 12 si se provee, o generado por el servidor si se omite; `rol: Literal[...]` con los 6 valores reales.

**Errores**: 422 `cedula_duplicada`; 422 `email_duplicado`; 422 `rol_invalido`; 409 `ultimo_admin_usuarios` al intentar desactivar el último con ese permiso.

**Pruebas**: tests de integración de cada endpoint + el caso límite del último `admin_usuarios`.

**Tamaño**: ~420 LOC (el router más grande de backend de toda esta Parte II, justificado por ser el único CU sin ningún andamiaje previo).

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F16.1-T1 | Schemas `UsuariosCreate/Read/Update/Filter/ReadList` (ya existen parcialmente en `schemas/auth.py` para `Permisos*`/`PermisosUsuario*`/`UsuariosSucursal*` — agregar los de `Usuarios`) | `backend/.../schemas/auth.py` |
| HU-F16.1-T2 | Router `usuarios.py`: CRUD base vía `make_router` | `backend/.../api/v1/usuarios.py` (nuevo) |
| HU-F16.1-T3 | Endpoints custom: permisos (otorgar/revocar), reset-password, sucursales, login history, cerrar sesión | `backend/.../api/v1/usuarios.py` |
| HU-F16.1-T4 | Validación "último admin_usuarios" | `backend/.../api/v1/usuarios.py` |
| HU-F16.1-T5 | Montar el router nuevo en `api/v1/__init__.py` | `backend/.../api/v1/__init__.py` |
| HU-F16.1-T6 | Tests de integración (9 endpoints + caso límite) | `backend/tests/integration/test_usuarios.py` |

---

### HU-F16.2 — Listado y creación de usuarios

**Given** el router de HU-F16.1 ya montado,
**When** el admin abre `/usuarios`,
**Then** ve una tabla filtrable por rol/sucursal/estado, y un wizard de 3 pasos para crear uno nuevo (datos → rol → sucursales).

**Reglas de negocio**: BR2/BR3/BR4 de HU-F16.1, aplicadas en el formulario.

**Tablas ER**: `usuarios`, `usuarios_sucursal`.

**Endpoints**: `GET/POST /api/v1/usuarios`.

**Componentes**: `UsuariosList.tsx` (DataTable con filtros), `UsuarioCrear.tsx` (wizard 3 pasos: `DatosPersonalesStep`, `RolStep`, `SucursalesStep`).

**Validaciones**: Zod espejo de HU-F16.1 (`cedula`, `email`, `rol` enum, `password` opcional min 12).

**Errores**: 422 `cedula_duplicada`/`email_duplicado` mostrados inline en el paso correspondiente del wizard.

**Pruebas**: e2e: crear usuario completo, cédula duplicada → error en paso 1, no continuar sin al menos advertir en paso 3 si no se marcó ninguna sucursal.

**Tamaño**: ~260 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F16.2-T1 | Zod `usuarios.ts` | `src/lib/schemas/usuarios.ts` |
| HU-F16.2-T2 | `UsuariosList.tsx` | `src/features/usuarios/pages/` |
| HU-F16.2-T3 | `UsuarioCrear.tsx` (wizard) | `src/features/usuarios/pages/` |
| HU-F16.2-T4 | e2e (3 escenarios) | `e2e/usuarios-crear.spec.ts` |

---

### HU-F16.3 — Detalle de usuario: permisos por árbol

**Given** que `permisos` tiene hoy 31 códigos reales sembrados (15 operativos de `0001_initial_schema.py` + 16 transversales de `0002_seed_permisos_canonicos.py`, más los 9 que agrega Fase 13),
**When** el admin abre la pestaña Permisos de un usuario,
**Then** ve el árbol agrupado por prefijo semántico (`config_*`, `admin_*`, `gestionar_*`, resto operativo) con checkboxes: marcar otorga (`POST .../permisos`), desmarcar revoca (`POST .../revocar`, cierre de vigencia — nunca `DELETE`).

**Reglas de negocio**
- BR1. Otorgar un permiso ya vigente para ese usuario es un no-op idempotente (el backend responde 200 sin duplicar fila).
- BR2. Revocar es un cierre de vigencia (`vigente_hasta=NOW()`), nunca un borrado — el histórico de cuándo tuvo cada permiso queda completo en la bitácora.

**Tablas ER**: `permisos` (R), `permisos_usuario` ([V], W).

**Endpoints**: `GET/POST /api/v1/usuarios/:uuid/permisos`, `POST /api/v1/usuarios/:uuid/permisos/:uuid_permiso/revocar` (HU-F16.1).

**Componentes**: `UsuarioDetalle.tsx` (4 pestañas: Datos, Permisos, Sucursales, Bitácora), `PermisosTree.tsx`.

**Validaciones**: ninguna de formulario (checkboxes puros).

**Errores**: 403 si el propio admin no tiene `admin_usuarios` (el backend lo exige para escribir en este recurso).

**Pruebas**: e2e: otorgar un permiso, revocarlo, ver la bitácora reflejar ambas transiciones.

**Tamaño**: ~220 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F16.3-T1 | `UsuarioDetalle.tsx` (4 tabs) | `src/features/usuarios/pages/` |
| HU-F16.3-T2 | `PermisosTree.tsx` (agrupado por prefijo) | `src/features/usuarios/components/` |
| HU-F16.3-T3 | Reutilizar bitácora (`LogTransaccional`, Fase 20) filtrada por `tabla_afectada IN ('usuarios','permisos_usuario')` | `src/features/usuarios/` |
| HU-F16.3-T4 | e2e (2 escenarios) | `e2e/usuarios-detalle.spec.ts` |

---

### HU-F16.4 — Reset de password, sucursales asignadas y último admin

**Given** que `configuracion_seguridad` ya define `dias_expiracion_password`/`max_intentos_login`/`minutos_bloqueo_login` (real, override por sucursal),
**When** el admin resetea la password de un usuario,
**Then** recibe una temporal de 12 caracteres una sola vez en pantalla (nunca se re-muestra), y el usuario debe cambiarla en su próximo login si excede `dias_expiracion_password` desde ese reset.

**Reglas de negocio**: BR5/BR6 de HU-F16.1.

**Tablas ER**: `usuarios` (W, `password_hash`/`fecha_cambio_password`), `usuarios_sucursal` ([V], W), `configuracion_seguridad` (R).

**Endpoints**: `POST /api/v1/usuarios/:uuid/reset-password`, `GET/POST /api/v1/usuarios/:uuid/sucursales` (HU-F16.1).

**Componentes**: `ResetPasswordModal.tsx` (muestra la temporal una vez, con botón "Copiar"), `SucursalesAsignadas.tsx` (tabla de asignación/revocación).

**Validaciones**: ninguna de formulario adicional.

**Errores**: 409 `ultimo_admin_usuarios` al intentar desactivar/quitar el último con ese permiso.

**Pruebas**: e2e: reset password (temporal visible una vez), asignar/revocar sucursal, intentar desactivar el último `admin_usuarios` → 409.

**Tamaño**: ~200 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F16.4-T1 | `ResetPasswordModal.tsx` | `src/features/usuarios/components/` |
| HU-F16.4-T2 | `SucursalesAsignadas.tsx` | `src/features/usuarios/components/` |
| HU-F16.4-T3 | e2e (3 escenarios) | `e2e/usuarios-reset.spec.ts` |

---

### HU-F16.5 — Sesiones activas e historial de login

**Given** que `login` es `[L-S]` real (lifecycle con `timestamp_cierre` set solo en el logout),
**When** el admin necesita cerrar remotamente la sesión de un usuario (p. ej. tras un reset de password),
**Then** ve las filas con `timestamp_cierre IS NULL` como "activas" y puede cerrarlas una a una.

**Reglas de negocio**: mismo patrón que `POST /auth/logout` ya usa internamente (`close_login_with_log`), expuesto aquí para que un admin lo dispare sobre la sesión de otro usuario.

**Tablas ER**: `login` ([L-S], real).

**Endpoints**: `GET /api/v1/usuarios/:uuid/login?activo=true`, `POST /api/v1/usuarios/:uuid/login/:login_uuid/cerrar` (HU-F16.1).

**Componentes**: `SesionesActivas.tsx`, `LoginHistory.tsx` (paginación cursor).

**Validaciones**: ninguna.

**Errores**: 404 si el `login_uuid` ya está cerrado (idempotente: 200 si ya estaba cerrado, no error).

**Pruebas**: e2e: ver sesiones activas, cerrar una, verla desaparecer de "activas" y aparecer en historial con `estado='cerrado'`.

**Tamaño**: ~140 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F16.5-T1 | `SesionesActivas.tsx` | `src/features/usuarios/components/` |
| HU-F16.5-T2 | `LoginHistory.tsx` | `src/features/usuarios/components/` |
| HU-F16.5-T3 | e2e (2 escenarios) | `e2e/usuarios-sesiones.spec.ts` |

---

## Fase 17 — Reportería y analítica (CU-09)

**Objetivo**: extender el dashboard ejecutivo ya real (`admin_views.py`) con más KPIs y gráficas, y construir las 3 vistas de reportería (operacional, financiera, suscripciones) que hoy no existen — con especial cuidado en la vista financiera, donde la auditoría de fidelidad detectó columnas inventadas (`numero_completo`, `iva`, `estado` directamente sobre `facturas`, ninguna real).

**CUs cubiertos**: CU-09 (completo).
**Prereq**: Fase 13.

### HU-F17.1 — Cerrar el placeholder de `ingresos_monto_total` y ampliar el dashboard ejecutivo

**Given** que `GET /admin/sucursales/{uuid}/dashboard` (real, ya construido) devuelve **siempre `0.0`** en `ingresos_monto_total` — confirmado literalmente en el código: *"`ingreso` carries no monetary column... reported as 0.0 until the salidas/facturas join lands"* —,
**When** el admin mira el dashboard hoy,
**Then** ve un monto de ingresos que nunca refleja la realidad, sin ningún error visible que lo delate — es un placeholder silencioso, el tipo de brecha más peligrosa porque no falla, solo miente.

**Reglas de negocio**
- BR1. El monto real de un ingreso se obtiene siguiendo la cadena `ingreso → salidas → facturas` (vía `facturas.uuid_ingreso`), sumando `facturas.total` para las facturas cuyo `uuid_ingreso` cae en el rango de fecha consultado — no hay atajo: `ingreso` en sí mismo nunca tuvo columna de monto (por diseño 4FN, el monto es un hecho de la factura, no del ingreso).
- BR2. Las 6 tarjetas adicionales del dashboard ejecutivo (ocupación agregada, suscripciones activas, medios de pago del día, top-5 sucursales por ingresos, estado de sync agregado, alertas por severidad) se calculan con consultas de agregación directas sobre las tablas reales — no se asume la existencia de vistas materializadas que no fueron verificadas; si el volumen de datos lo justifica más adelante, se evalúa una vista materializada como mejora de rendimiento (ver `RIESGO-ADM-09`), no como prerequisito de esta HU.

**Tablas ER**: `ingreso` (R), `salidas` (R), `facturas` (R), `subscripciones_cliente` (R), `factura_pagos` (R), `sync_log` (R), `alerta` (R).

**Endpoints**: `GET /api/v1/admin/sucursales/{uuid}/dashboard` (modificado: `ingresos_monto_total` real); `GET /api/v1/admin/dashboard/resumen?sucursales=X,Y,Z` (nuevo, agrega las 6 tarjetas adicionales para el conjunto de sucursales permitidas del actor).

**Componentes**: `KpiCard.tsx` (con skeleton), `useKpiData.ts` (SWR, una clave por tarjeta), 4 gráficas: `ChartLine` (ingresos 30 días), `ChartBar` (top-5 sucursales), `ChartPie` (estado FE 24h), `HeatmapOcupacion` (24h × N sucursales, con dynamic import para no inflar el bundle inicial).

**Validaciones**: ninguna de formulario.

**Errores**: si una sucursal del conjunto falla en su agregación individual, el resumen devuelve parcial con `errores: [{uuid_sucursal, motivo}]` en vez de fallar completo (resiliencia: un dato malo no debe tumbar el dashboard entero).

**Pruebas**: test de integración del cálculo real de `ingresos_monto_total` contra fixtures con ingreso→salida→factura completos; e2e de las 9 tarjetas + 4 gráficas con mock.

**Tamaño**: ~380 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F17.1-T1 | **Backend**: reemplazar el placeholder `0.0` por la agregación real ingreso→salida→factura | `backend/.../api/v1/admin_views.py` |
| HU-F17.1-T2 | **Backend**: `GET /admin/dashboard/resumen` (6 agregaciones) | `backend/.../api/v1/admin_views.py` |
| HU-F17.1-T3 | `useKpiData.ts` (9 claves SWR) | `src/features/dashboard/hooks/` |
| HU-F17.1-T4 | Ampliar `Dashboard.tsx` a grid 3×3 | `src/pages/Dashboard.tsx` → `src/features/dashboard/pages/` |
| HU-F17.1-T5 | 4 componentes de charts con dynamic import | `src/components/charts/` |
| HU-F17.1-T6 | Test de integración del monto real + e2e | `backend/tests/integration/`, `e2e/dashboard.spec.ts` |

---

### HU-F17.2 — Reportería operacional (ingresos, salidas, ocupación)

**Given** que no existe ningún endpoint de reportería operacional hoy,
**When** el admin necesita ver ingresos filtrados por sucursal/fecha/tipo, tiempos de estancia y ocupación,
**Then** un endpoint nuevo agrega sobre `ingreso`/`salidas` con filtros de servidor y paginación cursor estándar.

**Reglas de negocio**
- BR1. Tiempo de estancia = `salidas.fecha_salida - ingreso.fecha_ingreso`, promedio/máximo/mínimo agrupado por sucursal y día — se calcula en la consulta, no se persiste.
- BR2. Ocupación = ingresos con estado derivado "activo" (sin salida no anulada, mismo criterio `V_INGRESO_ESTADO` que usa `web_sucursal` y que hoy se resuelve con query ad-hoc, no con vista SQL — se reutiliza el mismo criterio, no se inventa uno nuevo) dividido por `cantidad_vehiculos_sucursal.cantidad` del tipo correspondiente.

**Tablas ER**: `ingreso` (R), `salidas` (R), `cantidad_vehiculos_sucursal` (R), `sucursal` (R), `tipos_vehiculo` (R).

**Endpoints**: `GET /api/v1/admin/reporteria/operacional?uuid_sucursal=&desde=&hasta=&uuid_tipo_vehiculo=&cursor=&limit=` (ingresos + tiempos de estancia); `GET /api/v1/admin/reporteria/ocupacion?desde=&hasta=` (heatmap 24h × N sucursales).

**Componentes**: `ReporteriaOperacional.tsx` (tabs: Ingresos, Salidas, Ocupación), `useReporteriaData.ts`.

**Validaciones**: rango `desde <= hasta`; ambos requeridos si se pide exportar (no se permite exportar "todo el histórico" sin acotar).

**Errores**: 422 `rango_fecha_invalido`.

**Pruebas**: e2e: aplicar filtros, ver heatmap con datos reales de fixture, exportar CSV filtrado.

**Tamaño**: ~330 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F17.2-T1 | **Backend**: `GET /admin/reporteria/operacional` | `backend/.../api/v1/admin_views.py` |
| HU-F17.2-T2 | **Backend**: `GET /admin/reporteria/ocupacion` | `backend/.../api/v1/admin_views.py` |
| HU-F17.2-T3 | `ReporteriaOperacional.tsx` | `src/features/reporteria/pages/` |
| HU-F17.2-T4 | `HeatmapOcupacion.tsx` con datos reales (reutiliza el de Fase 17.1) | `src/features/reporteria/` |
| HU-F17.2-T5 | e2e (2 escenarios) | `e2e/reporteria-operacional.spec.ts` |

---

### HU-F17.3 — Reportería financiera (facturas, FE, pagos) — corrección de columnas

**Given** que un documento previo definía esta pantalla con columnas `numero_completo, subtotal, iva, total, estado` **directamente sobre `facturas`**, ninguna de las cuales existe ahí (`facturas` real: `uuid, uuid_sucursal, subtotal, descuento, total, uuid_ingreso, uuid_salida, fecha_retencion_hasta` — sin `iva`, sin `estado`, sin `numero_completo`),
**When** se construye la tabla de facturas del admin,
**Then** cada columna se resuelve contra su tabla real: `numero_completo` = `prefijo + consecutivo` de `factura_electronica` (JOIN, solo si la factura tiene FE asociada); `iva` = suma de `factura_impuestos.valor` de esa factura (JOIN + agregación, snapshot ya persistido); `estado` = derivado en la consulta (no hay `V_FACTURA_ESTADO` ni como vista ni como endpoint — se calcula ad-hoc, mismo patrón que ya usa el backend real para `V_INGRESO_ESTADO` y `V_ARQUEO_DIFERENCIAS`: `EXISTS anulaciones ejecutada` sobre el `uuid_ingreso`/`uuid_salida` de la factura → `'anulada'`, si no → `'vigente'`).

**Reglas de negocio**
- BR1. El estado DIAN de la FE (`estado_dian`) es distinto del estado de la factura interna: se lee de `factura_electronica` + la vista real `v_factura_electronica_acuse` (existe de verdad, migración `0009_add_derived_read_views.py`, columnas `uuid_factura_electronica, cufe, estado, timestamp_evento` — **no** tiene `reportado_dian`, así que la UI muestra el `estado` crudo, uno de `pendiente|enviado|aceptado|rechazado`, nunca un booleano inventado).
- BR2. Los pagos se desglosan por `medio_pago` (`efectivo|datafono|transferencia`, valores reales de `factura_pagos`) sumando `valor` agrupado por día — un `tipo_movimiento='reverso'` resta en vez de sumar (nunca se filtra fuera: un reverso es tan real como el pago que revierte).

**Tablas ER**: `facturas` (R), `factura_electronica` (R), `factura_impuestos` (R), `factura_pagos` (R), `anulaciones` (R), `v_factura_electronica_acuse` (vista real, R).

**Endpoints**: `GET /api/v1/admin/reporteria/facturas?uuid_sucursal=&desde=&hasta=&cursor=&limit=`; `GET /api/v1/admin/reporteria/fe?estado=&cursor=&limit=` (usa `v_factura_electronica_acuse`); `GET /api/v1/admin/reporteria/pagos?uuid_sucursal=&desde=&hasta=` (agregado por `medio_pago`).

**Componentes**: `ReporteriaFinanciera.tsx` (tabs: Facturas, FE, Pagos), con columna `estado` mostrando un badge (`vigente`/`anulada`) y columna `estado_dian` separada y claramente etiquetada como distinta.

**Validaciones**: mismas de rango de fecha que HU-F17.2.

**Errores**: 422 `rango_fecha_invalido`.

**Pruebas**: test de integración verificando que `numero_completo`/`iva`/`estado` se resuelven vía los JOIN correctos (no como columnas directas); e2e de las 3 pestañas + drill-down a detalle de FE (placeholder, se completa en Fase 19 con el monitor DIAN).

**Tamaño**: ~350 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F17.3-T1 | **Backend**: `GET /admin/reporteria/facturas` con JOIN a `factura_electronica`+`factura_impuestos`+estado ad-hoc | `backend/.../api/v1/admin_views.py` |
| HU-F17.3-T2 | **Backend**: `GET /admin/reporteria/fe` sobre `v_factura_electronica_acuse` | `backend/.../api/v1/admin_views.py` |
| HU-F17.3-T3 | **Backend**: `GET /admin/reporteria/pagos` agregado por medio | `backend/.../api/v1/admin_views.py` |
| HU-F17.3-T4 | `ReporteriaFinanciera.tsx` | `src/features/reporteria/pages/` |
| HU-F17.3-T5 | Test de integración de las 3 resoluciones de columna + e2e | `backend/tests/integration/`, `e2e/reporteria-financiera.spec.ts` |

---

### HU-F17.4 — Reportería de suscripciones + exportes CSV/PDF

**Given** que `subscripciones_cliente` es real (Fase 20 construye su CRUD; esta HU solo lee para reportería agregada),
**When** el admin necesita ver cohortes de retención y exportar cualquier tabla de reportería,
**Then** un endpoint agrega por mes de alta y calcula el % que sigue vigente N meses después, y cada `DataTable` de reportería ofrece "Exportar CSV".

**Reglas de negocio**
- BR1. Cohorte = agrupar `subscripciones_cliente` por mes de `fecha_inicio_cobertura`; retención en el mes M = % de esa cohorte con `fecha_vencimiento >= inicio_cohorte + M meses` (aproximación por antigüedad, sin necesitar una tabla de eventos de cancelación que no existe).
- BR2. CSV en formato RFC 4180, columnas en español, encoding UTF-8 con BOM (para que Excel en Windows lo abra sin mojibake) — respeta los filtros activos de la tabla en pantalla, nunca exporta "todo" silenciosamente.
- BR3. Exporte PDF firmado (hash SHA256 embebido) se implementa específicamente para arqueos (Fase 18), no para reportería general — CU-09 solo pide CSV/PDF genérico, y el único CU que pide explícitamente un documento "firmado" para auditores externos es CU-10.

**Tablas ER**: `subscripciones_cliente` (R).

**Endpoints**: `GET /api/v1/admin/reporteria/suscripciones/cohorte?desde=&hasta=`.

**Componentes**: `SuscripcionesCohorte.tsx` (heatmap de cohortes), `SuscripcionesPorVencer.tsx` (lista top-20 con badge amarillo, reutilizando el mismo criterio de "próximas a vencer" que Fase 20 define para la vista de clientes — una sola función compartida `diasParaVencer()`, no dos implementaciones divergentes), `src/lib/export/csv.ts`.

**Validaciones**: rango de fecha para la cohorte.

**Errores**: 422 `rango_fecha_invalido`.

**Pruebas**: unit de `exportToCSV` (quoting RFC 4180, BOM); e2e de cohortes + exportar CSV desde las 3 pantallas de reportería.

**Tamaño**: ~280 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F17.4-T1 | **Backend**: `GET /admin/reporteria/suscripciones/cohorte` | `backend/.../api/v1/admin_views.py` |
| HU-F17.4-T2 | `SuscripcionesCohorte.tsx` + `SuscripcionesPorVencer.tsx` | `src/features/reporteria/` |
| HU-F17.4-T3 | `src/lib/export/csv.ts` + botón "Exportar CSV" en las 3 pantallas de reportería | `src/lib/export/`, `src/features/reporteria/` |
| HU-F17.4-T4 | Tests unit + e2e | `src/lib/export/__tests__/`, `e2e/reporteria-suscripciones.spec.ts` |

---

## Fase 18 — Arqueos y auditoría de caja (CU-10, lado admin)

**Objetivo**: CU-10 aclara explícitamente que la operación (apertura, conteo, justificación) es de `web_sucursal`; el admin **solo audita**: lista, filtra, ve diferencias y exporta evidencia firmada. `GET /caja/arqueo` y `GET /caja/arqueo/resumen` ya existen como montaje de solo lectura (`write_enabled=False`), pero sin filtros de consulta más allá de cursor/límite — se completan aquí.

**CUs cubiertos**: CU-10 (lado admin, auditoría).
**Prereq**: Fase 13.

### HU-F18.1 — Backend: filtros de consulta en `GET /caja/arqueo`

**Given** que el `list_endpoint` genérico de `router_factory.py` solo acepta `cursor`/`limit` (verificado leyendo el código: no hay parámetros de filtro arbitrarios en el listado estándar de ningún recurso `[V]`/`[A]` del sistema),
**When** el admin necesita "arqueos de la sucursal X entre el 1 y el 15 de marzo, tipo cierre_turno",
**Then** hace falta un filtro real por `uuid_sucursal`, `uuid_tipo_arqueo` y rango de fecha (`fecha_retencion_hasta` no sirve para esto — el filtro correcto es sobre `created_at`, que sí existe en toda tabla `[A]`).

**Reglas de negocio**
- BR1. Este mismo patrón de filtro (`uuid_sucursal`, rango de fecha) se necesita en más de un recurso `[A]` de esta Parte II (arqueos aquí; `log_transaccional` en Fase 20) — se implementa como una utilidad reutilizable de query-params en `router_factory.py` en vez de repetir la lógica en cada endpoint custom.
- BR2 (CU-10 AC2, real). El supervisor ve todos los arqueos con filtros por sucursal, fecha y cajero (`usuarios.uuid` vía `arqueo.created_by`, ya real) — sin necesitar un nuevo campo, solo exponer el filtro.

**Tablas ER**: `arqueo` ([A], real), `tipo_arqueo` (R), `usuarios` (R, para filtrar por cajero).

**Endpoints**: `GET /api/v1/caja/arqueo?uuid_sucursal=&uuid_tipo_arqueo=&desde=&hasta=&created_by=&cursor=&limit=` (extendido).

**Componentes**: ninguno en esta HU (backend puro).

**Validaciones**: `desde <= hasta`; `uuid_tipo_arqueo` debe existir en el catálogo real.

**Errores**: 422 `rango_fecha_invalido`.

**Pruebas**: test de integración de cada combinación de filtro + combinación de todos a la vez.

**Tamaño**: ~90 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F18.1-T1 | Utilidad de filtros de query reutilizable | `backend/.../api/router_factory.py` o helper nuevo |
| HU-F18.1-T2 | Aplicar a `GET /caja/arqueo` | `backend/.../api/v1/caja.py` |
| HU-F18.1-T3 | Tests de integración | `backend/tests/integration/` |

---

### HU-F18.2 — Listado y detalle de arqueos, con diferencias

**Given** que `GET /caja-sesion/arqueos/{uuid}/diferencias` **ya existe y funciona** (calcula esperado-vs-reportado en el momento de la consulta, sin depender de ninguna vista SQL — confirmado por lectura directa del código real),
**When** el admin abre el detalle de un arqueo,
**Then** ve el desglose completo (efectivo/datáfono esperado vs. reportado, diferencia, justificación) reutilizando ese endpoint tal cual, sin reconstruir el cálculo en el frontend.

**Reglas de negocio**
- BR1 (CU-10 BR2, real). `descuadre_pct = ((monto_real - monto_esperado) / monto_esperado) * 100` — se muestra como dato informativo adicional en la UI (el backend ya devuelve los valores absolutos; el porcentaje se calcula en cliente solo para mostrar, la decisión de alerta real la toma el backend contra `configuracion_tolerancias`, valores absolutos — DEC-ADM que ya viene de Fase 13/15).
- BR2 (CU-10 BR4, real). El cierre nunca modifica `factura_pagos` — la UI de detalle deja explícito que los pagos mostrados son de solo lectura, inmutables, sin ningún botón de edición sobre ellos.
- BR3. Si `|diferencia| > tolerancia` (leída de `configuracion_tolerancias` efectiva de esa sucursal, real), el detalle muestra un enlace directo a la alerta `descuadre_critico` asociada (`alerta.uuid_arqueo`, FK real) si ya fue generada por el backend.

**Tablas ER**: `arqueo` (R), `configuracion_tolerancias` (R, vía `.../efectiva`), `alerta` (R).

**Endpoints**: `GET /api/v1/caja/arqueo?...` (HU-F18.1), `GET /api/v1/caja-sesion/arqueos/{uuid}/diferencias` (ya existe).

**Componentes**: `ArqueosList.tsx` (DataTable con los filtros de HU-F18.1), `ArqueoDetalle.tsx` (`DiferenciasPanel` + enlace a alerta si existe).

**Validaciones**: ninguna de formulario (solo lectura).

**Errores**: 404 si el `uuid` de arqueo no existe (mismo contrato del endpoint real).

**Pruebas**: e2e: listar con filtros, ver detalle con diferencia dentro de tolerancia (sin alerta) y fuera de tolerancia (con enlace a alerta).

**Tamaño**: ~250 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F18.2-T1 | `ArqueosList.tsx` | `src/features/arqueos/pages/` |
| HU-F18.2-T2 | `ArqueoDetalle.tsx` + `DiferenciasPanel.tsx` | `src/features/arqueos/pages/`, `src/features/arqueos/components/` |
| HU-F18.2-T3 | Integración SWR (arqueo + diferencias + tolerancia efectiva + alerta enlazada) | `src/features/arqueos/hooks/` |
| HU-F18.2-T4 | e2e (2 escenarios) | `e2e/arqueos-list.spec.ts` |

---

### HU-F18.3 — Resumen de arqueos por sesión y por día

**Given** que CU-10 distingue tres flujos reales (`cierre_turno`, `auditoria`, `cierre_sesion` — los 3 códigos reales de `tipo_arqueo`; "arqueo parcial"/"cierre diario" del corpus de CU original son nombres de negocio para estos mismos 3, no un 4º valor `cierre_dia` que un plan previo proponía sembrar sin respaldo en el ER ni en el catálogo real),
**When** el admin necesita ver, para un día, el resumen de todas las sesiones (cajero, apertura, cierre, base, esperado, reportado, diferencia, justificado),
**Then** un endpoint agrega `sesion` con `factura_pagos` sumado por sesión, sin modificar ningún registro (CU-10 BR4).

**Reglas de negocio**
- BR1. Una fila del resumen = una `sesion` del día consultado, con sus arqueos de tipo `cierre_turno`/`cierre_sesion` asociados (`arqueo.uuid_sesion`).
- BR2. El "cierre diario" real (agregación de todas las sesiones del día en una sola sucursal) corresponde al tipo `auditoria` cuando `uuid_sesion IS NULL` (arqueo de todo el día, no de una sesión específica) — se filtra explícitamente por esa combinación, no por un tipo inventado.

**Tablas ER**: `sesion` (R), `arqueo` (R), `factura_pagos` (R), `usuarios` (R).

**Endpoints**: `GET /api/v1/caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD` (nuevo, JOIN `sesion`+`arqueo`+suma de `factura_pagos` por sesión).

**Componentes**: `ArqueosResumen.tsx` (DataTable agrupada por sesión).

**Validaciones**: `fecha` requerida, formato ISO.

**Errores**: 422 `fecha_invalida`.

**Pruebas**: e2e: resumen con 3 sesiones del mismo día, ver arqueo de tipo `auditoria` con `uuid_sesion=NULL` (cierre de todo el día).

**Tamaño**: ~180 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F18.3-T1 | **Backend**: `GET /caja/arqueo/resumen` | `backend/.../api/v1/caja.py` |
| HU-F18.3-T2 | `ArqueosResumen.tsx` | `src/features/arqueos/pages/` |
| HU-F18.3-T3 | e2e (2 escenarios) | `e2e/arqueos-resumen.spec.ts` |

---

### HU-F18.4 — Exportar PDF firmado para auditoría externa

**Given** que CU-09 pide exportes CSV/PDF y CU-10 es el único caso de uso que requiere explícitamente evidencia "firmada" para auditores externos,
**When** el admin exporta el detalle de un arqueo o el resumen de un día,
**Then** el PDF incluye un hash SHA256 del contenido embebido en el pie de página, calculable independientemente para verificar que el documento no fue alterado tras la exportación.

**Reglas de negocio**
- BR1. El hash se calcula sobre el contenido tabular exacto exportado (no sobre el PDF final, que incluiría metadatos variables como la fecha de generación) — se muestra el algoritmo y el valor en el propio documento para que sea verificable manualmente.
- BR2. El PDF incluye encabezado con logo de la sucursal (`documentos.tipo='logo'`, Fase 15) cuando existe.

**Tablas ER**: ninguna nueva (consume lo ya expuesto por HU-F18.2/F18.3).

**Endpoints**: ninguno nuevo (el hash se calcula en cliente sobre los datos ya recibidos).

**Componentes**: `src/lib/export/pdf.ts` (usa una librería de generación de PDF en cliente), integrado en `ArqueoDetalle.tsx` y `ArqueosResumen.tsx`.

**Validaciones**: ninguna.

**Errores**: si la generación falla (memoria, dataset muy grande), se muestra error explícito, nunca un PDF corrupto silencioso.

**Pruebas**: unit de generación de PDF + verificación de que el hash embebido coincide con el hash recalculado del contenido tabular.

**Tamaño**: ~150 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F18.4-T1 | `src/lib/export/pdf.ts` con hash SHA256 embebido | `src/lib/export/` |
| HU-F18.4-T2 | Integrar botón "Exportar PDF firmado" en detalle y resumen | `src/features/arqueos/` |
| HU-F18.4-T3 | Tests unit (generación + verificación de hash) | `src/lib/export/__tests__/` |

---

## Fase 19 — Sincronización, pairing y monitoreo de alertas (CU-07 admin, CU-14)

**Objetivo**: dar visibilidad cross-sucursal del estado de sincronización (CU-07 lado admin), completar el ciclo de vida de pairing (ya construido en el backend, solo falta consumirlo desde UI) y construir la bandeja de alertas con su flujo de revisión real. Verificado exhaustivamente: `api/v1/sync_router.py` **no** tiene ningún endpoint de lectura agregada — sus 7 endpoints (`hello, pair, push, pull, heartbeat, rotate-jwt, events`) son el protocolo que la sucursal usa para hablar con el cloud, no endpoints para que el admin monitoree. `sync_log` y `sync_conflict` no tienen ningún router montado hoy.

**CUs cubiertos**: CU-07 (lado admin: monitoreo + pairing), CU-14 (completo).
**Prereq**: Fase 13 (incluye `GET /envio-dian`, `GET /validacion-evento` de HU-F13.4).

### HU-F19.1 — Backend: lecturas de `sync_log`, `sync_conflict` y estado agregado

**Given** que ambas tablas son reales y ninguna tiene endpoint de lectura hoy,
**When** el admin necesita ver el histórico de ciclos de sincronización o los conflictos detectados,
**Then** dos endpoints nuevos de solo lectura (cursor-paginados, mismo contrato estándar) los exponen, más un tercero agregado que clasifica cada sucursal en verde/amarillo/rojo (CU-14 AC5, real).

**Reglas de negocio**
- BR1 (CU-14 BR3, real). El estado de sync (verde/amarillo/rojo) se calcula en tiempo de consulta, nunca se persiste — verde: última fila de `sync_log` de esa sucursal hace menos de 60s de lag; amarillo: 60-300s; rojo: sync fallida o más de 300s sin ciclo exitoso. Estos 3 umbrales replican el patrón `queue_depth`/`lag_seconds` que `admin_views.py::branch_dashboard` ya calcula hoy para una sola sucursal — se generaliza a "todas las permitidas" en un solo endpoint.
- BR2. Un conflicto (`sync_conflict`) muestra `datos_local` vs `datos_cloud` lado a lado; el campo `resolucion` (real, ya en el ER) documenta qué política se aplicó (`last-write-wins` por defecto, según CU-07 BR real) — esta fase no agrega un mecanismo de resolución manual nuevo si no lo pide ningún CU explícitamente (queda como `ABIERTO-51` si el negocio lo pide más adelante).

**Tablas ER**: `sync_log` ([A], real), `sync_conflict` ([A], real), `sucursal` (R).

**Endpoints**: `GET /api/v1/admin/sync/log?uuid_sucursal=&desde=&hasta=&cursor=&limit=`; `GET /api/v1/admin/sync/conflict?uuid_sucursal=&cursor=&limit=`; `GET /api/v1/admin/sync/estado` (agregado, una fila por sucursal permitida, con clasificación verde/amarillo/rojo).

**Componentes**: ninguno en esta HU (backend puro).

**Validaciones**: rango de fecha estándar.

**Errores**: 422 `rango_fecha_invalido`.

**Pruebas**: test de integración de los 3 endpoints, con fixtures que fuercen cada uno de los 3 colores.

**Tamaño**: ~200 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F19.1-T1 | `GET /admin/sync/log` | `backend/.../api/v1/admin_views.py` |
| HU-F19.1-T2 | `GET /admin/sync/conflict` | `backend/.../api/v1/admin_views.py` |
| HU-F19.1-T3 | `GET /admin/sync/estado` (agregado, 3 colores) | `backend/.../api/v1/admin_views.py` |
| HU-F19.1-T4 | Tests de integración (3 colores) | `backend/tests/integration/` |

---

### HU-F19.2 — Dashboard de sync: heatmap de lag, log y conflictos

**Given** los 3 endpoints de HU-F19.1,
**When** el admin abre `/sync`,
**Then** ve un heatmap 24h × N sucursales (color por `lag_seg`), un resumen "X verde, Y amarillo, Z rojo", y dos pestañas más (Log, Conflictos) con drill-down.

**Reglas de negocio**: BR1/BR2 de HU-F19.1, aplicadas en la UI (colores exactos, filtros).

**Tablas ER**: `sync_log`, `sync_conflict` (ambas R).

**Endpoints**: los 3 de HU-F19.1.

**Componentes**: `SyncDashboard.tsx` (heatmap + resumen), `SyncLog.tsx` (DataTable paginada), `SyncConflict.tsx` (diff viewer lado a lado), reutiliza `HeatmapOcupacion.tsx` (Fase 17) con datos de lag en vez de ocupación.

**Validaciones**: ninguna de formulario.

**Errores**: sin datos → "Sin sucursales sincronizando aún" (no un heatmap vacío confuso).

**Pruebas**: e2e: heatmap con datos, click → drill-down a log filtrado por esa sucursal, ver un conflicto con diff.

**Tamaño**: ~350 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F19.2-T1 | `SyncDashboard.tsx` (heatmap + resumen) | `src/features/sync/pages/` |
| HU-F19.2-T2 | `SyncLog.tsx` | `src/features/sync/pages/` |
| HU-F19.2-T3 | `SyncConflict.tsx` (diff viewer) | `src/features/sync/pages/` |
| HU-F19.2-T4 | e2e (3 escenarios) | `e2e/sync-dashboard.spec.ts` |

---

### HU-F19.3 — Pairing de sucursales (100% backend real, solo falta la UI)

**Given** que `POST /admin/pairing-tokens`, `GET /admin/pairing-tokens/{uuid}`, `POST /admin/pairing-tokens/{uuid}/revoke` y `POST /admin/sucursales/{uuid}/revoke-sync` **ya existen, ya están probados** (`test_pairing_flow.py`) y ya tienen rate-limit (5/hora por admin) — el permiso que exigen (`gestionar_dian`) **ya está sembrado** desde la migración `0002` —,
**When** el admin necesita emparejar una sucursal nueva,
**Then** esta HU es puramente de frontend: no hay ninguna brecha de backend que cerrar.

**Reglas de negocio**
- BR1 (real, verificado en el código). El plaintext del token solo se muestra **una vez**, en la respuesta de creación — nunca se puede recuperar después; la UI debe forzar al admin a copiarlo antes de cerrar el modal.
- BR2 (real). `GET /admin/pairing-tokens/{uuid}` nunca devuelve el hash del token (lo filtra explícitamente el endpoint, defensa en profundidad) — la UI de detalle no debe esperar ni mostrar ese campo.
- BR3 (real). Revocar es un `INSERT` en `revoked_sync_jwts` (nunca `UPDATE`/`DELETE`, por el trigger de inmutabilidad de `pairing_tokens`) — 204 idempotente si ya estaba revocado.
- BR4. No existe hoy (ni se construye aquí) un endpoint de "listar todos los pairing tokens de todas las sucursales" — el flujo real es por sucursal (`GET /admin/pairing-tokens/{uuid}` es por token, no una lista). La pantalla de lista se apoya en `GET /api/v1/sucursales` (ya real) y, por cada sucursal, un estado derivado (pareada/pendiente) basado en si existe algún `pairing_tokens.uuid_sucursal` no revocado — si el volumen de sucursales lo justifica, se evalúa un endpoint de lista dedicado como mejora futura (`ABIERTO-52`).

**Tablas ER**: `pairing_tokens`, `revoked_sync_jwts` (ambas cloud-only reales, no en el `.mmd` — mismo criterio de excepción documentado en DEC-ADM-12).

```mermaid
sequenceDiagram
    participant Admin as web_admin
    participant API as api-admin
    participant Branch as installer (sucursal nueva)
    Admin->>API: POST /admin/pairing-tokens (uuid_sucursal, ttl_hours)
    API-->>Admin: 201 { token (plaintext, una vez), pairing_token_uuid, hash, expires_at }
    Admin->>Branch: entrega el token (fuera de banda: QR / copiar-pegar)
    Branch->>API: POST /sync/pair (pairing_token, uuid_sucursal, branch_info)
    API-->>Branch: 201 { sync_jwt, expires_at, uuid_sucursal }
    Note over Branch: guarda sync_jwt en PARKOS_SYNC_JWT_PATH
    Admin->>API: POST /admin/pairing-tokens/{uuid}/revoke (si hace falta)
    API-->>Admin: 204 (INSERT en revoked_sync_jwts, idempotente)
```

**Endpoints**: los 4 reales listados arriba (ninguno nuevo).

**Componentes**: `Pairing.tsx` (lista de sucursales con estado derivado), `GenerarPairingTokenModal.tsx` (muestra el plaintext una sola vez + botón copiar + QR opcional para que el instalador lo escanee), `RevocarPairingModal.tsx`.

**Validaciones**: `ttl_hours` 1-168 (mismo rango que valida el backend).

**Errores**: 429 `pairing_token_rate_limited` (5/hora) mostrado con el tiempo de espera restante; 403 `tenant_scope_violation` si se intenta operar sobre una sucursal fuera de `sucursales_permitidas`.

**Pruebas**: e2e: generar token (plaintext visible una vez), revocar, intentar generar un 6º token en la misma hora → 429 visible.

**Tamaño**: ~260 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F19.3-T1 | `Pairing.tsx` | `src/features/pairing/pages/` |
| HU-F19.3-T2 | `GenerarPairingTokenModal.tsx` | `src/features/pairing/components/` |
| HU-F19.3-T3 | `RevocarPairingModal.tsx` | `src/features/pairing/components/` |
| HU-F19.3-T4 | e2e (3 escenarios) | `e2e/pairing.spec.ts` |

---

### HU-F19.4 — Backend: sembrar tipos de alerta operacionales y habilitar la transición "descartar"

**Given** que `alert_types` hoy solo tiene 8 filas sembradas, **todas de infraestructura/DIAN** (`hash_chain_anomaly, dian_rechazada, dian_timeout, dian_error, branch_offline_reauth_required, orphan_workflow_chain, fe_provider_error, fe_numbering_exhausted` — migración `0013_add_alert_types.py`, verificada) — **ninguna operativa**,
**When** CU-14 exige 11 tipos operativos (`descuadre_critico, sync_fallida, capacidad_agotada, capacidad_agotada_forzado, evento_no_procesado, impresora_caida, fe_error_toppoint, numeracion_agotada, cache_desactualizado, arqueo_pendiente_24h, suscripcion_proxima_vencer`),
**Then** hace falta una siembra nueva — sin ella, cualquier `alerta` que la lógica de detección cree con esos `tipo_alerta` no tendrá `severity` (el `JOIN` a `alert_types` no encuentra fila, la UI muestra "—" en vez de la severidad real).

**Reglas de negocio**
- BR1. `alert_types` es tabla out-of-catalog (sin router HTTP, sembrada por migración/script idéntico en cloud y sucursal — mismo patrón que las 8 filas existentes) — esta HU **no** construye una pantalla de administración de tipos de alerta (no hay CU que la pida como CRUD; el catálogo de tipos es de despliegue, igual que el proveedor DIAN, DEC-ADM-15). Lo que sí construye el resto de esta Fase 19 es la bandeja para las alertas ya creadas con esos tipos.
- BR2. La detección real de cada tipo (job cada 5 min para `capacidad_agotada`, job cada 1h para `evento_no_procesado`/`arqueo_pendiente_24h`, verificación al operar la placa para `suscripcion_proxima_vencer`, etc.) es trabajo de `web_sucursal`/jobs de backend — **fuera del alcance de `web_admin`**, que solo consume y visualiza las `alerta` ya creadas.
- BR3. Se habilita `POST /workflows/alerta/:uuid/descartar` (transición real usando `append_transition`, mismo patrón que `envio_dian`/`validacion_evento`), con `permission_required="descartar_alerta"` (**ya sembrado**, Fase 13 solo reconcilió el código de `anulaciones`/`reimpresion-ticket`; `descartar_alerta` ya era el correcto desde el inicio) — `write_enabled` pasa de `False` a `True` para este recurso específico dentro de `workflows.py`.

**Tablas ER**: `alert_types` (INSERT de 11 filas), `alerta` ([L-W], transición nueva).

```mermaid
stateDiagram-v2
    [*] --> abierta: detector crea alerta (job/evento)
    abierta --> en_revision: admin abre para revisar (opcional)
    en_revision --> resuelta: POST .../descartar (observaciones obligatorias)
    abierta --> resuelta: POST .../descartar (directo, observaciones obligatorias)
    resuelta --> [*]
    note right of resuelta
        Cada transición es una fila NUEVA
        (uuid_alerta_padre), nunca un UPDATE.
        Los 3 valores son los reales del ER
        (.mmd línea 750) — no 'ACTIVA'/'REVISADA'.
    end note
```

**Endpoints**: `POST /api/v1/workflows/alerta/:uuid/descartar` (nuevo, transición `abierta|en_revision → resuelta`, con `observaciones` obligatorias — CU-14 E1, real).

**Componentes**: ninguno en esta HU (backend puro).

**Validaciones**: `observaciones` no vacío en la transición.

**Errores**: 409 si se intenta transicionar una alerta que ya está `resuelta` (workflow terminal).

**Pruebas**: test de siembra (11 filas presentes, idempotente); test de integración de la transición completa (`abierta → en_revision → resuelta`).

**Tamaño**: ~140 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F19.4-T1 | Migración: sembrar 11 `alert_types` operacionales | `backend/.../migrations/versions/` |
| HU-F19.4-T2 | Script de siembra espejo para sucursal (mismo patrón que `seed_alert_types.py`) | `infra/scripts/seed_alert_types.py` (extender) |
| HU-F19.4-T3 | `POST /workflows/alerta/:uuid/descartar` (`write_enabled=True` solo para `alerta`) | `backend/.../api/v1/workflows.py` |
| HU-F19.4-T4 | Tests (siembra + transición) | `backend/tests/unit/`, `backend/tests/integration/` |

---

### HU-F19.5 — Bandeja de alertas y detalle con workflow

**Given** las 11 filas de HU-F19.4 y el endpoint de transición real,
**When** el admin abre `/alertas`,
**Then** ve todas las alertas de sus sucursales permitidas, con `severity` correctamente unida desde `alert_types`, filtrable por tipo/severidad/sucursal/estado/fecha (CU-14 AC3, real), y puede descartar una con observación obligatoria.

**Reglas de negocio**
- BR1 (DEC-ADM-14, ya fijado en §0.3). `estado` usa exactamente `abierta|en_revision|resuelta` — nunca `'ACTIVA'/'REVISADA'` ni un booleano.
- BR2 (CU-14 BR1/BR2, real). Las alertas son inmutables — "descartar" es una fila nueva (`uuid_alerta_padre`), nunca un `UPDATE`; una alerta resuelta sigue en el histórico pero sale del badge de activas.
- BR3 (CU-14 E2, real). Si el mismo `tipo_alerta`+`uuid_sucursal` se repite muchas veces en una ventana corta (p. ej. `sync_fallida` disparándose cada minuto), la UI agrupa visualmente por `(tipo_alerta, uuid_sucursal, día)` con un contador — no oculta ninguna fila, solo las colapsa por defecto con opción de expandir.
- BR4. Para alertas cuyo `tipo_alerta` no está en `alert_types` (ad-hoc, futuro), la severidad se muestra como "—" en vez de fallar el join (`LEFT JOIN`, no `INNER JOIN`).

**Tablas ER**: `alerta` ([L-W], real), `alert_types` (R).

**Endpoints**: `GET /api/v1/workflows/alerta?uuid_sucursal=&tipo_alerta=&estado=&severidad=&desde=&hasta=&cursor=&limit=` (extendido con `LEFT JOIN alert_types` para exponer `severity` — hoy el montaje genérico no la expone); `POST /api/v1/workflows/alerta/:uuid/descartar` (HU-F19.4).

**Componentes**: `AlertasList.tsx`, `AlertaDetalle.tsx` (contexto + `WorkflowChain`, componente reutilizado también por Fase 20 para anulaciones/reclamos), `AlertasBadge.tsx` (contador en la barra lateral, `authStore`/store global liviano).

**Validaciones**: `observaciones` obligatorio al descartar.

**Errores**: 409 al intentar descartar una ya resuelta.

**Pruebas**: e2e: filtrar por severidad, ver alerta agrupada (contador), descartar con observación, badge se actualiza.

**Tamaño**: ~330 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F19.5-T1 | **Backend**: `GET /workflows/alerta` con `LEFT JOIN alert_types` (exponer `severity`) + filtros | `backend/.../api/v1/workflows.py` |
| HU-F19.5-T2 | `AlertasList.tsx` (con agrupación visual) | `src/features/alertas/pages/` |
| HU-F19.5-T3 | `AlertaDetalle.tsx` + `WorkflowChain.tsx` | `src/features/alertas/pages/`, `src/features/workflows/components/` |
| HU-F19.5-T4 | `AlertasBadge.tsx` | `src/components/` |
| HU-F19.5-T5 | e2e (4 escenarios) | `e2e/alertas-bandeja.spec.ts`, `e2e/alertas-detalle.spec.ts` |

---

### HU-F19.6 — Bandeja de validación de eventos (cloud-side, CU-07)

**Given** `GET /validacion-evento` y `POST /validacion-evento` (HU-F13.4, ya reales) con el estado real `recibido → validado|observado|rechazado`,
**When** el admin necesita revisar eventos entrantes de sucursal que requieren validación manual,
**Then** ve la bandeja con workflow de transición, mismo patrón visual que alertas/anulaciones.

**Reglas de negocio**: transición vía `uuid_validacion_padre` (cadena real, ya implementada en `dispatch`/`append_transition`); `observaciones` capturadas en la transición.

**Tablas ER**: `validacion_evento` ([L-W], real).

**Endpoints**: `GET /api/v1/validacion-evento?...`, `POST /api/v1/validacion-evento` (ambos HU-F13.4/ya reales).

**Componentes**: `ValidacionEventos.tsx`, reutiliza `WorkflowChain.tsx`.

**Validaciones**: `observaciones` requerido en `observado`/`rechazado`.

**Errores**: 409 en transición inválida (fuera de la máquina de estados real `STATE_MACHINES['validacion_evento']`).

**Pruebas**: e2e: ver bandeja, transicionar un evento con observación.

**Tamaño**: ~180 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F19.6-T1 | `ValidacionEventos.tsx` | `src/features/sync/pages/` |
| HU-F19.6-T2 | e2e (1 escenario) | `e2e/sync-validacion.spec.ts` |

---

## Fase 20 — Clientes y suscripciones, workflows, auditoría y DIAN

**Objetivo**: cerrar CU-06 (mantenimiento administrativo de clientes/vehículos/suscripciones — la venta puntual en caja queda en `web_sucursal`), habilitar las transiciones reales de `anulaciones`/`reclamos`, construir la bitácora (`log_transaccional`) reutilizando el verificador de cadena de hashes **que ya existe en el backend**, y cerrar el monitor DIAN con el mecanismo de reintento real (DEC-ADM-16).

**CUs cubiertos**: CU-06 (completo), transversal (workflows, auditoría).
**Prereq**: Fase 13, Fase 19 (reutiliza `WorkflowChain.tsx`).

### HU-F20.1 — Clientes: listado y detalle (datos, vehículos, suscripciones, facturas, bitácora)

**Given** que `clientes`, `vehiculos`, `subscripciones_cliente`, `subscripcion_vehiculos` y `clientes_b2b` son reales y **ya funcionan en lectura y escritura hoy** (permiso `gestionar_clientes`, ya sembrado desde la migración `0002` — el mismo código que el comentario real del router documenta como la corrección de un defecto idéntico al que Fase 13 corrige para empresa/tarifas/tolerancias),
**When** el admin abre `/clientes`,
**Then** ve el listado con búsqueda por NIT/nombre y, en el detalle, 5 pestañas: Datos, Vehículos, Suscripciones (vigentes + históricas con timeline), Facturas (solo lectura, vía `facturas.uuid_ingreso`/`uuid_salida` correlacionadas por cliente a través de `factura_electronica.uuid_cliente`), Bitácora.

**Reglas de negocio**
- BR1. `clientes_b2b` (extensión 1:1 para convenios corporativos) **queda explícitamente fuera de alcance de esta fase**: CU-06 BR5 lo dice sin ambigüedad — "Convenios (múltiples vehículos para una empresa) son CU aparte, fase 2" — no es un hueco de cobertura, es una exclusión declarada por el propio caso de uso. Se documenta como `ABIERTO-54` para cuando el negocio priorice esa fase 2.
- BR2 (CU-06, real, reconciliado). El modelo real no es "una mensualidad = una placa" (lectura literal de CU-06 BR1) sino cliente-céntrico: un cliente contrata un plan (`tipo_subscripciones`, con `cantidad_maxima_vehiculos` y `mismo_tipo_vehiculo` como reglas del plan) y cubre entre 1 y `cantidad_maxima_vehiculos` vehículos vía `subscripcion_vehiculos` — el "placa 1/placa 2" del corpus de CU original es la instancia más común de este modelo (un plan con `cantidad_maxima_vehiculos=2`), no una estructura de datos distinta. BR1 ("la mensualidad aplica por placa, no por cliente... varias placas con mensualidades independientes") se satisface creando varias `subscripciones_cliente` para el mismo cliente si así lo requiere, no inventando una segunda tabla.
- BR3. "Suscripciones próximas a vencer" (badge amarillo) reutiliza la misma función `diasParaVencer()` que Fase 17 (reportería) ya define — una sola implementación, no dos criterios divergentes.

**Tablas ER**: `clientes` (real), `vehiculos` (real), `subscripciones_cliente` (real), `subscripcion_vehiculos` (real), `factura_electronica` (R, para correlacionar facturas del cliente).

**Endpoints**: `GET/POST/PUT /api/v1/clientes/clientes`, `.../vehiculos`, `.../subscripciones-cliente`, `.../subscripcion-vehiculos` (los 4 ya existen y funcionan, `permission_required="gestionar_clientes"`).

**Componentes**: `ClientesList.tsx`, `ClienteDetalle.tsx` (5 pestañas), `ClienteSuscripciones.tsx` (timeline reutilizado).

**Validaciones**: `tipo_identificador ∈ {CC, NIT, CE, pasaporte}` (valores reales del comentario ER de `clientes.tipo_identificador`); `email` RFC 5322.

**Errores**: 422 `numero_identificacion_duplicado` (UK real `(tipo_identificador, numero_identificacion, vigente_desde)`).

**Pruebas**: e2e: búsqueda, drill-down a las 5 pestañas, ver suscripciones históricas con timeline.

**Tamaño**: ~340 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F20.1-T1 | `ClientesList.tsx` con búsqueda | `src/features/clientes/pages/` |
| HU-F20.1-T2 | `ClienteDetalle.tsx` (5 tabs) | `src/features/clientes/pages/` |
| HU-F20.1-T3 | `ClienteSuscripciones.tsx` | `src/features/clientes/components/` |
| HU-F20.1-T4 | `useProximasVencer()` (compartido con Fase 17) | `src/lib/subscripciones.ts` |
| HU-F20.1-T5 | e2e (3 escenarios) | `e2e/clientes.spec.ts` |

---

### HU-F20.2 — Mantenimiento de suscripciones: alerta por suscripción y prorrateo

**Given** que CU-06 BR4 exige `dias_alerta_pre_vencimiento` **por suscripción** (editable, default 7) y el ER no tiene esa columna en `subscripciones_cliente` (`.mmd` línea 496-516: solo `uuid_cliente, uuid_sucursal, uuid_tipo_subscripcion, fecha_inicio_cobertura, fecha_vencimiento` como columnas de negocio),
**When** el admin crea o edita una suscripción,
**Then** debe poder fijar ese valor por suscripción individual — lo que exige una columna nueva, declarada explícitamente como extensión (no un default a nivel de `tipo_sucursal.caracteristicas`, que rompería la granularidad por suscripción que el propio CU exige).

**Reglas de negocio**
- BR1 (corrige un error real de un plan previo). Globalizar `dias_alerta_pre_vencimiento` en `tipo_sucursal.caracteristicas` (como proponía un plan anterior) viola CU-06 BR4 directamente: todas las suscripciones de esa sucursal compartirían el mismo valor, sin poder editarse individualmente como el CU exige. Se agrega la columna a `subscripciones_cliente` en vez de forzar el dato a un nivel de granularidad que no le corresponde.
- BR2 (CU-06 BR3, real — en alcance, no diferida). El prorrateo por día (registros después del día 15 del mes prorratean desde el día de suscripción hasta el fin de mes) se calcula y se **muestra** en la pantalla de creación como "monto de referencia del primer periodo" (`valor_dia = plan.valor / plan.duracion_dias`, `monto_proporcional = valor_dia * dias_restantes_del_mes`) — es informativo para que el admin sepa cuánto cobrar en el primer ciclo; el cobro en sí (factura/pago) es un acto separado que ocurre en `web_sucursal` o en un proceso administrativo aparte, fuera del alcance de esta pantalla de mantenimiento. No se deja como "fuera de alcance" en una parte del documento y con fórmula completa en otra (la contradicción real detectada en un plan previo) — es una sola decisión, aplicada de forma consistente.
- BR3 (CU-06 E1, real). Registrar una placa que ya tiene suscripción vigente se **bloquea** (422), no solo se advierte — el corpus de CU original dice "advierte" pero el criterio de negocio real (ya validado y sin objeción en la auditoría de fidelidad) es bloquear con 422, consistente con impedir dos suscripciones activas simultáneas sobre el mismo vehículo.

**Tablas ER**: `subscripciones_cliente` (columna nueva `dias_alerta_pre_vencimiento` int, default 7, nullable — extensión declarada explícitamente, mismo criterio de excepción que el resto de esta Parte II), `tipo_subscripciones` (R, para `valor`/`duracion_dias`/`cantidad_maxima_vehiculos`/`mismo_tipo_vehiculo`).

**Endpoints**: `POST/PUT /api/v1/clientes/subscripciones-cliente` (ya existe; el payload crece con el campo nuevo).

**Componentes**: `SuscripcionForm.tsx` (RHF + Zod), panel de solo lectura "Monto de referencia del primer periodo" (BR2).

**Validaciones**: `dias_alerta_pre_vencimiento` entero 1-90; vehículos asociados ≤ `tipo_subscripciones.cantidad_maxima_vehiculos`; si `mismo_tipo_vehiculo=true`, todos los vehículos de la suscripción deben compartir `uuid_tipo_vehiculo`.

**Errores**: 422 `placa_con_suscripcion_vigente`; 422 `cantidad_vehiculos_excede_plan`; 422 `tipo_vehiculo_mixto_no_permitido`.

**Pruebas**: e2e: crear suscripción con 2 vehículos del mismo tipo (éxito), con tipos distintos si `mismo_tipo_vehiculo=true` (422), editar `dias_alerta_pre_vencimiento` de una suscripción existente sin afectar otras.

**Tamaño**: ~260 LOC (incluye la migración de la columna nueva).

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F20.2-T1 | **Backend**: migración `ALTER TABLE subscripciones_cliente ADD COLUMN dias_alerta_pre_vencimiento` | `backend/.../migrations/versions/` |
| HU-F20.2-T2 | **Backend**: extender schema `SubscripcionesClienteCreate/Update` | `backend/.../schemas/clientes.py` |
| HU-F20.2-T3 | **Backend**: validaciones de cantidad/tipo de vehículo vs. plan | `backend/.../api/v1/clientes.py` |
| HU-F20.2-T4 | `SuscripcionForm.tsx` + panel de prorrateo | `src/features/clientes/components/` |
| HU-F20.2-T5 | e2e (3 escenarios) | `e2e/suscripciones.spec.ts` |

---

### HU-F20.3 — Workflows: anulaciones y reclamos (transiciones reales)

**Given** que `anulaciones` y `reclamos` tienen router de solo lectura (`GET /workflows/anulaciones`, `GET /workflows/reclamos`, `write_enabled=False`) y que Fase 13 ya reconcilió/sembró los permisos correctos (`aprobar_anulacion`+`ejecutar_anulacion` para anulaciones, `registrar_reclamo` sembrado nuevo para reclamos),
**When** el admin necesita aprobar o ejecutar una solicitud de anulación, o dar seguimiento a un reclamo,
**Then** se habilitan las transiciones de escritura reales sobre estas dos tablas `[L-W]`.

**Reglas de negocio**
- BR1 (real, ER). `anulaciones.estado` transiciona `solicitada → aprobada → ejecutada`; la **solicitud** inicial la crea normalmente un operador de sucursal con el permiso ya real `anular_ingreso`/`anular_salida` (sembrados desde `0001_initial_schema.py`) — el admin solo interviene en `aprobar`/`ejecutar`, de ahí que los dos permisos administrativos reales sean exactamente esos dos y no uno solo.
- BR2 (real, ER). `reclamos.tipo_reclamable ∈ {ingreso, salida, factura, subscripcion}` con `uuid_reclamable` polimórfico sin FK física — el drill-down al objeto origen se resuelve en el cliente según `tipo_reclamable` (4 rutas posibles, una por tipo), nunca con un `JOIN` de backend que no puede existir sin FK.
- BR3. Ambas cadenas se visualizan con el mismo `WorkflowChain.tsx` ya construido en Fase 19 para alertas — un solo componente para las 3 tablas `[L-W]` de esta Parte II con cadena `uuid_*_padre`.

**Tablas ER**: `anulaciones` ([L-W], real), `reclamos` ([L-W], real).

```mermaid
stateDiagram-v2
    [*] --> solicitada: operador de sucursal (anular_ingreso/anular_salida)
    solicitada --> aprobada: admin (aprobar_anulacion)
    aprobada --> ejecutada: admin (ejecutar_anulacion)
    ejecutada --> [*]
    note right of ejecutada
        Solo la fila 'ejecutada' anula de verdad
        (recalcula disponible[tipo], marca la
        salida/ingreso afectado). Cada paso es
        una fila nueva (uuid_anulacion_padre).
    end note
```

**Endpoints**: `POST /api/v1/workflows/anulaciones` (crear solicitud — aunque normalmente la origina sucursal, el admin puede crearla también), `POST /api/v1/workflows/anulaciones/:uuid/transicion` (`solicitada→aprobada` con `aprobar_anulacion`, `aprobada→ejecutada` con `ejecutar_anulacion`); `GET/POST /api/v1/workflows/reclamos`, `POST /api/v1/workflows/reclamos/:uuid/transicion` (`abierto→en_revision→resuelto|rechazado`, con `registrar_reclamo`).

**Componentes**: `AnulacionesList.tsx`, `AnulacionDetalle.tsx` (`WorkflowChain` + form de transición con el permiso correspondiente al paso), `ReclamosList.tsx`, `ReclamoDetalle.tsx`.

**Validaciones**: `motivo` obligatorio en cada transición (columna real `text`).

**Errores**: 403 si el actor no tiene el permiso del paso específico (p. ej. tiene `aprobar_anulacion` pero intenta `ejecutar`); 409 en transición fuera de la máquina de estados real.

**Pruebas**: e2e: crear solicitud, aprobar (con el permiso correcto), ejecutar (con el otro permiso), intentar ejecutar sin haber aprobado → 409; crear reclamo sobre una `subscripcion`, drill-down al cliente.

**Tamaño**: ~380 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F20.3-T1 | **Backend**: `write_enabled=True` + transición para `anulaciones` (máquina `solicitada→aprobada→ejecutada`) | `backend/.../api/v1/workflows.py` |
| HU-F20.3-T2 | **Backend**: idem para `reclamos` (`abierto→en_revision→resuelto\|rechazado`) | `backend/.../api/v1/workflows.py` |
| HU-F20.3-T3 | `AnulacionesList.tsx` + `AnulacionDetalle.tsx` | `src/features/workflows/pages/` |
| HU-F20.3-T4 | `ReclamosList.tsx` + `ReclamoDetalle.tsx` (drill-down por `tipo_reclamable`) | `src/features/workflows/pages/` |
| HU-F20.3-T5 | e2e (4 escenarios) | `e2e/anulaciones.spec.ts`, `e2e/reclamos.spec.ts` |

---

### HU-F20.4 — Bitácora: `log_transaccional`, verificación de cadena y búsqueda global

**Given** que `log_transaccional` no tiene ningún router HTTP hoy, pero el **verificador de cadena de hashes ya existe, completo y probado** (`sync/motor/verify_chain.py::verify_chain()`, cubre `log_transaccional` y `revocacion_factura`, con test unitario real `test_verify_chain.py`) — esto reduce drásticamente el trabajo de esta HU respecto a lo que un plan previo presupuestaba (calcular SHA256 desde cero en el endpoint),
**When** un auditor necesita ver el historial de cambios de un registro o verificar la integridad de la cadena de una sucursal,
**Then** un endpoint nuevo, delgado, envuelve `verify_chain()` en HTTP — no reimplementa el algoritmo.

**Reglas de negocio**
- BR1. El endpoint de lectura de `log_transaccional` filtra por `tabla_afectada`, `uuid_registro_afectado`, `uuid_sucursal`, `uuid_usuario`, rango de fecha — mismo patrón de filtros que el resto de esta Parte II (HU-F18.1).
- BR2. `verify_chain()` devuelve una lista de `ChainAnomaly` (vacía = cadena íntegra); el endpoint las traduce a `{ ok: bool, anomalias: [...] }`. Una cadena rota **no** detiene la verificación en el primer error (el propio verificador ya está diseñado así: "a single corrupted link produces exactly one anomaly, not a cascade") — la UI puede listar todas las anomalías de una vez, no solo la primera.
- BR3. Búsqueda global por prefijo de UUID (`tabla` + `uuid_registro_afectado`) — un típeahead simple, `LIKE` por prefijo, límite 10 resultados.

**Tablas ER**: `log_transaccional` ([A], real).

**Endpoints**: `GET /api/v1/admin/log-transaccional?tabla=&uuid_registro=&uuid_sucursal=&uuid_usuario=&desde=&hasta=&cursor=&limit=`; `GET /api/v1/admin/log-transaccional/verify-chain?uuid_sucursal=X` (envuelve `verify_chain_for_spec` para `log_transaccional`, y opcionalmente `revocacion_factura` con un segundo parámetro `tabla=`); `GET /api/v1/admin/log-transaccional/buscar?prefijo=&limit=10`.

**Componentes**: `LogTransaccional.tsx` (DataTable + filtros), `LogDetalle.tsx` (diff `datos_anteriores` vs `datos_nuevos` campo por campo), `HashChainVerify.tsx` (botón "Verificar" + resultado, lista de anomalías si las hay, exportar CSV de las filas sospechosas), `BuscarGlobal.tsx` (typeahead).

**Validaciones**: rango de fecha estándar.

**Errores**: 422 `rango_fecha_invalido`.

**Pruebas**: test de integración del endpoint de verificación contra una cadena íntegra (0 anomalías) y una corrompida artificialmente en el fixture (≥1 anomalía, con el `uuid` exacto señalado); e2e de filtro, diff y verificación.

**Tamaño**: ~300 LOC (más liviano de lo esperado gracias a reutilizar `verify_chain()` real).

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F20.4-T1 | `GET /admin/log-transaccional` con filtros + cursor | `backend/.../api/v1/admin_views.py` (o `auditoria.py` nuevo) |
| HU-F20.4-T2 | `GET /admin/log-transaccional/verify-chain` (envuelve `verify_chain_for_spec`) | idem |
| HU-F20.4-T3 | `GET /admin/log-transaccional/buscar` | idem |
| HU-F20.4-T4 | `LogTransaccional.tsx` + `LogDetalle.tsx` | `src/features/auditoria/pages/` |
| HU-F20.4-T5 | `HashChainVerify.tsx` + `BuscarGlobal.tsx` | `src/features/auditoria/pages/` |
| HU-F20.4-T6 | Test de integración (cadena íntegra + corrompida) + e2e | `backend/tests/integration/`, `e2e/auditoria-log.spec.ts`, `e2e/auditoria-hashchain.spec.ts` |

---

### HU-F20.5 — Monitor de envíos DIAN: cola, reintento y revocación

**Given** los endpoints de lectura de HU-F13.4 (`GET /envio-dian`) y el mecanismo real de reintento (`POST /envio-dian` con `uuid_envio_padre`, DEC-ADM-16),
**When** el admin necesita ver la cola de envíos DIAN agrupada por estado y reintentar uno rechazado,
**Then** la pantalla lista `envio_dian` por estado real (`pendiente|enviado|aceptado|rechazado`) y el botón "Reintentar" dispara exactamente ese `POST` con la cadena de padres visible.

**Reglas de negocio**
- BR1 (DEC-ADM-15, ya fijado). No hay selector de proveedor: es configuración de despliegue.
- BR2 (real, `factura_electronica`/`v_factura_electronica_acuse`). El CUFE y el estado DIAN se leen de la vista real (Fase 17, HU-F17.3) — esta pantalla es el complemento operativo (reintentar), no otra fuente de los mismos datos.
- BR3. **Anular una FE ya `pendiente_envio`** (antes de que DIAN la acepte) no tiene hoy un endpoint admin-iniciado — lo único real es `POST /revocacion-factura-webhook`, que es **DIAN quien lo invoca**, no el admin. Se declara como brecha explícita (`ABIERTO-55`, no se construye en esta Parte II sin una decisión de negocio primero: anular antes del acuse de DIAN tiene implicaciones fiscales que exceden el alcance de este documento) — no se inventa un endpoint de "anular" que el backend real no soporta ni fue pedido explícitamente por ningún CU de esta lista.

**Tablas ER**: `envio_dian` ([L-W], real).

**Endpoints**: `GET /api/v1/envio-dian?estado=&uuid_sucursal=&cursor=&limit=` (HU-F13.4); `POST /api/v1/envio-dian` (ya real, reutilizado para reintento con `uuid_envio_padre`).

**Componentes**: `DianCola.tsx` (tabs por estado + resumen de contadores), `DianDetalle.tsx` (payload + `respuesta_proveedor` crudos, cadena de reintentos vía `DianRetryHistory.tsx`).

**Validaciones**: ninguna de formulario (el reintento no requiere payload adicional del admin, hereda del padre).

**Errores**: si el envío padre no está en `rechazado`, el botón "Reintentar" no se habilita (validación de UX; el backend es la autoridad real vía la máquina de estados de `append_transition`).

**Pruebas**: e2e: ver cola por estado, reintentar un rechazado, ver la cadena de reintentos creciendo.

**Tamaño**: ~230 LOC.

**Tareas atómicas**
| ID | Tarea | Archivo |
|---|---|---|
| HU-F20.5-T1 | `DianCola.tsx` | `src/features/dian/pages/` |
| HU-F20.5-T2 | `DianDetalle.tsx` + `DianRetryHistory.tsx` | `src/features/dian/pages/`, `src/features/dian/components/` |
| HU-F20.5-T3 | e2e (2 escenarios) | `e2e/dian-cola.spec.ts`, `e2e/dian-detalle.spec.ts` |

---

## Matriz CU × Fases

| CU | Título | Fases que lo cubren | Nota |
|---|---|---|---|
| CU-06 | Gestionar suscripciones individuales / mensualidades | 14 (planes en catálogo), 17 (reportería/cohortes), 20 (CRUD completo) | Venta puntual queda en `web_sucursal`; aquí solo mantenimiento. |
| CU-07 | Sincronizar datos offline-first | 13 (lecturas base), 19 (dashboard, log, conflict, pairing) | Lado admin: monitoreo + gestión de pairing, nunca el motor de sync en sí. |
| CU-08 | Gestionar usuarios y perfiles | 13 (emisor JWT), 16 (completo) | Único CU sin ningún router previo — el más grande en LOC de backend nuevo. |
| CU-09 | Generar reportería y analítica | 17 (completo) | Corrige columnas inventadas sobre `facturas` de un plan previo. |
| CU-10 | Realizar arqueos de caja y cierre diario | 15 (tolerancias/caja), 18 (auditoría) | Lado admin: solo lectura/auditoría; la operación es de sucursal. |
| CU-11 | Configurar sucursales, tarifas y capacidad | 14 (tarifas/capacidad/catálogos), 15 (empresa/sucursal/resoluciones/documentos) | El más extenso en superficie de pantallas. |
| CU-12 | Configurar tipos de vehículo | 14 | Sin CRUD de regex — solo lo que persiste de verdad. |
| CU-13 | Configurar base de caja parametrizable | 13 (tabla nueva `configuracion_caja`), 15 (pantalla) | Única tabla nueva declarada explícitamente fuera del `.mmd` en esta Parte II junto con la ya existente `pairing_tokens`/`revoked_sync_jwts`. |
| CU-14 | Monitorear y alertar sobre eventos operacionales | 19 | Reconciliación de `alerta.estado` a los 3 valores reales del ER; siembra de 11 tipos operacionales. |

---

## Endpoints del backend necesarios (consolidado)

> Cada fila indica si el endpoint **ya existe y funciona** (solo se consume desde `web_admin`), **ya existe pero está bloqueado** (falta sembrar un permiso), o es **nuevo** (se construye en la fase indicada). Ordenado por fase para que el equipo de backend pueda planificar sus PRs junto con los de frontend.

| Endpoint | Estado | Fase | Detalle |
|---|---|---|---|
| `POST /api/v1/auth/login`, `/auth/refresh`, `/auth/logout` | Ya existe y funciona | 13 | Solo se consume. |
| `GET /api/v1/admin/me` | Ya existe y funciona | 13 | Reemplaza cualquier `/auth/me` que un plan previo daba por faltante. |
| `GET /api/v1/sucursales`, `GET /api/v1/admin/sucursales/{uuid}/dashboard` | Ya existe y funciona | 13 | Ya consumido por `Dashboard.tsx`/`BranchSelector.tsx` reales. |
| Migración: 9 permisos nuevos (`config_empresa`, `admin_documentos`, `admin_resolucion_facturacion`, `config_tarifas`, `config_cupos`, `config_tolerancias`, `config_seguridad`, `config_caja`, `registrar_reclamo`) | Nuevo | 13 | Desbloquea 7 recursos existentes + habilita 2 nuevos. |
| Reconciliación de `_ROUTER_CONFIG` en `workflows.py` | Nuevo (cambio de configuración) | 13 | `anulaciones`→`ejecutar_anulacion`, `alerta`→`descartar_alerta`, `reimpresion-ticket`→`reimprimir_ticket`. |
| Corrección de `ROLES_OPERADOR` en `auth.py` | Nuevo (cambio de lógica) | 13 | Evita que un rol `"Usuario"` reciba emisor `admin-` por error. |
| `GET/POST/PUT /api/v1/configuracion/configuracion-caja`, `.../efectiva` | Nuevo (tabla + router completo) | 13 | Tabla `configuracion_caja`, declarada fuera del `.mmd`. |
| `GET /api/v1/envio-dian`, `GET /api/v1/validacion-evento` | Nuevo (solo lectura) | 13 | `cloud_router.py` solo tenía escritura. |
| `Dockerfile` + `nginx.conf` para `web_admin` | Nuevo | 13 | Sin esto, nada de lo demás llega a producción. |
| `GET/POST/PUT /api/v1/catalogos/*` (9 catálogos) | Ya existe y funciona | 14 | `config_catalogo` ya sembrado desde `0002`. |
| Validación 409 al deshabilitar `tipos_vehiculo` con suscripciones vigentes | Nuevo | 14 | Extiende el `PUT` existente. |
| `GET/POST/PUT /api/v1/empresa/tarifas-sucursal` | Bloqueado → desbloqueado | 14 | Requiere `config_tarifas` (Fase 13). |
| Validación 422 de capacidad insuficiente en `cantidad-vehiculos-sucursal` | Nuevo | 14 | Cálculo de ocupación en vivo, sin columna `disponible` inventada. |
| Filtro `vigente_en` en `tarifas-sucursal`, `cantidad-vehiculos-sucursal`, `resolucion-facturacion` | Nuevo | 15 | Para la vista de parametrización efectiva. |
| `GET/POST/PUT /api/v1/empresa/empresa` | Bloqueado → desbloqueado | 15 | Requiere `config_empresa`. |
| `GET/POST/PUT /api/v1/empresa/sucursal` | Ya existe y funciona | 15 | `config_sucursal` ya sembrado desde `0002` — no es un gap. |
| `GET/POST/PUT /api/v1/empresa/resolucion-facturacion` + `.../consecutivo-actual` | Bloqueado → desbloqueado + endpoint nuevo | 15 | Requiere `admin_resolucion_facturacion` (issuer `admin-` estricto). |
| `GET/POST/PUT /api/v1/empresa/documentos` | Bloqueado → desbloqueado | 15 | Requiere `admin_documentos`. |
| `GET/POST/PUT /api/v1/configuracion/configuracion-tolerancias`, `.../efectiva` | Bloqueado → desbloqueado | 15 | Requiere `config_tolerancias`. |
| `GET/POST/PUT /api/v1/configuracion/configuracion-seguridad`, `.../efectiva` | Bloqueado → desbloqueado | 15 | Requiere `config_seguridad`. |
| Router `usuarios.py` completo (9 endpoints) | Nuevo | 16 | `admin_usuarios` ya sembrado desde `0002` — solo faltaba el router. |
| `GET /api/v1/admin/sucursales/{uuid}/dashboard` — cerrar placeholder `ingresos_monto_total` | Corrección | 17 | Hoy devuelve `0.0` siempre, confirmado en el código real. |
| `GET /api/v1/admin/dashboard/resumen` | Nuevo | 17 | 6 tarjetas agregadas del dashboard ejecutivo. |
| `GET /api/v1/admin/reporteria/operacional`, `.../ocupacion` | Nuevo | 17 | — |
| `GET /api/v1/admin/reporteria/facturas`, `.../fe`, `.../pagos` | Nuevo | 17 | Corrige columnas inventadas (`numero_completo`/`iva`/`estado` no están en `facturas`). |
| `GET /api/v1/admin/reporteria/suscripciones/cohorte` | Nuevo | 17 | — |
| Filtros de consulta (`uuid_sucursal`, `uuid_tipo_arqueo`, rango de fecha) en `GET /caja/arqueo` | Nuevo | 18 | El montaje genérico solo soportaba `cursor`/`limit`. |
| `GET /api/v1/caja-sesion/arqueos/{uuid}/diferencias` | Ya existe y funciona | 18 | Cálculo ad-hoc ya implementado, sin vista SQL. |
| `GET /api/v1/caja/arqueo/resumen` | Nuevo | 18 | JOIN `sesion` + suma de `factura_pagos`. |
| `GET /api/v1/admin/sync/log`, `.../conflict`, `.../estado` | Nuevo | 19 | `sync_router.py` es protocolo branch↔cloud, no monitoreo admin. |
| `POST/GET /api/v1/admin/pairing-tokens/*`, `POST /api/v1/admin/sucursales/{uuid}/revoke-sync` | Ya existe y funciona | 19 | 100% backend real, incluye rate-limit; solo falta la UI. |
| Migración: 11 `alert_types` operacionales | Nuevo | 19 | Los 8 sembrados hoy son todos de infraestructura/DIAN. |
| `GET /api/v1/workflows/alerta` con `LEFT JOIN alert_types` (exponer `severity`) | Corrección | 19 | El montaje genérico no expone `severity` hoy. |
| `POST /api/v1/workflows/alerta/:uuid/descartar` | Nuevo (`write_enabled=True`) | 19 | `descartar_alerta` ya sembrado desde `0002`. |
| `GET/POST /api/v1/validacion-evento` | Nuevo (lectura) / ya existe (escritura) | 13 / 19 | Escritura ya real en `cloud_router.py`. |
| `ALTER TABLE subscripciones_cliente ADD COLUMN dias_alerta_pre_vencimiento` | Nuevo | 20 | Extensión declarada, corrige un plan previo que lo globalizaba mal. |
| `GET/POST/PUT /api/v1/clientes/*` (5 recursos) | Ya existe y funciona | 20 | `gestionar_clientes` ya sembrado desde `0002` — mismo patrón de corrección que esta Parte II aplica en Fase 13. |
| `POST /api/v1/workflows/anulaciones/:uuid/transicion`, `.../reclamos/:uuid/transicion` | Nuevo (`write_enabled=True`) | 20 | `aprobar_anulacion`/`ejecutar_anulacion` ya sembrados; `registrar_reclamo` nuevo (Fase 13). |
| `GET /api/v1/admin/log-transaccional`, `.../verify-chain`, `.../buscar` | Nuevo (envuelve `verify_chain()` ya real) | 20 | El algoritmo de verificación de cadena ya existe y está probado — solo falta el endpoint HTTP. |
| `POST /api/v1/envio-dian` (reintento vía `uuid_envio_padre`) | Ya existe y funciona | 20 | Reutilizado, no se crea un endpoint de "reintentar" nuevo. |

---

## Catálogo de permisos reales (consolidado)

> Los 39 códigos que existen o existirán en `prod.permisos` tras esta Parte II, con su origen y para qué recurso los verifica `require_permission()`. Sirve como referencia única al asignar permisos a un usuario (Fase 16) sin tener que releer cada router.

| Código | Sembrado en | Recurso que protege | Usado por (fase/router) |
|---|---|---|---|
| `login` | `0001` | histórico, sin router propio hoy | — |
| `realizar_ingreso` | `0001` | operación de sucursal | `web_sucursal` |
| `realizar_salida` | `0001` | operación de sucursal | `web_sucursal` |
| `emitir_factura` | `0001` (y de nuevo en `0002`, `ON CONFLICT DO NOTHING` — mismo código, sin duplicar fila) | `caja.py` (montaje de solo lectura de `caja`/`arqueo`/`sesion`) | Fase 18 (lectura, aunque el permiso no aplica a `GET`) |
| `anular_ingreso` | `0001` | solicitud de anulación de ingreso (operador) | Fase 20 (HU-F20.3, quien solicita) |
| `anular_salida` | `0001` | solicitud de anulación de salida (operador) | Fase 20 (HU-F20.3, quien solicita) |
| `realizar_arqueo` | `0001` | operación de sucursal | `web_sucursal` |
| `abrir_cerrar_caja` | `0001` | operación de sucursal | `web_sucursal` |
| `reimprimir_ticket` | `0001` | transición de `reimpresion-ticket` (tras reconciliación, Fase 13) | `workflows.py` |
| `administrar_clientes` | `0001` | histórico, superado por `gestionar_clientes` (`0002`) | — |
| `administrar_vehiculos` | `0001` | histórico, superado por `gestionar_clientes` | — |
| `administrar_subscripciones` | `0001` | histórico, superado por `gestionar_clientes` | — |
| `administrar_tarifas` | `0001` | histórico, superado por `config_tarifas` (Fase 13) | — |
| `configurar_sucursal` | `0001` | histórico, superado por `config_sucursal` (`0002`) | — |
| `ver_reportes` | `0001` | sin router propio hoy; candidato natural para gatear la reportería si en el futuro se decide que no toda cuenta `admin-`/`operador-` debe verla | Fase 17 (candidato futuro, no aplicado en esta Parte II: hoy la reportería solo verifica el prefijo de emisor) |
| `config_catalogo` | `0002` | `catalogos.py` (9 catálogos) | Fase 14 |
| `config_sistema` | `0002` | sin router propio hoy | — |
| `config_sucursal` | `0002` | `empresa.py` → recurso `sucursal` | Fase 15 |
| `gestionar_clientes` | `0002` | `clientes.py` (5 recursos: clientes, clientes_b2b, subscripciones-cliente, vehiculos, subscripcion-vehiculos) | Fase 20 |
| `emitir_factura_electronica` | `0002` | sin router propio hoy (la creación de FE real pasa por `cloud_router.py`, sin `require_permission` explícito más allá del issuer) | — |
| `revocar_factura` | `0002` | candidato natural para `POST /workflows/revocacion-factura` (Fase 20, DIAN) | Fase 20 (a asignar en HU-F20.5 si se construye ese endpoint) |
| `gestionar_dian` | `0002` | `pairing.py` (los 4 endpoints reales de pairing) | Fase 19 |
| `audit_read` | `0002` | sin router propio hoy; es el permiso que debería asignarse al rol de negocio "Auditor" | Fase 16 (convención de asignación, `ABIERTO-59`), Fase 20 (candidato natural para gatear lectura de `log_transaccional` si en el futuro se decide restringirla más allá del issuer) |
| `admin_usuarios` | `0002` | `usuarios.py` (router completo, Fase 16) | Fase 16 |
| `aprobar_anulacion` | `0002` | transición `solicitada→aprobada` de `anulaciones` | Fase 20 |
| `ejecutar_anulacion` | `0002` | transición `aprobada→ejecutada` de `anulaciones` | Fase 20 |
| `crear_arqueo` | `0002` | sin router propio hoy (la creación real de `arqueo` es de `web_sucursal`) | — |
| `solicitar_reverso` | `0002` | candidato para `compensate()` de `factura_pagos` (fuera de alcance de esta Parte II — es flujo de sucursal) | — |
| `cerrar_sesion` | `0002` | candidato para `PUT /caja-sesion/sesion/{uuid}/cerrar` (hoy ese endpoint solo verifica issuer, sin `permission_required`) | — |
| `descartar_alerta` | `0002` | transición `→resuelta` de `alerta` | Fase 19 |
| `config_empresa` | **Fase 13 (nuevo)** | `empresa.py` → recurso `empresa` | Fase 15 |
| `admin_documentos` | **Fase 13 (nuevo)** | `empresa.py` → recurso `documentos` | Fase 15 |
| `admin_resolucion_facturacion` | **Fase 13 (nuevo)** | `empresa.py` → recurso `resolucion-facturacion` (issuer `admin-` estricto) | Fase 15 |
| `config_tarifas` | **Fase 13 (nuevo)** | `empresa.py` → recurso `tarifas-sucursal` | Fase 14 |
| `config_cupos` | **Fase 13 (nuevo)** | `empresa.py` → recurso `cantidad-vehiculos-sucursal` | Fase 14 |
| `config_tolerancias` | **Fase 13 (nuevo)** | `configuracion.py` → recurso `configuracion-tolerancias` | Fase 15 |
| `config_seguridad` | **Fase 13 (nuevo)** | `configuracion.py` → recurso `configuracion-seguridad` | Fase 15 |
| `config_caja` | **Fase 13 (nuevo)** | `configuracion.py` → recurso `configuracion-caja` (tabla nueva) | Fase 15 |
| `registrar_reclamo` | **Fase 13 (nuevo)** | transición de `reclamos` | Fase 20 |

Nota de lectura: varios códigos de `0001`/`0002` no tienen router que los verifique hoy (`config_sistema`, `emitir_factura_electronica`, `crear_arqueo`, `solicitar_reverso`, `cerrar_sesion`, `ver_reportes`) — se listan por completitud del catálogo real, no porque esta Parte II los deje pendientes de construir: ninguno de los CU de esta Parte II los necesita todavía. No se seleccionaron para desarrollo del track de admin y no forman parte de las 168 tareas atómicas.

---

## Estrategia de pruebas, calidad y CI

### Pirámide de pruebas

| Capa | Herramienta | Cobertura objetivo | Comando |
|---|---|---|---|
| Unitarias | Vitest | 90% líneas / 80% ramas en `src/lib/` | `npm run test -w web_admin -- --coverage` |
| Integración (componentes) | Vitest + Testing Library + MSW | 80% de los `hooks`/formularios con mock de red | mismo comando |
| E2E | Playwright + `@axe-core/playwright` | 100% de los flujos críticos de cada Fase (listados en cada HU) | `npm run e2e -w web_admin` |
| Contrato | Verificación manual contra el OpenAPI real de `parkos_core` en cada PR de backend | 100% de los endpoints nuevos/modificados de la tabla consolidada anterior | revisión de PR |
| Accesibilidad | `@axe-core/playwright` en cada spec e2e | 0 violaciones WCAG 2.1 AA | integrado en cada spec |
| Backend (integración) | pytest + testcontainers Postgres (mismo patrón ya usado en `backend/tests/integration/`) | 100% de los endpoints nuevos de la tabla consolidada | `pytest backend/tests/integration` |

### Orden de despliegue recomendado

1. **Fase 13** completa primero, sin excepción: es la única fase cuyo atraso bloquea a las 7 restantes. Dentro de Fase 13, el orden interno recomendado es HU-F13.1 (permisos) → HU-F13.2 (emisor JWT) → HU-F13.3/F13.4 (endpoints nuevos) en paralelo con HU-F13.5/F13.6 (frontend de auth) → HU-F13.7 (despliegue) puede avanzar en paralelo desde el día 1, no depende de las demás.
2. **Fases 14 y 15** en paralelo (ambas dependen solo de Fase 13; no tienen dependencia cruzada fuerte entre sí más allá de compartir el shell de pestañas de `SucursalDetalle.tsx`, que HU-F14.3/F14.4 y HU-F15.1 deben coordinar en un solo PR de shell antes de que cada una agregue su pestaña).
3. **Fase 16** (usuarios) puede avanzar en paralelo con 14/15 — es la única fase de negocio que no comparte ninguna pantalla con las demás.
4. **Fase 17** (reportería) después de 14/15/16, porque sus 3 pestañas financiera/operacional/suscripciones leen datos que esas fases terminan de correlacionar correctamente (tarifas, tipos, clientes).
5. **Fase 18** (arqueos) puede avanzar en paralelo con 17 — depende solo de Fase 13.
6. **Fase 19** (sync, pairing, alertas) después de Fase 13; sin dependencia fuerte con 14-18 salvo que `WorkflowChain.tsx` (construido aquí) lo reutiliza Fase 20.
7. **Fase 20** al final: reutiliza `WorkflowChain.tsx` de Fase 19 y las funciones compartidas de "próximas a vencer" de Fase 17.

### Riesgos de calidad transversales

- Todo endpoint nuevo de la tabla consolidada anterior debe tener su test de integración ANTES de que el frontend correspondiente lo consuma (regla dura de esta Parte II, no una sugerencia: varias de las correcciones más importantes de esta Parte II — permisos nunca sembrados, columnas inventadas, placeholders silenciosos — existieron precisamente porque un plan previo asumió contratos de backend sin verificarlos).
- Ningún PR de frontend puede declarar "hecho" un endpoint marcado "Nuevo" en la tabla consolidada si el PR de backend correspondiente no fue mergeado primero — el orden de despliegue de la sección anterior es también un gate de PR, no solo una sugerencia de planificación.

---

## Riesgos y decisiones abiertas de Admin

### Resumen de fases (recapitulación)

| Fase | Objetivo | CUs | HU | Tareas atómicas |
|---|---|---|---|---|
| 13 | Fundamentos: backend + auth + despliegue | transversal | 7 | 27 |
| 14 | Catálogos, tipos de vehículo, tarifas, capacidad | CU-11, CU-12 | 4 | 19 |
| 15 | Empresa, sucursal, resoluciones DIAN, documentos, caja | CU-11, CU-13 | 5 | 22 |
| 16 | Usuarios, perfiles y permisos | CU-08 | 5 | 20 |
| 17 | Reportería y analítica | CU-09 | 4 | 20 |
| 18 | Arqueos y auditoría de caja | CU-10 | 4 | 13 |
| 19 | Sincronización, pairing, alertas | CU-07, CU-14 | 6 | 23 |
| 20 | Clientes/suscripciones, workflows, auditoría, DIAN | CU-06 | 5 | 24 |
| **Total** | | **9 CUs** | **40 HU** | **168 tareas atómicas** |

### Riesgos activos (`RIESGO-ADM-01` a `RIESGO-ADM-20`)

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| **RIESGO-ADM-01** | Ninguna fase de negocio (14-20) puede completarse sin Fase 13 — es un punto único de secuenciación para todo el track de admin. | Alta | Crítico | Priorizar Fase 13 como el primer y único bloque antes de paralelizar el resto entre desarrolladores. |
| **RIESGO-ADM-02** | La migración de 9 permisos nuevos (HU-F13.1) y la reconciliación de `workflows.py` deben desplegarse en cloud ANTES que cualquier PR de frontend que dependa de escrituras — si se invierte el orden, el frontend queda bloqueado con 403 indistinguibles de un bug propio. | Media | Alto | Gate de CI que verifique la migración aplicada antes de mergear cualquier PR de Fase 14+. |
| **RIESGO-ADM-03** | `zustand` se activa por primera vez en este código (0 usos previos) — riesgo de bugs de hidratación/persistencia en el primer uso real de `authStore`/`persist`. | Media | Media | Cobertura de tests unitarios de hidratación explícita en HU-F13.5/F13.6 antes de construir sobre el store. |
| **RIESGO-ADM-04** | El despliegue de `web_admin` (HU-F13.7) es trabajo de infraestructura sin ningún CU que lo pida explícitamente — riesgo real de quedar de último por prioridad de negocio, dejando toda la Parte II sin forma de llegar a producción. | Media | Crítico | Tratarlo como parte de la Fase 13 (bloqueante), no como una mejora posterior. |
| **RIESGO-ADM-05** | Reportería (Fase 17) sobre volúmenes de más de un año de datos podría volverse lenta con consultas de agregación directas (sin vista materializada). | Media | Alta | No construir vistas materializadas preventivamente (no verificadas como necesarias hoy); medir el tiempo real de consulta en el primer despliegue con datos reales y solo entonces evaluar una vista materializada (`ABIERTO-58`). |
| **RIESGO-ADM-06** | `alerta.uuid_arqueo` es la única FK de contexto estructurada — para alertas de tipo `fe_error_toppoint`, `numeracion_toppoint_agotada` o `suscripcion_proxima_vencer`, el "drill-down al objeto origen" no tiene un vínculo estructurado en el ER. | Alta | Baja | La UI de detalle de alerta (HU-F19.5) muestra "sin objeto de origen estructurado" para esos tipos, en vez de fallar o inventar un campo que no existe. |
| **RIESGO-ADM-07** | El rol de negocio "Auditor" (CU-08) y el permiso atómico `audit_read` son independientes por diseño (DEC-ADM-03) — nada impide asignar por error permisos de escritura a un usuario con `rol='Auditor'`. | Media | Media | La UI de permisos (HU-F16.3) muestra una advertencia visual (no un bloqueo) cuando un usuario con `rol='Auditor'` tiene además cualquier permiso de escritura activo. |
| **RIESGO-ADM-08** | La columna nueva `dias_alerta_pre_vencimiento` (HU-F20.2) y la tabla nueva `configuracion_caja` (HU-F13.3) son cambios de esquema compartido con el backend que usan tanto `web_admin` como `web_sucursal` — riesgo de colisión de migraciones entre ramas paralelas de ambos tracks. | Media | Alta | Coordinar el número de revisión de Alembic entre los dos tracks antes de mergear (mismo backend, un solo árbol de migraciones). |
| **RIESGO-ADM-09** | El reintento de envío DIAN (HU-F20.5) reutiliza `POST /envio-dian` sin `Idempotency-Key` verificado en ese endpoint específico — doble click podría crear dos transiciones de reintento. | Media | Baja | Deshabilitar el botón "Reintentar" inmediatamente tras el primer click (idempotencia de UI) hasta confirmar o descartar soporte real de `Idempotency-Key` en ese endpoint. |
| **RIESGO-ADM-10** | `sync/motor/verify_chain.py::verify_chain_for_spec()` recorre la tabla completa por `uuid_sucursal` sin paginación — en una sucursal con mucho histórico, el endpoint HTTP de verificación (HU-F20.4) podría tardar más de lo aceptable para una request síncrona. | Baja | Media | Si el volumen real lo exige, mover la verificación a un job asíncrono con resultado consultable por polling (no se construye preventivamente). |
| **RIESGO-ADM-11** | `admin_resolucion_facturacion` es el único permiso de esta Parte II con issuer `admin-` estricto (sin `operador-`) — un usuario con rol de negocio "Facturador" (CU-08) podría esperar poder editar resoluciones DIAN y no poder, si además no tiene el permiso atómico correcto asignado. | Media | Media | Documentar explícitamente en el onboarding de usuarios (HU-F16.2) que el rol de negocio es solo una etiqueta descriptiva — el permiso atómico se asigna siempre por separado. |
| **RIESGO-ADM-12** | Bundle de producción con TanStack Table + Recharts + generación de PDF en cliente podría superar 800 KB gzipped si no se cuida el `dynamic import`. | Media | Media | Todas las gráficas (Fase 17) y el exportador de PDF (Fase 18) usan `React.lazy`/`import()` dinámico desde el inicio, no como optimización posterior. |
| **RIESGO-ADM-13** | Tablas densas (`DataTable` con 8-10 columnas en reportería/auditoría) son más difíciles de hacer accesibles (foco, lectura por lector de pantalla) que formularios simples. | Media | Media | Auditar con `@axe-core/playwright` cada `DataTable` nueva, no solo las pantallas de formulario. |
| **RIESGO-ADM-14** | La corrección del emisor JWT (HU-F13.2) podría afectar datos de prueba/QA que ya usan `rol='operador'` textual en vez de `'Usuario'`. | Baja | Baja | Se mantiene `"operador"` en la lista `ROLES_OPERADOR` explícitamente por retrocompatibilidad — no es un riesgo real si se implementa como se especifica. |
| **RIESGO-ADM-15** | La reconciliación de permisos en `workflows.py` (HU-F13.1) cambia qué código exacto gatea cada escritura — riesgo de romper una integración externa que ya asumiera los nombres viejos. | Baja | Baja | Verificado: ninguno de esos 4 recursos tiene hoy `write_enabled=True`, así que no existe ningún contrato externo real en producción que se pueda romper. |
| **RIESGO-ADM-16** | El límite real de 5 pairing tokens por hora por admin (rate limit ya implementado) podría generar fricción operativa al emparejar muchas sucursales el mismo día (p. ej. una apertura masiva). | Baja | Media | Documentar el límite visiblemente en la UI; no se propone aumentarlo sin una decisión de negocio explícita (debilitaría la defensa real contra abuso). |
| **RIESGO-ADM-17** | No existe hoy un endpoint de "listar todos los pairing tokens de todas las sucursales" — el estado de pairing por sucursal se deriva, no se consulta directo. | Baja | Baja | Ver `ABIERTO-52`. |
| **RIESGO-ADM-18** | Esta Parte II no construye ninguna pantalla de "reglas de alerta configurables" (a diferencia de un plan previo, que proponía una tabla `alert_rules` sin CU que la respalde) — si el negocio la pide más adelante, es una tabla nueva completa, no una extensión menor. | Baja | Media | Ver `ABIERTO-56`. |
| **RIESGO-ADM-19** | El modelo de tenancy real (`sucursales_permitidas`) asume una sola empresa hoy — si el negocio crece a multiempresa real, `DEC-ADM-02` y varias pantallas (selector, dashboard) necesitarían revisión. | Baja | Alta | Ver `ABIERTO-57`. No se construye una cascada empresa→sucursal especulativa sin necesidad real hoy. |
| **RIESGO-ADM-20** | No hay un mapeo por defecto entre los 6 roles de negocio de CU-08 y un conjunto sugerido de permisos atómicos — dar de alta un usuario "Auditor" no le otorga `audit_read` automáticamente. | Media | Media | Ver `ABIERTO-59`. |

### Decisiones abiertas (`ABIERTO-50` a `ABIERTO-60`)

> Numeración iniciada en 50 para no colisionar con la numeración de Sucursal (no se conoce el rango exacto que dejó la Parte I al momento de escribir esta Parte II; el ensamblador final del documento maestro debe renumerar si hace falta cerrar el hueco).

| ID | Decisión pendiente | Contexto | Opciones |
|---|---|---|---|
| **ABIERTO-50** | ¿Existe un campo "Título del ticket" por sucursal? | El corpus de CU original lo menciona en el flujo de creación de sucursal (CU-11); ninguna tabla del ER lo tiene. | (a) Usar `empresa.mensaje_bienvenida` como título implícito; (b) agregar `documentos.tipo='titulo_ticket'` (texto plano, mismo patrón que "observaciones", HU-F15.4); (c) confirmar con negocio que no hace falta un título distinto del nombre de la sucursal. |
| **ABIERTO-51** | ¿Se necesita un mecanismo de resolución manual de `sync_conflict` más allá de "last-write-wins" automático? | Ningún CU de esta Parte II lo pide explícitamente; el campo `resolucion` ya documenta qué se aplicó. | (a) Mantener solo lectura (esta Parte II); (b) agregar un endpoint de resolución manual si el negocio reporta casos reales de conflictos mal resueltos automáticamente. |
| **ABIERTO-52** | ¿Hace falta un endpoint de "listar todos los pairing tokens" cuando el número de sucursales crezca? | Hoy el estado de pairing se deriva por sucursal (HU-F19.3 BR4); funciona bien con pocas decenas de sucursales. | (a) Mantener el patrón derivado; (b) construir el endpoint de lista dedicado cuando el volumen lo justifique. |
| ~~**ABIERTO-53**~~ | ¿Modo oscuro en v1? | Ningún CU lo pide. | **Resuelto 2026-09-25**: (b) construirlo — el operador lo priorizó explícitamente. Ver `Fase 31`. |
| **ABIERTO-54** | ¿Cuándo se aborda `clientes_b2b` (convenios corporativos)? | CU-06 BR5 lo declara explícitamente "fase 2". | (a) Esperar a que negocio priorice esa fase 2 con su propio CU; (b) adelantarla si aparece demanda real de clientes corporativos. |
| **ABIERTO-55** | ¿Se construye un endpoint admin-iniciado para anular una FE antes del acuse DIAN? | Hoy solo existe el webhook DIAN-iniciado (`POST /revocacion-factura-webhook`); anular antes del acuse tiene implicaciones fiscales que exceden el alcance de planificación de este documento. | (a) No construirlo sin decisión de negocio/fiscal explícita; (b) construirlo si Legal/Contabilidad confirma que es una operación válida ante la DIAN. |
| **ABIERTO-56** | ¿Se necesitan reglas de alerta configurables por el admin (más allá de los 19 tipos sembrados — 8 de infraestructura + 11 operacionales)? | Un plan previo proponía una tabla `alert_rules` sin respaldo de ningún CU. | (a) No construirla sin un CU que la pida (posición de esta Parte II); (b) construirla como tabla nueva declarada (mismo patrón de excepción que `configuracion_caja`) si negocio la solicita explícitamente. |
| **ABIERTO-57** | ¿El negocio proyecta operar más de una empresa (multiempresa real) en el horizonte de este sistema? | Hoy `empresa` 1—N `sucursal` con una sola empresa en operación real. | (a) Mantener el modelo de tenancy simple actual (recomendado mientras haya una sola empresa); (b) diseñar la cascada empresa→sucursal cuando exista una segunda empresa real que la necesite. |
| **ABIERTO-58** | ¿Cuándo se justifica una vista materializada para reportería? | No hay evidencia de volumen real que lo requiera hoy. | (a) Medir tiempos de consulta reales tras el primer despliegue con datos de producción; (b) construir la vista materializada si superan un umbral acordado (p. ej. >2s en el p95). |
| **ABIERTO-59** | ¿Debe el alta de usuario (HU-F16.2) sugerir un set de permisos por defecto según el rol de negocio elegido? | Hoy rol y permisos son 100% independientes (DEC-ADM-03); un alta de "Auditor" no otorga `audit_read` automáticamente. | (a) Mantener 100% manual (más simple, menos "magia" implícita); (b) agregar una plantilla sugerida por rol que el admin puede aceptar o modificar al crear el usuario. |
| **ABIERTO-60** | ¿Se justifica extraer un paquete de workspace `apps/ui-kit` compartido entre `web_admin` y `web_sucursal`? | Hoy cada app mantiene su propio `components/ui/` independiente; un plan previo proponía el paquete compartido sin evidencia de duplicación real (§0.6). | (a) No extraerlo mientras la duplicación sea mínima (posición de esta Parte II); (b) extraerlo si el catálogo de componentes puramente visuales duplicados entre ambas apps supera 8-10. |

---

### Trazabilidad contra los CU originales

> Verificación explícita de que cada CU relevante a `web_admin` fue leído completo desde el `.md` original (no solo desde el digest) y que esta redacción cumple sus reglas de negocio, con las desviaciones ya reconciliadas contra el ER real.

| CU | Reglas/campos verificados contra el original | Desviación reconciliada en esta Parte II |
|---|---|---|
| CU-06 | BR1-BR5, AC1-AC6, flujo de 7 pasos, alerta `suscripcion_proxima_vencer` | Modelo cliente-céntrico (no "por placa" literal); `dias_alerta_pre_vencimiento` por suscripción (columna nueva, no default global); prorrateo BR3 en alcance con cálculo de referencia, no diferido ni contradictorio; `clientes_b2b` excluido explícitamente por BR5. |
| CU-07 | BR1-BR3, AC1-AC4, backoff exponencial | Lado admin acotado a monitoreo + pairing; el motor de sync en sí es transversal, no de `web_admin`. |
| CU-08 | BR1-BR4, AC1-AC3, 6 roles | Roles como valores libres de `usuarios.rol`; emisor JWT corregido para clasificar bien al rol `"Usuario"`; "username" reconciliado a `cedula`/`email`. |
| CU-09 | BR1-BR2, AC1-AC3 | Reportería financiera corregida (columnas reales, no las inventadas sobre `facturas`); sin vistas materializadas preventivas sin evidencia de necesidad. |
| CU-10 | BR1-BR4, AC1-AC3, 3 flujos (parcial/turno/diario) | Lado admin acotado a auditoría; `descuadre_pct` como dato informativo, la decisión de alerta real usa `configuracion_tolerancias` (valores absolutos). |
| CU-11 | BR1-BR8, AC1-AC9, E1-E6 | `regex_placa` no persiste (solo lectura documentada); capacidad validada contra ocupación calculada en vivo, sin columna `disponible`. |
| CU-12 | BR1-BR3, AC1-AC3, E1-E3 | CRUD limitado a la única columna de negocio real (`tipo`); sin CRUD de regex/prioridad/orden inexistentes en el ER. |
| CU-13 | BR1-BR2, AC1-AC3, E1-E2 | Tabla `configuracion_caja` nueva y declarada explícitamente (el ER no tiene `config_caja`); "umbral de alerta" reutiliza `configuracion_tolerancias` real en vez de duplicar la fuente de verdad. |
| CU-14 | BR1-BR3, AC1-AC5, 11 tipos de alerta | `alerta.estado` usa los 3 valores reales del ER (no `'ACTIVA'/'REVISADA'`); los 11 tipos operacionales se siembran explícitamente (hoy solo hay 8 de infraestructura/DIAN); sin reglas de alerta configurables sin respaldo de CU (`ABIERTO-56`). |

### Alcance explícitamente excluido de esta Parte II

Para que ningún desarrollador asuma que falta algo que en realidad se decidió no construir: `clientes_b2b`/convenios corporativos (CU-06 BR5, fase 2 del negocio), reglas de alerta configurables más allá de los 19 tipos sembrados, cascada empresa→sucursal (una sola empresa real hoy), modo oscuro, cambio de proveedor DIAN desde UI, anulación de FE admin-iniciada antes del acuse DIAN, endpoint dedicado de "listar todos los pairing tokens", vistas materializadas de reportería (sin evidencia de necesidad), y el paquete de workspace `apps/ui-kit` compartido. Cada uno tiene su `ABIERTO-##` correspondiente arriba con el criterio exacto para reabrirlo.

### Cierre

Esta Parte II queda autocontenida: cualquier desarrollador que la lea completa, sin acceso a ningún otro documento del proyecto, tiene el ER real (citado tabla por tabla), el estado verificado del backend (qué existe, qué está bloqueado por un permiso sin sembrar, qué falta construir), el estado verificado del frontend (`apps/web_admin` tal como está hoy en disco), las 20 decisiones de arquitectura que gobiernan el resto de las fases, las 8 fases con sus 40 historias de usuario y 168 tareas atómicas, la tabla consolidada de endpoints, la estrategia de pruebas y CI, y los riesgos/decisiones abiertas con los que el equipo debe seguir. Ninguna corrección de las auditorías de fidelidad se narra como "esto estaba mal": se aplicó en silencio en la redacción, con la nota de una línea donde ayudaba a que el desarrollador no repita el error (permisos nunca sembrados, columnas inventadas sobre `facturas`, el emisor JWT que clasifica mal a `"Usuario"`, la tabla `config_caja` que nunca existió en el ER canónico, el modelo de tenancy de 4 niveles que el backend real nunca implementó).




## PARTE III — INSTALADOR, DESPLIEGUE Y PRODUCCIÓN

> Parte III del documento maestro del proyecto de parqueaderos. Cubre el ciclo de vida completo del instalador de `web_sucursal` (instalación limpia, actualización, reparación, diagnóstico, desinstalación), la seguridad del entorno de escritorio, la firma de código y distribución, la operación en campo sin supervisión (backups, WAL, monitoreo, sincronización), la impresión térmica, el entorno de desarrollo local y el testing/CI-CD del propio instalador. El contenido es autocontenido: toda corrección derivada de auditorías previas ya está aplicada como texto final, no como hallazgo pendiente.

---

## Sección 0 — Visión del instalador y arquitectura de despliegue

### 0.1 Qué instala, dónde y qué queda corriendo

El nodo de sucursal (`web_sucursal`) se despliega en un equipo Windows del cliente que **no tiene Docker** y que, en el caso general, es hardware modesto compartido con la operación diaria de un parqueadero (un solo puesto de caja, sin equipo de TI local). El instalador es un único ejecutable — `parkos-installer.exe`, empaquetado desde `parkos-installer.ps1` (PowerShell 7 vía `ps2exe`) — que orquesta la instalación de todo el stack en una sola corrida.

Al terminar una instalación limpia, el equipo del cliente queda con:

| Componente | Naturaleza | Puerto/alcance | Notas |
|---|---|---|---|
| PostgreSQL 16 (+ `pg_partman`) | Servicio Windows nativo (`postgresql-x64-16`) | `127.0.0.1:5432` (o `:5433` si 5432 está ocupado) | Nunca expuesto a la LAN; solo loopback. |
| `api-sucursal` | Servicio Windows vía NSSM (`ParkosApiSucursal`) | `127.0.0.1:8000` | FastAPI empaquetado standalone (binario congelado, no requiere Python instalado en el equipo del cliente). |
| `job-sync-sucursal` | Servicio Windows vía NSSM (`ParkosJobSyncSucursal`) | Sin puerto de escucha (worker de salida; expone `/healthz` interno en `127.0.0.1:9999` solo para diagnóstico local) | Ejecuta el ciclo de sincronización descrito en la Fase 29. |
| `web_sucursal` (Electron) | Aplicación de escritorio instalada vía MSI | N/A (UI local) | No se autoarranca tras la instalación; el operador la abre al iniciar turno. |
| Módulo PowerShell `parkos` | Módulo de gestión post-instalación | N/A | Cmdlets documentados en la Fase 26. |

El instalador **nunca** escribe en el modelo de datos (`modelo_datos_er.mmd`, INTOCABLE): solo ejecuta migraciones Alembic ya existentes en el repositorio y siembra catálogos con `INSERT ... ON CONFLICT DO NOTHING`. No agrega tablas, columnas ni constraints.

```
Equipo Windows del cliente (sin Docker)
├── Servicio Windows: postgresql-x64-16          (127.0.0.1:5432|5433)
├── Servicio Windows: ParkosApiSucursal (NSSM)     (127.0.0.1:8000)
├── Servicio Windows: ParkosJobSyncSucursal (NSSM)  (worker, sin puerto público)
├── Aplicación: web_sucursal (Electron, MSI)
├── C:\Program Files\Parkos\
│   ├── api-sucursal\            (binario standalone)
│   ├── job-sync-sucursal\       (binario standalone)
│   ├── web_sucursal\            (Electron instalado)
│   └── nssm.exe
├── C:\ProgramData\Parkos\
│   ├── logs\                     (rotación 10 MB × 5 archivos, por servicio)
│   ├── pg-data\                  (data directory de Postgres)
│   ├── backups\                  (pg_dump programados, Fase 29)
│   ├── secrets\                  (clave JWT + .env; ACL restrictiva, Fase 27)
│   └── releases\                 (paquetes de las 2 últimas versiones estables, Fase 25/28)
└── C:\Program Files\PowerShell\Modules\parkos\   (módulo de gestión, Fase 26)
```

### 0.2 Decisiones de arquitectura del instalador (DEC-INST-01…16)

| ID | Decisión |
|---|---|
| **DEC-INST-01** | El instalador es un único TUI PowerShell 7 (`parkos-installer.ps1`, ANSI puro, sin `Terminal.Gui`), empaquetado a `.exe` con `ps2exe` para no exigir que el técnico de campo tenga PowerShell 7 antes de arrancar (el propio `.exe` se relanza en PS7 si detecta 5.1). |
| **DEC-INST-02** | Los binarios de `api-sucursal` y `job-sync-sucursal` se distribuyen **standalone** (entorno Python congelado con `uv`, sin depender de un Python del sistema): el equipo del cliente no necesita nada preinstalado salvo Windows 10 21H2+ y el Visual C++ Redistributable que el propio empaquetado incluye. |
| **DEC-INST-03** | Postgres 16 se instala vía `winget` (`PostgreSQL.PostgreSQL.16`) como método preferente, con fallback a un ZIP oficial de EDB para equipos sin `winget` o sin internet en el momento de instalar. |
| **DEC-INST-04** | El instalador nunca usa el superusuario `parkos` como identidad de conexión de los servicios en ejecución. Ver §0.3. |
| **DEC-INST-05** | La sesión de usuario final se modela como JWT Bearer, nunca como cookie. Ver §0.4. |
| **DEC-INST-06** | **Canal único de actualización: `latest`.** No existe canal `beta` en esta versión del producto: una mención a un canal piloto en una versión previa de este documento no estaba respaldada por ninguna decisión de arquitectura real, y queda descartada aquí de forma explícita. Un cliente piloto que necesite probar una versión candidata recibe un MSI etiquetado `-rc.N` instalado manualmente con `Repair-ParkosInstall -Version <rc>` (Fase 26), nunca mediante un segundo feed de auto-update. Si el negocio decide en el futuro que sí necesita un canal piloto real, eso exige una nueva decisión explícita (`DEC-INST-06-rev2`) que reemplace esta, no una convivencia tácita de dos canales. |
| **DEC-INST-07** | Firma de código con **Azure Trusted Signing** (HSM gestionado, cumple el requisito del CA/Browser Forum vigente desde 2023 para certificados EV) en vez de un `.pfx` plano. En staging se acepta un certificado autofirmado (con el warning de SmartScreen esperado y aceptado en ese ambiente). |
| **DEC-INST-08** | `allowDowngrade: false` en `electron-updater`. El rollback de una versión defectuosa en producción es un procedimiento manual documentado (Fase 25), nunca downgrade automático. |
| **DEC-INST-09** | NSSM (Non-Sucking Service Manager) como wrapper de servicios Windows para `api-sucursal` y `job-sync-sucursal`: decisión estándar de la industria para envolver binarios standalone como servicios administrados, con reinicio automático y logging integrado. |
| **DEC-INST-10** | Ambas conexiones a Postgres se distinguen explícitamente por identidad: la conexión de **migración** (superusuario `parkos`, usada solo por el paso de instalación/actualización) y la conexión de **runtime** (`parkos_app`, mínimo privilegio, usada por los dos servicios NSSM). Nunca se reutiliza la de migración para runtime. |
| **DEC-INST-11** | El instalador **no** introduce infraestructura de monitoreo nueva (sin Prometheus/Grafana/agentes externos). El heartbeat de salud reutiliza el canal de sincronización que el producto ya necesita para operar (Fase 29). |
| **DEC-INST-12** | Los backups automáticos usan `pg_dump` nativo (formato `custom`, `-Fc`) vía una tarea programada de Windows (`Register-ScheduledTask`), sin herramientas de terceros (`pgBackRest`/`wal-g` quedan fuera de alcance v1 por sobre-ingeniería para un solo nodo por sucursal). |
| **DEC-INST-13** | `pg_partman` en Windows nativo requiere binarios de terceros y `shared_preload_libraries` (no viene incluido en el instalador oficial de Postgres, a diferencia de la imagen Docker del entorno de desarrollo/cloud). El instalador lo trata como un paso propio con reinicio del servicio, no como un efecto colateral de `alembic upgrade head`. Ver Fase 22. |
| **DEC-INST-14** | El mantenimiento de particiones de `pg_partman` (`partman.run_maintenance_proc()`) se dispara desde una tarea programada de Windows que invoca `psql`, no desde `pg_cron` (extensión no disponible de forma confiable en el instalador oficial de Postgres para Windows). |
| **DEC-INST-15** | Licenciamiento/activación: ver RIESGO-INST-01 (recomendación explícita, Sección final). No se implementa un mecanismo de activación en línea obligatoria en v1: violaría el carácter *offline-capable* del producto. |
| **DEC-INST-16** | Compatibilidad de versión entre el auto-update de Electron (independiente) y la actualización del backend (instalador): `web_sucursal` valida en cada arranque que `GET /health` de `api-sucursal` reporta un `api_contract_version` compatible con el build de Electron; si no lo es, la UI bloquea la operación con un mensaje claro en vez de fallar de forma silenciosa a mitad de una transacción de caja. |

### 0.3 El rol de base de datos `parkos_app` y por qué el instalador nunca usa el superusuario

Este es el hallazgo más crítico que esta parte corrige. La migración `0021_least_privilege_and_immutability_contract.py` (ya mergeada en esta misma rama, commit `5edb317`, "la app deja de conectarse como superusuario") documenta el problema con precisión: el rol `rol_app` existe desde la migración inicial (`0001_initial_schema.py`) pero es `NOLOGIN` — un rol de agrupación de privilegios, nunca pensado para conectarse directamente. El único rol con `LOGIN` que existía hasta la `0021` era `parkos`, que además **es el superusuario de Postgres**. Como un superusuario ignora por definición cualquier `GRANT`/`REVOKE`, todo el contrato de mínimo privilegio que las migraciones anteriores habían escrito era, en la práctica, inerte: cada `REVOKE UPDATE/DELETE` era letra muerta porque la única identidad que se conectaba nunca pasaba por esa verificación.

La migración `0021` corrige la causa raíz creando el rol de login real:

```sql
-- Ejecutado automáticamente por `alembic upgrade head` (migración 0021),
-- nunca como paso manual separado del instalador:
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parkos_app') THEN
        CREATE ROLE parkos_app LOGIN INHERIT PASSWORD '<PARKOS_APP_DB_PASSWORD>';
    END IF;
END
$$;
GRANT rol_app TO parkos_app;
```

y a partir de ahí aplica, por primera vez de forma efectiva, `REVOKE`/`GRANT` columna-por-columna sobre `rol_app` para 36 tablas adicionales (26 `[V]`, `login`/`sesion`, 8 `[L-W]`/`[L-E]`, `envio_dian` con `UPDATE` acotado a la columna `payload`, y `alert_types` como catálogo de solo lectura para la aplicación). Once tablas `[A]` con trigger propio desde la `0001` (`fn_<tabla>_inmutable()`) no se tocan porque ya tenían protección real incluso contra el superusuario.

**Implicación directa para el instalador**: si el instalador crea únicamente el superusuario `parkos` con una contraseña aleatoria y apunta `PARKOS_DB_URL`/`DATABASE_URL` de los dos servicios NSSM a esa misma identidad, **reintroduce exactamente el problema que el commit `5edb317` acaba de cerrar** — todo el contrato de mínimo privilegio vuelve a ser inerte en el equipo del cliente, aunque el código ya lo soporte. Esta es la razón por la que la Fase 22 exige crear `parkos_app` como paso obligatorio de instalación, nunca opcional.

La regla que este instalador implementa, sin excepción:

1. **Conexión de migración** (privilegiada): el superusuario `parkos`, generado con contraseña aleatoria de 24+ caracteres en la Fase 22, usado **exclusivamente** por el paso `Invoke-MigrationsAndSeed` (Fase 23) y por `Update-ParkosStack` (Fase 25) al aplicar `alembic upgrade head`. Esta identidad nunca se escribe en el `.env` que consumen los servicios NSSM.
2. **Conexión de runtime** (mínimo privilegio): `parkos_app`, con la contraseña que el propio proceso de instalación genera y exporta como `PARKOS_APP_DB_PASSWORD` **antes** de invocar `alembic upgrade head` — la migración `0021` la lee de esa variable de entorno (con un default de desarrollo `parkos_app_dev` que el instalador **nunca** debe dejar vigente en un despliegue real). Esta es la única identidad que `PARKOS_DB_URL`/`DATABASE_URL` de `ParkosApiSucursal` y `ParkosJobSyncSucursal` conocen.

```mermaid
sequenceDiagram
    participant Inst as parkos-installer.ps1
    participant PG as PostgreSQL (superusuario parkos)
    participant Alembic as alembic upgrade head
    participant App as parkos_app (runtime)

    Inst->>Inst: genera password aleatoria (24+ chars) para `parkos` (superusuario)
    Inst->>Inst: genera password aleatoria (24+ chars) para PARKOS_APP_DB_PASSWORD
    Inst->>PG: initdb + CREATE ROLE parkos LOGIN SUPERUSER (paso único de instalación)
    Inst->>Alembic: DATABASE_URL=postgresql://parkos:<pw_superuser>@127.0.0.1:5432/parkos<br/>PARKOS_APP_DB_PASSWORD=<pw_app> (env var, no persistida en disco fuera de secrets\)
    Alembic->>PG: ejecuta 0001..0021 (incluida CREATE ROLE parkos_app + GRANT/REVOKE)
    PG-->>Alembic: head alcanzado
    Inst->>App: escribe C:\ProgramData\Parkos\secrets\.env con<br/>PARKOS_DB_URL/DATABASE_URL apuntando a parkos_app (NUNCA a parkos)
    Inst->>App: registra servicios NSSM leyendo ese .env
    App->>PG: conecta como parkos_app (mínimo privilegio, contrato REVOKE/GRANT real)
```

Ninguna instalación puede considerarse terminada si `PARKOS_DB_URL`/`DATABASE_URL` de los servicios en ejecución resuelve al usuario `parkos`. La Fase 22 (paso de creación de roles) y la Fase 24 (verificación post-instalación) incluyen un chequeo explícito de esta regla como *gate* bloqueante, no como buena práctica opcional.

### 0.4 Modelo de sesión: JWT Bearer, no cookie

El backend real de `parkos_core` (`POST /api/v1/auth/login`) autentica por `email` + `password` (bcrypt) y devuelve un `TokenPair` en el **cuerpo** de la respuesta JSON — nunca mediante `Set-Cookie`:

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "expires_in": 3600
}
```

No existe ninguna cookie `httpOnly` de sesión en el backend real; cualquier sección de un documento de producción que diseñe la seguridad de sesión alrededor de una cookie `parkos_session` describe un mecanismo que no existe y queda descartada aquí. El modelo real, que esta Parte III adopta como autoridad para todo lo relativo a sesión/token en instalación y producción:

- **Emisión**: `access_token` con TTL de 3600 s (1 hora); `refresh_token` con TTL de 7 días (`7 * 24 * 3600` s). Firma HS256 con secreto compartido leído de `PARKOS_JWT_KEY_PATH` (bytes crudos del archivo). Migración planeada a RS256 + JWKS con rotación (`JWT_OVERLAP_HOURS=24`) aún no implementada — HS256 es el estado real, no un detalle transitorio a ignorar.
- **Refresh**: `POST /api/v1/auth/refresh` intercambia el `refresh_token` por un nuevo `access_token`; en el estado actual del backend **no rota** el `refresh_token` (devuelve el mismo). El *pre-flight refresh* (renovar el access token antes de que expire, no solo al recibir 401) es responsabilidad del cliente Electron, no de esta parte del documento — se documenta aquí solo porque afecta el diseño de almacenamiento de abajo.
- **Logout**: `POST /api/v1/auth/logout` exige `Authorization: Bearer <access_token>` y cierra la fila `login` activa del usuario.
- **Almacenamiento en `web_sucursal` (Electron)**: ni `localStorage` del renderer ni una cookie (no aplica, no hay servidor HTTP intermedio que la fije). El patrón correcto para una app de escritorio Electron es mantener el par de tokens en memoria del **proceso principal** (`main`), nunca expuesto directamente al proceso `renderer`; el renderer solicita operaciones autenticadas vía IPC (`contextBridge`) y el main process adjunta el header `Authorization` al hacer la llamada HTTP real a `api-sucursal`. Para sobrevivir a un reinicio de la aplicación sin forzar un nuevo login en cada turno, el `refresh_token` se persiste cifrado con `safeStorage` de Electron (que en Windows delega en DPAPI, atado a la cuenta de usuario del sistema operativo) en `C:\ProgramData\Parkos\secrets\`, nunca en texto plano ni en `localStorage`. Esta decisión de almacenamiento del lado del cliente es responsabilidad de diseño de la app de escritorio (Parte II); se fija aquí porque la Fase 27 (seguridad desktop) de esta Parte III es quien la hace cumplir a nivel de instalador (permisos NTFS del directorio `secrets\`) y porque el mismo error de diseño (cookie inexistente) había contaminado la sección de producción que esta parte reemplaza.
- **Rate limiting** de `/auth/login`/`/auth/refresh` y el *lockout* tras intentos fallidos son trabajo de backend **pendiente de construir** (no implementado hoy, verificado por lectura directa de `auth.py`); el instalador no depende de ellos para nada de su propio ciclo de vida, pero la Fase 27 los deja como precondición explícita de seguridad antes de un primer despliegue en producción real (ver RIESGO-INST-04).
- **Secreto JWT en el filesystem del cliente**: dado que el backend cae al secreto de desarrollo hardcodeado (`_DEFAULT_DEV_SECRET`, visible en el propio código fuente) si `PARKOS_JWT_KEY_PATH` no apunta a un archivo real, el instalador trata esto como un *gate* de instalación obligatorio — no un detalle de configuración. Ver Fase 27.

### 0.5 Alcance y deslinde con el resto del documento maestro

Esta Parte III cubre exclusivamente instalador, despliegue y producción **de infraestructura** de `web_sucursal`. No duplica ni redefine:

- Las reglas de negocio de los 19 casos de uso (motor de tarifa, factura electrónica, arqueos, catálogos) — esas viven en la Parte que documenta la lógica de cada CU. En particular, la regla de IVA de CU-02 (BR5: si no hay tarifa de impuesto vigente, el sistema **rechaza el cobro con un error de configuración**, nunca calcula con 0%) pertenece al motor de tarifa de sucursal, no a esta parte. Se deja constancia aquí, en una sola línea, de que una versión previa de la documentación de producción proponía un *fallback* de IVA al 0% cuando no hay tarifa vigente — esa regla contradecía CU-02 BR5 y queda descartada; el motor de tarifa debe bloquear, no aproximar.
- Las decisiones de UX/accesibilidad/i18n de cada pantalla — pertenecen a la Parte de frontend correspondiente.
- Lo que es exclusivo de `web_admin` (consola cloud, PWA sin instalador nativo) no se repite aquí. Donde algo aplica a **ambos** frontends (backups de la base de datos cloud, monitoreo de sucursales desde el panel admin, WAL a nivel de motor Postgres) se marca explícitamente como *transversal* en la fase correspondiente; donde algo es exclusivo de sucursal (NSSM, Electron MSI, impresión térmica) se declara así y no se generaliza a admin.

---

## Fase 21 — Instalación limpia: pre-flight, EULA, rutas y arranque del instalador

### Objetivo

Entregar el punto de entrada único (`parkos-installer.exe`) que valida el equipo del cliente, obtiene el consentimiento legal, define las rutas de instalación y arranca el resto del pipeline (Postgres → migraciones → servicios → Electron) de forma reproducible, con rollback automático ante cualquier fallo.

### Tablas ER relevantes

Ninguna: esta fase no toca la base de datos todavía (se ejecuta antes de que Postgres exista en el equipo).

### Diagrama de estados de la fase

```mermaid
stateDiagram-v2
    [*] --> VerificandoPS7: parkos-installer.exe arranca
    VerificandoPS7 --> InstalandoPS7: PSVersion < 7.0
    InstalandoPS7 --> Relanzando: MSI de PS7 instalado silenciosamente
    Relanzando --> PreFlight: relanzado con -ExecutionPolicy Bypass
    VerificandoPS7 --> PreFlight: PSVersion >= 7.0

    PreFlight --> PreFlightFallo: algún check crítico falla
    PreFlightFallo --> [*]: exit 2, mensaje claro, sin cambios en el sistema

    PreFlight --> EULA: 6 checks OK
    EULA --> [*]: rechazada, exit 0, sin cambios
    EULA --> Rutas: aceptada

    Rutas --> Confirmacion: rutas válidas (editables, con defaults)
    Confirmacion --> Instalando: técnico confirma
    Instalando --> [*]: continúa en Fase 22 (Postgres)
```

### HU-F21.1 — Pre-flight check con 6 verificaciones bloqueantes

**Historia**: Como técnico de despliegue, al ejecutar `parkos-installer.exe` en el equipo del cliente quiero que el instalador verifique automáticamente que el equipo cumple los requisitos mínimos antes de tocar nada, para no dejar una instalación a medias por un problema detectable de antemano.

**Given/When/Then**:
- **Given** un equipo Windows 10 21H2 (o superior) con 5 GB libres en el disco de instalación, conectividad a internet, permisos de administrador y sin una instalación previa de Parkos,
  **When** el técnico ejecuta `parkos-installer.exe`,
  **Then** el instalador muestra 6 líneas de verificación en verde (`OK`) en menos de 2 segundos y avanza automáticamente a la pantalla de EULA.
- **Given** el equipo NO tiene permisos de administrador,
  **When** se ejecuta el instalador,
  **Then** el instalador se relanza a sí mismo con `Start-Process pwsh -Verb RunAs` una sola vez; si el usuario rechaza la elevación de UAC, el instalador termina con exit code `2` y un mensaje explícito ("Se requieren permisos de administrador para instalar Parkos").
- **Given** el disco de instalación tiene menos de 5 GB libres,
  **When** corre el pre-flight,
  **Then** el check de disco falla en rojo, el instalador no continúa a EULA, y el mensaje indica cuánto espacio falta.
- **Given** ya existe una instalación previa de Parkos en el equipo (detectada por la presencia de `C:\ProgramData\Parkos\pairing.json` o del servicio `ParkosApiSucursal`),
  **When** corre el pre-flight,
  **Then** el instalador detiene el flujo de instalación limpia y ofrece dos rutas: `Repair-ParkosInstall` (Fase 26) o `Update-ParkosStack` (Fase 25) — nunca continúa como si fuera una instalación nueva sobre un equipo ya provisto.

**Reglas de negocio**:
- BR1. Los 6 checks son: (1) Windows ≥ 10 21H2, (2) PowerShell ≥ 7 (o auto-instalable), (3) permisos de administrador, (4) ≥ 5 GB libres en el disco de instalación, (5) conectividad HTTP saliente (necesaria para descargar Postgres/NSSM/dependencias si no vienen en el payload), (6) ausencia de instalación previa.
- BR2. Ningún check individual puede omitirse con un flag silencioso salvo en modo `-Unattended` (Fase 30), y aun en ese modo el check de "instalación previa" nunca se salta: `-Unattended` sobre un equipo ya instalado siempre falla con exit `2`, nunca sobreescribe en silencio.
- BR3. El pre-flight es idempotente y de solo lectura: ejecutarlo dos veces seguidas nunca dejar rastros ni archivos temporales en el disco.

**Comandos concretos**:

```powershell
# T-F21.1-T2 — función Test-Preflight (extracto real, PowerShell 7)
function Test-Preflight {
    [CmdletBinding()]
    param()
    $results = [ordered]@{
        'Windows >= 10 21H2'      = (Test-WindowsVersion -MinBuild 19044)
        'PowerShell >= 7'         = ($PSVersionTable.PSVersion.Major -ge 7)
        'Permisos de administrador' = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
        'Espacio en disco (>=5GB)'  = ((Get-PSDrive -Name ($InstallPath.Substring(0,1))).Free -gt 5GB)
        'Conectividad saliente'     = (Test-NetConnection -ComputerName 'github.com' -Port 443 -InformationLevel Quiet)
        'Sin instalación previa'    = -not (Test-Path "$env:ProgramData\Parkos\pairing.json")
    }
    foreach ($check in $results.GetEnumerator()) {
        $color = if ($check.Value) { 'Green' } else { 'Red' }
        Write-Host ("[{0}] {1}" -f ($check.Value ? 'OK' : 'FALLO'), $check.Key) -ForegroundColor $color
    }
    return -not ($results.Values -contains $false)
}
```

**Pruebas**: 6 pruebas Pester unitarias (una por check, con mocks de `Test-NetConnection`/`Get-PSDrive`/`Test-Path`), más 1 prueba de integración que ejecuta `Test-Preflight` en una VM Windows limpia sin ninguna de las 6 condiciones satisfechas y verifica que las 6 fallan simultáneamente (no solo la primera).

**Tamaño estimado**: 100 LOC (función) + 100 LOC (tests).

**Tareas atómicas**:
- `HU-F21.1-T1`: Función `Test-WindowsVersion` (auxiliar de build mínimo).
- `HU-F21.1-T2`: Función `Test-Preflight` con los 6 checks.
- `HU-F21.1-T3`: Relanzamiento automático con `Start-Process pwsh -Verb RunAs` si no hay privilegios de administrador.
- `HU-F21.1-T4`: 6 pruebas Pester unitarias + 1 de integración en VM limpia.

---

### HU-F21.2 — Auto-instalación de PowerShell 7 cuando el equipo trae 5.1

**Historia**: Como técnico de despliegue, si el equipo del cliente trae PowerShell 5.1 (el default de fábrica en Windows), quiero que el instalador resuelva esto automáticamente sin pedirme un paso manual previo.

**Given/When/Then**:
- **Given** `$PSVersionTable.PSVersion` reporta 5.1,
  **When** se ejecuta `parkos-installer.exe`,
  **Then** el instalador descarga `powershell-7.4.x-win-x64.msi` desde GitHub Releases (URL fija, con verificación de hash SHA256 contra un valor embebido en el propio instalador), lo instala en modo silencioso (`msiexec /qn`), y se relanza a sí mismo bajo PowerShell 7 con `-ExecutionPolicy Bypass`, sin intervención del técnico.
- **Given** la descarga de PowerShell 7 falla (sin internet, GitHub inaccesible),
  **When** ocurre el fallo,
  **Then** el instalador termina con exit code `2` y un mensaje que indica exactamente qué instalar manualmente y desde dónde, sin dejar el equipo en un estado intermedio (ningún servicio ni archivo de Parkos creado todavía).

**Reglas de negocio**:
- BR1. La verificación de hash SHA256 del instalador de PS7 es obligatoria antes de ejecutar el MSI descargado; un hash que no coincide aborta con exit `2` (no se ejecuta un binario no verificado, aunque provenga de un dominio confiable).
- BR2. El relanzamiento preserva todos los argumentos originales de la invocación (incluidos los flags de `-Unattended` de la Fase 30).

**Comandos concretos**:

```powershell
function Ensure-PowerShell7 {
    if ($PSVersionTable.PSVersion.Major -ge 7) { return }
    Write-Host "Instalando PowerShell 7 (requerido)..." -ForegroundColor Yellow
    $msiPath = Join-Path $env:TEMP 'powershell-7.4.6-win-x64.msi'
    Invoke-WebRequest -Uri $script:PS7_MSI_URL -OutFile $msiPath -UseBasicParsing
    $actualHash = (Get-FileHash -Path $msiPath -Algorithm SHA256).Hash
    if ($actualHash -ne $script:PS7_MSI_SHA256) {
        throw "Hash de PowerShell 7 no coincide; instalación abortada por seguridad."
    }
    Start-Process msiexec.exe -ArgumentList "/i `"$msiPath`" /qn" -Wait
    Start-Process pwsh -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`" $args" -Wait
    exit $LASTEXITCODE
}
```

**Pruebas**: 1 prueba Pester con mock de `Invoke-WebRequest`/`Get-FileHash` (éxito), 1 con hash deliberadamente incorrecto (debe abortar), 1 de integración end-to-end en VM Windows con PS 5.1 de fábrica.

**Tamaño estimado**: 80 LOC + 60 LOC de tests.

**Tareas atómicas**:
- `HU-F21.2-T1`: Función `Ensure-PowerShell7` con descarga + verificación de hash.
- `HU-F21.2-T2`: Relanzamiento preservando argumentos originales.
- `HU-F21.2-T3`: 3 pruebas Pester (éxito, hash inválido, integración VM).

---

### HU-F21.3 — EULA y selección de rutas de instalación

**Historia**: Como técnico de despliegue, quiero ver y aceptar explícitamente los términos de licencia antes de que se instale nada, y poder confirmar (o ajustar) las rutas de instalación por defecto.

**Given/When/Then**:
- **Given** el pre-flight pasó,
  **When** se muestra la pantalla de EULA (contenido de `payload\README-EULA.txt`, incluidas las atribuciones de licencias de terceros: PostgreSQL BSD, NSSM dominio público, Electron MIT),
  **Then** el instalador exige una confirmación explícita ("Acepto") antes de continuar; si el técnico no acepta, el instalador termina con exit code `0` (salida limpia, no es un error) y no crea ningún archivo.
- **Given** el EULA fue aceptado,
  **When** se muestra la pantalla de rutas,
  **Then** el instalador propone `C:\Program Files\Parkos` (binarios) y `C:\ProgramData\Parkos` (datos) como defaults editables, y rechaza explícitamente rutas inválidas: `C:\Windows\`, `C:\Program Files (x86)\` (evita el árbol de 32 bits), rutas con espacios sin comillas correctamente escapadas para NSSM, o rutas en una unidad de red.

**Reglas de negocio**:
- BR1. El texto del EULA se muestra completo, con capacidad de scroll, nunca truncado ni resumido.
- BR2. Rechazar el EULA es una salida exitosa (`exit 0`), no un fallo — el instalador no debe registrar telemetría ni intentar nada más tras el rechazo.
- BR3. Las rutas confirmadas por el técnico se usan de forma consistente por el resto de las Fases 22-26; ningún paso posterior asume la ruta por defecto si el técnico la cambió aquí.

**Tablas/campos ER**: no aplica (paso pre-Postgres).

**Pruebas**: 2 pruebas Pester (aceptación/rechazo de EULA con exit codes correctos), 3 pruebas de validación de rutas (ruta inválida en `C:\Windows`, ruta con 32-bit `Program Files (x86)`, ruta de red UNC rechazada).

**Tamaño estimado**: 100 LOC + 80 LOC de tests.

**Tareas atómicas**:
- `HU-F21.3-T1`: Función `Show-Eula` con scroll y confirmación obligatoria.
- `HU-F21.3-T2`: Función `Read-InstallPaths` con validación de rutas prohibidas.
- `HU-F21.3-T3`: 5 pruebas Pester (2 EULA + 3 validación de rutas).

---

## Fase 22 — Postgres nativo, roles de mínimo privilegio y `pg_partman` en Windows

### Objetivo

Instalar PostgreSQL 16 como servicio Windows nativo, crear correctamente las dos identidades de conexión (superusuario de migración y `parkos_app` de runtime — ver §0.3), y resolver un problema real que la documentación previa del instalador no cubría: `pg_partman` no viene incluido en el instalador oficial de Postgres para Windows y requiere un paso propio con reinicio del servicio.

### Tablas ER relevantes

Esta fase no crea filas de negocio; prepara el motor de base de datos sobre el que la Fase 23 aplicará las migraciones. Las tablas particionadas por `pg_partman` que dependen de esta fase para funcionar correctamente son `salidas`, `caja`, y `sync_queue_lw_buffer` (ver Fase 29 para el rol de esta última en el motor de sincronización).

### Diagrama de estados

```mermaid
stateDiagram-v2
    [*] --> DetectandoPuertos: Fase 21 completada
    DetectandoPuertos --> InstalandoWinget: :5432 libre
    DetectandoPuertos --> InstalandoWingetPuerto5433: :5432 ocupado, :5433 libre
    DetectandoPuertos --> ErrorPuertos: ambos ocupados por un proceso no-Parkos
    ErrorPuertos --> [*]: exit 2, mensaje claro

    InstalandoWinget --> InstalandoZip: winget no disponible
    InstalandoWingetPuerto5433 --> InstalandoZip: winget no disponible
    InstalandoWinget --> PostgresListo: winget install OK
    InstalandoWingetPuerto5433 --> PostgresListo: winget install OK
    InstalandoZip --> PostgresListo: extracción + initdb OK
    InstalandoZip --> ErrorInstalacion: descarga o initdb falla
    ErrorInstalacion --> [*]: rollback, exit 1

    PostgresListo --> CreandoSuperusuario: CREATE ROLE parkos LOGIN SUPERUSER
    CreandoSuperusuario --> InstalandoPgPartman: contraseña de 24+ chars generada y persistida en secrets\
    InstalandoPgPartman --> ConfigurandoPreload: binarios pg_partman copiados a $PGLIB
    ConfigurandoPreload --> ReiniciandoServicio: shared_preload_libraries = 'pg_partman_bgw'
    ReiniciandoServicio --> ExtensionCreada: CREATE EXTENSION pg_partman (tras reinicio)
    ExtensionCreada --> TareaMantenimiento: Register-ScheduledTask para run_maintenance_proc()
    TareaMantenimiento --> [*]: continúa en Fase 23 (migraciones)
```

### HU-F22.1 — Detección de puertos y coexistencia con un Postgres preexistente

**Historia**: Como técnico de despliegue, si el equipo del cliente ya tiene otro Postgres corriendo (por ejemplo, de un ERP previo), quiero que el instalador de Parkos coexista con él sin conflicto, en vez de fallar o de interferir con la instancia existente.

**Given/When/Then**:
- **Given** el puerto `5432` está libre,
  **When** el instalador prueba la disponibilidad de puertos,
  **Then** Postgres de Parkos se instala escuchando en `5432`.
- **Given** el puerto `5432` está ocupado por otro proceso (Postgres u otro servicio),
  **When** el instalador prueba disponibilidad,
  **Then** usa automáticamente el puerto `5433` para su propia instancia, nombrada como servicio Windows `postgresql-x64-16-parkos` (para no colisionar con el nombre de servicio de un Postgres preexistente), y persiste el puerto elegido en la configuración de conexión que la Fase 23 en adelante usa.
- **Given** ambos puertos `5432` y `5433` están ocupados,
  **When** el instalador prueba disponibilidad,
  **Then** falla el pre-flight de esta fase con exit code `2` y un mensaje que lista los procesos que ocupan ambos puertos (`Get-NetTCPConnection` + `Get-Process`), sin intentar forzar nada.

**Reglas de negocio**:
- BR1. El instalador nunca detiene ni reconfigura un servicio Postgres preexistente que no le pertenezca.
- BR2. El puerto elegido queda grabado en `C:\ProgramData\Parkos\secrets\.env` (`PARKOS_PG_PORT`) para que toda fase posterior (migraciones, backups, health checks) lo lea de ahí en vez de asumir `5432`.

**Comandos concretos**:

```powershell
function Test-PostgresPorts {
    foreach ($port in 5432, 5433) {
        $inUse = Test-NetConnection -ComputerName '127.0.0.1' -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
        if (-not $inUse) { return $port }
    }
    throw "Puertos 5432 y 5433 ambos ocupados; no se puede instalar Postgres de Parkos."
}
```

**Pruebas**: 3 pruebas Pester con mocks de `Test-NetConnection` (5432 libre, 5432 ocupado→5433, ambos ocupados→excepción).

**Tamaño estimado**: 30 LOC + 40 LOC de tests.

**Tareas atómicas**:
- `HU-F22.1-T1`: Función `Test-PostgresPorts`.
- `HU-F22.1-T2`: Persistencia de `PARKOS_PG_PORT` en `.env`.
- `HU-F22.1-T3`: 3 pruebas Pester.

---

### HU-F22.2 — Instalación de Postgres 16 vía `winget` con fallback a ZIP EDB

**Historia**: Como técnico de despliegue, quiero que el instalador use el método más simple disponible (`winget`) y, si no está disponible o falla, recurra automáticamente a un ZIP oficial sin requerir mi intervención manual.

**Given/When/Then**:
- **Given** `winget` está disponible en el equipo,
  **When** el instalador ejecuta la instalación de Postgres,
  **Then** corre `winget install --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements` y verifica el código de salida.
- **Given** `winget` no está instalado (Windows 10 sin App Installer actualizado) o el comando falla,
  **When** el instalador detecta el fallo,
  **Then** descarga el ZIP oficial de EDB (`postgresql-16.x-windows-x64-binaries.zip`, ~150 MB, ya incluido en el payload `parkos-installer-payload-{version}.zip` para no depender de conectividad en ese momento) y lo extrae a `C:\Program Files\Parkos\postgresql\`.
- **Given** ninguno de los dos métodos funciona (winget falla Y el ZIP del payload está corrupto o ausente),
  **When** el instalador agota ambos caminos,
  **Then** termina con exit `1`, ejecuta el rollback de este paso (revierte cualquier archivo parcialmente extraído) y reporta el error de ambos métodos, no solo del último intentado.

**Reglas de negocio**:
- BR1. El ZIP de EDB va empaquetado dentro del payload del instalador (no se descarga en el momento) precisamente para que el fallback no dependa de que haya internet disponible cuando `winget` falla — el escenario más común de necesitar el fallback es justamente falta de conectividad.
- BR2. `initdb` se ejecuta con locale `es-CO.UTF-8` (o `Spanish_Colombia.1252` si el locale ICU no está disponible en el binario de Windows) para que el ordenamiento de texto (nombres de clientes, placas) sea consistente con el resto del stack.

**Comandos concretos**:

```powershell
function Install-PostgresViaWinget {
    winget install --id PostgreSQL.PostgreSQL.16 --silent `
        --accept-package-agreements --accept-source-agreements
    return $LASTEXITCODE -eq 0
}

function Install-PostgresViaZip {
    param([string]$PayloadZipPath, [string]$InstallPath)
    Expand-Archive -Path $PayloadZipPath -DestinationPath $InstallPath -Force
    & "$InstallPath\bin\initdb.exe" -D "$env:ProgramData\Parkos\pg-data" `
        --locale=es-CO --encoding=UTF8 -U parkos
}
```

**Pruebas**: 4 pruebas Pester (winget disponible/éxito, winget ausente→fallback ZIP, ambos fallan→rollback, `initdb` con locale correcto verificado por `pg_controldata`).

**Tamaño estimado**: 150 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F22.2-T1`: Función `Install-PostgresViaWinget`.
- `HU-F22.2-T2`: Función `Install-PostgresViaZip` con `initdb` y locale es-CO.
- `HU-F22.2-T3`: Lógica de fallback + rollback si ambos fallan.
- `HU-F22.2-T4`: 4 pruebas Pester.

---

### HU-F22.3 — Creación del superusuario de migración y del rol `parkos_app` de runtime

**Historia**: Como responsable de seguridad del despliegue, quiero que el instalador nunca deje los servicios de producción conectados como superusuario, para que el contrato de mínimo privilegio de la migración `0021` sea real en el equipo del cliente, no solo en el código.

**Given/When/Then**:
- **Given** Postgres acaba de instalarse (`initdb` completado),
  **When** el instalador provisiona las identidades,
  **Then** genera dos contraseñas aleatorias independientes de 24+ caracteres (una para `parkos`, superusuario de migración; otra para `PARKOS_APP_DB_PASSWORD`, la que usará el rol `parkos_app` de runtime) usando `RNGCryptoServiceProvider`/`[System.Security.Cryptography.RandomNumberGenerator]`, nunca `Get-Random` (no criptográficamente seguro).
- **Given** las dos contraseñas fueron generadas,
  **When** el instalador invoca `alembic upgrade head` (Fase 23),
  **Then** exporta `PARKOS_APP_DB_PASSWORD` como variable de entorno del proceso de migración (nunca la escribe en un archivo de log ni en el propio script de migración) para que la migración `0021` cree `parkos_app` con esa contraseña real, no con el default de desarrollo `parkos_app_dev`.
- **Given** la migración terminó y `parkos_app` existe,
  **When** el instalador escribe la configuración de runtime,
  **Then** `C:\ProgramData\Parkos\secrets\.env` contiene `PARKOS_DB_URL`/`DATABASE_URL` apuntando exclusivamente a `parkos_app` (nunca a `parkos`), y el archivo recibe la ACL restrictiva descrita en la Fase 27 antes de que cualquier servicio lo lea.
- **Given** un técnico intenta (por error o por un script de terceros) apuntar `PARKOS_DB_URL` de un servicio NSSM al superusuario `parkos`,
  **When** corre la verificación post-instalación (`HU-F24.4`),
  **Then** el chequeo detecta que el usuario de la cadena de conexión de runtime es `parkos` y bloquea con un error explícito ("los servicios de Parkos nunca deben conectarse como superusuario; usa `parkos_app`"), no una advertencia silenciosa.

**Reglas de negocio**:
- BR1. `PARKOS_APP_DB_PASSWORD` nunca debe quedar en el valor por defecto `parkos_app_dev` (el que la migración usa si la variable no está seteada) fuera de un entorno de desarrollo/CI explícitamente marcado como tal.
- BR2. La contraseña del superusuario `parkos` no se persiste en ningún archivo de configuración de los servicios en ejecución — solo existe en `C:\ProgramData\Parkos\secrets\.env.migration` (permisos aún más restrictivos que el `.env` de runtime: solo la cuenta de servicio administrativa que corre `Update-ParkosStack`, nunca `svc-parkos`, ver Fase 27).
- BR3. `rol_app` permanece `NOLOGIN` — nunca se le agrega la capacidad de login directamente; solo `parkos_app` hereda sus privilegios vía `GRANT rol_app TO parkos_app`.

**Comandos concretos**:

```powershell
function New-SecurePassword {
    param([int]$Length = 24)
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).Substring(0, $Length) -replace '[+/=]', 'x'
}

function Initialize-DatabaseRoles {
    param([string]$InstallPath, [int]$Port)

    $superuserPassword = New-SecurePassword
    $appPassword = New-SecurePassword

    # 1. Crear el superusuario de migración (rol único que hace login con privilegios completos).
    & "$InstallPath\bin\psql.exe" -p $Port -U postgres -c `
        "ALTER ROLE parkos WITH PASSWORD '$superuserPassword' SUPERUSER LOGIN;"

    # 2. Persistir la conexión de migración (solo para Update-ParkosStack, ACL propia — Fase 27).
    $migrationEnv = @"
PARKOS_MIGRATION_DB_URL=postgresql://parkos:$superuserPassword@127.0.0.1:$Port/parkos
"@
    Set-Content -Path "$env:ProgramData\Parkos\secrets\.env.migration" -Value $migrationEnv -NoNewline

    # 3. Exportar PARKOS_APP_DB_PASSWORD SOLO para el proceso hijo que corre alembic (Fase 23);
    #    nunca queda en $env:PARKOS_APP_DB_PASSWORD del proceso padre del instalador.
    return @{ SuperuserPassword = $superuserPassword; AppPassword = $appPassword }
}
```

```powershell
# Fase 23 consume el resultado de arriba así (extracto de Invoke-MigrationsAndSeed):
$roles = Initialize-DatabaseRoles -InstallPath $InstallPath -Port $Port
$env:DATABASE_URL = "postgresql://parkos:$($roles.SuperuserPassword)@127.0.0.1:$Port/parkos"
$env:PARKOS_APP_DB_PASSWORD = $roles.AppPassword
& uv run alembic upgrade head
Remove-Item Env:\PARKOS_APP_DB_PASSWORD   # nunca queda en el entorno del proceso padre tras usarla

# .env de runtime (nunca usa parkos, siempre parkos_app):
$runtimeEnv = @"
PARKOS_DB_URL=postgresql+psycopg://parkos_app:$($roles.AppPassword)@127.0.0.1:$Port/parkos
DATABASE_URL=postgresql+asyncpg://parkos_app:$($roles.AppPassword)@127.0.0.1:$Port/parkos
"@
Add-Content -Path "$env:ProgramData\Parkos\secrets\.env" -Value $runtimeEnv
```

**Pruebas**: 5 pruebas Pester — generación de contraseña con entropía suficiente (no `Get-Random`), `.env` de runtime nunca contiene la palabra `SUPERUSER` ni la contraseña del superusuario, `.env.migration` tiene ACL distinta y más restrictiva que `.env`, verificación post-instalación detecta y bloquea si `PARKOS_DB_URL` de un servicio apunta a `parkos`, y una prueba de integración completa que levanta Postgres real en CI y confirma que `parkos_app` no puede ejecutar `CREATE ROLE` ni `DROP TABLE` (mínimo privilegio real, no solo declarado).

**Tamaño estimado**: 180 LOC + 150 LOC de tests.

**Tareas atómicas**:
- `HU-F22.3-T1`: Función `New-SecurePassword` (criptográficamente segura).
- `HU-F22.3-T2`: Función `Initialize-DatabaseRoles` (superusuario + export de `PARKOS_APP_DB_PASSWORD`).
- `HU-F22.3-T3`: Escritura separada de `.env.migration` (privilegiada) y `.env` (runtime, solo `parkos_app`).
- `HU-F22.3-T4`: Chequeo post-instalación que bloquea si el runtime apunta al superusuario.
- `HU-F22.3-T5`: 5 pruebas Pester (incluida 1 de integración contra Postgres real en CI verificando privilegios reales de `parkos_app`).

---

### HU-F22.4 — `pg_partman` en Windows nativo: binarios, `shared_preload_libraries` y mantenimiento programado

**Historia**: Como técnico de despliegue, quiero que el instalador deje `pg_partman` completamente funcional (no solo la extensión creada, sino el particionado automático en marcha) porque varias tablas de alto volumen (`salidas`, `caja`, `sync_queue_lw_buffer`) lo requieren para no degradar con el tiempo.

**Corrección aplicada**: la versión anterior de este plan trataba `CREATE EXTENSION pg_partman` como si bastara con que la migración `0001_initial_schema.py` la ejecutara. Eso es cierto para el entorno Docker (la imagen `parkos-postgres:16-pgpartman` ya trae los binarios de `pg_partman` compilados y `shared_preload_libraries` configurado de fábrica), pero **no** para un Postgres instalado nativamente en Windows vía `winget` o el ZIP de EDB: ninguno de los dos incluye los binarios de `pg_partman` (es una extensión en C, compilada contra la versión exacta de Postgres, que no forma parte de la distribución oficial). Sin este paso adicional, `CREATE EXTENSION pg_partman;` simplemente falla con `could not open extension control file`.

**Given/When/Then**:
- **Given** Postgres 16 nativo está instalado y el superusuario `parkos` existe,
  **When** el instalador ejecuta el paso de `pg_partman`,
  **Then** copia los binarios de `pg_partman` (precompilados para Postgres 16 Windows x64, incluidos en el payload — no se compilan en el equipo del cliente) a `$InstallPath\lib\` y `$InstallPath\share\extension\`, agrega `pg_partman_bgw` a `shared_preload_libraries` en `postgresql.conf`, y **reinicia el servicio Postgres** (paso obligatorio: `shared_preload_libraries` solo se aplica en el arranque del proceso, no con `SELECT pg_reload_conf()`).
- **Given** el servicio reinició correctamente,
  **When** el instalador continúa,
  **Then** ejecuta `CREATE EXTENSION IF NOT EXISTS pg_partman;` como el superusuario `parkos`, y verifica con `SELECT * FROM pg_extension WHERE extname = 'pg_partman';` que la extensión quedó activa antes de continuar a la Fase 23.
- **Given** el reinicio del servicio Postgres falla (por ejemplo, un error de sintaxis introducido al escribir `shared_preload_libraries`),
  **When** el instalador detecta que el servicio no vuelve a `Running` en 30 segundos,
  **Then** revierte `postgresql.conf` a la copia de respaldo tomada antes de la edición, reinicia de nuevo, y solo entonces marca el paso como fallido si el segundo intento también falla — nunca deja Postgres inoperante sin haber intentado el rollback de configuración.

**Reglas de negocio**:
- BR1. El mantenimiento de particiones (`partman.run_maintenance_proc()`) se agenda vía `Register-ScheduledTask` de Windows, invocando `psql` con un script SQL fijo cada 24 horas — no se depende de `pg_cron` (extensión con el mismo problema de no venir incluida, y con menor beneficio marginal para una carga de un solo nodo por sucursal frente a una tarea programada nativa de Windows).
- BR2. La tarea de mantenimiento corre con la cuenta de servicio `svc-parkos` (Fase 27), nunca con el superusuario, usando `parkos_app` — que sí tiene los privilegios necesarios sobre las tablas particionadas que administra, dado que `pg_partman` opera sobre las particiones ya creadas, no sobre el catálogo de roles.
- BR3. El backup de `postgresql.conf` antes de cualquier edición automática es obligatorio y se conserva en `C:\ProgramData\Parkos\backups\config\postgresql.conf.bak-<timestamp>`.

**Comandos concretos**:

```powershell
function Install-PgPartman {
    param([string]$InstallPath, [string]$PayloadPath, [int]$Port)

    # 1. Copiar binarios precompilados (payload\pg_partman\pg16-win-x64\*)
    Copy-Item "$PayloadPath\pg_partman\lib\*"       "$InstallPath\lib\"              -Force
    Copy-Item "$PayloadPath\pg_partman\extension\*" "$InstallPath\share\extension\"  -Force

    # 2. Backup + edición de postgresql.conf
    $confPath = "$env:ProgramData\Parkos\pg-data\postgresql.conf"
    Copy-Item $confPath "$env:ProgramData\Parkos\backups\config\postgresql.conf.bak-$(Get-Date -Format yyyyMMddHHmmss)"
    Add-Content -Path $confPath -Value "shared_preload_libraries = 'pg_partman_bgw'"

    # 3. Reiniciar el servicio (obligatorio para shared_preload_libraries)
    Restart-Service -Name 'postgresql-x64-16' -Force
    $started = Wait-ForServiceStatus -Name 'postgresql-x64-16' -Status 'Running' -TimeoutSeconds 30
    if (-not $started) {
        Write-Warning "Postgres no reinició tras configurar pg_partman; revirtiendo postgresql.conf"
        Copy-Item "$env:ProgramData\Parkos\backups\config\postgresql.conf.bak-*" $confPath -Force
        Restart-Service -Name 'postgresql-x64-16' -Force
        throw "pg_partman: reinicio de Postgres falló incluso tras revertir la configuración."
    }

    # 4. Crear la extensión y verificar
    & "$InstallPath\bin\psql.exe" -p $Port -U parkos -c "CREATE EXTENSION IF NOT EXISTS pg_partman;"
    $check = & "$InstallPath\bin\psql.exe" -p $Port -U parkos -tAc `
        "SELECT 1 FROM pg_extension WHERE extname = 'pg_partman';"
    if ($check.Trim() -ne '1') { throw "pg_partman no quedó activo tras CREATE EXTENSION." }
}

function Register-PgPartmanMaintenance {
    $action = New-ScheduledTaskAction -Execute "$InstallPath\bin\psql.exe" `
        -Argument "-U parkos_app -d parkos -c `"CALL partman.run_maintenance_proc();`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 2am
    $principal = New-ScheduledTaskPrincipal -UserId 'svc-parkos' -LogonType ServiceAccount
    Register-ScheduledTask -TaskName 'ParkosPgPartmanMaintenance' `
        -Action $action -Trigger $trigger -Principal $principal `
        -Description 'Mantenimiento diario de particiones pg_partman (Parkos)'
}
```

**Pruebas**: 5 pruebas Pester — copia de binarios verificada, edición de `postgresql.conf` con backup previo confirmado, reinicio exitoso detectado dentro del timeout, rollback de configuración cuando el reinicio falla, y verificación de que `CREATE EXTENSION pg_partman` deja la extensión realmente activa (consulta a `pg_extension`). Prueba de integración adicional en VM: instalar sobre Postgres 16 real, confirmar partición diaria creada para una tabla de prueba tras invocar `run_maintenance_proc()` manualmente.

**Tamaño estimado**: 220 LOC + 160 LOC de tests.

**Tareas atómicas**:
- `HU-F22.4-T1`: Empaquetado de binarios `pg_partman` precompilados para Postgres 16 Windows x64 en el payload.
- `HU-F22.4-T2`: Función `Install-PgPartman` (copia + `shared_preload_libraries` + reinicio + verificación).
- `HU-F22.4-T3`: Rollback de `postgresql.conf` si el reinicio falla.
- `HU-F22.4-T4`: Función `Register-PgPartmanMaintenance` (tarea programada diaria).
- `HU-F22.4-T5`: 6 pruebas Pester (5 unitarias + 1 de integración VM).

---

## Fase 23 — Migraciones Alembic y seed inicial de catálogos

### Objetivo

Aplicar las 21+ migraciones Alembic existentes sobre la base de datos recién creada y sembrar los catálogos mínimos para que una sucursal recién instalada sea operativa desde el primer turno, sin intervención manual de un administrador. Esta fase corrige dos huecos reales encontrados en la documentación previa: la ausencia de seed de `impuestos` (IVA) y de `config_caja`.

### Tablas ER relevantes

| Tabla | Clase ER | Seed en esta fase | Motivo |
|---|---|---|---|
| `permisos` | `[V]` | Sí (catálogo fijo) | Ya cubierto por migración `0001` (sembrado idempotente). |
| `tipo_persona` | `[V]` | Sí (catálogo fijo) | Ya cubierto por migración `0001`/`0020`. |
| `tipos_vehiculo` | `[V]` | Sí (catálogo base: `carro`, `moto`, `bicicleta`, `patineta`) | **No** tiene seed idempotente en ninguna migración real hoy; el instalador lo aporta como paso propio, no como si ya existiera. |
| `tipo_tarifa` | `[V]` | Sí | Idem — sin seed en migración; aportado por el instalador. |
| `tipo_arqueo` | `[V]` | Sí (`cierre_turno`, `auditoria`, `cierre_sesion`) | Idem. |
| `alert_types` | catálogo out-of-catalog, sin FK física | Sí — **8 filas reales**, no 11 | La migración `0013_add_alert_types.py` siembra exactamente 8 filas de infraestructura/DIAN (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`). Los tipos operativos de negocio (`capacidad_agotada`, `descuadre_critico`, etc.) que otras partes del sistema usan pertenecen al catálogo de negocio de esas partes, no a esta migración de infraestructura — el instalador no inventa 3 filas adicionales que no tienen respaldo real en el código. |
| **`impuestos`** | `[V]` | **Sí — corrección aplicada aquí** | Ninguna migración ni tarea previa del instalador sembraba el registro de IVA. CU-02 BR5 exige un registro de IVA vigente para poder calcular cualquier tarifa; sin este seed, una sucursal recién instalada no puede cobrar absolutamente nada hasta que alguien inserte manualmente la fila. Ver HU-F23.3. |
| **`config_caja`** | `[V]` | **Sí — corrección aplicada aquí** | CU-13 (Configurar base de caja) no tenía dueño en ningún documento previo: ni pantalla de administración ni seed por defecto. Sin un valor inicial de `base_inicial`, el primer arqueo del primer turno no tiene contra qué comparar el efectivo esperado. Ver HU-F23.3. |

### HU-F23.1 — Ejecución de `alembic upgrade head` con conexión de migración

**Historia**: Como técnico de despliegue, quiero que el instalador aplique todas las migraciones existentes en un solo paso, de forma idempotente, usando la conexión de migración (superusuario) definida en la Fase 22, nunca la de runtime.

**Given/When/Then**:
- **Given** los roles `parkos` (superusuario) y `parkos_app` fueron creados en la Fase 22,
  **When** el instalador ejecuta `Invoke-MigrationsAndSeed`,
  **Then** setea `DATABASE_URL` a la conexión de migración (superusuario), exporta `PARKOS_APP_DB_PASSWORD` solo para ese proceso hijo, y ejecuta `alembic upgrade head` con salida transmitida en vivo a la consola del instalador (no un log silencioso hasta el final).
- **Given** el equipo ya tiene una base de datos parcialmente migrada (por ejemplo, tras un intento de instalación previo que falló a mitad de camino),
  **When** se re-ejecuta `alembic upgrade head`,
  **Then** el comando es idempotente: Alembic detecta la revisión actual (`alembic current`) y solo aplica las migraciones pendientes, sin error ni duplicación.
- **Given** una migración individual falla a mitad del proceso (por ejemplo, un timeout de lock),
  **When** el instalador detecta el código de salida distinto de 0,
  **Then** detiene el flujo, no continúa al seed de catálogos, y reporta la revisión exacta en la que falló (`alembic current` antes y después del intento) para que el diagnóstico (Fase 26) tenga contexto preciso.

**Reglas de negocio**:
- BR1. Todas las migraciones usan `lock_timeout` corto (5 s, ya establecido como convención en las migraciones reales del repositorio) para no dejar el instalador colgado indefinidamente si otra sesión tiene un lock sobre una tabla.
- BR2. La conexión de migración nunca se reutiliza para el seed de catálogos de negocio (`tipos_vehiculo`, `tipo_tarifa`, etc. — HU-F23.2) si ese seed pasa por el API real (`POST /api/v1/catalogos/...`) en vez de SQL directo; en ese caso el seed usa un JWT `admin-` de un solo uso emitido localmente, nunca la conexión de base de datos directa, para no crear un camino de escritura que se salte las reglas de negocio del propio backend.

**Comandos concretos**:

```powershell
function Invoke-MigrationsAndSeed {
    param([hashtable]$Roles, [int]$Port)

    $env:DATABASE_URL = "postgresql://parkos:$($Roles.SuperuserPassword)@127.0.0.1:$Port/parkos"
    $env:PARKOS_APP_DB_PASSWORD = $Roles.AppPassword
    try {
        Push-Location "$InstallPath\api-sucursal"
        & .\venv\Scripts\alembic.exe upgrade head 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) {
            $current = & .\venv\Scripts\alembic.exe current
            throw "alembic upgrade head falló. Revisión actual: $current"
        }
    } finally {
        Pop-Location
        Remove-Item Env:\PARKOS_APP_DB_PASSWORD -ErrorAction SilentlyContinue
    }
}
```

**Pruebas**: 3 pruebas Pester (`alembic upgrade head` sobre DB vacía, re-ejecución idempotente sobre DB ya migrada, fallo simulado reporta la revisión exacta). 1 prueba de integración en CI contra Postgres real que verifica el conteo final de tablas (51, contra el ER canónico) y la presencia de las 8 filas exactas de `alert_types`.

**Tamaño estimado**: 90 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F23.1-T1`: Función `Invoke-MigrationsAndSeed` (wrapper de `alembic upgrade head`).
- `HU-F23.1-T2`: Manejo de error con reporte de revisión actual/objetivo.
- `HU-F23.1-T3`: 4 pruebas (3 unitarias + 1 de integración con conteo de tablas real).

---

### HU-F23.2 — Seed idempotente de catálogos operativos base

**Historia**: Como técnico de despliegue, quiero que una sucursal recién instalada tenga los catálogos mínimos de operación (tipos de vehículo, tipos de tarifa, tipos de arqueo) poblados desde el primer arranque, sin que el primer operador tenga que crearlos manualmente antes de poder cobrar el primer ingreso.

**Given/When/Then**:
- **Given** las migraciones terminaron y el servicio `api-sucursal` aún no está corriendo (o corre en modo mantenimiento sin exponerse a la LAN),
  **When** el instalador ejecuta el seed de catálogos,
  **Then** inserta `carro`, `moto`, `bicicleta`, `patineta` en `tipos_vehiculo` (cada uno con su `formato_placa_regex` correspondiente: `^[A-Z]{3}[0-9]{3}$` para carro, `^[A-Z]{3}[0-9]{2}[A-Z]$` para moto — los dos únicos formatos con respaldo real en CU-01 BR5; `bicicleta`/`patineta` se siembran con una regex documentada como decisión de producto explícita, no como requisito derivado del corpus de casos de uso, dado que ningún CU define su formato), `cierre_turno`/`auditoria`/`cierre_sesion` en `tipo_arqueo`, y `natural`/`juridica` en `tipo_persona` si la migración `0020` no los dejó ya sembrados.
- **Given** el instalador se re-ejecuta sobre una sucursal ya sembrada (actualización, no instalación limpia),
  **When** corre el seed,
  **Then** cada inserción usa `ON CONFLICT DO NOTHING` sobre la clave natural del catálogo (`tipo`/`codigo`), de forma que una segunda ejecución no duplica filas ni genera error.
- **Given** el seed se ejecuta contra el API real (no SQL directo) para respetar las reglas de negocio de creación de catálogo,
  **When** el instalador arma la petición,
  **Then** emite un JWT `admin-` local de un solo uso (firmado con la misma clave que `PARKOS_JWT_KEY_PATH`, TTL de 5 minutos, revocado lógicamente al terminar el seed por su propia expiración corta) y llama `POST /api/v1/catalogos/{tabla}` con `X-Sucursal-Context` fijado a la sucursal recién instalada.

**Reglas de negocio**:
- BR1. El seed de `bicicleta`/`patineta` se marca explícitamente en los logs de instalación como "catálogo de producto, no de negocio verificado por CU" — una futura auditoría de fidelidad a los CU no debe interpretar esta fila como si viniera de una regla de negocio documentada.
- BR2. El JWT local de seed nunca se persiste a disco ni se loguea; vive solo en memoria del proceso del instalador durante la ejecución de este paso.

**Comandos concretos**:

```powershell
function Invoke-CatalogSeed {
    param([string]$ApiBaseUrl, [string]$JwtKeyPath, [guid]$SucursalUuid)

    $seedJwt = New-LocalAdminJwt -KeyPath $JwtKeyPath -SucursalUuid $SucursalUuid -TtlSeconds 300
    $catalogos = @{
        'tipos-vehiculo' = @(
            @{ tipo = 'carro';     formato_placa_regex = '^[A-Z]{3}[0-9]{3}$' }
            @{ tipo = 'moto';      formato_placa_regex = '^[A-Z]{3}[0-9]{2}[A-Z]$' }
            @{ tipo = 'bicicleta'; formato_placa_regex = '^[A-Z0-9]{5,7}$' }   # decisión de producto, sin respaldo de CU
            @{ tipo = 'patineta';  formato_placa_regex = '^[A-Z0-9]{5,7}$' }
        )
        'tipo-arqueo' = @(
            @{ codigo = 'cierre_turno' }, @{ codigo = 'auditoria' }, @{ codigo = 'cierre_sesion' }
        )
    }
    foreach ($tabla in $catalogos.Keys) {
        foreach ($fila in $catalogos[$tabla]) {
            Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/catalogos/$tabla" `
                -Headers @{ Authorization = "Bearer $seedJwt"; 'X-Sucursal-Context' = $SucursalUuid } `
                -Body ($fila | ConvertTo-Json) -ContentType 'application/json' `
                -ErrorAction Continue   # ON CONFLICT DO NOTHING equivalente a nivel de API: 409 tolerado
        }
    }
}
```

**Pruebas**: 6 pruebas Pester (una por catálogo insertado + verificación de regex correcta por tipo), 1 prueba de re-ejecución idempotente (segunda corrida no duplica ni falla), 1 prueba que confirma que el JWT de seed nunca aparece en los logs de instalación.

**Tamaño estimado**: 120 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F23.2-T1`: Función `New-LocalAdminJwt` (JWT de un solo uso, TTL 5 min).
- `HU-F23.2-T2`: Función `Invoke-CatalogSeed` con los 3 catálogos base.
- `HU-F23.2-T3`: Manejo idempotente de conflictos (`ON CONFLICT`/409 tolerado).
- `HU-F23.2-T4`: 8 pruebas Pester.

---

### HU-F23.3 — Seed de `impuestos` (IVA) y `config_caja` (base de caja) — corrección de un hueco real

**Historia**: Como técnico de despliegue, quiero que una sucursal recién instalada pueda calcular tarifas y abrir su primer turno de caja sin que un administrador tenga que insertar manualmente el IVA vigente o la base de caja inicial antes del primer cliente.

**Corrección aplicada**: ningún módulo del proyecto le daba dueño real a `config_caja`, y el seed inicial del instalador nunca incluía `impuestos`. Ambos son bloqueantes operativos reales: sin `impuestos` vigente, CU-02 BR5 obliga al sistema a **rechazar** cualquier cálculo de tarifa (no a calcular con 0% — esa era una regla incorrecta de una versión previa de la documentación de producción, ya descartada en la Sección 0.5); sin `config_caja.base_inicial`, el primer arqueo de caja no tiene contra qué comparar el efectivo esperado.

**Given/When/Then**:
- **Given** el seed de catálogos base (HU-F23.2) terminó,
  **When** el instalador continúa con este paso,
  **Then** siembra en `impuestos` una fila de IVA con `nombre='IVA'`, `porcentaje=19.00`, `estado='VIGENTE'`, `vigente_desde` = fecha/hora de instalación (UTC), `vigente_hasta` = `NULL` — usando el mismo mecanismo de JWT local de un solo uso que HU-F23.2 (o, si el endpoint de `impuestos` aún no acepta escritura vía API en la versión instalada, un `INSERT ... ON CONFLICT DO NOTHING` directo ejecutado con la conexión de migración, documentado explícitamente como tal en el log de instalación).
- **Given** el seed de `impuestos` terminó,
  **When** el instalador continúa,
  **Then** siembra en `config_caja` una fila con `base_inicial` = 0 (valor conservador; el primer arqueo real del cliente parte de una base configurable en cero hasta que el administrador la ajuste desde `web_admin`), `redondeo` = el criterio por defecto documentado (redondeo a la centena para pesos colombianos), y `denominaciones_permitidas` = el conjunto estándar de billetes/monedas COP vigentes.
- **Given** una instalación se ejecuta como **actualización** de una sucursal ya operativa (no instalación limpia),
  **When** corre este paso,
  **Then** el seed de `impuestos`/`config_caja` se omite si ya existe una fila vigente para la sucursal (verificación explícita antes de insertar, no solo `ON CONFLICT` sobre una clave que podría no existir todavía en el esquema real) — nunca sobreescribe un IVA o una base de caja que el administrador ya configuró manualmente.

**Reglas de negocio**:
- BR1. El 19% es el valor vigente de IVA en Colombia al momento de escribir este documento; se documenta explícitamente como un valor de configuración inicial editable desde `web_admin`, no como una constante de código — el instalador solo provee un punto de partida operable, la fuente de verdad editable vive en la pantalla de administración de impuestos.
- BR2. Este seed es el punto donde esta Parte III se detiene explícitamente en el límite de su alcance: la pantalla de administración de `config_caja` (CRUD real de `base_inicial`/`redondeo`/`denominaciones_permitidas`) es responsabilidad de la parte de `web_admin`, no de este instalador — aquí solo se documenta el valor por defecto que el instalador siembra para que la sucursal no arranque sin ningún valor.

**Comandos concretos**:

```powershell
function Invoke-TaxAndCashConfigSeed {
    param([string]$ApiBaseUrl, [string]$JwtKeyPath, [guid]$SucursalUuid)

    $seedJwt = New-LocalAdminJwt -KeyPath $JwtKeyPath -SucursalUuid $SucursalUuid -TtlSeconds 300

    $existingTax = Invoke-RestMethod -Uri "$ApiBaseUrl/api/v1/impuestos?estado=VIGENTE" `
        -Headers @{ Authorization = "Bearer $seedJwt" } -Method Get
    if (-not $existingTax.items) {
        Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/impuestos" `
            -Headers @{ Authorization = "Bearer $seedJwt" } -ContentType 'application/json' `
            -Body (@{
                nombre = 'IVA'; porcentaje = 19.00; estado = 'VIGENTE'
                vigente_desde = (Get-Date).ToUniversalTime().ToString('o')
            } | ConvertTo-Json)
        Write-Host "[INFO] tax.seed { nombre: 'IVA', porcentaje: 19.00 }"
    } else {
        Write-Host "[INFO] tax.seed.skipped { reason: 'ya existe IVA vigente' }"
    }

    $existingCaja = Invoke-RestMethod -Uri "$ApiBaseUrl/api/v1/config-caja?uuid_sucursal=$SucursalUuid" `
        -Headers @{ Authorization = "Bearer $seedJwt" } -Method Get
    if (-not $existingCaja.items) {
        Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/config-caja" `
            -Headers @{ Authorization = "Bearer $seedJwt" } -ContentType 'application/json' `
            -Body (@{
                uuid_sucursal = $SucursalUuid; base_inicial = 0; redondeo = 100
                denominaciones_permitidas = @(100000,50000,20000,10000,5000,2000,1000,500,200,100)
            } | ConvertTo-Json)
        Write-Host "[INFO] config_caja.seed { base_inicial: 0 }"
    } else {
        Write-Host "[INFO] config_caja.seed.skipped { reason: 'ya existe configuración de caja' }"
    }
}
```

**Pruebas**: 5 pruebas Pester — seed de IVA sobre sucursal nueva, seed de `config_caja` sobre sucursal nueva, ambos omitidos correctamente cuando ya existe una fila vigente (actualización), y 1 prueba de integración end-to-end que simula CU-02 (cálculo de tarifa) inmediatamente después de una instalación limpia y confirma que **no** falla por ausencia de IVA vigente.

**Tamaño estimado**: 110 LOC + 90 LOC de tests.

**Tareas atómicas**:
- `HU-F23.3-T1`: Función `Invoke-TaxAndCashConfigSeed`.
- `HU-F23.3-T2`: Verificación de "ya existe" antes de insertar (nunca sobreescribe configuración de un administrador).
- `HU-F23.3-T3`: 5 pruebas Pester (incluida la de integración CU-02 post-instalación).

---

## Fase 24 — Servicios NSSM, instalación de la app Electron y verificación post-instalación

### Objetivo

Registrar `api-sucursal` y `job-sync-sucursal` como servicios Windows administrados por NSSM, instalar `web_sucursal` (MSI de Electron) sin autoarrancarla, y ejecutar una verificación post-instalación que confirme — con evidencia real, no solo "el instalador terminó sin error" — que el stack completo quedó operativo y seguro.

### Tablas ER relevantes

Ninguna nueva; esta fase consume la base de datos ya migrada y sembrada por la Fase 23.

### Endpoints relevantes

`GET /health` de `api-sucursal` (usado por la verificación de arranque del servicio) y `GET /openapi.json` (usado por el healthcheck que ya existe en `docker-compose.branch.yml` y que este instalador reutiliza como criterio de "servicio arriba").

### HU-F24.1 — Registro de `ParkosApiSucursal` vía NSSM

**Historia**: Como técnico de despliegue, quiero que `api-sucursal` quede corriendo como un servicio Windows administrado, con reinicio automático ante caída y logs rotados, sin depender de una consola abierta.

**Given/When/Then**:
- **Given** el binario standalone `api-sucursal.exe` fue extraído a `C:\Program Files\Parkos\api-sucursal\` y el `.env` de runtime (Fase 22/23) existe con `parkos_app` como identidad de conexión,
  **When** el instalador registra el servicio,
  **Then** ejecuta la secuencia NSSM completa (`install`, `set AppParameters`, `set AppDirectory`, `set AppStdout`/`AppStderr`, `set AppRotateFiles 1`, `set AppRotateBytes 10485760` [10 MB], `set Start SERVICE_AUTO_START`, `set AppRestartDelay 1000`, `set AppEnvironmentExtra` con las variables del `.env`), y el servicio queda registrado con nombre `ParkosApiSucursal`, corriendo bajo la cuenta `svc-parkos` (Fase 27), escuchando solo en `127.0.0.1:8000`.
- **Given** el servicio fue registrado,
  **When** el instalador verifica el arranque,
  **Then** hace polling de `GET http://127.0.0.1:8000/health` con timeout total de 30 segundos (reintentos cada 2 segundos); si no responde `200` dentro de ese tiempo, el paso falla y dispara el rollback de este paso (desregistra el servicio) antes de continuar a `job-sync-sucursal`.
- **Given** `api-sucursal.exe` crashea después de estar en producción,
  **When** NSSM detecta la salida del proceso,
  **Then** lo reinicia automáticamente en menos de 5 segundos (backoff: 1 s, 5 s, 30 s en intentos sucesivos si el crash se repite), sin intervención del operador.

**Reglas de negocio**:
- BR1. El servicio nunca se expone a la LAN (`0.0.0.0`); solo `127.0.0.1`, dado que la app Electron corre en el mismo equipo.
- BR2. Los logs de este servicio viven en `C:\ProgramData\Parkos\logs\api-sucursal.*.log`, con la ACL restrictiva de la Fase 27 (legibles por `svc-parkos` y administradores locales, no por cualquier usuario del equipo).

**Comandos concretos**:

```powershell
function Install-ApiService {
    param([string]$NssmPath, [string]$ExePath, [string]$EnvFilePath, [string]$ServiceAccount)

    & $NssmPath install ParkosApiSucursal $ExePath
    & $NssmPath set ParkosApiSucursal AppDirectory (Split-Path $ExePath)
    & $NssmPath set ParkosApiSucursal AppStdout "$env:ProgramData\Parkos\logs\api-sucursal.out.log"
    & $NssmPath set ParkosApiSucursal AppStderr "$env:ProgramData\Parkos\logs\api-sucursal.err.log"
    & $NssmPath set ParkosApiSucursal AppRotateFiles 1
    & $NssmPath set ParkosApiSucursal AppRotateBytes 10485760
    & $NssmPath set ParkosApiSucursal AppRotateOnline 1
    & $NssmPath set ParkosApiSucursal Start SERVICE_AUTO_START
    & $NssmPath set ParkosApiSucursal AppRestartDelay 1000
    & $NssmPath set ParkosApiSucursal ObjectName ".\svc-parkos" (Get-ServiceAccountPassword)

    $envVars = Get-Content $EnvFilePath | Where-Object { $_ -match '=' }
    & $NssmPath set ParkosApiSucursal AppEnvironmentExtra ($envVars -join "`r`n")

    Start-Service ParkosApiSucursal
}

function Wait-ForApiHealth {
    param([string]$Url = 'http://127.0.0.1:8000/health', [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($resp.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Seconds 2 }
    }
    return $false
}
```

**Pruebas**: 2 pruebas Pester (instalación limpia con verificación de `Get-Service ParkosApiSucursal` en estado `Running`, y reinicio simulado con verificación de `Wait-ForApiHealth` tras matar el proceso).

**Tamaño estimado**: 150 LOC + 80 LOC de tests.

**Tareas atómicas**:
- `HU-F24.1-T1`: Función `Install-ApiService` (secuencia NSSM completa).
- `HU-F24.1-T2`: Función `Wait-ForApiHealth` (polling con timeout).
- `HU-F24.1-T3`: 2 pruebas Pester.

---

### HU-F24.2 — Registro de `ParkosJobSyncSucursal` vía NSSM

**Historia**: Como técnico de despliegue, quiero que el worker de sincronización quede corriendo como servicio administrado, dependiendo explícitamente de que `api-sucursal` ya esté saludable antes de arrancar.

**Given/When/Then**:
- **Given** `ParkosApiSucursal` está `Running` y responde `200` en `/health`,
  **When** el instalador registra `job-sync-sucursal.exe` como servicio NSSM `ParkosJobSyncSucursal`,
  **Then** aplica el mismo patrón de la HU-F24.1 (rotación de logs, `AppRestartDelay`, cuenta `svc-parkos`), con las variables de entorno adicionales `PARKOS_SYNC_POLL_INTERVAL_S=10` y `PARKOS_SYNC_BATCH_SIZE=100` (los mismos defaults reales que `runtime/env.py` usa si no se sobreescriben, para que el comportamiento del servicio Windows sea idéntico al del contenedor Docker de desarrollo).
- **Given** el servicio fue registrado,
  **When** el instalador verifica el arranque,
  **Then** revisa que el archivo de log `job-sync-sucursal.out.log` contenga al menos una línea de ciclo de sondeo ("poll cycle" o equivalente estructurado) dentro de los primeros 30 segundos — no basta con que el servicio esté en estado `Running`; NSSM puede reportar `Running` aunque el proceso esté atascado antes de su primer ciclo útil.

**Reglas de negocio**:
- BR1. `ParkosJobSyncSucursal` nunca se registra como `SERVICE_AUTO_START` antes de que `ParkosApiSucursal` haya pasado su propio chequeo de salud — el orden de arranque importa porque el worker depende del API local para varias operaciones de sincronización.
- BR2. El worker no expone ningún puerto a la LAN; su `/healthz` interno en `127.0.0.1:9999` es solo para el diagnóstico local de la Fase 26, nunca para consumo externo.

**Comandos concretos**:

```powershell
function Install-JobService {
    param([string]$NssmPath, [string]$ExePath, [string]$EnvFilePath)
    & $NssmPath install ParkosJobSyncSucursal $ExePath
    & $NssmPath set ParkosJobSyncSucursal AppDirectory (Split-Path $ExePath)
    & $NssmPath set ParkosJobSyncSucursal AppStdout "$env:ProgramData\Parkos\logs\job-sync.out.log"
    & $NssmPath set ParkosJobSyncSucursal AppRotateFiles 1
    & $NssmPath set ParkosJobSyncSucursal AppRotateBytes 10485760
    & $NssmPath set ParkosJobSyncSucursal Start SERVICE_AUTO_START
    & $NssmPath set ParkosJobSyncSucursal AppRestartDelay 1000
    & $NssmPath set ParkosJobSyncSucursal ObjectName ".\svc-parkos" (Get-ServiceAccountPassword)
    $envVars = (Get-Content $EnvFilePath | Where-Object { $_ -match '=' }) + @(
        'PARKOS_SYNC_POLL_INTERVAL_S=10', 'PARKOS_SYNC_BATCH_SIZE=100'
    )
    & $NssmPath set ParkosJobSyncSucursal AppEnvironmentExtra ($envVars -join "`r`n")
    Start-Service ParkosJobSyncSucursal
}

function Wait-ForSyncPollCycle {
    param([string]$LogPath = "$env:ProgramData\Parkos\logs\job-sync.out.log", [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-Content $LogPath -ErrorAction SilentlyContinue) -match 'poll') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}
```

**Pruebas**: 2 pruebas Pester (registro + verificación de dependencia de orden con `ParkosApiSucursal`, y verificación de que el log muestra ciclo de sondeo dentro del timeout).

**Tamaño estimado**: 100 LOC + 60 LOC de tests.

**Tareas atómicas**:
- `HU-F24.2-T1`: Función `Install-JobService`.
- `HU-F24.2-T2`: Función `Wait-ForSyncPollCycle`.
- `HU-F24.2-T3`: 2 pruebas Pester.

---

### HU-F24.3 — Instalación silenciosa del MSI de `web_sucursal`

**Historia**: Como técnico de despliegue, quiero instalar la aplicación de escritorio sin que se autoarranque, para que sea el operador quien la abra deliberadamente al iniciar su turno.

**Given/When/Then**:
- **Given** `ParkosJobSyncSucursal` está corriendo con al menos un ciclo de sondeo confirmado,
  **When** el instalador ejecuta el MSI de `web_sucursal`,
  **Then** corre `msiexec.exe /i web_sucursal-{version}-x64.msi /qn /l*v install.log` (silencioso, con log detallado de MSI para diagnóstico), verifica exit code `0`, y confirma la instalación con `Get-Package | Where-Object Name -match 'Parkos'`.
- **Given** el MSI termina correctamente,
  **When** el instalador continúa,
  **Then** **no** lanza el proceso de `web_sucursal.exe`; solo confirma que el acceso directo del menú de inicio existe.
- **Given** el MSI se interrumpe a mitad de instalación (por ejemplo, un corte de energía),
  **When** el instalador detecta el fallo,
  **Then** Windows Installer revierte automáticamente el estado parcial (comportamiento nativo de MSI); el instalador de Parkos, adicionalmente, corre `msiexec /x` sobre el mismo paquete como medida de limpieza explícita antes de reportar el error, para no depender únicamente del rollback implícito de MSI.

**Reglas de negocio**:
- BR1. El MSI está firmado con el certificado de Azure Trusted Signing de producción (Fase 28); en staging se acepta un certificado autofirmado con el warning de SmartScreen esperado.
- BR2. El acceso directo del menú de inicio no requiere privilegios de administrador para ejecutarse (el operador de caja normalmente no es administrador del equipo).

**Comandos concretos**:

```powershell
function Install-Electron {
    param([string]$MsiPath)
    $logPath = "$env:ProgramData\Parkos\logs\electron-install.log"
    $proc = Start-Process msiexec.exe -ArgumentList "/i `"$MsiPath`" /qn /l*v `"$logPath`"" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Start-Process msiexec.exe -ArgumentList "/x `"$MsiPath`" /qn" -Wait
        throw "Instalación de web_sucursal falló (exit $($proc.ExitCode)); ver $logPath"
    }
    $installed = Get-Package | Where-Object { $_.Name -match 'Parkos' }
    if (-not $installed) { throw "MSI reportó éxito pero web_sucursal no aparece en Programas instalados." }
}
```

**Pruebas**: 2 pruebas Pester (instalación silenciosa exitosa con verificación de `Get-Package`, y rollback con `msiexec /x` ante fallo simulado).

**Tamaño estimado**: 60 LOC + 50 LOC de tests.

**Tareas atómicas**:
- `HU-F24.3-T1`: Función `Install-Electron`.
- `HU-F24.3-T2`: Rollback explícito con `msiexec /x` ante fallo.
- `HU-F24.3-T3`: 2 pruebas Pester.

---

### HU-F24.4 — Verificación post-instalación integral (el *gate* final)

**Historia**: Como responsable de calidad del despliegue, quiero que el instalador confirme con evidencia real — no solo "cada paso individual no falló" — que el stack completo cumple los invariantes de seguridad y funcionamiento antes de declarar la instalación exitosa.

**Given/When/Then**:
- **Given** todos los pasos anteriores de la instalación reportaron éxito individualmente,
  **When** el instalador ejecuta la verificación final,
  **Then** corre `python -m parkos_core.cli.doctor` (el diagnóstico real ya existente en el backend, reutilizado en vez de reimplementado) y exige que las 5 verificaciones reporten estado sano: `env_status: "ok"`, `db_connectivity: "ok"`, `jwt_key_path_exists: true`, `sync_jwt_path_readable` (solo aplica tras el *pairing* de la Fase 29; se tolera `false` en instalación limpia sin *pairing* todavía, mensaje distinto para ese caso puntual), `cloud_api_url_reachable: "ok"` (o un aviso explícito y no bloqueante si el equipo instala en modo desconectado a propósito).
- **Given** el diagnóstico general pasó,
  **When** el instalador ejecuta el chequeo específico de mínimo privilegio,
  **Then** conecta a Postgres con las credenciales de `PARKOS_DB_URL` del `.env` de runtime y verifica dos cosas con una sola consulta: (a) `current_user` es `parkos_app`, nunca `parkos`; (b) un intento de `CREATE ROLE` o `DROP TABLE prod.usuarios` contra esa misma conexión falla con `InsufficientPrivilege` — no basta con leer el nombre de usuario en la cadena de conexión, se prueba el privilegio real.
- **Given** el chequeo de mínimo privilegio pasó,
  **When** el instalador ejecuta el chequeo del secreto JWT,
  **Then** confirma que `PARKOS_JWT_KEY_PATH` apunta a un archivo real generado por este mismo instalador (no vacío, con al menos 32 bytes de entropía, y con un hash distinto al de cualquier archivo de ejemplo/dev conocido embebido como *denylist* en el propio instalador) — si el archivo no existe o coincide con el secreto de desarrollo conocido, el instalador **rechaza continuar** y no arranca los servicios (ver Fase 27, HU-F27.3).
- **Given** todos los chequeos anteriores pasaron,
  **When** el instalador presenta el resumen final,
  **Then** muestra una tabla de una línea por check (`Format-Table`, accesible para lectores de pantalla) y termina con exit code `0`.

**Reglas de negocio**:
- BR1. Ningún check de esta HU puede omitirse en modo `-Unattended`; si algo falla en modo desatendido, el exit code distingue `1` (rollback ejecutado) de `2` (pre-flight/verificación falló sin necesidad de rollback de datos).
- BR2. Esta verificación es el único punto del instalador donde se prueba el privilegio real de `parkos_app` contra la base de datos (no solo se confía en que la migración `0021` lo dejó bien configurado) — es la garantía de que la Sección 0.3 se cumple en la práctica, no solo en el diseño.

**Comandos concretos**:

```powershell
function Test-PostInstallation {
    param([string]$EnvFilePath)

    $doctorJson = & python -m parkos_core.cli.doctor | ConvertFrom-Json
    $doctorOk = $doctorJson.env_status -eq 'ok' -and $doctorJson.db_connectivity -eq 'ok' -and $doctorJson.jwt_key_path_exists

    $runtimeConn = Get-ConnectionStringFromEnv -Path $EnvFilePath
    $currentUser = (& psql $runtimeConn -tAc "SELECT current_user;").Trim()
    $privilegeDenied = $true
    try {
        & psql $runtimeConn -c "CREATE ROLE test_should_fail_$(Get-Random) LOGIN;" 2>$null
        if ($LASTEXITCODE -eq 0) { $privilegeDenied = $false }
    } catch { }
    $isAppUser = ($currentUser -eq 'parkos_app') -and $privilegeDenied

    $jwtPath = (Get-EnvValue -Path $EnvFilePath -Name 'PARKOS_JWT_KEY_PATH')
    $jwtOk = (Test-Path $jwtPath) -and ((Get-Item $jwtPath).Length -ge 32) -and
             ((Get-FileHash $jwtPath).Hash -notin $script:KNOWN_DEV_SECRET_HASHES)

    $results = [ordered]@{
        'Diagnóstico general (doctor)'      = $doctorOk
        'Runtime conecta como parkos_app'   = $isAppUser
        'parkos_app no puede CREATE ROLE'   = $privilegeDenied
        'Secreto JWT real (no dev fallback)' = $jwtOk
    }
    $results.GetEnumerator() | Format-Table -AutoSize
    if ($results.Values -contains $false) {
        throw "Verificación post-instalación falló; ver detalle arriba. La instalación NO se considera exitosa."
    }
}
```

**Pruebas**: 6 pruebas Pester — `doctor` sano (mock), `doctor` con `db_connectivity` en error, runtime conectando correctamente como `parkos_app`, runtime detectado erróneamente como `parkos` (debe fallar el gate), `parkos_app` intentando `CREATE ROLE` con éxito (debe fallar el gate — indica que el mínimo privilegio no es real), y secreto JWT coincidiendo con el hash del secreto de desarrollo conocido (debe fallar el gate). Prueba de integración en VM: instalación limpia completa seguida de esta verificación, sin mocks.

**Tamaño estimado**: 160 LOC + 130 LOC de tests.

**Tareas atómicas**:
- `HU-F24.4-T1`: Función `Test-PostInstallation` (wrapper de `doctor` + chequeo de privilegio real + chequeo de secreto JWT).
- `HU-F24.4-T2`: Lista de hashes conocidos de secretos de desarrollo (*denylist*) embebida en el instalador.
- `HU-F24.4-T3`: 7 pruebas Pester (6 unitarias + 1 de integración VM).

---

## Fase 25 — Actualización del stack completo (`Update-ParkosStack`)

### Objetivo

Cubrir el hueco más señalado por la auditoría de completitud del instalador: hasta ahora solo existía un cmdlet de actualización del binario Electron (`Update-ParkosElectron`), sin ningún flujo que actualizara `api-sucursal`, `job-sync-sucursal` ni aplicara migraciones nuevas sobre datos reales de un cliente en producción. Esta fase define `Update-ParkosStack` como la pieza central del ciclo de vida post-instalación, con la secuencia obligatoria **detener → backup → migrar → reemplazar → reiniciar → verificar**, con rollback automático si cualquier paso falla.

### Diagrama de estados del ciclo de vida completo

```mermaid
stateDiagram-v2
    [*] --> Instalado: Instalación limpia (Fases 21-24)

    Instalado --> VerificandoActualizacion: Update-ParkosStack
    VerificandoActualizacion --> PreCheckFallo: pre-check de salud falla (doctor no sano)
    PreCheckFallo --> Instalado: abortar, sin cambios

    VerificandoActualizacion --> BackupObligatorio: pre-check OK
    BackupObligatorio --> BackupFallido: pg_dump falla
    BackupFallido --> Instalado: abortar, sin cambios (nunca se migra sin backup verificado)

    BackupObligatorio --> DeteniendoServicios: pg_dump -Fc completado y verificado (tamaño > 0, `pg_restore --list` legible)
    DeteniendoServicios --> ReemplazandoBinarios: NSSM stop job-sync primero, luego api-sucursal
    ReemplazandoBinarios --> VerificandoFirma: binarios nuevos copiados
    VerificandoFirma --> RestaurandoBackup: firma/checksum del binario nuevo no coincide con el manifiesto firmado
    VerificandoFirma --> MigrandoEsquema: firma verificada OK

    MigrandoEsquema --> MigracionFallida: alembic upgrade head falla
    MigracionFallida --> RestaurandoBackup: pg_restore del backup + reinstala binarios N-1

    MigrandoEsquema --> IniciandoServicios: alembic upgrade head OK
    IniciandoServicios --> PostCheck: NSSM start api-sucursal, luego job-sync-sucursal
    PostCheck --> RestaurandoBackup: smoke test post-actualización falla
    PostCheck --> Instalado: smoke test OK, versión N activa, versión N-1 archivada en releases\

    RestaurandoBackup --> Instalado: reiniciado con versión N-1, alerta generada, actualización marcada fallida

    Instalado --> Reparando: Repair-ParkosInstall (Fase 26)
    Instalado --> Diagnosticando: Export-ParkosDiagnostics (Fase 26)
    Instalado --> Desinstalando: Uninstall-Parkos (Fase 26)
```

### HU-F25.1 — Pre-check de salud y backup obligatorio antes de tocar nada

**Historia**: Como técnico de soporte, quiero que `Update-ParkosStack` se niegue a empezar si el sistema ya está en mal estado, y que nunca migre esquema sin un backup verificado inmediatamente antes.

**Given/When/Then**:
- **Given** una sucursal en producción con `api-sucursal`, `job-sync-sucursal` y Postgres corriendo,
  **When** el operador ejecuta `Update-ParkosStack -PayloadPath .\parkos-installer-payload-1.1.0.zip`,
  **Then** el cmdlet ejecuta primero `python -m parkos_core.cli.doctor` y aborta con un mensaje claro si `db_connectivity` o `env_status` no son `ok` — no tiene sentido actualizar un sistema que ya está fallando; el operador debe diagnosticar primero (Fase 26).
- **Given** el pre-check pasó,
  **When** el cmdlet continúa,
  **Then** ejecuta `pg_dump -Fc -U parkos_app -d parkos -f "C:\ProgramData\Parkos\backups\pre-update-{version}-{timestamp}.dump"` y verifica el resultado con `pg_restore --list` sobre el archivo recién creado (confirma que el dump es legible, no solo que el archivo existe con tamaño mayor a cero) antes de considerar el backup válido.
- **Given** el backup falla (disco lleno, Postgres no responde),
  **When** el cmdlet detecta el fallo,
  **Then** aborta inmediatamente sin detener ningún servicio ni tocar ningún binario — el sistema queda exactamente como estaba antes de invocar `Update-ParkosStack`.
- **Given** el operador quiere ver qué haría la actualización sin ejecutarla,
  **When** invoca `Update-ParkosStack -WhatIf`,
  **Then** el cmdlet imprime la secuencia de pasos que ejecutaría (versión actual → versión destino, qué se detendría, si hay migraciones pendientes) sin modificar nada.

**Reglas de negocio**:
- BR1. El backup de esta fase reutiliza exactamente el mismo mecanismo que la tarea programada diaria de la Fase 29 (`pg_dump -Fc`), nunca un mecanismo paralelo — si uno se corrige o mejora, el otro se beneficia automáticamente.
- BR2. `-Force` existe para saltar el pre-check de salud **solo** en escenarios de soporte ya documentados (por ejemplo, un `doctor` que reporta `cloud_api_url_reachable` en error porque el cliente está deliberadamente offline) — nunca para saltar el backup, que no tiene bandera de omisión bajo ninguna circunstancia.

**Comandos concretos**:

```powershell
function Update-ParkosStack {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$PayloadPath,
        [switch]$Force,
        [switch]$RollbackOnly
    )

    if ($RollbackOnly) { Invoke-StackRollback; return }

    $doctor = & python -m parkos_core.cli.doctor | ConvertFrom-Json
    if (-not $Force -and ($doctor.env_status -ne 'ok' -or -not $doctor.db_connectivity.StartsWith('ok'))) {
        throw "Pre-check de salud falló (doctor: $($doctor | ConvertTo-Json -Compress)). Usa -Force solo si ya diagnosticaste la causa."
    }

    if ($PSCmdlet.ShouldProcess('stack de Parkos', 'actualizar')) {
        $backupPath = Invoke-MandatoryBackup   # HU-F25.1 — sin bandera de omisión
        try {
            Stop-ParkosServicesInOrder          # HU-F25.2
            $newVersion = Install-NewBinaries -PayloadPath $PayloadPath   # HU-F25.2, con verificación de firma
            Invoke-MigrationUpdate              # HU-F25.3
            Start-ParkosServicesInOrder         # HU-F25.4
            Test-PostUpdateSmoke                # HU-F25.4
            Move-PreviousVersionToReleases
        } catch {
            Write-Warning "Actualización falló: $($_.Exception.Message). Restaurando desde $backupPath..."
            Invoke-StackRollback -BackupPath $backupPath
            throw
        }
    }
}

function Invoke-MandatoryBackup {
    $backupPath = "$env:ProgramData\Parkos\backups\pre-update-$(Get-Date -Format yyyyMMddHHmmss).dump"
    & pg_dump -Fc -U parkos_app -d parkos -f $backupPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backupPath) -or (Get-Item $backupPath).Length -eq 0) {
        throw "Backup pre-actualización falló; actualización abortada sin tocar el sistema."
    }
    $listing = & pg_restore --list $backupPath
    if (-not $listing) { throw "Backup generado pero ilegible (pg_restore --list vacío); actualización abortada." }
    return $backupPath
}
```

**Pruebas**: 5 pruebas Pester — pre-check bloquea con `doctor` en error, `-Force` lo salta correctamente, backup fallido aborta sin tocar servicios, backup exitoso pero ilegible aborta igual, y `-WhatIf` no ejecuta ninguna acción real.

**Tamaño estimado**: 140 LOC + 110 LOC de tests.

**Tareas atómicas**:
- `HU-F25.1-T1`: Función `Update-ParkosStack` (esqueleto con `-WhatIf`/`-Force`/`-RollbackOnly`).
- `HU-F25.1-T2`: Función `Invoke-MandatoryBackup` con verificación de legibilidad.
- `HU-F25.1-T3`: 5 pruebas Pester.

---

### HU-F25.2 — Detención ordenada y reemplazo de binarios con verificación de firma

**Historia**: Como técnico de soporte, quiero que la actualización detenga los servicios en el orden correcto (el worker de sincronización antes que el API, para no dejar conexiones a medias) y verifique la firma de los binarios nuevos antes de sustituir los anteriores.

**Given/When/Then**:
- **Given** el backup fue verificado,
  **When** `Update-ParkosStack` detiene los servicios,
  **Then** detiene primero `ParkosJobSyncSucursal` (el consumidor, para que deje de generar tráfico de sincronización) y solo después `ParkosApiSucursal` — el orden inverso al de arranque de la Fase 24.
- **Given** los servicios están detenidos,
  **When** el instalador copia los binarios nuevos desde el payload,
  **Then** verifica el checksum SHA256 de cada binario contra el manifiesto firmado incluido en el payload **antes** de sobrescribir el binario anterior — si algún checksum no coincide, el paso completo falla y dispara el rollback (Fase 25.1) sin haber tocado ningún binario todavía.
- **Given** los binarios pasaron la verificación,
  **When** el instalador los coloca en `C:\Program Files\Parkos\`,
  **Then** conserva el binario anterior en `C:\ProgramData\Parkos\releases\{version-anterior}\` antes de sobrescribir (nunca borra la versión N-1 hasta que el smoke test post-actualización de HU-F25.4 confirme éxito).

**Reglas de negocio**:
- BR1. Se conservan al menos las 2 últimas versiones estables en `releases\` (rotación: al agregar una tercera, se elimina la más antigua) — esto es lo que permite el rollback manual documentado en la Fase 28.
- BR2. La verificación de firma/checksum de esta fase es la misma que usa `Repair-ParkosInstall` (Fase 26) para detectar binarios corrompidos — un solo mecanismo, dos consumidores.

**Comandos concretos**:

```powershell
function Stop-ParkosServicesInOrder {
    Stop-Service ParkosJobSyncSucursal -Force
    Stop-Service ParkosApiSucursal -Force
}

function Install-NewBinaries {
    param([string]$PayloadPath)
    $manifest = Get-Content "$PayloadPath\manifest.sha256.json" | ConvertFrom-Json
    foreach ($binario in $manifest.binarios) {
        $actualHash = (Get-FileHash "$PayloadPath\$($binario.ruta)" -Algorithm SHA256).Hash
        if ($actualHash -ne $binario.sha256) {
            throw "Checksum inválido para $($binario.ruta); posible payload corrompido o manipulado. Actualización abortada."
        }
    }
    $currentVersion = Get-CurrentParkosVersion
    New-Item -ItemType Directory -Path "$env:ProgramData\Parkos\releases\$currentVersion" -Force | Out-Null
    Copy-Item "C:\Program Files\Parkos\api-sucursal\*" "$env:ProgramData\Parkos\releases\$currentVersion\api-sucursal\" -Recurse -Force
    Copy-Item "C:\Program Files\Parkos\job-sync-sucursal\*" "$env:ProgramData\Parkos\releases\$currentVersion\job-sync-sucursal\" -Recurse -Force
    foreach ($binario in $manifest.binarios) {
        Copy-Item "$PayloadPath\$($binario.ruta)" "C:\Program Files\Parkos\$($binario.destino)" -Force
    }
    return $manifest.version
}
```

**Pruebas**: 4 pruebas Pester (orden de detención verificado con `Should -Invoke` en secuencia, checksum válido permite continuar, checksum inválido aborta antes de tocar binarios, versión anterior conservada en `releases\` antes de sobrescribir).

**Tamaño estimado**: 130 LOC + 90 LOC de tests.

**Tareas atómicas**:
- `HU-F25.2-T1`: Función `Stop-ParkosServicesInOrder`.
- `HU-F25.2-T2`: Función `Install-NewBinaries` con verificación de checksum y conservación de N-1.
- `HU-F25.2-T3`: 4 pruebas Pester.

---

### HU-F25.3 — Migración de esquema sobre datos reales de cliente

**Historia**: Como responsable de datos, quiero que una migración de esquema durante una actualización en producción nunca corra con los servicios activos, y que un fallo a mitad de camino se resuelva restaurando el backup, nunca dejando el sistema en un estado mixto de "esquema nuevo con binario viejo" (o viceversa).

**Given/When/Then**:
- **Given** los servicios están detenidos y los binarios nuevos ya pasaron la verificación de firma,
  **When** `Update-ParkosStack` migra el esquema,
  **Then** ejecuta `alembic upgrade head` con la conexión de migración (superusuario `parkos`, nunca `parkos_app` — las migraciones reales incluyen particionado con `pg_partman`, UUIDs determinísticos y cambios de `GRANT`/`REVOKE` que exceden los privilegios de `parkos_app` por diseño).
- **Given** la migración falla a mitad de camino,
  **When** el instalador detecta el fallo,
  **Then** restaura la base de datos completa desde el backup de HU-F25.1 (`pg_restore --clean` sobre el dump), reinstala los binarios de la versión N-1 desde `releases\`, y reinicia los servicios con la versión anterior — nunca deja el esquema a mitad de migrar ni los binarios nuevos corriendo contra un esquema viejo.
- **Given** la migración de esta actualización particular no incluye ningún cambio de esquema nuevo (por ejemplo, una actualización que solo trae fixes de la app Electron),
  **When** `alembic upgrade head` se ejecuta,
  **Then** es un no-op verificado (`alembic current` antes y después son la misma revisión) — el paso no falla ni tarda de forma perceptible solo porque no había nada que migrar.

**Reglas de negocio**:
- BR1. Nunca se ejecuta `alembic upgrade head` con los servicios `ParkosApiSucursal`/`ParkosJobSyncSucursal` activos — correr con conexiones activas durante un cambio de esquema con particionado y cadena de hash inmutable es un riesgo real de corrupción lógica, no solo de bloqueo.
- BR2. `pg_restore --clean` se ejecuta contra una base de datos en un estado conocido (los servicios detenidos, sin conexiones activas de aplicación) para evitar conflictos de lock durante la restauración.

**Comandos concretos**:

```powershell
function Invoke-MigrationUpdate {
    param([hashtable]$MigrationRoles)
    $env:DATABASE_URL = "postgresql://parkos:$($MigrationRoles.SuperuserPassword)@127.0.0.1:$Port/parkos"
    $before = & alembic current
    & alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head falló durante la actualización (revisión previa: $before)."
    }
}

function Invoke-StackRollback {
    param([string]$BackupPath)
    Stop-Service ParkosApiSucursal, ParkosJobSyncSucursal -Force -ErrorAction SilentlyContinue
    & pg_restore --clean --if-exists -U parkos -d parkos $BackupPath
    $previousVersion = Get-PreviousReleaseVersion
    Copy-Item "$env:ProgramData\Parkos\releases\$previousVersion\api-sucursal\*" "C:\Program Files\Parkos\api-sucursal\" -Recurse -Force
    Copy-Item "$env:ProgramData\Parkos\releases\$previousVersion\job-sync-sucursal\*" "C:\Program Files\Parkos\job-sync-sucursal\" -Recurse -Force
    Start-Service ParkosApiSucursal
    Start-Service ParkosJobSyncSucursal
    Write-EventLog -LogName Application -Source 'ParkosInstaller' -EventId 9001 -EntryType Warning `
        -Message "Actualización revertida automáticamente a la versión $previousVersion tras un fallo. Ver logs de instalación."
}
```

**Pruebas**: 4 pruebas Pester (migración exitosa con conexión de superusuario, migración fallida dispara restauración completa, no-op verificado cuando no hay migraciones pendientes, y una prueba de integración que simula el ciclo completo detener→backup→migrar-fallido→restaurar en una VM con Postgres real).

**Tamaño estimado**: 120 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F25.3-T1`: Función `Invoke-MigrationUpdate` (conexión de superusuario, nunca `parkos_app`).
- `HU-F25.3-T2`: Función `Invoke-StackRollback` (restauración completa + reinicio con versión N-1).
- `HU-F25.3-T3`: 5 pruebas (4 unitarias + 1 de integración VM).

---

### HU-F25.4 — Reinicio ordenado y smoke test post-actualización

**Historia**: Como técnico de soporte, quiero que la actualización solo se considere exitosa después de una prueba funcional mínima real (no solo "los servicios están en estado `Running`"), y que un smoke test fallido dispare el mismo rollback automático que un fallo de migración.

**Given/When/Then**:
- **Given** la migración terminó exitosamente,
  **When** `Update-ParkosStack` reinicia los servicios,
  **Then** arranca `ParkosApiSucursal` primero (orden inverso al de detención), espera su chequeo de salud (`Wait-ForApiHealth`, HU-F24.1), y solo después arranca `ParkosJobSyncSucursal`.
- **Given** ambos servicios están arriba,
  **When** el instalador ejecuta el smoke test,
  **Then** hace login con un usuario de prueba dedicado (creado en la instalación inicial, con permisos mínimos de solo lectura) y consulta un catálogo (`GET /api/v1/catalogos/tipos-vehiculo`) — un smoke test de negocio mínimo, no solo un `GET /health`, porque el objetivo es confirmar que el contrato de mínimo privilegio y las migraciones nuevas realmente permiten operar, no solo que el proceso arrancó.
- **Given** el smoke test falla,
  **When** el instalador lo detecta,
  **Then** dispara `Invoke-StackRollback` (HU-F25.3) exactamente igual que ante un fallo de migración — desde la perspectiva del operador, cualquier fallo posterior al backup termina en el mismo lugar seguro: la versión N-1 funcionando.
- **Given** el smoke test pasa,
  **When** el instalador termina,
  **Then** elimina la versión N-2 de `releases\` si ya hay 3 conservadas (rotación: 2 últimas estables), registra el evento de actualización exitosa en el Event Log de Windows, y termina con exit `0`.

**Reglas de negocio**:
- BR1. El smoke test nunca usa credenciales de un usuario real de negocio — un usuario de prueba dedicado, sembrado en la instalación inicial (HU-F23.2), con permisos de solo lectura sobre catálogos, para no dejar rastro de actividad ficticia en los reportes operativos del cliente.
- BR2. El registro en el Event Log de Windows (tanto de éxito como de rollback) es lo que permite que `Export-ParkosDiagnostics` (Fase 26) reconstruya el historial de actualizaciones de una sucursal sin depender solo de los logs de aplicación.

**Comandos concretos**:

```powershell
function Start-ParkosServicesInOrder {
    Start-Service ParkosApiSucursal
    if (-not (Wait-ForApiHealth)) { throw "api-sucursal no respondió saludable tras el reinicio." }
    Start-Service ParkosJobSyncSucursal
    if (-not (Wait-ForSyncPollCycle)) { throw "job-sync-sucursal no completó un ciclo de sondeo tras el reinicio." }
}

function Test-PostUpdateSmoke {
    $smokeJwt = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/auth/login' `
        -Body (@{ email = 'smoke-test@parkos.local'; password = (Get-SmokeTestPassword) } | ConvertTo-Json) `
        -ContentType 'application/json'
    $catalogo = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/catalogos/tipos-vehiculo' `
        -Headers @{ Authorization = "Bearer $($smokeJwt.access_token)" }
    if (-not $catalogo.items -or $catalogo.items.Count -eq 0) {
        throw "Smoke test post-actualización falló: catálogo de tipos de vehículo vacío o inaccesible."
    }
}
```

**Pruebas**: 4 pruebas Pester (arranque en orden correcto, smoke test exitoso con catálogo no vacío, smoke test fallido dispara rollback, rotación de `releases\` a 2 versiones tras éxito). 1 prueba de integración de ciclo completo en VM: instalación limpia → `Update-ParkosStack` con una versión que introduce una migración real → smoke test → confirmación de versión activa.

**Tamaño estimado**: 130 LOC + 110 LOC de tests.

**Tareas atómicas**:
- `HU-F25.4-T1`: Función `Start-ParkosServicesInOrder`.
- `HU-F25.4-T2`: Función `Test-PostUpdateSmoke` (usuario de prueba dedicado).
- `HU-F25.4-T3`: Rotación de `releases\` a 2 versiones estables.
- `HU-F25.4-T4`: 5 pruebas (4 unitarias + 1 de integración VM de ciclo completo).

---

## Fase 26 — Reparación, diagnóstico y desinstalación

### Objetivo

Cubrir tres capacidades que la documentación previa trataba solo como comportamiento incidental de `--force-cleanup`: reparar una instalación con servicios rotos sin tocar datos, empaquetar un diagnóstico unificado para soporte remoto, y desinstalar con una política explícita de qué se preserva y qué se borra.

### HU-F26.1 — `Repair-ParkosInstall`: reparación sin tocar datos

**Historia**: Como técnico de soporte, quiero poder reparar una instalación con servicios Windows rotos (por ejemplo, tras una actualización de Windows que desregistró NSSM, o una ACL corrompida) sin reinstalar desde cero ni arriesgar los datos del cliente.

**Given/When/Then**:
- **Given** un equipo donde `Get-Service ParkosApiSucursal` reporta "no encontrado" (el registro de Windows quedó inconsistente) pero los binarios y la base de datos siguen intactos,
  **When** el técnico ejecuta `Repair-ParkosInstall`,
  **Then** el cmdlet re-registra los servicios NSSM (`ParkosApiSucursal`, `ParkosJobSyncSucursal`) usando los binarios y el `.env` ya existentes en disco, sin volver a ejecutar migraciones ni tocar Postgres.
- **Given** el binario `api-sucursal.exe` fue reemplazado accidentalmente por una copia corrupta,
  **When** `Repair-ParkosInstall` corre,
  **Then** verifica el checksum de cada binario contra el manifiesto firmado (el mismo mecanismo de la HU-F25.2) y, si detecta una discrepancia, reemplaza únicamente el binario afectado desde la copia conservada en `releases\{version-actual}\`, sin degradar a una versión anterior.
- **Given** la ACL de `C:\ProgramData\Parkos\secrets\` fue alterada (por ejemplo, un administrador local ejecutó `icacls /reset` por error),
  **When** `Repair-ParkosInstall` corre,
  **Then** reaplica la ACL restrictiva de la Fase 27 (`svc-parkos` + `Administradores locales`, herencia revocada para `Usuarios`).
- **Given** la reparación terminó,
  **When** el cmdlet finaliza,
  **Then** ejecuta `Get-ParkosHealth` (HU-F26.2) y reporta su resultado como parte del resumen de reparación.

**Reglas de negocio**:
- BR1. `Repair-ParkosInstall` **nunca** toca Postgres, los datos, ni el `.env` de runtime — su alcance es exclusivamente servicios Windows, binarios y ACLs. Cualquier problema de datos se resuelve con `Update-ParkosStack -RollbackOnly` o con soporte manual, nunca con este cmdlet.
- BR2. Si la reparación detecta que faltan piezas que no puede reconstruir por sí sola (por ejemplo, el propio `.env` de runtime desapareció), reporta el diagnóstico exacto y recomienda `Export-ParkosDiagnostics` en vez de intentar adivinar valores.

**Comandos concretos**:

```powershell
function Repair-ParkosInstall {
    [CmdletBinding()]
    param()

    Write-Host "Verificando servicios NSSM..." -ForegroundColor Cyan
    foreach ($svc in 'ParkosApiSucursal', 'ParkosJobSyncSucursal') {
        if (-not (Get-Service -Name $svc -ErrorAction SilentlyContinue)) {
            Write-Warning "$svc no registrado; re-registrando..."
            Register-MissingNssmService -ServiceName $svc
        }
    }

    Write-Host "Verificando integridad de binarios..." -ForegroundColor Cyan
    $manifest = Get-Content "C:\Program Files\Parkos\manifest.sha256.json" | ConvertFrom-Json
    foreach ($binario in $manifest.binarios) {
        $path = "C:\Program Files\Parkos\$($binario.destino)"
        if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $binario.sha256) {
            Write-Warning "Binario corrupto detectado: $path. Restaurando desde releases\$($manifest.version)\..."
            Copy-Item "$env:ProgramData\Parkos\releases\$($manifest.version)\$($binario.destino)" $path -Force
        }
    }

    Write-Host "Reaplicando ACL de secretos..." -ForegroundColor Cyan
    Set-ParkosSecretsAcl   # HU-F27.1, reutilizada aquí

    Write-Host "Verificación final:" -ForegroundColor Cyan
    Get-ParkosHealth
}
```

**Pruebas**: 4 pruebas Pester (re-registro de servicio faltante, restauración de binario corrupto desde `releases\`, reaplicación de ACL, y ejecución de `Get-ParkosHealth` al final). Prueba de integración: en VM, desregistrar deliberadamente un servicio NSSM y corromper un binario, ejecutar `Repair-ParkosInstall`, confirmar que ambos quedan resueltos sin que los datos de Postgres cambien.

**Tamaño estimado**: 140 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F26.1-T1`: Función `Repair-ParkosInstall`.
- `HU-F26.1-T2`: Función `Register-MissingNssmService` (re-registro sin migraciones).
- `HU-F26.1-T3`: 5 pruebas (4 unitarias + 1 de integración VM).

---

### HU-F26.2 — `Get-ParkosHealth`: diagnóstico de 4 verificaciones reutilizando `doctor`

**Historia**: Como técnico de soporte o administrador, quiero un comando único que me diga en segundos si el stack está sano, sin tener que revisar servicios, logs y conectividad por separado.

**Corrección aplicada**: la documentación previa proponía reimplementar 4 verificaciones desde cero en PowerShell. El backend real ya tiene `parkos_core.cli.doctor`, que cubre 3 de esas 4 verificaciones (`env_status`, `db_connectivity`, `jwt_key_path_exists`/`sync_jwt_path_readable`, `cloud_api_url_reachable`) con salida JSON estructurada. `Get-ParkosHealth` **envuelve** ese diagnóstico y le agrega únicamente lo que `doctor` no cubre por diseño (no es responsabilidad de un proceso Python decirle a PowerShell el estado de los servicios Windows ni el espacio en disco).

**Given/When/Then**:
- **Given** el stack está sano,
  **When** el técnico ejecuta `Get-ParkosHealth`,
  **Then** el cmdlet corre `python -m parkos_core.cli.doctor`, parsea su JSON, y lo combina con `Get-Service ParkosApiSucursal, ParkosJobSyncSucursal, postgresql-x64-16` y el espacio libre en `C:\ProgramData\Parkos\` (`Get-PSDrive`), presentando las 6 líneas resultantes en una sola tabla con `Format-Table` y colores ANSI.
- **Given** algún servicio Windows está detenido,
  **When** corre `Get-ParkosHealth`,
  **Then** esa línea se muestra en rojo y el exit code del cmdlet es `1` (no `0`), para que un script de monitoreo externo (Fase 29) pueda detectar el problema por código de salida, no solo por texto.
- **Given** el disco tiene menos del 10% libre,
  **When** corre `Get-ParkosHealth`,
  **Then** esa línea se muestra en amarillo (advertencia, no crítico) con exit code `2` si ningún otro check está en rojo.

**Reglas de negocio**:
- BR1. `Get-ParkosHealth` nunca requiere permisos de administrador para ejecutarse — un operador de caja sin privilegios elevados debe poder correrlo para ver si el sistema está sano antes de llamar a soporte.
- BR2. Exit codes: `0` = todo sano, `1` = al menos un check crítico en rojo, `2` = solo advertencias (amarillo), nunca rojo.

**Comandos concretos**:

```powershell
function Get-ParkosHealth {
    [CmdletBinding()]
    param()

    $doctor = & python -m parkos_core.cli.doctor | ConvertFrom-Json
    $services = Get-Service ParkosApiSucursal, ParkosJobSyncSucursal, 'postgresql-x64-16' -ErrorAction SilentlyContinue
    $freeSpacePct = [math]::Round(((Get-PSDrive -Name 'C').Free / (Get-PSDrive -Name 'C').Used) * 100, 1)

    $checks = [ordered]@{
        'api-sucursal (servicio)'    = ($services | Where-Object Name -eq 'ParkosApiSucursal').Status -eq 'Running'
        'job-sync-sucursal (servicio)' = ($services | Where-Object Name -eq 'ParkosJobSyncSucursal').Status -eq 'Running'
        'PostgreSQL (servicio)'      = ($services | Where-Object Name -eq 'postgresql-x64-16').Status -eq 'Running'
        'Conectividad a BD'          = $doctor.db_connectivity -eq 'ok'
        'Alcance a nube'             = $doctor.cloud_api_url_reachable -eq 'ok'
        'Espacio en disco'           = $freeSpacePct -gt 10
    }
    $checks.GetEnumerator() | ForEach-Object {
        $color = if ($_.Value) { 'Green' } elseif ($_.Key -eq 'Espacio en disco') { 'Yellow' } else { 'Red' }
        Write-Host ("[{0}] {1}" -f ($_.Value ? 'OK' : 'ALERTA'), $_.Key) -ForegroundColor $color
    }

    if ($checks.Values -contains $false -and ($checks['api-sucursal (servicio)'] -eq $false -or
        $checks['job-sync-sucursal (servicio)'] -eq $false -or $checks['PostgreSQL (servicio)'] -eq $false -or
        $checks['Conectividad a BD'] -eq $false)) { exit 1 }
    if ($checks['Espacio en disco'] -eq $false) { exit 2 }
    exit 0
}
```

**Pruebas**: 6 pruebas Pester (todo sano exit 0, servicio detenido exit 1, disco bajo sin otros problemas exit 2, `doctor` reportando `db_connectivity` en error propagado correctamente, no requiere admin verificado con `Test-IsAdmin` mockeado a `false`, y salida sin colores/ANSI cuando `$Host` no soporta color).

**Tamaño estimado**: 110 LOC + 90 LOC de tests.

**Tareas atómicas**:
- `HU-F26.2-T1`: Función `Get-ParkosHealth` (wrapper de `doctor` + servicios + disco).
- `HU-F26.2-T2`: Exit codes 0/1/2 según severidad.
- `HU-F26.2-T3`: 6 pruebas Pester.

---

### HU-F26.3 — `Export-ParkosDiagnostics`: paquete unificado para soporte

**Historia**: Como técnico de soporte remoto, quiero un único archivo que el cliente pueda enviarme con toda la información necesaria para diagnosticar un problema, sin tener que pedirle 5 capturas de pantalla distintas ni exponer secretos.

**Given/When/Then**:
- **Given** un problema reportado por un cliente,
  **When** el operador local (o el propio técnico por acceso remoto) ejecuta `Export-ParkosDiagnostics`,
  **Then** el cmdlet genera un único ZIP en el escritorio con: salida de `nssm dump` para ambos servicios, los últimos 7 días de logs ya rotados (`C:\ProgramData\Parkos\logs\*.log`), la salida completa de `Get-ParkosHealth` y de `python -m parkos_core.cli.doctor`, las versiones de todos los componentes (Electron/api-sucursal/job-sync/Postgres, leídas de sus respectivos manifiestos), las entradas del Event Log de Windows filtradas por fuente `ParkosInstaller` de los últimos 30 días, y el `.env` de runtime con **todos los valores de secretos redactados** (se muestra el nombre de cada variable y si tiene valor, nunca el valor en sí: `PARKOS_DB_URL=<redactado, 87 caracteres>`).
- **Given** el ZIP fue generado,
  **When** el operador lo revisa antes de enviarlo,
  **Then** ningún archivo dentro contiene una contraseña, un JWT completo, ni una clave privada en texto plano — la redacción se verifica automáticamente al final del empaquetado con una búsqueda de patrones conocidos (cadenas que parecen JWT, `PASSWORD=`, `_KEY_PATH` con contenido de archivo incluido en vez de solo la ruta) antes de considerar el ZIP completo.

**Reglas de negocio**:
- BR1. Este es el equivalente funcional, en el mundo sin Docker, de "recolectar `docker-compose logs`" — el objetivo es que un técnico de soporte remoto nunca tenga que pedir capturas de pantalla ni acceso interactivo al equipo del cliente para un diagnóstico inicial.
- BR2. La redacción de secretos no es opcional ni configurable — no existe una bandera para exportar el `.env` completo sin redactar.

**Comandos concretos**:

```powershell
function Export-ParkosDiagnostics {
    [CmdletBinding()]
    param([string]$OutputPath = "$env:USERPROFILE\Desktop\parkos-diagnostics-$(Get-Date -Format yyyyMMddHHmmss).zip")

    $stagingDir = Join-Path $env:TEMP "parkos-diag-$(Get-Random)"
    New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null

    & nssm dump ParkosApiSucursal > "$stagingDir\nssm-api-sucursal.txt"
    & nssm dump ParkosJobSyncSucursal > "$stagingDir\nssm-job-sync.txt"
    Copy-Item "$env:ProgramData\Parkos\logs\*.log" $stagingDir -ErrorAction SilentlyContinue
    Get-ParkosHealth *> "$stagingDir\health.txt"
    & python -m parkos_core.cli.doctor > "$stagingDir\doctor.json"
    Get-ParkosComponentVersions | Out-File "$stagingDir\versions.txt"
    Get-EventLog -LogName Application -Source 'ParkosInstaller' -After (Get-Date).AddDays(-30) |
        Export-Csv "$stagingDir\eventlog.csv" -NoTypeInformation
    Export-RedactedEnv -Path "$env:ProgramData\Parkos\secrets\.env" -OutputPath "$stagingDir\env-redacted.txt"

    if (Test-DiagnosticsContainSecrets -Path $stagingDir) {
        throw "Redacción de secretos falló verificación final; diagnóstico NO generado por seguridad."
    }

    Compress-Archive -Path "$stagingDir\*" -DestinationPath $OutputPath -Force
    Remove-Item $stagingDir -Recurse -Force
    Write-Host "Diagnóstico generado en: $OutputPath" -ForegroundColor Green
}

function Export-RedactedEnv {
    param([string]$Path, [string]$OutputPath)
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=(.*)$') {
            "$($matches[1])=<redactado, $($matches[2].Length) caracteres>"
        } else { $_ }
    } | Set-Content $OutputPath
}
```

**Pruebas**: 5 pruebas Pester (ZIP contiene todos los archivos esperados, `.env` redactado nunca expone valores reales, verificación de patrones de secretos bloquea la generación si algo se filtró, entradas del Event Log filtradas correctamente por rango de fechas, y ZIP resultante es abrible/legible sin corrupción).

**Tamaño estimado**: 150 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F26.3-T1`: Función `Export-ParkosDiagnostics`.
- `HU-F26.3-T2`: Función `Export-RedactedEnv` (redacción de secretos).
- `HU-F26.3-T3`: Función `Test-DiagnosticsContainSecrets` (verificación final de patrones).
- `HU-F26.3-T4`: 5 pruebas Pester.

---

### HU-F26.4 — `Uninstall-Parkos`: política explícita de preservación

**Historia**: Como técnico de despliegue, quiero que la desinstalación tenga un comportamiento predecible y documentado sobre qué se borra y qué se conserva, en vez de que sea un efecto colateral incidental de una bandera de limpieza forzada.

**Given/When/Then**:
- **Given** un cliente decide desinstalar el producto (por ejemplo, para reinstalar en un equipo nuevo),
  **When** el técnico ejecuta `Uninstall-Parkos` (sin banderas adicionales),
  **Then** se detienen y desregistran los 3 servicios (Postgres, `ParkosApiSucursal`, `ParkosJobSyncSucursal`), se desinstala el MSI de `web_sucursal`, se eliminan los binarios de `C:\Program Files\Parkos\`, y se elimina la entrada del programa en "Agregar o quitar programas" — pero los datos de Postgres, los logs y la configuración/clave JWT en `C:\ProgramData\Parkos\` **se preservan**, con un mensaje explícito al final indicando dónde quedan y cómo reactivarlos.
- **Given** el cliente quiere un borrado total (por ejemplo, para reinstalar limpio tras una corrupción severa),
  **When** ejecuta `Uninstall-Parkos -PurgeData`,
  **Then** además de lo anterior, elimina también la base de datos, los logs y la configuración/clave JWT — con una confirmación explícita de doble paso (escribir "CONFIRMAR" en la consola, no solo `-Confirm:$true` de PowerShell) antes de ejecutar el borrado, dado que esta acción es irreversible.

**Tabla de política de desinstalación (referencia normativa de esta HU)**:

| Elemento | `Uninstall-Parkos` (default) | `Uninstall-Parkos -PurgeData` |
|---|---|---|
| Servicios NSSM (`ParkosApiSucursal`, `ParkosJobSyncSucursal`) | Se detienen y desregistran | Igual |
| Servicio Postgres (`postgresql-x64-16`) | Se detiene y desregistra (el binario del motor se desinstala) | Igual |
| Binarios en `C:\Program Files\Parkos\` | Se eliminan | Igual |
| Base de datos Postgres (`C:\ProgramData\Parkos\pg-data\`) | **Se preserva** (mensaje explícito de ruta y cómo reactivar) | Se elimina |
| Logs (`C:\ProgramData\Parkos\logs\`) | **Se preservan** | Se eliminan |
| Configuración/`.env`/clave JWT (`C:\ProgramData\Parkos\secrets\`) | **Se preservan** | Se eliminan |
| Backups (`C:\ProgramData\Parkos\backups\`) | **Se preservan** | Se eliminan |
| App Electron (`web_sucursal`, MSI) | Se desinstala | Igual |
| Entrada en "Agregar o quitar programas" | Se elimina | Igual |
| Cuenta de servicio `svc-parkos` (Fase 27) | Se preserva (puede reutilizarse en una reinstalación) | Se elimina |

**Reglas de negocio**:
- BR1. La opción por defecto es siempre la conservadora (preservar datos, logs y configuración) — el borrado total exige una bandera explícita, el mismo criterio ya usado para `--force-cleanup` durante una instalación fallida (Fase 30).
- BR2. `-PurgeData` exige escribir literalmente `CONFIRMAR` en un prompt interactivo, incluso si se invocó con `-Confirm:$false` — no existe combinación de banderas que permita un borrado total silencioso en modo interactivo (en modo `-Unattended` sí, ver Fase 30, pero requiere el flag explícito `-UnattendedPurgeConfirmed` además de `-PurgeData`, para que un script de automatización no pueda destruir datos por un error de copiar/pegar de un solo flag).

**Comandos concretos**:

```powershell
function Uninstall-Parkos {
    [CmdletBinding()]
    param([switch]$PurgeData, [switch]$UnattendedPurgeConfirmed)

    if ($PurgeData -and -not $UnattendedPurgeConfirmed) {
        $confirmation = Read-Host "Esto eliminará TODOS los datos de Parkos de forma irreversible. Escribe CONFIRMAR para continuar"
        if ($confirmation -ne 'CONFIRMAR') { Write-Host "Desinstalación cancelada."; return }
    }

    Stop-Service ParkosJobSyncSucursal, ParkosApiSucursal, 'postgresql-x64-16' -Force -ErrorAction SilentlyContinue
    & nssm remove ParkosApiSucursal confirm
    & nssm remove ParkosJobSyncSucursal confirm
    Start-Process msiexec.exe -ArgumentList "/x $(Get-ElectronMsiProductCode) /qn" -Wait
    Remove-Item 'C:\Program Files\Parkos' -Recurse -Force

    if ($PurgeData) {
        Remove-Item "$env:ProgramData\Parkos" -Recurse -Force
        Remove-LocalUser -Name 'svc-parkos' -ErrorAction SilentlyContinue
        Write-Host "Parkos desinstalado completamente. Todos los datos fueron eliminados." -ForegroundColor Yellow
    } else {
        Write-Host "Parkos desinstalado. Datos preservados en C:\ProgramData\Parkos\ (pg-data, logs, secrets, backups)." -ForegroundColor Green
        Write-Host "Para reactivar: reinstalar y apuntar el paso de Postgres a este mismo pg-data\." -ForegroundColor Green
    }
}
```

**Pruebas**: 6 pruebas Pester (desinstalación default preserva los 4 elementos marcados en la tabla, `-PurgeData` sin confirmación interactiva cancela, `-PurgeData` con "CONFIRMAR" correcto ejecuta el borrado total, `-PurgeData -UnattendedPurgeConfirmed` en modo desatendido no pide confirmación interactiva, cuenta `svc-parkos` preservada en desinstalación default, y eliminada en purga total).

**Tamaño estimado**: 130 LOC + 110 LOC de tests.

**Tareas atómicas**:
- `HU-F26.4-T1`: Función `Uninstall-Parkos` con lógica default/`-PurgeData`.
- `HU-F26.4-T2`: Confirmación de doble paso para purga total.
- `HU-F26.4-T3`: Tabla de política de desinstalación como documentación embebida (`Get-Help Uninstall-Parkos -Full`).
- `HU-F26.4-T4`: 6 pruebas Pester.

---

## Fase 27 — Seguridad desktop: secretos, cuenta de servicio, ACL y hardening de Electron

### Objetivo

Resolver el problema que la auditoría de completitud del instalador marcó como el hueco de mayor severidad después del rol de mínimo privilegio: en el entorno Docker, `PARKOS_JWT_KEY_PATH` y las credenciales de Postgres viven en un volumen nombrado que el propio motor de contenedores aísla del resto del sistema operativo host. Sin Docker, ese aislamiento desaparece — el archivo de clave y el `.env` son archivos normales en el filesystem de Windows del cliente. Esta fase cierra esa brecha con una cuenta de servicio dedicada, ACL NTFS restrictiva, y un *gate* de instalación que impide arrancar los servicios si el secreto JWT no es real.

### HU-F27.1 — Cuenta de servicio dedicada `svc-parkos` y ACL restrictiva

**Historia**: Como responsable de seguridad, quiero que los servicios de Parkos corran bajo una cuenta local de mínimo privilegio, nunca como `LocalSystem`, y que el directorio de secretos sea ilegible para cualquier otro usuario del equipo.

**Given/When/Then**:
- **Given** el equipo está en la Fase 22 (después de instalar Postgres, antes de registrar los servicios NSSM),
  **When** el instalador crea la cuenta de servicio,
  **Then** ejecuta `New-LocalUser -Name 'svc-parkos'` con una contraseña aleatoria de 24+ caracteres (generada con el mismo `New-SecurePassword` de la Fase 22, nunca reutilizada de otra identidad), `-AccountNeverExpires`, `-UserMayNotChangePassword`, y la agrega **explícitamente** al grupo `Users` — nunca a `Administrators`, ni siquiera transitoriamente durante la instalación.
- **Given** `svc-parkos` fue creada,
  **When** el instalador provisiona `C:\ProgramData\Parkos\secrets\`,
  **Then** aplica `icacls /inheritance:r` (revoca la herencia del directorio padre) seguido de `icacls /grant:r "svc-parkos:(OI)(CI)F"` y `icacls /grant:r "BUILTIN\Administrators:(OI)(CI)F"` — ningún otro usuario o grupo (incluido `Users` en general) tiene acceso de lectura a ese directorio.
- **Given** los servicios NSSM se registran (Fase 24),
  **When** el instalador los configura,
  **Then** usa `ObjectName ".\svc-parkos"` con la contraseña generada, en vez del comportamiento por defecto de NSSM (correr como `LocalSystem`).

**Reglas de negocio**:
- BR1. `svc-parkos` nunca tiene "inicio de sesión interactivo" habilitado — es una cuenta puramente de servicio, no utilizable para iniciar sesión gráfica en el equipo.
- BR2. La ACL de `secrets\` se verifica, no solo se aplica: la Fase 24 (HU-F24.4) y la Fase 26 (`Repair-ParkosInstall`) confirman activamente que la ACL vigente coincide con la esperada, no asumen que quedó bien la primera vez.

**Comandos concretos**:

```powershell
function New-ParkosServiceAccount {
    $svcPassword = New-SecurePassword -Length 24
    $securePwd = ConvertTo-SecureString $svcPassword -AsPlainText -Force
    New-LocalUser -Name 'svc-parkos' -Password $securePwd -AccountNeverExpires `
        -UserMayNotChangePassword -Description 'Cuenta de servicio Parkos (sin login interactivo)'
    Add-LocalGroupMember -Group 'Users' -Member 'svc-parkos'   # explícitamente NO Administrators
    return $svcPassword
}

function Set-ParkosSecretsAcl {
    $secretsPath = "$env:ProgramData\Parkos\secrets"
    New-Item -ItemType Directory -Path $secretsPath -Force | Out-Null
    icacls $secretsPath /inheritance:r
    icacls $secretsPath /grant:r "svc-parkos:(OI)(CI)F"
    icacls $secretsPath /grant:r "BUILTIN\Administrators:(OI)(CI)F"
}

function Test-ParkosSecretsAcl {
    # Usado por HU-F24.4 y Repair-ParkosInstall para verificar, no solo aplicar.
    $acl = Get-Acl "$env:ProgramData\Parkos\secrets"
    $identities = $acl.Access | ForEach-Object { $_.IdentityReference.Value }
    $unexpected = $identities | Where-Object { $_ -notmatch 'svc-parkos|Administrators|SYSTEM' }
    return ($unexpected.Count -eq 0)
}
```

**Pruebas**: 5 pruebas Pester (cuenta creada sin privilegios de administrador, contraseña con entropía suficiente, ACL revoca herencia correctamente, `Test-ParkosSecretsAcl` detecta una ACL alterada por un `icacls /reset` simulado, y verificación de que `svc-parkos` no puede iniciar sesión interactiva). 1 prueba de integración en VM que confirma, con un usuario Windows distinto sin privilegios de administrador, que un intento de `Get-Content` sobre `secrets\.env` falla con acceso denegado.

**Tamaño estimado**: 120 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F27.1-T1`: Función `New-ParkosServiceAccount`.
- `HU-F27.1-T2`: Función `Set-ParkosSecretsAcl`.
- `HU-F27.1-T3`: Función `Test-ParkosSecretsAcl` (verificación activa, reutilizada por Fase 24 y Fase 26).
- `HU-F27.1-T4`: 6 pruebas (5 unitarias + 1 de integración VM con usuario sin privilegios).

---

### HU-F27.2 — Cifrado adicional del `.env` con DPAPI (capa complementaria, no sustituta)

**Historia**: Como responsable de seguridad, quiero una capa adicional de protección para que, incluso si alguien copia el archivo `.env` fuera del equipo (por ejemplo, en un backup mal manejado), el contenido no sea legible sin la máquina original.

**Given/When/Then**:
- **Given** el `.env` de runtime fue escrito con la ACL restrictiva de la HU-F27.1,
  **When** el instalador aplica la capa adicional de cifrado,
  **Then** cifra el contenido con `ConvertTo-SecureString`/`Protect-CmsMessage` (DPAPI nativo de Windows, sin librerías externas), atado a la máquina local — un archivo copiado a otro equipo no es descifrable ni con acceso de administrador en el equipo destino.
- **Given** el servicio `ParkosApiSucursal` necesita leer el `.env` al arrancar,
  **When** NSSM lo invoca,
  **Then** el binario `api-sucursal.exe` descifra el `.env` en memoria al inicio del proceso (usando la misma API DPAPI, ejecutándose como `svc-parkos` en la misma máquina) — el texto plano nunca se escribe de vuelta a disco.

**Reglas de negocio**:
- BR1. Esta capa es **complementaria** a la ACL de la HU-F27.1, nunca un reemplazo: si DPAPI fallara por cualquier motivo, la ACL restrictiva sigue siendo la primera línea de defensa real.
- BR2. El respaldo (`Update-ParkosStack`, Fase 25) preserva el archivo cifrado tal cual — nunca lo descifra para hacer backup, evitando una ventana de texto plano en disco durante una actualización.

**Comandos concretos**:

```powershell
function Protect-ParkosEnvFile {
    param([string]$Path)
    $content = Get-Content $Path -Raw
    $protected = Protect-CmsMessage -Content $content -To 'CN=ParkosLocalMachine' -OutSaveThenExport
    Set-Content -Path "$Path.dpapi" -Value $protected
    Remove-Item $Path -Force   # el texto plano nunca queda en disco tras cifrar
}

function Unprotect-ParkosEnvFile {
    param([string]$Path)
    Unprotect-CmsMessage -Path "$Path.dpapi"
}
```

**Pruebas**: 3 pruebas Pester (cifrado deja un archivo `.dpapi` y elimina el texto plano original, descifrado en la misma máquina recupera el contenido correcto, y un archivo `.dpapi` copiado a un contexto de usuario distinto simulado no es descifrable).

**Tamaño estimado**: 70 LOC + 60 LOC de tests.

**Tareas atómicas**:
- `HU-F27.2-T1`: Función `Protect-ParkosEnvFile` (cifrado DPAPI, elimina texto plano).
- `HU-F27.2-T2`: Función `Unprotect-ParkosEnvFile` (descifrado en el arranque del servicio).
- `HU-F27.2-T3`: 3 pruebas Pester.

---

### HU-F27.3 — *Gate* de instalación: rechazo si el secreto JWT cae al fallback de desarrollo

**Historia**: Como responsable de seguridad, quiero que el instalador se niegue activamente a arrancar los servicios de un cliente si el secreto de firma JWT no es uno generado por este mismo instalador, para no dejar en producción el secreto de desarrollo hardcodeado que existe en el código fuente del backend.

**Corrección aplicada / hecho verificado del backend real**: `parkos_core.auth.tokens._get_secret()` lee el secreto JWT de `PARKOS_JWT_KEY_PATH`, y si la variable no está definida o el archivo no existe, cae silenciosamente a un secreto de desarrollo hardcodeado en el propio código fuente (`_DEFAULT_DEV_SECRET`). El comentario del propio módulo aclara que la migración a RS256 + JWKS con rotación está planeada pero no implementada — el estado real hoy es HS256 con este fallback. Esto no es un hueco de los planes de frontend; es un hecho del backend que el instalador debe conocer y mitigar activamente.

**Given/When/Then**:
- **Given** el instalador llega a la Fase 24 (verificación post-instalación, antes de dejar los servicios arrancados de forma definitiva),
  **When** ejecuta el *gate* de secreto JWT,
  **Then** confirma que `PARKOS_JWT_KEY_PATH` apunta a un archivo que (a) existe, (b) fue generado por este mismo instalador durante esta instalación (con al menos 32 bytes de entropía criptográfica real, nunca una cadena de texto legible), y (c) su hash SHA256 **no** coincide con el hash conocido de `_DEFAULT_DEV_SECRET` (embebido como constante en el propio instalador, calculado una sola vez contra el valor público del código fuente).
- **Given** cualquiera de las tres condiciones anteriores falla,
  **When** el *gate* corre,
  **Then** el instalador se niega a completar la instalación: no marca el proceso como exitoso, no dice "instalación completada", y el mensaje de error indica exactamente cuál de las tres condiciones falló.
- **Given** el *gate* pasó,
  **When** la instalación se considera completa,
  **Then** el archivo de clave JWT vive dentro de `C:\ProgramData\Parkos\secrets\`, protegido por la ACL de la HU-F27.1 y, opcionalmente, por la capa DPAPI de la HU-F27.2.

**Reglas de negocio**:
- BR1. Este *gate* es idéntico, en espíritu, al chequeo de mínimo privilegio de `parkos_app` (HU-F24.4) — ambos son verificaciones de seguridad que el instalador prueba activamente, no supuestos que da por sentados.
- BR2. La lista de hashes conocidos de secretos de desarrollo (*denylist*, compartida con HU-F24.4) se actualiza cada vez que el equipo de backend cambie el valor de `_DEFAULT_DEV_SECRET` — es responsabilidad explícita del proceso de release mantenerla sincronizada, documentado como tarea de checklist en la Fase 28 (CI/CD).

**Comandos concretos**:

```powershell
function New-JwtKeyFile {
    param([string]$Path = "$env:ProgramData\Parkos\secrets\jwt_private.pem")
    $bytes = New-Object byte[] 64
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [System.IO.File]::WriteAllBytes($Path, $bytes)
    return $Path
}

function Test-JwtSecretGate {
    param([string]$JwtKeyPath)
    if (-not (Test-Path $JwtKeyPath)) { return @{ Ok = $false; Reason = 'archivo no existe' } }
    $length = (Get-Item $JwtKeyPath).Length
    if ($length -lt 32) { return @{ Ok = $false; Reason = "solo $length bytes; se requieren >=32" } }
    $hash = (Get-FileHash $JwtKeyPath -Algorithm SHA256).Hash
    if ($hash -in $script:KNOWN_DEV_SECRET_HASHES) {
        return @{ Ok = $false; Reason = 'coincide con el secreto de desarrollo conocido (_DEFAULT_DEV_SECRET)' }
    }
    return @{ Ok = $true; Reason = $null }
}
```

**Pruebas**: 5 pruebas Pester (archivo generado por el instalador pasa el gate, archivo ausente falla con razón clara, archivo demasiado corto falla, archivo cuyo hash coincide con el secreto de desarrollo conocido falla, y el gate bloquea la finalización completa del instalador — no solo emite una advertencia).

**Tamaño estimado**: 90 LOC + 80 LOC de tests.

**Tareas atómicas**:
- `HU-F27.3-T1`: Función `New-JwtKeyFile` (generación con entropía criptográfica real).
- `HU-F27.3-T2`: Función `Test-JwtSecretGate` (las 3 condiciones).
- `HU-F27.3-T3`: *Denylist* de hashes de secretos de desarrollo conocidos, documentada como parte del checklist de release (Fase 28).
- `HU-F27.3-T4`: 5 pruebas Pester.

---

### HU-F27.4 — Hardening del proceso Electron: `contextIsolation`, `sandbox`, CSP

**Historia**: Como responsable de seguridad, quiero que la aplicación de escritorio `web_sucursal` no exponga ninguna API de Node.js al contenido web que renderiza, para reducir la superficie de ataque de una vulnerabilidad de XSS a "solo el DOM", no a "todo el sistema operativo".

**Nota de alcance**: la implementación de estas flags vive en el código de la app Electron (Parte II, frontend). Esta Parte III las documenta porque el instalador es quien empaqueta y firma el binario final, y porque la Fase 28 (firma de código) y esta misma fase (permisos del filesystem) dependen de que el modelo de amenazas del proceso `main` esté correctamente acotado. Se listan aquí como **contrato verificado en el binario empaquetado**, no como diseño nuevo.

**Given/When/Then**:
- **Given** el binario `web_sucursal.exe` fue empaquetado por `electron-builder`,
  **When** el instalador (o el pipeline de CI/CD, Fase 30) verifica el contrato de seguridad del binario,
  **Then** confirma, inspeccionando la configuración empaquetada de `BrowserWindow`, que `contextIsolation: true`, `nodeIntegration: false` y `sandbox: true` están activos — un binario que no cumpla esto no se firma ni se distribuye (gate de CI, Fase 30).
- **Given** el proceso `renderer` necesita invocar una operación privilegiada (imprimir, leer USB, hacer una llamada HTTP autenticada),
  **When** lo hace,
  **Then** pasa exclusivamente por `contextBridge.exposeInMainWorld` con una whitelist explícita de funciones — nunca por acceso directo a módulos de Node.
- **Given** la app carga cualquier contenido,
  **When** se aplica la Content-Security-Policy,
  **Then** el CSP es `default-src 'self'; connect-src 'self' http://127.0.0.1:8000; img-src 'self' data:; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'` — sin `connect-src` hacia ningún dominio de nube (`web_sucursal` habla únicamente con su `api-sucursal` local; el `api-sucursal` es quien, del lado del servidor, habla con el cloud).

**Reglas de negocio**:
- BR1. El CSP de sucursal difiere deliberadamente del de `web_admin` (que sí necesita `connect-src` hacia el dominio de la API cloud, por ser una PWA que habla directo con el backend en la nube) — no se debe copiar un CSP de un frontend al otro sin ajustar `connect-src` a la topología real de cada uno.
- BR2. El buffer ESC/POS de impresión se construye siempre en el proceso `main`, nunca en el `renderer` — evita que una inyección en el DOM pueda manipular directamente el hardware de impresión.

**Pruebas**: la verificación de este contrato es un chequeo de CI (Fase 30), no una prueba Pester del instalador — se documenta aquí la regla, se implementa allá el gate automático.

**Tamaño estimado**: sin LOC propio de esta fase (contrato verificado, no implementado aquí); el gate de CI que lo aplica se dimensiona en la Fase 30.

**Tareas atómicas**:
- `HU-F27.4-T1`: Documentar el contrato de seguridad de Electron como *checklist* verificable de CI (implementación del gate en Fase 30, HU-F30.4).
- `HU-F27.4-T2`: CSP diferenciado explícitamente entre `web_sucursal` y `web_admin`, documentado en ambos lugares para que nadie copie uno al otro sin ajustar `connect-src`.

---

## Fase 28 — Firma de código y distribución

### Objetivo

Firmar todos los binarios distribuibles (MSI de Electron, ejecutables standalone de `api-sucursal`/`job-sync-sucursal`, el propio `parkos-installer.exe`) con un certificado gestionado por HSM, distribuirlos por un canal único y consistente (sin la contradicción de "un canal" vs "canal + beta" que documentos previos dejaban abierta), y dar un procedimiento de rollback manual real para cuando una versión falla en producción de un cliente.

### HU-F28.1 — Firma de código con Azure Trusted Signing

**Historia**: Como responsable de release, quiero que todos los binarios distribuidos estén firmados con un certificado EV gestionado en HSM, para que SmartScreen de Windows no bloquee la instalación en el equipo del cliente.

**Given/When/Then**:
- **Given** un binario recién compilado (`web_sucursal.msi`, `api-sucursal.exe`, `job-sync-sucursal.exe`, `parkos-installer.exe`),
  **When** el pipeline de CI/CD de producción lo firma,
  **Then** usa Azure Trusted Signing (identidad administrada de Azure, sin `.pfx` plano que rote manualmente ni viva en un archivo dentro del repositorio o de un runner), integrado en `electron-builder.yml` vía `win.signtoolOptions` apuntando al endpoint de Trusted Signing, con algoritmo de hash `sha256`.
- **Given** el binario fue firmado,
  **When** el pipeline verifica el resultado,
  **Then** ejecuta `signtool verify /pa` sobre el binario firmado y confirma exit `0` antes de publicar el artefacto — un binario que no pasa esta verificación nunca llega a `releases`/GitHub Releases.
- **Given** el ambiente es staging (no producción),
  **When** se firma un build de prueba,
  **Then** se acepta un certificado autofirmado, con el warning de SmartScreen esperado y documentado como aceptable solo en ese ambiente — nunca en un build que se distribuya a un cliente real.

**Reglas de negocio**:
- BR1. Ningún binario sin firma válida (verificada con `signtool verify /pa`, exit `0`) puede ser copiado al payload de un release de producción — este chequeo es parte del *gate* de CI, no una revisión manual.
- BR2. Los binarios `api-sucursal.exe`/`job-sync-sucursal.exe` se firman con el mismo mecanismo que el MSI de Electron — la auditoría de completitud del instalador señaló que un instalador de campo suele firmar solo el instalador visible y olvidar los binarios de servicio; aquí los 4 artefactos pasan por el mismo paso de firma.

**Checklist de adquisición/renovación del certificado (proceso operativo, no solo decisión técnica)**:

| Paso | Responsable sugerido | Nota |
|---|---|---|
| 1. Validar la identidad de la organización ante la autoridad certificadora (requerido por los *baseline requirements* vigentes para certificados EV/Trusted Signing) | Administración/Legal | Puede tomar 1-2 semanas en la primera solicitud. |
| 2. Aprovisionar el recurso "Trusted Signing" en Azure (suscripción + identidad administrada) | Infraestructura | Es un recurso de Azure gestionado, no un archivo `.pfx` que rota manualmente. |
| 3. Integrar la firma en el pipeline de CI (`win.signtoolOptions` de `electron-builder` apuntando al endpoint de Trusted Signing) | Desarrollo | Ver HU-F30.4 (CI/CD de empaquetado y firma). |
| 4. Calendario de renovación/monitoreo de la identidad de firma | Infraestructura | Evitar que expire sin aviso y bloquee un release; agregar alerta de calendario 30 días antes del vencimiento. |

**Comandos concretos**:

```yaml
# electron-builder.yml (extracto relevante de firma)
win:
  signtoolOptions:
    signingHashAlgorithms: ["sha256"]
    certificateSubjectName: "Parkos S.A.S."
    # Azure Trusted Signing: el endpoint y las credenciales viven en GitHub
    # Secrets / Azure Key Vault, nunca en este archivo versionado.
    signWithParams: "/tr http://timestamp.acs.microsoft.com /td sha256 /fd sha256"
```

```powershell
# Verificación post-firma, parte del gate de CI (Fase 30)
function Test-BinarySignature {
    param([string]$Path)
    $result = & signtool verify /pa $Path
    if ($LASTEXITCODE -ne 0) { throw "Firma inválida o ausente en $Path; release bloqueado." }
}
```

**Pruebas**: 2 pruebas de CI (no Pester del instalador en sí): binario firmado pasa `signtool verify /pa`, binario sin firmar (o con firma expirada, simulada con un certificado de prueba vencido) bloquea el pipeline antes de publicar.

**Tamaño estimado**: 60 LOC (configuración + script de verificación) + 40 LOC de pruebas de CI.

**Tareas atómicas**:
- `HU-F28.1-T1`: Configuración de `win.signtoolOptions` con Azure Trusted Signing.
- `HU-F28.1-T2`: Función `Test-BinarySignature` como gate de CI.
- `HU-F28.1-T3`: Checklist de onboarding a Trusted Signing documentado en el runbook de release.
- `HU-F28.1-T4`: 2 pruebas de CI (firma válida / firma ausente bloquea).

---

### HU-F28.2 — Canal único de actualización (`latest`), sin contradicción entre documentos

**Historia**: Como responsable de release, quiero un único canal de distribución de actualizaciones, documentado de forma consistente en todo lugar donde se mencione, para que ningún desarrollador construya por error un segundo canal que la decisión de arquitectura ya descartó.

**Corrección aplicada**: versiones previas de la documentación tenían una contradicción real — un documento fijaba explícitamente un solo canal `latest` sin beta, mientras otros dos mencionaban canales `latest`/`beta` como si ambos existieran. Esta Parte III fija, de forma única y consistente (DEC-INST-06, Sección 0.2), **un solo canal: `latest`**. No hay ninguna mención de canal `beta` en ningún cmdlet, configuración de `electron-updater`, ni procedimiento de esta parte del documento.

**Given/When/Then**:
- **Given** una nueva versión de `web_sucursal` se publica,
  **When** el pipeline de CI/CD la sube al feed de actualización,
  **Then** se publica exclusivamente al canal `latest` (configurado en `electron-builder.yml` como `publish.channel: latest`); no existe una segunda ruta de publicación ni una bandera que active un canal alternativo.
- **Given** el negocio necesita que un cliente piloto pruebe una versión candidata antes del release general,
  **When** eso ocurre,
  **Then** el cliente piloto recibe un MSI etiquetado `-rc.N` instalado **manualmente** con `Repair-ParkosInstall -Version <rc>` (Fase 26) — nunca mediante un segundo canal de auto-update. El auto-updater de ese cliente sigue apuntando a `latest`, y se pausa temporalmente (`electron-updater` con `autoDownload: false`) mientras dure la prueba piloto, para que no reciba automáticamente el release general antes de que el equipo decida promoverlo.
- **Given** el negocio decide en el futuro que sí necesita un canal piloto real y sostenido (no solo instalaciones manuales puntuales),
  **When** se toma esa decisión,
  **Then** requiere una revisión explícita de `DEC-INST-06` (documentada como tal, con fecha y responsable), no una convivencia tácita de dos canales sin que nadie lo decida formalmente.

**Reglas de negocio**:
- BR1. `allowDowngrade: false` en `electron-updater` (DEC-INST-08) — el canal único `latest` nunca permite que un cliente reciba una versión anterior a la que ya tiene instalada por la vía del auto-update.
- BR2. La versión de `api-sucursal`/`job-sync-sucursal` (actualizada por `Update-ParkosStack`, Fase 25) y la versión de Electron (actualizada por su propio auto-updater) son ciclos independientes por diseño (DEC-INST-16, Sección 0.2) — el canal único de Electron no implica que backend y frontend se actualicen atómicamente juntos; el chequeo de `api_contract_version` en `GET /health` es el mecanismo real de compatibilidad entre ambos.

**Comandos concretos**:

```yaml
# electron-builder.yml (extracto relevante de publicación)
publish:
  provider: s3
  bucket: parkos-releases-prod
  channel: latest   # ÚNICO canal; no existe "beta" en ningún lugar de esta configuración
```

**Pruebas**: 2 pruebas de CI (configuración de `electron-builder.yml` no contiene la palabra `beta` en ninguna clave de publicación — chequeo de higiene documental automatizado, para que una futura reintroducción accidental del canal beta falle el build; y verificación de que `allowDowngrade` es `false`).

**Tamaño estimado**: 20 LOC de configuración + 30 LOC de prueba de higiene de CI.

**Tareas atómicas**:
- `HU-F28.2-T1`: Configuración de `publish.channel: latest` único en `electron-builder.yml`.
- `HU-F28.2-T2`: Prueba de CI que falla si aparece la palabra `beta` en la configuración de publicación.
- `HU-F28.2-T3`: Procedimiento documentado de distribución manual de un MSI `-rc.N` a un cliente piloto, sin canal alternativo.

---

### HU-F28.3 — Rollback manual de versión en producción de cliente

**Historia**: Como técnico de soporte, quiero un procedimiento documentado y probado para revertir una versión defectuosa en el equipo de un cliente, en vez de improvisar en el primer incidente real.

**Given/When/Then**:
- **Given** `allowDowngrade: false` impide el downgrade automático (por diseño, para evitar ataques de downgrade),
  **When** soporte detecta una versión defectuosa en campo,
  **Then** ejecuta `Restore-ParkosVersion -Version <N-1>`, que: (1) pausa el feed de auto-update (`autoDownload: false` vía IPC al proceso Electron en ejecución, o edición del `electron-updater.yml` local si la app no está corriendo) para evitar que vuelva a autoactualizarse a la versión defectuosa, (2) reinstala el MSI de la versión N-1 conservado en `C:\ProgramData\Parkos\releases\` (Fase 25, HU-F25.2 — se conservan al menos las 2 últimas versiones estables), y (3) dispara `Update-ParkosStack -RollbackOnly` si el backend también había avanzado en esa misma actualización.
- **Given** el rollback de versión se completó,
  **When** soporte lo verifica,
  **Then** corre `Get-ParkosHealth` (Fase 26) y confirma que la versión activa reportada coincide con N-1 antes de cerrar el incidente.
- **Given** este procedimiento nunca se ha probado antes de un incidente real,
  **When** se agrega al checklist de release (Fase 30),
  **Then** cada release mayor incluye una prueba deliberada de `Restore-ParkosVersion` en un entorno de staging, no se deja para el primer incidente real en producción.

**Reglas de negocio**:
- BR1. `Restore-ParkosVersion` nunca reinstala una versión que no esté en `releases\` — si la versión solicitada ya fue rotada (más de 2 versiones atrás), el comando falla con un mensaje claro en vez de intentar descargarla de un canal que, por diseño (`allowDowngrade: false`), no la serviría de todas formas.
- BR2. Pausar el auto-update es un paso obligatorio y previo a la reinstalación — reinstalar la versión anterior sin pausar el feed dejaría al cliente re-actualizándose a la versión defectuosa en el siguiente ciclo de chequeo del `electron-updater`.

**Comandos concretos**:

```powershell
function Restore-ParkosVersion {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Version)

    $releasePath = "$env:ProgramData\Parkos\releases\$Version"
    if (-not (Test-Path $releasePath)) {
        throw "Versión $Version no está conservada en releases\ (rotación de 2 versiones); no se puede revertir automáticamente."
    }

    Set-Content "$env:ProgramData\Parkos\secrets\auto-update-paused.flag" -Value (Get-Date).ToString('o')
    Start-Process msiexec.exe -ArgumentList "/i `"$releasePath\web_sucursal-$Version.msi`" /qn" -Wait

    if (Test-Path "$releasePath\api-sucursal") {
        Update-ParkosStack -PayloadPath $releasePath -RollbackOnly
    }

    Write-Host "Versión $Version restaurada. Auto-update pausado hasta remover manualmente el flag." -ForegroundColor Yellow
    Get-ParkosHealth
}
```

**Pruebas**: 4 pruebas Pester (versión disponible en `releases\` se restaura correctamente, versión no disponible falla con mensaje claro, auto-update queda pausado tras el rollback, y `Get-ParkosHealth` posterior confirma la versión activa correcta). 1 prueba de integración en el checklist de release de staging (HU-F30.4).

**Tamaño estimado**: 100 LOC + 90 LOC de tests.

**Tareas atómicas**:
- `HU-F28.3-T1`: Función `Restore-ParkosVersion`.
- `HU-F28.3-T2`: Mecanismo de pausa del auto-update (`auto-update-paused.flag`).
- `HU-F28.3-T3`: Integración con `Update-ParkosStack -RollbackOnly` cuando el backend también avanzó.
- `HU-F28.3-T4`: 5 pruebas (4 unitarias + 1 de checklist de staging por release).

---

## Fase 29 — Operación en campo: backups, recuperación ante fallos, monitoreo y sincronización

### Objetivo

Cubrir el hueco de mayor severidad que la auditoría de completitud del instalador encontró: la operación sin supervisión de un nodo de sucursal (backups automáticos, resiliencia ante corte de energía, monitoreo proactivo) estaba casi vacía en la documentación previa. Esta fase también documenta, con el detalle que el diseño real exige, el motor de sincronización (`CU-07`) y la tabla `sync_queue_lw_buffer`, que ningún documento anterior del proyecto mencionaba.

**Nota de alcance (transversal vs. específico de sucursal)**: los backups de base de datos, el WAL/crash recovery de Postgres y el monitoreo de infraestructura descritos en esta fase son **transversal-reales**: el mismo mecanismo de `pg_dump`/`pg_basebackup` y las mismas garantías de `fsync`/`full_page_writes` aplican igual de cara al nodo cloud (que respalda la base de datos de `web_admin`) que al nodo de sucursal — la diferencia es solo quién opera la tarea programada (en cloud, un job gestionado por infraestructura; en sucursal, la tarea de Windows que este instalador crea). Donde el mecanismo es exclusivo de un solo frontend (el motor de sincronización `CU-07`, el `sync_queue_lw_buffer`, el heartbeat que reutiliza el canal de *pairing*) se marca explícitamente como **específico de sucursal**, porque no tiene equivalente en `web_admin` (que no sincroniza con nada — es la fuente de verdad cloud).

### Tablas ER relevantes

| Tabla | Clase ER | Rol en esta fase |
|---|---|---|
| `sync_queue` | `[A]` | Outbox local de eventos pendientes de enviar a la nube (específico de sucursal). |
| `sync_log` | `[A]` | Métrica por ciclo de sincronización (`operaciones_enviadas`, `operaciones_exitosas`, `operaciones_fallidas`, `lag_seg`) — alimenta las alertas `sync_failure`/`branch_offline` (específico de sucursal). |
| `sync_conflict` | `[A]` | Conflictos detectados al sincronizar (versión local vs. versión cloud), con la resolución "última escritura gana" por timestamp UTC (específico de sucursal). |
| **`sync_queue_lw_buffer`** | `[A]`, particionada diariamente por `pg_partman` | Buffer de dependencia: retiene una fila hasta que su padre declarado (`depends_on`) llegue — espera genérica en ambas direcciones (ADR-002 del diseño de sincronización). Es la tabla del ER que ninguna de las auditorías previas encontró cubierta por ningún documento. Ver HU-F29.5. |

### HU-F29.1 — Resiliencia ante corte de energía: `fsync`, `full_page_writes` y prueba de humo de *crash recovery*

**Historia**: Como responsable de operación, quiero la certeza verificada (no asumida) de que un corte de energía abrupto en el equipo del cliente no corrompe ni pierde datos, porque el equipo de un parqueadero no tiene UPS garantizado ni personal de TI local.

**Given/When/Then**:
- **Given** Postgres 16 fue instalado (vía `winget` o el ZIP de EDB, Fase 22),
  **When** el instalador revisa la configuración resultante,
  **Then** verifica explícitamente (no asume) que `fsync = on` y `full_page_writes = on` en el `postgresql.conf` generado — ambos son el *default* real de Postgres, pero cualquier ajuste de "rendimiento" que un técnico aplique después (o que un tutorial de internet sugiera) no debe desactivarlos; el instalador falla el pre-flight de la Fase 22 si detecta que alguno quedó en `off`.
- **Given** la configuración es correcta,
  **When** el instalador ejecuta la prueba de humo de recuperación (parte del checklist de instalación, no opcional),
  **Then** simula una escritura activa (una transacción de prueba abierta) y mata el proceso de Postgres de forma abrupta (`Stop-Process -Force` sobre el PID del *postmaster*, no `Stop-Service` — que hace un apagado ordenado y no probaría nada), luego reinicia el servicio y confirma que Postgres vuelve a `Running` y acepta conexiones dentro de 30 segundos, sin intervención manual, mediante la reproducción de WAL en el arranque.
- **Given** la prueba de humo falla (el servicio no se recupera solo),
  **When** el instalador lo detecta,
  **Then** bloquea la instalación completa con un mensaje explícito ("la recuperación ante fallos de Postgres no funcionó en este equipo; no se recomienda continuar sin investigar la causa") — no es una advertencia ignorable, es un *gate*.

**Reglas de negocio**:
- BR1. Esta prueba se ejecuta **una sola vez**, durante la instalación limpia (no en cada arranque de servicio, que sería disruptivo) — es una verificación de que el entorno del cliente soporta el comportamiento esperado, no un chequeo continuo.
- BR2. El WAL en sí (`pg_wal/`) vive dentro de `C:\ProgramData\Parkos\pg-data\`, incluido en el alcance de los backups de la HU-F29.2 solo en la medida en que `pg_dump` no lo necesita (un `pg_dump` lógico no depende del WAL para restaurar) — el WAL es responsabilidad del propio motor de Postgres para *crash recovery*, no un artefacto que este instalador respalde por separado.

**Comandos concretos**:

```powershell
function Test-CrashRecovery {
    param([int]$Port)
    & psql -p $Port -U parkos -c "SHOW fsync;" | Should -Match 'on'
    & psql -p $Port -U parkos -c "SHOW full_page_writes;" | Should -Match 'on'

    # Prueba de humo: transacción abierta + kill abrupto + verificación de recuperación
    Start-Job -ScriptBlock {
        & psql -p $using:Port -U parkos_app -d parkos -c "BEGIN; INSERT INTO prod.log_transaccional (...) VALUES (...); SELECT pg_sleep(5);"
    } | Out-Null
    Start-Sleep -Seconds 2
    $pid = (Get-Process postgres | Select-Object -First 1).Id
    Stop-Process -Id $pid -Force

    Start-Service postgresql-x64-16
    $recovered = Wait-ForServiceStatus -Name 'postgresql-x64-16' -Status 'Running' -TimeoutSeconds 30
    if (-not $recovered) {
        throw "Postgres no se recuperó tras el corte simulado; la instalación NO continúa."
    }
    $connectOk = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet
    if (-not $connectOk) { throw "Postgres recuperado pero no acepta conexiones." }
}
```

**Pruebas**: 4 pruebas Pester (`fsync`/`full_page_writes` verificados en `on`, uno de los dos en `off` bloquea el pre-flight, prueba de humo con recuperación exitosa en VM real, y prueba de humo con un `postgresql.conf` deliberadamente corrupto que confirma que el instalador bloquea en vez de continuar). Esta HU depende de una VM real (no se puede mockear un corte de energía de forma significativa).

**Tamaño estimado**: 100 LOC + 90 LOC de tests (mayormente de integración VM).

**Tareas atómicas**:
- `HU-F29.1-T1`: Verificación de `fsync`/`full_page_writes` en el pre-flight de Postgres (Fase 22).
- `HU-F29.1-T2`: Función `Test-CrashRecovery` (prueba de humo de recuperación).
- `HU-F29.1-T3`: 4 pruebas (todas dependientes de VM con Postgres real).

---

### HU-F29.2 — Backups automáticos con `pg_dump` y política de retención

**Historia**: Como responsable de operación, quiero backups diarios automáticos de la base de datos de cada sucursal, con una política de retención razonable, sin depender de que un técnico recuerde ejecutarlos manualmente.

**Given/When/Then**:
- **Given** la instalación limpia terminó exitosamente,
  **When** el instalador registra la tarea de backup,
  **Then** crea una tarea programada de Windows (`Register-ScheduledTask`, nativo, sin dependencias de terceros) que ejecuta `pg_dump -Fc -U parkos_app -d parkos -f "C:\ProgramData\Parkos\backups\parkos_{timestamp}.dump"` diariamente a las 3 AM (fuera del horario pico de operación del parqueadero), corriendo bajo la cuenta `svc-parkos` (nunca como superusuario, ni siquiera para el backup — `parkos_app` tiene permisos de `SELECT` suficientes sobre todas las tablas para que `pg_dump` funcione correctamente).
- **Given** el backup diario se ejecuta,
  **When** termina,
  **Then** aplica la política de retención (7 diarios + 4 semanales + 1 mensual, esquema abuelo-padre-hijo simplificado) eliminando automáticamente los backups más antiguos que exceden esa ventana, **antes** de crear el backup del día (para no quedarse sin espacio si el disco está ajustado).
- **Given** `Update-ParkosStack` (Fase 25) necesita un backup antes de migrar,
  **When** invoca `Invoke-MandatoryBackup`,
  **Then** reutiliza exactamente este mismo mecanismo (`pg_dump -Fc`), nunca un segundo mecanismo de backup paralelo — si la Fase 25 necesita un backup fuera del horario de la tarea diaria, lo dispara bajo demanda con la misma función.

**Reglas de negocio**:
- BR1. El formato `custom` (`-Fc`) se elige explícitamente sobre un dump SQL plano porque es comprimido y restaurable selectivamente con `pg_restore` (tabla por tabla si hiciera falta), útil tanto para la restauración completa de un desastre como para diagnósticos puntuales.
- BR2. La política de retención nunca borra el backup más reciente, incluso si por algún motivo excede la cuenta esperada — siempre se conserva al menos 1 backup válido en todo momento.

**Comandos concretos** (registro de la tarea programada, ejecutado por el instalador durante la Fase 22/23):

```powershell
function Register-ParkosBackupTask {
    $scriptPath = "$env:ProgramData\Parkos\scripts\Invoke-DailyBackup.ps1"
    $action = New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument "-File `"$scriptPath`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 3am
    $principal = New-ScheduledTaskPrincipal -UserId 'svc-parkos' -LogonType ServiceAccount
    Register-ScheduledTask -TaskName 'ParkosBackupDiario' -Action $action `
        -Trigger $trigger -Principal $principal -Description 'Backup diario de PostgreSQL (Parkos)'
}

# Invoke-DailyBackup.ps1 (contenido del script programado)
function Invoke-DailyBackup {
    Remove-ExpiredBackups -RetentionDaily 7 -RetentionWeekly 4 -RetentionMonthly 1
    $backupPath = "$env:ProgramData\Parkos\backups\parkos_$(Get-Date -Format yyyyMMdd_HHmmss).dump"
    & pg_dump -Fc -U parkos_app -d parkos -f $backupPath
    if ($LASTEXITCODE -ne 0) {
        Write-EventLog -LogName Application -Source 'ParkosBackup' -EventId 9101 -EntryType Error `
            -Message "Backup diario falló (exit $LASTEXITCODE)."
        # La ausencia de un backup reciente es detectada por Get-ParkosHealth (Fase 26) y por el
        # heartbeat de la HU-F29.3 — no requiere un mecanismo de alerta paralelo.
    }
}
```

**Pruebas**: 5 pruebas Pester (tarea programada registrada con el horario correcto, backup exitoso genera un archivo `.dump` legible con `pg_restore --list`, retención elimina backups fuera de la ventana antes de crear el nuevo, retención nunca deja el sistema con 0 backups válidos, y `Invoke-MandatoryBackup` de la Fase 25 reutiliza esta misma función sin duplicar lógica).

**Tamaño estimado**: 130 LOC + 100 LOC de tests.

**Tareas atómicas**:
- `HU-F29.2-T1`: Función `Register-ParkosBackupTask`.
- `HU-F29.2-T2`: Script `Invoke-DailyBackup.ps1` con retención abuelo-padre-hijo.
- `HU-F29.2-T3`: Función `Remove-ExpiredBackups` (retención 7+4+1, nunca deja 0 backups).
- `HU-F29.2-T4`: 5 pruebas Pester.

---

### HU-F29.3 — Monitoreo/heartbeat proactivo reutilizando el canal de sincronización

**Historia**: Como responsable de operación, quiero saber si una sucursal cae de forma silenciosa (servicio detenido, disco lleno, Postgres no responde) sin tener que introducir un sistema de monitoreo nuevo (Prometheus/Grafana serían sobre-ingeniería para un solo nodo por sucursal).

**Given/When/Then**:
- **Given** `job-sync-sucursal` está operativo,
  **When** ejecuta su ciclo periódico (Fase 24, `PARKOS_SYNC_POLL_INTERVAL_S=10` por defecto),
  **Then** cada ciclo también invoca internamente `Get-ParkosHealth` (o su equivalente en el propio proceso Python, reutilizando `parkos_core.cli.doctor` como librería en vez de invocarlo como subproceso en cada ciclo de 10 s) y, si detecta 3 fallos consecutivos de cualquier check crítico, agrega un evento de salud al próximo payload de sincronización hacia el nodo cloud — no se construye un canal de alerta nuevo; se reutiliza la conectividad que el producto ya necesita para sincronizar.
- **Given** el propio servicio de sincronización es el que falló (no hay ciclos para reportar nada),
  **When** el nodo cloud no recibe ningún evento de una sucursal durante más de `PARKOS_SYNC_HEARTBEAT_S` (60 segundos por defecto, según `runtime/env.py`) multiplicado por un umbral razonable (recomendado: 15 minutos sin ningún contacto),
  **Then** el propio nodo cloud (lado `web_admin`, fuera del alcance de esta Parte III) marca la sucursal como "silenciosa" basándose en la ausencia de actividad en `sync_log`, sin que la sucursal misma tenga que reportar su propia caída — un mecanismo de "última vez visto" es suficiente y no requiere que el nodo caído haga nada.
- **Given** el disco del equipo del cliente se llena,
  **When** el chequeo de salud lo detecta (ya cubierto por `Get-ParkosHealth`, Fase 26),
  **Then** ese mismo hecho se reporta en el próximo ciclo de sync junto con el resto del estado de salud, sin un mecanismo de alerta separado.

**Reglas de negocio**:
- BR1. Esta decisión (DEC-INST-11, Sección 0.2) es deliberada: no se introduce infraestructura de monitoreo nueva. El costo de operar un sistema de alertas dedicado para un nodo por sucursal no se justifica frente a reutilizar la conectividad que `job-sync-sucursal` ya mantiene por diseño.
- BR2. El heartbeat de salud viaja en el mismo payload de sincronización (`sync_log` de cada ciclo), nunca en un canal HTTP separado — esto evita abrir un segundo endpoint de red desde el equipo del cliente hacia la nube.

**Comandos/código concretos**:

```python
# jobs/sync_sucursal.py (extracto conceptual del ciclo del worker, ya existente;
# esta Parte III documenta la extensión de salud, no reescribe el worker completo)
async def sync_cycle(self) -> None:
    health = await self._check_local_health()   # reusa parkos_core.cli.doctor como librería
    if health.consecutive_failures >= 3:
        self._pending_health_event = health.to_sync_payload()
    await self._push_outbox()   # sync_queue -> cloud, incluye el evento de salud si existe
    await self._pull_remote_changes()
    self._record_sync_log(operaciones_enviadas=..., operaciones_exitosas=..., lag_seg=...)
```

**Pruebas**: 3 pruebas de integración del worker (evento de salud se agrega al payload tras 3 fallos consecutivos, un solo fallo aislado no dispara el evento — evita falsos positivos por un timeout transitorio, y el evento de salud viaja en el mismo ciclo de `sync_queue` sin abrir conexión adicional).

**Tamaño estimado**: 80 LOC (extensión del worker existente) + 70 LOC de tests. Este trabajo pertenece al backend (`job_sync_sucursal`), no al instalador PowerShell — se documenta aquí porque es la pieza operativa que cierra el hueco de monitoreo que esta fase cubre.

**Tareas atómicas**:
- `HU-F29.3-T1`: Extensión de `sync_cycle` para adjuntar el evento de salud tras 3 fallos consecutivos.
- `HU-F29.3-T2`: Consumo del evento de salud del lado cloud (`web_admin`, fuera de alcance de esta parte — solo se documenta el contrato de payload aquí).
- `HU-F29.3-T3`: 3 pruebas de integración del worker.

---

### HU-F29.4 — Sincronización offline-first: outbox, idempotencia y backoff (CU-07)

**Historia**: Como responsable de operación, quiero que el motor de sincronización implemente exactamente las reglas de negocio declaradas en CU-07 (backoff exponencial, idempotencia por UUID, regla de "última escritura gana"), y que el instalador no interfiera con ese contrato en ningún paso del ciclo de vida.

**Descripción del mecanismo (CU-07, verbatim del caso de uso original)**: `job-sync-sucursal` corre como servicio del sistema operativo (Fase 24), hace *pull* de cambios remotos desde el último cursor local, los aplica en cache local con la regla "última escritura gana" por timestamp UTC, toma eventos del *outbox* local (`sync_queue`) y los envía al backend cloud, y aplica *backoff* exponencial ante cualquier error. El intervalo de sondeo real configurado por defecto en el código (`runtime/env.py`, `PARKOS_SYNC_POLL_INTERVAL_S=10`) es de 10 segundos — más frecuente que el "60 segundos por defecto" que describe el texto original de CU-07; esta Parte III usa el valor real del código como autoridad para el instalador (es el que efectivamente se despliega), y deja constancia de la diferencia como ABIERTO-104 en la Sección final, para que quien mantenga CU-07 decida si actualiza el texto del caso de uso o si el valor de código debería alinearse a 60 s.

**Given/When/Then**:
- **Given** un evento de negocio se genera en sucursal (por ejemplo, `ingreso.creado`),
  **When** se encola en `sync_queue`,
  **Then** lleva un UUID v4 propio (garantía de idempotencia — reenviar el mismo evento N veces nunca genera duplicados del lado cloud, que deduplica por ese UUID).
- **Given** el envío de un evento falla (cloud no disponible),
  **When** `job-sync-sucursal` reintenta,
  **Then** aplica el backoff exponencial canónico de CU-07 BR2: `1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s, 300s` (máximo, y se mantiene en 300 s para reintentos posteriores) — este es el backoff del *outbox* genérico de sincronización, distinto del backoff de reintento manual de Facturación Electrónica (CU-05, escala de minutos/horas) y del backoff automático del *dispatcher* DIAN (escala de segundos-minutos, gestionado del lado cloud); los tres coexisten porque son colas con propósitos y actores distintos, no una inconsistencia a resolver. La siguiente tabla los distingue explícitamente para que ningún desarrollador confunda una escala con otra:

| Cola | Quién reintenta | Escala de backoff | Umbral de fallo permanente |
|---|---|---|---|
| `sync_queue` (outbox genérico de sucursal, CU-07) | `job-sync-sucursal`, automático | `1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s, 300s` (máx.) | 24 horas sin procesar → `fallido permanente` + alerta |
| Reintento de Factura Electrónica (CU-05) | Usuario/administrador, manual (botón "Reintentar"), con reintento automático de respaldo | `1 min, 5 min, 15 min, 1 h, 6 h, 24 h` | 6 reintentos agotados → estado `rechazado` + alerta al administrador |
| *Dispatcher* DIAN automático (cloud, fuera de esta parte) | Proceso automático del lado cloud | `60 s, 300 s, 900 s` | Gestionado por el dispatcher cloud, documentado en la parte de `web_admin` |

- **Given** un evento permanece sin procesar 24 horas,
  **When** el backoff se agota,
  **Then** se marca `fallido permanente` (CU-07 BR3) y se genera una alerta — este es el único punto donde la cola genérica de sync se cruza con el sistema de alertas (`alert_types`), y es responsabilidad del backend, no del instalador; el instalador únicamente garantiza que el servicio que ejecuta este ciclo (`ParkosJobSyncSucursal`) está corriendo de forma confiable (Fase 24).
- **Given** dos nodos modifican el mismo registro mientras uno está offline,
  **When** ambos se reconectan,
  **Then** la regla "última escritura gana" por timestamp UTC decide el ganador y el perdedor se registra en `sync_conflict` con ambas versiones (`datos_local`, `datos_cloud`) para auditoría, nunca se descarta silenciosamente.

**Reglas de negocio**:
- BR1 (CU-07 BR1). Idempotencia garantizada por UUID v4 en cada evento — no por número de secuencia ni por timestamp, que no son suficientes ante reintentos concurrentes.
- BR2 (CU-07 BR2). El backoff exponencial de arriba se implementa como una tabla de valores explícita en el worker, no como una fórmula recalculada en cada intento (evita drift de precisión de punto flotante en despliegues de larga duración).
- BR3 (CU-07 BR3). El umbral de 24 horas se mide desde la primera vez que el evento entró a la cola, no desde el último reintento — un evento puede acumular sus 10 reintentos de backoff en menos de 10 minutos reales; las 24 horas son el límite absoluto de vida en cola, no la suma de los intervalos de backoff.
- BR4. Sin conexión, el módulo local (el nodo de sucursal completo: Postgres local + `api-sucursal` + `job-sync-sucursal`, **no** un IndexedDB de navegador ni un SQLite embebido — corrección explícita frente a documentación previa de otras partes del proyecto que asumía SQLite) sigue operando al 100% (CU-07 AC1): ingresos, salidas, cobros y arqueos se registran localmente sin ninguna dependencia de que el ciclo de sincronización esté funcionando.

**Pruebas**: 6 pruebas de integración del worker (idempotencia verificada reenviando el mismo evento 5 veces sin duplicados en cloud, secuencia de backoff exacta verificada intento por intento, marcado de `fallido permanente` tras simular 24 horas de reloj, conflicto detectado y ambas versiones preservadas en `sync_conflict`, operación 100% local con el worker deliberadamente detenido, y reconexión sin pérdida de datos tras un corte de red simulado de 10 minutos).

**Tamaño estimado**: trabajo de backend ya existente (`jobs/sync_sucursal.py`) — esta HU documenta el contrato que el instalador debe respetar (no reiniciar el worker de forma que rompa un ciclo de backoff en curso, por ejemplo) más las 6 pruebas de contrato: 120 LOC de tests de integración.

**Tareas atómicas**:
- `HU-F29.4-T1`: Tabla de backoff explícita (no recalculada) para `sync_queue`, documentada como contrato verificado por prueba.
- `HU-F29.4-T2`: Verificación de que `Update-ParkosStack` (Fase 25) detiene `ParkosJobSyncSucursal` de forma ordenada (nunca a mitad de un ciclo de escritura en `sync_queue`) para no corromper el estado de reintento de un evento en curso.
- `HU-F29.4-T3`: 6 pruebas de integración del worker (contrato de CU-07).

---

### HU-F29.5 — `sync_queue_lw_buffer`: buffer de dependencias entre padres e hijos aún no resueltos

**Historia**: Como responsable de operación, quiero entender y verificar el mecanismo que resuelve el problema de orden de llegada entre registros dependientes durante la sincronización (por ejemplo, una `salida` cuyo `ingreso` padre todavía no llegó al otro nodo), porque ninguna documentación previa del proyecto mencionaba esta tabla del ER.

**Descripción (verificada directamente contra `modelo_datos_er.mmd`)**: `sync_queue_lw_buffer` es una tabla `[A]`, particionada diariamente por `pg_partman` (clave de partición: `buffered_at`), cuyo propósito documentado en el propio ER es actuar como "buffer de dependencia: retiene una fila hasta que su padre declarado (`depends_on`) llegue; espera genérica en ambas direcciones (ADR-002)". Sus columnas relevantes: `uuid` (PK), `buffered_at` (clave de partición), `uuid_sucursal` (FK, nullable si la fila en espera no tiene sucursal propia), `tabla` (tabla del registro en espera), `uuid_registro` (uuid del registro en espera, polimórfico), y `tabla_padre` (tabla del padre declarado en `depends_on` aún no resuelto).

**Por qué importa para esta Parte III (instalador/producción)**: esta tabla participa del mismo particionado por `pg_partman` que la Fase 22 configura para el equipo Windows nativo (HU-F22.4) — sin ese paso de instalación correctamente resuelto, `sync_queue_lw_buffer` no tiene mantenimiento automático de particiones y crecería sin límite en un nodo de alto volumen. Es, además, la pieza que explica por qué el motor de sincronización (HU-F29.4) puede recibir eventos en un orden distinto al de su creación (por ejemplo, tras una reconexión larga con múltiples eventos encolados) sin romper la integridad referencial: en vez de rechazar un evento cuyo padre no ha llegado todavía, el ciclo de sincronización lo retiene aquí y lo reintenta cuando el padre se resuelve, en ambas direcciones (un padre que llega tarde desde sucursal hacia cloud, o un padre que llega tarde desde cloud hacia sucursal).

**Given/When/Then**:
- **Given** `job-sync-sucursal` recibe (o intenta enviar) un registro cuyo padre declarado en `depends_on` todavía no existe en el nodo destino,
  **When** el ciclo de sincronización detecta la dependencia no resuelta,
  **Then** inserta la fila en espera en `sync_queue_lw_buffer` con `tabla`/`uuid_registro` del hijo y `tabla_padre` de la dependencia faltante, en vez de fallar la operación completa o descartar el registro.
- **Given** el padre finalmente llega (en cualquier dirección),
  **When** el próximo ciclo de sincronización lo detecta,
  **Then** resuelve las filas en espera correspondientes de `sync_queue_lw_buffer` y las reintegra al flujo normal de aplicación de cambios — este reintento no tiene el mismo backoff exponencial de `sync_queue` (HU-F29.4): se resuelve tan pronto el padre esté disponible, en el ciclo inmediatamente siguiente, no según una escala de tiempo de reintento por fallo.
- **Given** el instalador configura `pg_partman` en la Fase 22,
  **When** registra la tarea de mantenimiento diario (`Register-PgPartmanMaintenance`, HU-F22.4),
  **Then** esa misma tarea programada cubre el particionado de `sync_queue_lw_buffer` (junto con `salidas` y `caja`) — no requiere una tarea de mantenimiento separada; es la misma llamada a `partman.run_maintenance_proc()` la que administra todas las tablas particionadas del esquema.

**Reglas de negocio**:
- BR1. `sync_queue_lw_buffer` no tiene su propio ciclo de "fallido permanente" a 24 horas como `sync_queue` (HU-F29.4 BR3) — una dependencia que nunca se resuelve es un problema de integridad de datos más profundo que un simple reintento de red, y se documenta como ABIERTO-105 en la Sección final para que el equipo de backend defina un umbral y una alerta específicos, dado que ninguna auditoría previa lo había cubierto.
- BR2. La partición diaria de esta tabla, igual que `salidas`/`caja`, depende de que la Fase 22 (`pg_partman` en Windows nativo) esté correctamente resuelta — un despliegue que se salte ese paso (por ejemplo, restaurando un backup en un equipo sin `pg_partman` instalado) dejaría esta tabla sin mantenimiento automático de particiones, un riesgo operativo real a mediano plazo, no inmediato.

**Pruebas**: 3 pruebas de integración del worker (un evento con dependencia no resuelta se retiene en `sync_queue_lw_buffer` en vez de fallar, la llegada del padre resuelve la fila en espera en el ciclo siguiente sin esperar un backoff, y la tarea de mantenimiento de `pg_partman` de la Fase 22 crea particiones nuevas para esta tabla igual que para `salidas`/`caja`).

**Tamaño estimado**: trabajo de backend ya existente (motor de sincronización) — esta HU documenta el contrato y agrega 3 pruebas de integración (70 LOC) que verifican que el instalador (particionado de la Fase 22) y el motor de sync (backend) están correctamente acoplados para esta tabla específicamente.

**Tareas atómicas**:
- `HU-F29.5-T1`: Verificación de que `Register-PgPartmanMaintenance` (Fase 22) cubre `sync_queue_lw_buffer` en su alcance de particionado, no solo `salidas`/`caja`.
- `HU-F29.5-T2`: 3 pruebas de integración del worker (retención, resolución al llegar el padre, particionado).
- `HU-F29.5-T3`: Documentar como ABIERTO-105 la ausencia de un umbral de "dependencia nunca resuelta" (fuera del alcance de esta Parte III cerrarlo, pero se deja trazado explícitamente).

---

## Fase 30 — Impresión térmica, entorno de desarrollo local, testing del instalador y CI/CD de empaquetado

### Objetivo

Cerrar cuatro capacidades que la documentación previa dejaba incompletas: una matriz real de impresoras térmicas soportadas (no solo un modelo citado una vez), un entorno de desarrollo local que no exige instalar el producto completo, el testing automatizado del instalador — incluida la app Electron empaquetada —, y el pipeline de CI/CD que arma, firma y publica todos los artefactos de release.

### HU-F30.1 — Matriz de compatibilidad de impresoras térmicas ESC/POS

**Historia**: Como técnico de despliegue, quiero saber de antemano qué impresoras térmicas son compatibles y cuáles requieren un tratamiento especial, en vez de descubrirlo en campo con el primer cliente que trae una marca distinta.

**Given/When/Then**:
- **Given** el cliente tiene una impresora térmica de alguna de las marcas de la matriz siguiente,
  **When** el técnico la conecta antes o durante la instalación,
  **Then** `web_sucursal` la detecta vía USB (`bridge.usb.list()`, ya cubierto por la Parte de frontend) y el instalador no requiere ningún paso adicional para las marcas marcadas como "ESC/POS estándar" en la tabla.
- **Given** el cliente tiene una impresora Star Micronics,
  **When** el técnico la conecta,
  **Then** el instalador advierte explícitamente (mensaje en la TUI, no solo en documentación) que este modelo puede requerir su propio driver StarPRNT en vez de ESC/POS puro, y no asume compatibilidad genérica sin verificarla.

**Matriz de compatibilidad (catálogo inicial recomendado para `printer_profiles`, tabla que — de decidirse su creación por el equipo de frontend como una adaptación explícita y declarada del ER, no una tabla "out-of-catalog" silenciosa — vive fuera del alcance de escritura de esta Parte III; aquí se documenta el contenido de referencia, no el esquema)**:

| Marca / modelo | Interfaz | Ancho de papel | Notas de compatibilidad ESC/POS |
|---|---|---|---|
| Epson TM-T20 / TM-T20III | USB | 80 mm | Referencia de facto del set de comandos ESC/POS estándar; se usa como baseline de pruebas de esta Parte III (Fase 30, HU-F30.4). |
| Epson TM-T88 (V/VI/VII) | USB / Ethernet | 80 mm | Compatible con el mismo set; la variante de red es útil si a futuro se comparte impresora entre puestos de caja. |
| Xprinter XP-58/80 series | USB | 58 mm / 80 mm | Muy común en el mercado colombiano de bajo costo; algunos clones tienen dialectos ESC/POS incompletos (fuentes/código de barras limitados) — validar contra el catálogo de perfiles antes de dar por soportado un lote nuevo del proveedor. |
| Star Micronics TSP100/TSP143 | USB / Ethernet | 80 mm | Requiere a veces su propio driver StarPRNT en vez de ESC/POS puro — tratar como caso especial, nunca asumir compatibilidad genérica sin probarla. |

**Reglas de negocio**:
- BR1. El instalador no bloquea la instalación si la impresora conectada no está en esta matriz — solo advierte y recomienda validar antes de la puesta en producción real.
- BR2. El fallback funcional (`window.print()` cuando la impresora térmica no responde) es responsabilidad de la Parte de frontend; el instalador únicamente documenta la matriz de hardware, no implementa la lógica de impresión.

**Pruebas**: la validación de esta matriz se hace mediante la prueba E2E de la Fase 30.4 (HU-F30.4) contra al menos un modelo Epson TM-T20 real como baseline; las demás marcas se validan en campo con el checklist de puesta en producción, no con automatización de CI (no es viable tener las 4 marcas físicas conectadas a un runner de CI).

**Tamaño estimado**: documentación (esta tabla) + 1 mensaje de advertencia en la TUI del instalador (20 LOC).

**Tareas atómicas**:
- `HU-F30.1-T1`: Mensaje de advertencia en el instalador para marcas fuera de la matriz de "ESC/POS estándar" conocida.
- `HU-F30.1-T2`: Matriz documentada como referencia normativa para el checklist de puesta en producción (Fase 30.4).

---

### HU-F30.2 — Entorno de desarrollo local sin instalar el producto completo

**Historia**: Como desarrollador del equipo, quiero levantar el backend y la base de datos localmente para trabajar en la app Electron sin pasar por el instalador de producción completo (Postgres nativo, servicios NSSM, MSI).

**Given/When/Then**:
- **Given** un desarrollador clona el repositorio y tiene Docker Desktop instalado,
  **When** ejecuta el flujo de desarrollo local,
  **Then** levanta el backend y Postgres con el `docker-compose.branch.yml` que ya existe en el repositorio (`infra/deploy/docker-compose.branch.yml` — el mismo que mirroa la topología de producción: `branch-db` con `pg_partman`, `api-sucursal`, `job-sync-sucursal`, con las variables `PARKOS_SUCURSAL_UUID`/`PARKOS_CLOUD_API_URL` requeridas explícitamente por el propio archivo), y corre la app Electron en modo desarrollo con HMR apuntando a ese backend local.
- **Given** el backend local está arriba,
  **When** el desarrollador arranca la app Electron,
  **Then** usa `npm run dev` dentro de `apps/web_sucursal` (con Vite HMR ya cubierto por la Parte de frontend), sin ningún paso de instalación de Postgres/NSSM/MSI de por medio.

**Comandos concretos**:

```bash
# Backend + Postgres (reutilizando infra/deploy/docker-compose.branch.yml del repo,
# el mismo compose que ya exige PARKOS_SUCURSAL_UUID y PARKOS_CLOUD_API_URL — ver
# el propio archivo, comentarios de cabecera).
export PARKOS_SUCURSAL_UUID=$(uuidgen)
export PARKOS_CLOUD_API_URL=http://localhost:8100   # nodo cloud local de desarrollo, si aplica
docker compose -f infra/deploy/docker-compose.branch.yml up -d

# Primer arranque: emparejar la sucursal de desarrollo con el cloud local (si aplica)
docker compose -f infra/deploy/docker-compose.branch.yml exec api-sucursal \
    parkos-core pair --cloud-url "$PARKOS_CLOUD_API_URL" --admin-jwt "$PARKOS_ADMIN_JWT"

# Frontend Electron en modo desarrollo (HMR)
cd apps/web_sucursal && npm run dev
```

**Reglas de negocio**:
- BR1. Este flujo es exclusivamente para desarrollo local — nunca se usa como sustituto del instalador para un despliegue real de cliente (no crea el rol `parkos_app` con las mismas garantías de mínimo privilegio que la Fase 22, dado que el compose de desarrollo prioriza velocidad de iteración sobre el checklist de seguridad completo del instalador; sí usa `parkos_app` en vez del superusuario, según el propio `docker-compose.branch.yml` ya verificado, pero no pasa por el *gate* de verificación de la HU-F24.4).
- BR2. La pieza de Docker Compose ya existe en el repositorio — el hueco real que esta HU cierra es la **documentación explícita** de este flujo desde la Parte de frontend (que antes no la referenciaba), no la infraestructura en sí.

**Debugging del proceso principal de Electron** (capacidad complementaria de este mismo entorno de desarrollo):

```json
// .vscode/launch.json — adjuntar el debugger de VS Code al proceso `main` de Electron
{
  "type": "node",
  "request": "launch",
  "name": "Electron: Main process",
  "runtimeExecutable": "${workspaceFolder}/apps/web_sucursal/node_modules/.bin/electron",
  "args": ["--inspect=9229", "."],
  "cwd": "${workspaceFolder}/apps/web_sucursal",
  "outputCapture": "std"
}
```

El proceso `renderer` se depura con las DevTools de Chromium ya estándar (`Ctrl+Shift+I` en modo desarrollo); lo que faltaba documentar era específicamente el proceso `main`, que corre como proceso Node y necesita esta configuración de `launch.json` para ser inspeccionable.

**Iteración rápida del instalador PowerShell sin VM completa**: para probar cambios destructivos del propio `parkos-installer.ps1` sin necesitar la VM `windows-2019` completa de CI en cada iteración, se recomienda **Windows Sandbox** (incluido gratis en Windows 10/11 Pro, se descarta al cerrar, arranca en segundos) como entorno de prueba desechable en la máquina del propio desarrollador, reservando la VM de GitHub Actions (HU-F30.4) para la validación final antes de mergear.

**Pruebas**: 1 prueba de humo documentada (no automatizada en CI, es un flujo de desarrollador): `docker compose -f infra/deploy/docker-compose.branch.yml up -d` seguido de `curl http://localhost:8000/health` debe responder `200` en menos de 60 segundos en una máquina de desarrollo limpia.

**Tamaño estimado**: 0 LOC de infraestructura nueva (reutiliza el compose existente) + documentación de flujo (esta sección) + 40 LOC de configuración de `launch.json`.

**Tareas atómicas**:
- `HU-F30.2-T1`: Documentar el flujo de `docker compose up` + `npm run dev` en la guía de desarrollo del repositorio, con referencia cruzada explícita desde la Parte de frontend (hoy ausente).
- `HU-F30.2-T2`: `.vscode/launch.json` para debugging del proceso `main` de Electron.
- `HU-F30.2-T3`: Recomendación documentada de Windows Sandbox para iteración del instalador.

---

### HU-F30.3 — Testing del instalador: Pester (unit + integración) y VM de Windows

**Historia**: Como responsable de calidad, quiero que cada función del instalador tenga cobertura automatizada, con mocks para las dependencias externas (`winget`, NSSM, `msiexec`) en pruebas rápidas, y validación end-to-end real en una VM Windows limpia para lo que no se puede mockear con confianza (instalación de Postgres real, `pg_partman`, recuperación ante fallos).

**Given/When/Then**:
- **Given** cualquier función nueva del módulo `parkos-installer.ps1` o del módulo PowerShell `parkos`,
  **When** se agrega al código,
  **Then** tiene al menos una prueba Pester unitaria con mocks de sus dependencias externas (`Mock winget`, `Mock -CommandName 'nssm'`, `Mock Invoke-WebRequest`), ejecutándose en segundos, sin requerir una VM.
- **Given** un cambio toca instalación de Postgres, `pg_partman`, recuperación ante fallos, o el ciclo completo de `Update-ParkosStack`,
  **When** se valida antes de mergear,
  **Then** corre además en una VM Windows real (provista por GitHub Actions, `windows-2019` o superior) donde se ejecuta el instalador de punta a punta en modo `-Unattended`, sin mocks, verificando el estado real del sistema al final (servicios `Running`, Postgres respondiendo, `parkos_app` con privilegios reales verificados).

**Cobertura consolidada por fase de esta Parte III**:

| Fase | Pruebas unitarias (Pester, mocks) | Pruebas de integración (VM real) |
|---|---|---|
| 21 (instalación limpia: pre-flight, EULA, rutas) | 14 | 1 (unattended en VM limpia) |
| 22 (Postgres, roles, pg_partman) | 20 | 3 (init, privilegios reales, crash recovery) |
| 23 (migraciones + seed) | 17 | 2 (conteo de tablas real, smoke CU-02 post-seed) |
| 24 (servicios NSSM, Electron, verificación) | 13 | 1 (instalación limpia completa) |
| 25 (Update-ParkosStack) | 17 | 2 (ciclo completo con migración real, rollback) |
| 26 (reparación, diagnóstico, desinstalación) | 21 | 2 (reparación tras servicio roto, purge total) |
| 27 (seguridad desktop) | 19 | 2 (ACL con usuario sin privilegios, gate de secreto JWT) |
| 28 (firma y distribución) | 4 | 2 (verificación de firma en CI, checklist de rollback en staging) |
| 29 (operación en campo) | 8 | 4 (crash recovery, backup real, worker de sync x2) |
| 30 (este apartado + CI/CD) | ver HU-F30.4 | ver HU-F30.4 |
| **Total (Fases 21-29)** | **133** | **19** |

**Reglas de negocio**:
- BR1. Ninguna prueba unitaria depende de que exista una VM o un Postgres real corriendo — todas mockean sus dependencias externas.
- BR2. Las pruebas de integración en VM son las únicas que pueden tardar minutos (no segundos); se ejecutan en el pipeline de CI antes de mergear a la rama principal, no en cada guardado local del desarrollador.

**Comandos concretos**:

```powershell
# Ejecutar solo pruebas unitarias (rápido, sin VM)
Invoke-Pester -Path .\Tests\Unit -Output Detailed

# Ejecutar pruebas de integración (requiere VM o entorno con Postgres real)
Invoke-Pester -Path .\Tests\Integration -Output Detailed -Tag 'RequiresVM'
```

**Pruebas**: esta HU *es* la definición de las pruebas de las Fases 21-29 (tabla de arriba); no tiene una prueba propia adicional más allá de un chequeo de cobertura mínima en CI (falla el build si el porcentaje de funciones sin prueba supera un umbral acordado).

**Tamaño estimado**: las 152 pruebas (133 + 19) ya están contabilizadas en el tamaño estimado de cada HU individual de las Fases 21-29; esta HU aporta la organización (`Tests\Unit\` vs `Tests\Integration\`) y el gate de cobertura mínima en CI (30 LOC).

**Tareas atómicas**:
- `HU-F30.3-T1`: Estructura de carpetas `Tests\Unit\` / `Tests\Integration\` con el tag `RequiresVM`.
- `HU-F30.3-T2`: Gate de cobertura mínima en CI.
- `HU-F30.3-T3`: Documentación de la tabla de cobertura consolidada (mantenida junto al código, no solo en este documento).

---

### HU-F30.4 — Testing de la app Electron empaquetada (`_electron.launch` + axe) y CI/CD de empaquetado y firma

**Historia**: Como responsable de calidad, quiero que el pipeline de CI no solo compile la app Electron, sino que la lance realmente empaquetada (el binario final, no el código fuente en modo desarrollo) y verifique accesibilidad y el contrato de seguridad de `BrowserWindow` antes de firmarla y publicarla.

**Given/When/Then**:
- **Given** un build de `web_sucursal` recién empaquetado por `electron-builder` (MSI/NSIS),
  **When** el pipeline de CI ejecuta la prueba E2E de la app,
  **Then** usa `playwright` con `_electron.launch({ executablePath: '<ruta del binario empaquetado>' })` — lanzando el **binario real**, no `npm run dev` — para probar el flujo de login y un ingreso de vehículo de punta a punta contra el `api-sucursal` local levantado para la prueba (`docker-compose.branch.yml`, reutilizado también aquí, mismo mecanismo que HU-F30.2).
- **Given** la app está corriendo en la prueba E2E,
  **When** el pipeline ejecuta el chequeo de accesibilidad,
  **Then** inyecta `axe-core` sobre cada pantalla visitada por el flujo E2E y falla el build si se detecta alguna violación seria (`serious`/`critical`), consistente con el checklist WCAG 2.1 AA del resto del proyecto.
- **Given** la app está corriendo en la prueba E2E,
  **When** el pipeline verifica el contrato de seguridad de Electron (HU-F27.4),
  **Then** consulta `webContents.getWebPreferences()` del `BrowserWindow` principal vía el propio Playwright/Electron y confirma `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` — un build que no cumpla esto falla el pipeline antes de llegar al paso de firma (HU-F28.1), nunca se firma un binario con el hardening de seguridad roto.
- **Given** el binario pasó las pruebas E2E, axe-core y el contrato de seguridad,
  **When** el pipeline continúa,
  **Then** lo firma (HU-F28.1), lo publica al canal único `latest` (HU-F28.2) y actualiza el manifiesto de checksums (`manifest.sha256.json`) que `Update-ParkosStack` (Fase 25) y `Repair-ParkosInstall` (Fase 26) consumen.

**Comandos concretos**:

```typescript
// tests/e2e/electron-installer.spec.ts
import { _electron as electron } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

test('flujo de login + ingreso vehicular sobre el binario empaquetado', async () => {
  const app = await electron.launch({
    executablePath: process.env.PARKOS_PACKAGED_BINARY_PATH!,  // el MSI/NSIS ya instalado, no npm run dev
  });
  const window = await app.firstWindow();

  const prefs = await window.evaluate(() => (window as any).__PARKOS_SECURITY_CONTRACT__);
  expect(prefs.contextIsolation).toBe(true);
  expect(prefs.nodeIntegration).toBe(false);
  expect(prefs.sandbox).toBe(true);

  await window.fill('#email', 'operador-e2e@parkos.local');
  await window.fill('#password', process.env.PARKOS_E2E_PASSWORD!);
  await window.click('#submit');
  await window.waitForSelector('[data-testid="ocupacion-strip"]');

  const results = await new AxeBuilder({ page: window as any }).analyze();
  expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact!))).toHaveLength(0);

  await window.fill('#placa', 'ABC123');
  await window.click('#confirmar-ingreso');
  await window.waitForSelector('text=Ingreso registrado');

  await app.close();
});
```

```yaml
# .github/workflows/parkos-installer-release.yml (extracto)
name: parkos-installer release
on:
  push:
    tags: ['v*']
jobs:
  build-and-test:
    runs-on: windows-2019
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - uses: microsoft/setup-powershell@v2
        with: { version: '7.4.x' }
      - run: pip install uv
      - name: Pruebas unitarias del instalador
        run: pwsh -Command "Invoke-Pester -Path ./infra/parkos-installer/Tests/Unit -Output Detailed -CI"
      - name: Build de artefactos (binarios standalone + MSI Electron)
        run: pwsh -Command "./infra/parkos-installer/build-installer.ps1"
      - name: E2E sobre binario empaquetado (Playwright + electron.launch + axe-core)
        run: |
          docker compose -f infra/deploy/docker-compose.branch.yml up -d
          npx playwright test tests/e2e/electron-installer.spec.ts
      - name: Verificación de firma (bloquea si algún binario no está firmado)
        run: pwsh -Command "Test-BinarySignature -Path .\dist\web_sucursal-*.msi"
      - name: Firma con Azure Trusted Signing
        run: pwsh -Command "./scripts/build-windows-prod.ps1"
        env:
          AZURE_TRUSTED_SIGNING_ENDPOINT: ${{ secrets.AZURE_TRUSTED_SIGNING_ENDPOINT }}
      - name: Publicar al canal único (latest)
        run: pwsh -Command "./scripts/publish-release.ps1 -Channel latest"

  e2e-unattended-vm:
    runs-on: windows-2019   # VM limpia, sin nada de Parkos preinstalado
    needs: build-and-test
    steps:
      - uses: actions/checkout@v4
      - run: pwsh -Command ".\parkos-installer.exe -Unattended -EulaAccepted -PostgresPort 5433"
      - run: pwsh -Command "Get-Service Parkos* | Should -Not -BeNullOrEmpty"
      - run: pwsh -Command "Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing | Should -BeSuccessful"
      - run: pwsh -Command "Test-PostInstallation -EnvFilePath 'C:\ProgramData\Parkos\secrets\.env'"   # HU-F24.4, incluido el gate de mínimo privilegio real
      - name: Prueba de rollback de versión (parte del checklist de release)
        run: pwsh -Command "Restore-ParkosVersion -Version (Get-PreviousReleaseVersion)"   # HU-F28.3
```

**Reglas de negocio**:
- BR1. `_electron.launch` apunta siempre al binario **empaquetado y firmado** (o firmado con certificado de staging en pipelines de prueba), nunca a `npm run dev` — el objetivo de este test es verificar el artefacto que realmente se distribuye, no el código fuente.
- BR2. El chequeo de `axe-core` y el de contrato de seguridad de Electron son *gates* bloqueantes de release, no advertencias — un build que falle cualquiera de los dos no llega al paso de firma.
- BR3. La prueba de rollback de versión (HU-F28.3) se ejecuta como parte del checklist de cada release en la VM de CI, no se deja para el primer incidente real en producción de un cliente.

**Pruebas**: la propia prueba E2E de esta HU (login + ingreso vehicular + axe + contrato de seguridad) cuenta como 1 prueba de integración adicional a la tabla de HU-F30.3, más 1 prueba de humo del rollback de versión en la VM de CI de cada release. Total de pruebas de integración de la Parte III: **21** (19 de la tabla de HU-F30.3 + 2 de esta HU).

**Tamaño estimado**: 150 LOC (spec de Playwright) + 120 LOC (workflow de GitHub Actions).

**Tareas atómicas**:
- `HU-F30.4-T1`: Spec de Playwright `electron-installer.spec.ts` (login + ingreso + axe + contrato de seguridad, sobre el binario empaquetado real).
- `HU-F30.4-T2`: Workflow `parkos-installer-release.yml` completo (build → pruebas unitarias → E2E → verificación de firma → firma → publicación canal único).
- `HU-F30.4-T3`: Job separado `e2e-unattended-vm` que instala de punta a punta en una VM limpia y ejecuta la verificación post-instalación completa (HU-F24.4) más la prueba de rollback de versión (HU-F28.3) como parte del checklist de cada release.

---

## Sección final — Riesgos y decisiones abiertas

### Riesgos (RIESGO-INST-01…16)

| ID | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| **RIESGO-INST-01** | **Licenciamiento/activación por sucursal — decisión de negocio pendiente.** Ningún documento de este proyecto (instalador, producción, ni los planes de frontend) define un mecanismo de licencia o activación. | N/A (decisión de producto) | Alto si el negocio requiere cortar el servicio a una sucursal morosa y no hay mecanismo para hacerlo | Ver recomendación explícita más abajo en esta misma fila: **Opción A (recomendada)**. |
| RIESGO-INST-02 | Un antivirus corporativo marca `nssm.exe` como *hacktool* o *PUA* (falso positivo común dado su uso legítimo pero poco conocido para envolver binarios como servicios). | Media | Media (bloquea la instalación o la desinstala solo) | Distribuir NSSM firmado dentro del payload firmado del instalador; documentar el proceso de excepción/*allowlist* para el equipo de TI del cliente si corresponde; reportar el falso positivo al proveedor de antivirus si se detecta en campo. |
| RIESGO-INST-03 | `winget` ausente en equipos Windows 10 21H2 sin actualizaciones de App Installer recientes. | Media | Media | El fallback a ZIP de EDB (HU-F22.2) ya cubre este caso; el payload incluye el ZIP para no depender de conectividad en el momento exacto del fallback. |
| RIESGO-INST-04 | El backend no implementa hoy *rate limiting* en `/auth/login`/`/auth/refresh` ni *lockout* tras intentos fallidos (verificado por lectura directa de `auth.py` — es un hecho actual, no una suposición). | Alta (mientras no se implemente) | Alto en un despliegue de producción real expuesto a fuerza bruta local | No es responsabilidad de este instalador implementarlo, pero **esta Parte III bloquea explícitamente** la recomendación de ir a producción con clientes reales sin que el backend cierre este hueco primero — se documenta como precondición dura del primer despliegue de producción (no del instalador en sí, que funciona igual con o sin esta protección). |
| RIESGO-INST-05 | El JWT se firma hoy con HS256 y un secreto compartido leído de archivo, con *fallback* a un secreto de desarrollo hardcodeado si el archivo no existe (RS256 + JWKS con rotación está planeado, no implementado). | Media (mientras no se implemente RS256) | Alto si el secreto de un cliente se filtrara (permitiría forjar tokens válidos para esa instancia) | El *gate* de instalación de la HU-F27.3 cierra la parte que el instalador controla (garantiza que el secreto real nunca es el de desarrollo); la migración a RS256 + JWKS sigue siendo trabajo de backend pendiente, fuera del alcance de esta parte. |
| RIESGO-INST-06 | `pg_partman` para Postgres 16 en Windows nativo depende de binarios de terceros precompilados que el equipo de instalador debe mantener actualizados junto con cada versión menor de Postgres. | Media | Media (un desajuste de versión entre el binario de `pg_partman` y la versión exacta de Postgres puede impedir `CREATE EXTENSION`) | Fijar la versión exacta de Postgres 16.x que el instalador soporta oficialmente en cada release, y recompilar/validar los binarios de `pg_partman` como parte del checklist de release (HU-F30.4) antes de cada actualización de versión menor de Postgres. |
| RIESGO-INST-07 | Espacio en disco agotado durante la instalación (Postgres + binarios + payload pueden superar 1 GB en total). | Baja | Media | El pre-flight de la Fase 21 valida ≥5 GB libres antes de empezar; el mismo chequeo se repite antes de `Update-ParkosStack` (Fase 25) para una actualización, dado que un backup adicional también consume espacio. |
| RIESGO-INST-08 | NSSM no es compatible de forma confiable con Windows Server Core (sin interfaz gráfica) si algún cliente corporativo grande decide correr el nodo de sucursal sobre ese SKU. | Baja | Media | Documentar Windows Server Core como no soportado en esta versión; si un cliente lo requiere, evaluar una imagen de contenedor Windows como alternativa (fuera del alcance de este documento). |
| RIESGO-INST-09 | `--force-cleanup` (Fase 30, modo unattended) o `Uninstall-Parkos -PurgeData` (Fase 26) ejecutados por error borran datos de producción de un cliente de forma irreversible. | Baja | Crítico | Confirmación explícita de doble paso ("CONFIRMAR" tecleado) en modo interactivo (HU-F26.4); en modo desatendido, exige el flag adicional `-UnattendedPurgeConfirmed` para que un solo flag copiado por error no dispare el borrado. |
| RIESGO-INST-10 | Un binario `api-sucursal.exe`/`job-sync-sucursal.exe` no arranca en el equipo del cliente por ausencia del Visual C++ Redistributable. | Media | Media | El empaquetado con `electron-builder`/`ps2exe` incluye el redistribuible necesario en el payload; el pre-flight de la Fase 21 podría ampliarse en una futura revisión para detectarlo explícitamente antes de instalar (ver ABIERTO-102). |
| RIESGO-INST-11 | Incompatibilidad de versión entre el auto-update independiente de Electron (canal `latest`) y la versión del backend que el instalador gestiona por separado, si ambos ciclos se desalinean en un despliegue real sin que nadie lo note. | Media | Alto (una ventana real donde el renderer llama a un `api-sucursal` de una versión incompatible, en un despliegue sin supervisión) | DEC-INST-16 (Sección 0.2): `web_sucursal` valida `api_contract_version` en cada arranque vía `GET /health` y bloquea la operación con un mensaje claro si no es compatible, en vez de fallar de forma silenciosa a mitad de una transacción de caja. |
| RIESGO-INST-12 | La restauración de un backup (`pg_restore`) nunca se ha probado en una ejecución real de este instalador fuera de la prueba automatizada de CI — un backup que "se crea bien" pero "no restaura bien" solo se descubre en el peor momento posible (un desastre real). | Media | Crítico | Agregar una prueba periódica (no solo en CI de release, sino recomendada como parte del checklist trimestral de soporte) que restaure un backup real de una sucursal representativa en un entorno aislado y verifique la integridad de los datos restaurados, no solo que el comando `pg_restore` termine con exit `0`. |
| RIESGO-INST-13 | El `sync_queue_lw_buffer` no tiene, hoy, un umbral definido de "dependencia nunca resuelta" (a diferencia de las 24 horas de `sync_queue`) — una dependencia rota podría acumular filas indefinidamente sin que nadie lo note. | Baja (mientras el volumen sea bajo) | Media a largo plazo (crecimiento no acotado de una tabla particionada) | Ver ABIERTO-105 — requiere una decisión de backend, fuera del alcance de esta Parte III cerrarla, pero trazada explícitamente para que no se pierda. |
| RIESGO-INST-14 | El certificado de Azure Trusted Signing expira sin que nadie lo note, bloqueando un release de producción en el peor momento (por ejemplo, tras detectar un bug crítico que requiere un parche urgente). | Baja | Alto (bloquea cualquier release nuevo hasta renovar) | Calendario de renovación/monitoreo explícito (HU-F28.1, checklist de adquisición) con alerta 30 días antes del vencimiento. |
| RIESGO-INST-15 | Un cliente con conectividad extremadamente pobre (zona rural, solo datos móviles intermitentes) hace que el heartbeat de la HU-F29.3 tarde en reflejar una caída real del servicio, retrasando la detección de soporte. | Media | Media | El umbral de "sucursal silenciosa" (recomendado en 15 minutos sin contacto, HU-F29.3) es deliberadamente conservador para tolerar conectividad intermitente sin generar falsos positivos; ajustar ese umbral por perfil de conectividad del cliente es una mejora futura, no un defecto de diseño de esta versión. |
| RIESGO-INST-16 | La matriz de impresoras térmicas (HU-F30.1) no está validada en CI para las 3 marcas no-Epson (Xprinter, Star) — solo se prueba automáticamente contra un Epson TM-T20 real. | Media | Baja a Media (un cliente con una marca no probada podría descubrir incompatibilidades solo en campo) | El checklist de puesta en producción de cada cliente nuevo incluye una prueba de impresión real con el hardware específico del cliente antes del primer día de operación, independientemente de lo que diga la matriz de referencia. |

**Recomendación explícita sobre RIESGO-INST-01 (licenciamiento/activación)**: se presentan dos alternativas razonadas, ya evaluadas, para que el equipo de producto decida con criterio informado, en vez de dejar el tema completamente sin trazar:

- **Opción A — Sin licenciamiento técnico explícito (recomendada por esta Parte III)**: cada sucursal necesita `PARKOS_SUCURSAL_UUID` y el *pairing* con el nodo cloud (Fase 24, `Get-ParkosPairingToken`) para sincronizar — esto ya es un requisito funcional, no de licencia. Si el nodo cloud simplemente deja de aceptar sincronización de una sucursal cuyo contrato terminó (revocando el JWT de sincronización vía `Revoke-ParkosPairingToken` o el mecanismo equivalente del lado cloud), no hace falta un mecanismo de licencia adicional: el control ya existe como efecto colateral de la arquitectura de sincronización que el producto necesita de todas formas. Es la opción más simple, la que menos superficie de implementación nueva agrega, y la recomendación de esta Parte III **si el negocio tolera** que, en el peor caso, una sucursal offline siga operando localmente sin sincronizar hasta que se reactive el pairing — comportamiento coherente con el carácter *offline-first* del producto, no una debilidad accidental.
- **Opción B — Archivo de licencia firmado por sucursal**: si el negocio requiere que la aplicación deje de **operar** (no solo de sincronizar) cuando vence un contrato, la alternativa razonada es un archivo de configuración firmado (JSON + firma con clave asimétrica: clave privada en manos del proveedor, clave pública embebida en el binario), verificable **offline**, sin depender de conectividad — coherente con el carácter *offline-capable* del producto. Se recomienda evitar explícitamente cualquier esquema de activación en línea obligatoria, que contradiría ese requisito de diseño y dejaría a un cliente con conectividad intermitente legítima sin poder operar por un problema de licenciamiento, no de pago real.

Esta Parte III dejó la pregunta trazada como decisión abierta explícita (no omitida silenciosamente) — ver ABIERTO-100.

### Decisiones abiertas (ABIERTO-100…109)

| ID | Decisión pendiente | Contexto |
|---|---|---|
| ABIERTO-100 | Licenciamiento/activación por sucursal: ¿Opción A (de facto, vía pairing) u Opción B (archivo firmado offline)? | Ver RIESGO-INST-01 y la recomendación explícita de arriba (esta Parte III recomienda A). |
| ABIERTO-101 | ¿El instalador debe soportar una instalación multi-sucursal en el mismo equipo físico (dos instancias de Postgres/servicios en puertos distintos), o cada equipo siempre corresponde a exactamente una sucursal? | Ningún documento del proyecto contempla este escenario; la detección de puertos de la Fase 22 (HU-F22.1) ya resuelve la coexistencia con *otro* Postgres, pero no está pensada para correr dos instalaciones completas de Parkos en el mismo equipo. |
| ABIERTO-102 | ¿El pre-flight de la Fase 21 debe verificar explícitamente la presencia del Visual C++ Redistributable antes de instalar, en vez de depender solo de que el empaquetado lo incluya? | Ver RIESGO-INST-10; hoy se mitiga empaquetando el redistribuible, pero una verificación explícita de pre-flight daría un mensaje de error más claro si algo falla de todas formas. |
| ABIERTO-103 | ¿Debe existir una política formal de "ventana de parche" para actualizar la versión de Electron ante CVEs de Chromium (por ejemplo, aplicar el parche de seguridad más reciente dentro de N días hábiles de su publicación, verificado por Dependabot o `npm audit` en CI, con una release fuera de ciclo si el CVE es crítico)? | Detectado por la auditoría de completitud del instalador como un hueco de higiene de seguridad continua; no bloquea el instalador en sí, pero afecta directamente el canal único de distribución (Fase 28) si se decide una cadencia de parches más agresiva que el ciclo de release normal. |
| ABIERTO-104 | El texto original de CU-07 describe el ciclo de sincronización como "cada 60 segundos por defecto", mientras el valor real configurado en el código (`runtime/env.py`, `PARKOS_SYNC_POLL_INTERVAL_S=10`) y en `docker-compose.branch.yml` es de 10 segundos. ¿Se actualiza el texto de CU-07 a 10 s, o se ajusta el default de código a 60 s? | Ver HU-F29.4; esta Parte III usa el valor real de código (10 s) como autoridad para el instalador, por ser el que efectivamente se despliega, pero deja la reconciliación formal del texto de CU-07 como decisión pendiente de quien mantiene ese documento. |
| ABIERTO-105 | `sync_queue_lw_buffer` no tiene un umbral definido de "dependencia nunca resuelta" (a diferencia de las 24 horas de `sync_queue`, CU-07 BR3). ¿Cuál debería ser ese umbral, y qué alerta debería dispararse? | Ver HU-F29.5 y RIESGO-INST-13; es un hueco real del diseño del motor de sincronización, no de esta Parte III, pero ninguna auditoría previa lo había identificado — se deja trazado aquí para que el equipo de backend lo resuelva con la misma prioridad que el resto del contrato de CU-07. |
| ABIERTO-106 | ¿La cuenta de servicio `svc-parkos` (Fase 27) debe rotarse periódicamente (contraseña) como parte de un ciclo de higiene de credenciales, o se considera aceptable que viva sin rotación mientras el equipo esté en producción? | No definido en esta Parte III; se documenta la creación inicial (HU-F27.1) pero no una política de rotación continua. |
| ABIERTO-107 | ¿Debe el instalador soportar una ruta de recuperación ante desastres que no dependa de tener acceso físico al mismo equipo (por ejemplo, restaurar un backup de una sucursal en un equipo de reemplazo distinto, con un `PARKOS_SUCURSAL_UUID` idéntico)? | La Fase 29 cubre backup/restauración en el mismo equipo (o uno equivalente preparado manualmente); un procedimiento formal de "reemplazo de hardware con continuidad de sucursal" no está documentado como flujo propio en esta versión. |
| ABIERTO-108 | ¿El umbral de "sucursal silenciosa" (15 minutos recomendado en la HU-F29.3) debe ser configurable por sucursal según su perfil de conectividad conocido, o un valor único para todas? | Ver RIESGO-INST-15; esta Parte III no define un mecanismo de configuración por sucursal para este umbral, solo el valor recomendado por defecto. |
| ABIERTO-109 | ¿Debe el checklist de release (HU-F30.4) incluir validación automatizada contra las 3 marcas de impresora no-Epson (Xprinter, Star), o se mantiene como validación manual de campo por cliente? | Ver RIESGO-INST-16; hoy la automatización de CI solo cubre un modelo Epson TM-T20 real como baseline. |

---

**Resumen de cobertura de esta Parte III**: 10 fases (21-30), 33 historias de usuario (`HU-F21.1`…`HU-F30.4`), 124 tareas atómicas, 152 pruebas automatizadas documentadas por fase/HU (133 unitarias Pester + 19 de integración VM, más 2 pruebas de integración de la Fase 30.4 no contadas en esa tabla = 21 pruebas de integración totales), 16 riesgos (`RIESGO-INST-01`…`16`) y 10 decisiones abiertas (`ABIERTO-100`…`109`). Las tres correcciones de mayor impacto aplicadas frente a la documentación previa de este mismo proyecto: (1) el instalador ahora crea y usa el rol `parkos_app` de mínimo privilegio para toda conexión de runtime, nunca el superusuario `parkos` (Sección 0.3, Fase 22, HU-F24.4); (2) el modelo de sesión de producción se corrigió de una cookie `httpOnly` inexistente a JWT Bearer real, con el almacenamiento correcto para una app de escritorio Electron (Sección 0.4); (3) el canal de actualización quedó fijado a uno solo (`latest`, DEC-INST-06) y la regla de IVA de producción que contradecía CU-02 BR5 (fallback a 0%) fue descartada explícitamente en favor del rechazo por error de configuración que el caso de uso original exige.

## PARTE IV — AJUSTES DE BACKEND TRANSVERSALES

### 0. Alcance de esta Parte

Las Partes I, II y III ya resuelven, cada una dentro de su propio alcance, los ajustes de backend que necesitan para construir su frontend o su instalador. Esta Parte IV **no repite ese trabajo**. Es un catálogo consolidado, con ID `GAP-BE-01`…`09`, de todo ajuste de backend (`parkos_core`) que cumple al menos una de estas dos condiciones:

- (a) es prerrequisito de **más de una** de las 3 partes (una sola migración, un solo fix, consumido por HU de fases distintas), o
- (b) es una corrección de bug/hueco real del backend detectado por las auditorías de fidelidad ER/backend, de consistencia de casos de uso y de completitud del instalador que precedieron a este plan, que dos o más partes resuelven cada una a su manera — o que **ninguna** resuelve todavía, pese a afectar a varias.

El valor de este catálogo no es solo consolidar: al cruzar las 3 partes ya terminadas se encontraron **3 inconsistencias nuevas** que ninguna auditoría ni ninguna parte individual había detectado (porque cada una se escribió sin ver el contenido final de las otras dos): la duplicación de un endpoint de backend entre Parte I y Parte II (§1.3), el desacuerdo de nombre/ruta de `config_caja` entre las 3 partes (§1.8) y un permiso mal asignado en dos routers de caja (§1.5). Un equipo de backend debe leer este catálogo **antes** de tocar `parkos_core`, para no resolver el mismo problema tres veces ni dejar una migración a medio camino.

**Resumen (severidad = bloquea backlog de más de una parte si no se resuelve primero):**

| ID | Descripción corta | Estado | Bloquea |
|---|---|---|---|
| GAP-BE-01 | Login por `cedula` vs `email` | Cerrado en las 3 partes (backend ya era correcto) | — (histórico) |
| GAP-BE-02 | Bug `router_factory.py` (orden por `vigente_desde` sin `hasattr`) | Parcialmente cerrado por HU-F1.1 (Parte 1) | Parte 1 (HU-F11.2), Parte 2 (Fase 18) |
| GAP-BE-03 | 7 códigos de permiso de `empresa.py`/`configuracion.py` sin sembrar | Cerrado por HU-F13.1 (Parte 2) | Parte 2 (Fases 14-15) |
| GAP-BE-04 | 4 códigos de permiso de `workflows.py` sin sembrar | Cerrado por HU-F13.1 (Parte 2, reconciliación) | Parte 2 (Fase 20) |
| GAP-BE-05 | Permiso `emitir_factura` mal asignado en `caja.py`/`caja_sesion.py` | **Abierto — no cerrado por ninguna parte** | Parte 1 (F1.13), Parte 2 (F18.1) |
| GAP-BE-06 | Rol `parkos_app` / migración `0021` (mínimo privilegio) | Ya existe en backend; instalador debe crearlo | Parte 3 (HU-F22.3) |
| GAP-BE-07 | Conteo "54 tablas" (real: 51) | Corregido en este documento | Front-matter y anexos |
| GAP-BE-08 | `config_caja`/`configuracion_caja`: tabla fantasma + desacuerdo de nombre/ruta entre partes | **Abierto — requiere reconciliación antes de codear el instalador** | Parte 2 (F13.3/F15.5), Parte 3 (F23.3) |
| GAP-BE-09 | Contrato del motor de tarifa/cotizar/salida | Cerrado — contrato consolidado abajo | Parte 1 (F1.7/F1.8/F1.9/F1.10) |

---

### 1.1 GAP-BE-01 — Login por `cedula` vs `email`

**Descripción.** Los 7 documentos fuente originales que precedieron a este plan diseñaban el formulario de login alrededor de `cedula`. El backend real (`api/v1/auth.py:45-59`, `schemas/auth.py:244-248 LoginRequest`) siempre autenticó exclusivamente por `email: EmailStr` + `password`.

**Estado real verificado.** El backend nunca tuvo el bug — el bug estaba en los documentos de planificación, no en `parkos_core`. Confirmado de forma independiente en esta integración (lectura directa de `schemas/auth.py:244-248`): no existe campo `cedula` en `LoginRequest`.

**Corrección exacta.** Ninguna en backend. Ya aplicada en el frontend: DEC-SUC-02 (Parte 1) y DEC-ADM-04 (Parte 2) fijan login por `email`+`password`. Se documenta aquí únicamente como registro histórico, para que nadie reintroduzca `cedula` en una fase futura no cubierta por este plan (p. ej. una Parte V).

**HU que dependen de él:** HU-F3.1 (Parte 1), HU-F13.6 (Parte 2). Ninguna acción pendiente.

---

### 1.2 GAP-BE-02 — Bug de `router_factory.py`: orden por `vigente_desde` sin `hasattr`

**Descripción.** `list_endpoint` (la función genérica que arma cualquier router vía `make_router`) protege el filtro `WHERE vigente_hasta IS NULL` con `if hasattr(model_cls, "vigente_hasta")`, pero **no** protege el `ORDER BY` de la misma forma.

**Estado real verificado (línea exacta).** `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:105`: `stmt = stmt.order_by(model_cls.vigente_desde.desc(), model_cls.uuid.asc())` se ejecuta siempre, sin guarda, mientras que la línea 104 (el `.where()`) sí está protegida por el `hasattr` de la línea 103.

**Impacto verificado por modelo** (quién tiene `vigente_desde` y quién no, confirmado leyendo los archivos de modelo reales):

| Modelo | Declara `vigente_desde` | Endpoint afectado | ¿Lo cierra HU-F1.1? |
|---|---|---|---|
| `Alerta`, `Anulaciones`, `Reclamos`, `ReimpresionTicket` (`models/L_W/`) | Sí (re-declarado explícitamente) | `GET /workflows/{alerta,anulaciones,reclamos,reimpresion-ticket}` | Sí — no están rotos, pero HU-F1.1 los usa como caso de prueba de la corrección |
| `Caja`, `Arqueo` (`models/A/`, extienden `AppendOnlyBase`) | No | `GET /caja/caja`, `GET /caja/arqueo` | **No mencionado por Parte 1** |
| `Sesion` (`models/L_S/`) | No | `GET /caja-sesion/sesion` | **No mencionado por Parte 1** |

**Corrección exacta.** El fix que describe HU-F1.1 (Parte 1, §8.1 de su digest) ya es genérico por diseño: condicionar la línea 105 al mismo `hasattr(model_cls, "vigente_desde")`, con fallback a `getattr(model_cls, "timestamp_evento", model_cls.created_at)` desc + `uuid` asc, extraído a una función `_order_key(model_cls)` reutilizada en listado y en paginación por cursor. **Al implementarse así, la corrección alcanza automáticamente** a `Caja`/`Arqueo`/`Sesion`, aunque Parte 1 solo declare como beneficiarios explícitos a los 4 endpoints de `workflows.py`.

**Nota de coordinación (el hallazgo nuevo de esta integración):** quien implemente HU-F1.1 debe verificar con una prueba explícita que `GET /caja/caja`, `GET /caja/arqueo` y `GET /caja-sesion/sesion` también dejan de fallar — Parte 1 no lo prueba porque no los consume directamente, pero Parte 2 sí los necesita sanos: HU-F18.1/HU-F18.2 (Fase 18, listado y filtros de arqueos) dependen transitivamente de este mismo fix. Si HU-F1.1 se implementa de forma más estrecha (hardcodeada a los 4 modelos `[L-W]`), Parte 2 se bloquea sin que ninguna de las dos partes lo haya anticipado.

**HU que dependen de él:** HU-F1.1 (cierra, Parte 1) · HU-F11.2 (consume `GET /workflows/alerta`, Parte 1) · HU-F18.1, HU-F18.2 (consumen `GET /caja/arqueo`, Parte 2, dependencia transitiva no declarada por ninguna de las dos partes).

---

### 1.3 GAP-BE-03 y GAP-BE-04 — Códigos de permiso nunca sembrados (consolidado en una sola migración)

**Descripción.** Dos auditorías y las 3 partes coinciden: hay 11 códigos de permiso que los routers exigen vía `permission_required=`/`require_permission()` pero que no existen en ninguna fila de `prod.permisos`. El efecto es idéntico en los 11 casos: `require_permission()` hace `JOIN permisos_usuario → permisos WHERE permiso = :codigo`; si el código no existe, el resultado es siempre vacío → **403 permanente para cualquier actor**, sin importar qué permisos tenga.

**Los 7 de `empresa.py`/`configuracion.py`** (GAP-BE-03, requeridos por escritura, las lecturas si funcionan):

| Código | Router:línea | Endpoint que bloquea | Consumido por |
|---|---|---|---|
| `config_empresa` | `empresa.py:60` | `PUT /empresa/empresa` | HU-F15.2 (Parte 2) |
| `admin_documentos` | `empresa.py:62` | `POST/PUT /empresa/documentos` | HU-F15.4 (Parte 2) |
| `admin_resolucion_facturacion` | `empresa.py:63` | `POST/PUT /empresa/resolucion-facturacion` | HU-F15.3 (Parte 2) |
| `config_tarifas` | `empresa.py:64` | `POST/PUT /empresa/tarifas-sucursal` | HU-F14.3 (Parte 2) |
| `config_cupos` | `empresa.py:65` | `POST/PUT /empresa/cantidad-vehiculos-sucursal` | HU-F14.4 (Parte 2) |
| `config_tolerancias` | `configuracion.py:39` | `POST/PUT /configuracion/configuracion-tolerancias` | HU-F15.5 (Parte 2) |
| `config_seguridad` | `configuracion.py:40` | `POST/PUT /configuracion/configuracion-seguridad` | HU-F15.5 (Parte 2, vía `.../efectiva`) |

**Los 4 de `workflows.py:74-77`** (GAP-BE-04) — con matiz importante: **3 de los 4 ya tienen un equivalente semántico sembrado**, así que la corrección correcta no es sembrar 4 códigos nuevos sino **reconciliar nombres**:

| Código pedido por `workflows.py` | ¿Existe ya un equivalente sembrado? | Corrección |
|---|---|---|
| `anular_ingreso_salida` | Sí — `ejecutar_anulacion` (más fino, ya distingue aprobar/ejecutar) | Reconciliar: usar `ejecutar_anulacion` |
| `registrar_alerta` | Sí — `descartar_alerta` | Reconciliar: usar `descartar_alerta` |
| `emitir_reimpresion` | Sí — `reimprimir_ticket` | Reconciliar: usar `reimprimir_ticket` |
| `registrar_reclamo` | No — sin equivalente | Sembrar como código genuinamente nuevo |

**Corrección exacta (consolidada en una sola migración).** HU-F13.1 (Parte 2, Fase 13) ya especifica exactamente esto: una migración nueva (`0022_seed_permisos_empresa_config.py` o el siguiente número libre en `migrations/versions/` al momento de implementar) que siembra 9 códigos con el patrón `INSERT ... ON CONFLICT (permiso, vigente_desde) DO NOTHING` ya usado en `0002_seed_permisos_canonicos.py`: los 7 de la tabla de arriba + `config_caja` (ver GAP-BE-08) + `registrar_reclamo`; y una reconciliación de configuración (no de esquema) en `_ROUTER_CONFIG` de `workflows.py` para los otros 3.

**Secuenciación obligatoria (RIESGO-ADM-01/02 de Parte 2):** esta migración debe desplegarse en cloud **antes** de mergear cualquier PR de frontend de Parte 2 que dependa de ella (Fases 14 y 15 completas). Si se invierte el orden, los 403 resultantes son indistinguibles de un bug de frontend nuevo.

**HU que dependen de él:** HU-F13.1 (cierra, Parte 2) · HU-F14.3, HU-F14.4, HU-F15.2, HU-F15.3, HU-F15.4, HU-F15.5 (Parte 2, todas bloqueadas hasta que la migración exista) · HU-F20.3 (Parte 2, Fase 20, usa `registrar_reclamo`).

---

### 1.4 GAP-BE-05 — Permiso `emitir_factura` mal asignado en `caja.py`/`caja_sesion.py` (abierto, sin dueño)

**Descripción (hallazgo nuevo de esta integración, no reportado por ninguna auditoría previa).** `api/v1/caja.py:53` y `api/v1/caja_sesion.py:204` protegen los routers de solo lectura de `caja`, `arqueo` y `sesion` con `permission_required="emitir_factura"` — un código semánticamente ajeno (facturación, no caja). El código sí está sembrado (no produce 403 permanente como GAP-BE-03/04), pero es incorrecto: un actor con permiso de facturación (y ninguno de caja) puede leer arqueos/sesiones; un actor con `realizar_arqueo`/`abrir_cerrar_caja` (ya sembrados desde `0001`, pensados exactamente para esto) no tiene acceso si no tiene además `emitir_factura`.

**Estado real.** Confirmado por lectura directa de ambos archivos en esta integración. **No aparece mencionado en ningún lugar de las Partes 1, 2 o 3** — ninguna HU lo toca, ni como corrección ni como riesgo. Es el único de los 9 gaps de este catálogo sin ninguna HU que lo cierre.

**Corrección exacta.** Cambiar `permission_required="emitir_factura"` a `permission_required="realizar_arqueo"` en `caja.py:53` y en la porción de `caja_sesion.py:204` que protege `GET /caja/arqueo`/`GET /caja/caja`; usar `abrir_cerrar_caja` para el mount de solo lectura de `sesion`. Es una corrección de una línea por archivo, sin migración.

**Recomendación de asignación.** Bundlear esta corrección en HU-F1.13 (Parte 1, que ya toca `caja.py` al construir `POST /caja/arqueo`) o en HU-F18.1 (Parte 2, que ya toca los filtros de `GET /caja/arqueo`) — cualquiera de las dos evita abrir una HU nueva solo para esto. Se recomienda HU-F1.13 por cercanía de archivo.

**HU que dependen de él:** ninguna lo cierra hoy — se asigna como tarea adicional a HU-F1.13 (Parte 1) o HU-F18.1 (Parte 2) al implementar.

---

### 1.5 GAP-BE-06 — Rol `parkos_app` y migración `0021` (mínimo privilegio)

**Descripción.** Hasta la migración `0021`, el único rol de `LOGIN` en Postgres era el superusuario `parkos`, así que cualquier `REVOKE`/`GRANT` previo (`rol_app`, `NOLOGIN` desde `0001`) era inerte — la aplicación se conectaba siempre con privilegios totales.

**Estado real verificado.** `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py` (depende de `0020_deterministic_tipo_persona_empresa_uuids`), commit `5edb317` de esta misma rama ("la app deja de conectarse como superusuario, ahora usa un rol de mínimo privilegio real"). Crea `CREATE ROLE parkos_app LOGIN INHERIT IN ROLE rol_app`, aplica `REVOKE`/`GRANT` columna-por-columna sobre 36 tablas (26 `[V]`, `login`/`sesion`, 8 `[L-W]`/`[L-E]`, `envio_dian` con `UPDATE` acotado a `payload`, `alert_types` de solo lectura); 11 tablas `[A]` con trigger `fn_<tabla>_inmutable()` desde `0001` no se tocan (ya protegidas). `docker-compose.branch.yml:98-99,144-145` ya usa `${PARKOS_APP_DB_USER:-parkos_app}:${PARKOS_APP_DB_PASSWORD:-parkos_app_dev}` para runtime, nunca el superusuario.

**Relación con el instalador (Parte 3).** El backend ya tiene el rol; lo que falta es que un despliegue **sin Docker** también lo cree y lo use. HU-F22.3 (Parte 3, Fase 22) ya lo cubre explícitamente: crea el superusuario de migración (`parkos`) y el rol `parkos_app` de runtime por separado (DEC-INST-04/DEC-INST-10: dos identidades de conexión nunca intercambiables), y HU-F24.4 (Parte 3, verificación post-instalación) prueba en vivo que `parkos_app` falla al intentar `CREATE ROLE`/`DROP TABLE` (no solo lee el nombre de usuario configurado).

**Corrección exacta.** Ninguna en el backend (ya está completo y correcto). El trabajo pendiente es enteramente del instalador y ya está planificado en Parte 3.

**HU que dependen de él:** HU-F22.3, HU-F24.4 (Parte 3).

---

### 1.6 GAP-BE-07 — Conteo de tablas del ER: "54" es incorrecto, son 51

**Descripción.** Varios documentos de la planificación original repitieron "54 tablas". El conteo real, verificado línea por línea sobre `modelo_datos_er.mmd` de forma independiente en tres pasadas distintas (la auditoría de fidelidad ER/backend que precedió a este plan, el digest cruzado de esta integración, y el propio front-matter de este documento), es **51**.

**Hallazgo adicional de esta integración:** el mismo error de conteo no se quedó en los documentos de planificación — aparece también en un comentario de código real: el docstring de la migración `0021_least_privilege_and_immutability_contract.py` (línea 131) dice *"Exhaustive live SQL testing of all 54 tables individually..."*. No afecta ningún dato ejecutable (es un comentario), pero confirma que el error es más viejo y estaba más extendido de lo que las auditorías de los 7 documentos originales habían cubierto.

**Corrección exacta.** Este plan maestro fija **51** como el único número correcto en todo el documento (front-matter, Parte IV, anexos). Se recomienda, como higiene menor y no bloqueante, corregir el comentario de la migración `0021` en un futuro touch de ese archivo (nunca solo por esto).

**Nota de origen del error:** el corpus original de 19 archivos de casos de uso (vía `FLUJO_CUS_ER.md`) trae su **propio** anexo de "50 tablas" — un tercer número, que no es el mismo error que "54": ese anexo incluye `config_caja` (que el `.mmd` canónico actual no tiene, ver GAP-BE-08) pero no incluye `alert_types` ni `sync_queue_lw_buffer` (que el `.mmd` canónico actual sí tiene, por ser adiciones posteriores al ER que ese corpus nunca vio). Los tres números (54, 51, 50) tienen así tres orígenes distintos; solo 51 es correcto hoy.

**HU que dependen de él:** ninguna directamente — es una corrección de higiene documental para todo el plan maestro.

---

### 1.7 GAP-BE-08 — `config_caja`/`configuracion_caja`: tabla fantasma y desacuerdo de nombre/ruta entre las 3 partes

**Descripción.** Este es el gap más delicado del catálogo porque **las 3 partes lo tocan de forma distinta, sin haberse leído entre sí**, y el resultado — leído en conjunto por primera vez en esta integración — es contradictorio.

**Punto de partida.** `config_caja` (base de caja, redondeo, denominaciones permitidas, umbral de alerta) aparece en el corpus original de 19 CU (CU-10, CU-11, CU-13) y en `FLUJO_CUS_ER.md`, pero **no existe** en el ER canónico actual (`modelo_datos_er.mmd`, 51 tablas) ni en el backend real (`Glob "**/config_caja*"` sobre todo `backend/`: 0 resultados, confirmado de forma independiente en esta integración). Es una tabla de una versión anterior del ER que el `.mmd` canónico nunca materializó.

**Lo que decide cada parte, de forma independiente:**

| Parte | Decisión | Detalle |
|---|---|---|
| **Parte 1 (Sucursal)** | No existe ninguna tabla de "base de caja" separada. La base real del turno es siempre `sesion.valor_inicial_efectivo`/`valor_inicial_datafono` (Adaptación A-10). | Ninguna HU de Parte 1 lee ni escribe `config_caja`/`configuracion_caja`. |
| **Parte 2 (Admin)** | Crea una tabla **nueva** `configuracion_caja` (DEC-ADM-12, HU-F13.3): `base_inicial_sugerida`, `redondeo`, `denominaciones_permitidas`. Endpoint real: `GET/POST/PUT /api/v1/configuracion/configuracion-caja` (+ `.../efectiva`). | El nombre de columna es explícitamente "sugerida", no autoritativa — ver reconciliación abajo. |
| **Parte 3 (Instalador)** | HU-F23.3 siembra un valor inicial asumiendo que ya existe un endpoint `GET/POST /api/v1/config-caja` (sin "configuracion", sin el subpath `/configuracion/`). | Este path **no coincide** con el que Parte 2 realmente construye. |

**Reconciliación (la que ninguna de las 3 partes hizo, porque ninguna vio el contenido final de las otras dos):**

1. **Nombre y ruta autoritativos:** la tabla es `configuracion_caja` y el endpoint real es `GET/POST/PUT /api/v1/configuracion/configuracion-caja` (+ `.../efectiva`), tal como lo construye Parte 2 (HU-F13.3). El instalador (HU-F23.3, Parte 3) debe sembrar contra **ese** path, no contra `/api/v1/config-caja` — es un ajuste de una línea en el script del instalador, pero debe hacerse antes de codificarlo, no descubrirse en integración.
2. **`base_inicial_sugerida` no contradice a Parte 1:** no es un reemplazo de `sesion.valor_inicial_efectivo` — es un valor por defecto que la pantalla de apertura de turno (HU-F3.3, Parte 1) debería precargar como sugerencia editable al abrir un turno nuevo. Parte 1 no consume hoy este campo; se deja como tarea explícita a agregar a HU-F3.3 cuando se implemente, para que `configuracion_caja` no quede como configuración muerta.
3. **`redondeo` y `denominaciones_permitidas` tampoco los consume Parte 1** hoy (ni HU-F10.1, arqueo parcial, ni el flujo de pago de HU-F8.1 los mencionan). Es una decisión de producto pendiente: si estos campos deben aplicarse en el cálculo de vueltos (CU-04) o en el conteo de arqueo (CU-10), Parte 1 necesita una HU nueva que los consuma; si no, se documentan como configuración informativa sin efecto operativo todavía (ver `ABIERTO-200` en Anexo E, ID nuevo asignado en esta integración — ninguna de las 3 partes lo había abierto).
4. **El "umbral de alerta" de CU-13 no vive en `configuracion_caja`:** reutiliza `configuracion_tolerancias.tolerancia_efectivo`/`tolerancia_datafono`, ya real (aclarado correctamente por DEC-ADM-12, sin conflicto).
5. **Permiso:** el código atómico `config_caja` (sembrado por la migración de GAP-BE-03/04) es correcto y consistente con la convención `config_<recurso>` del resto del catálogo, aunque el nombre de tabla sea `configuracion_caja` — no es un error, es la misma convención que ya usan `config_tarifas`→`tarifas_sucursal` y `config_cupos`→`cantidad_vehiculos_sucursal`.

**Corrección exacta.** (a) Parte 3 ajusta HU-F23.3 al path real `/api/v1/configuracion/configuracion-caja` antes de implementar el seed del instalador. (b) Se abre explícitamente la decisión de producto del punto 3 como ítem nuevo en Anexo E.

**HU que dependen de él:** HU-F13.3, HU-F15.5 (Parte 2, definen la tabla real) · HU-F23.3 (Parte 3, debe corregir el path antes de codear) · HU-F3.3, HU-F10.1 (Parte 1, candidatas a consumir los campos si el negocio lo decide).

---

### 1.8 GAP-BE-09 — Contrato consolidado del motor de tarifa/cotizar/salida

**Descripción.** Las auditorías originales solo confirmaron la **ausencia** de estos endpoints (`GET /operacion/cotizar`, `GET /operacion/ocupacion`, función `calcular_cotizacion`, escritura de `salidas`) sin proponer contrato. Parte 1 (Fases 1 y 7) sí define el contrato completo — se consolida aquí en un solo lugar para que un equipo de backend no tenga que reconstruirlo leyendo HU sueltas.

**`GET /operacion/cotizar?uuid_ingreso=X`** (cierra HU-F1.8, función PL/pgSQL `calcular_cotizacion`; consumido por HU-F7.1):

```jsonc
// 200 OK — rotación normal
{ "uuid_ingreso": "…", "cobrar": true, "tiempo_minutos": 135, "tarifa_valor": 100,
  "subtotal": 11345, "iva": 2155, "total": 13500, "vigente_hasta": "2026-09-11T16:20:00Z" }
// 200 OK — mensualidad vigente (no genera cobro, pero SÍ desglose completo desde migration 0050)
{ "uuid_ingreso": "…", "cobrar": false, "motivo": "mensualidad_vigente",
  "subtotal": 11345, "iva": 2155, "total": 13500, "tiempo_minutos": 135,
  "tarifa_uuid": "…", "vigente_hasta": "2026-09-11T16:20:00Z",
  "uuid_subscripcion_cliente": "…", "concepto_descuento": "Plan Oro" }
// 200 OK — 2da placa simultánea, plan empresa (cantidad_maxima_vehiculos>2, 2026-09-24)
{ "uuid_ingreso": "…", "cobrar": false, "motivo": "multiple_vehiculos_plan_empresa", "...": "mismos campos que mensualidad_vigente" }
```
Fórmula (DEC-SUC-24, literal de CU-02 AC7, sin "corregir" la base fiscal): `iva = total_a_pagar * porcentaje_impuesto`; `subtotal = total_a_pagar - iva`. Errores: `404 ingreso_no_encontrado`, `500 iva_no_configurado`. *(Corrección 2026-09-24, migration 0050: el desglose fiscal se calcula SIEMPRE ahora, incluso cuando `cobrar=false` — antes la mensualidad hacía short-circuit antes de calcular tarifa/IVA. Ver "Factura por mensualidad ($0)" en el glosario.)*

**`POST /operacion/salidas`** (cierra HU-F1.7; consumido por HU-F7.2):
```jsonc
// Request
{ "uuid_ingreso": "…", "uuid_cotizacion_ref": "…" }
// 201 Created
{ "uuid": "…", "uuid_ingreso": "…", "estado": "PENDIENTE_PAGO", "fecha_salida": "2026-09-11T16:05:00Z" }
```
Errores: `409 salida_duplicada`, `410 cotizacion_expirada` (la cotización de `GET /operacion/cotizar` vence a los 15 min). No persiste monto (`salidas` sin columna `valor` — DEC-SUC-23; el monto vive únicamente en `facturas`, generado en CU-04).

**`POST /operacion/salidas/mensualidad`** *(Corrección 2026-09-24: no existe como endpoint separado — es el mismo `POST /operacion/salidas` derivando `tipo_salida='MENSUALIDAD'` server-side, DEC-MONO-01)*: mismo patrón, `estado='MENSUALIDAD_PAGO'` conceptual; error `400 mensualidad_no_vigente` si la placa no tiene mensualidad vigente. Desde migration 0050, el frontend encadena `POST /facturacion/factura` (`medio_pago='suscripcion'`, desglose completo + descuento a $0) inmediatamente después — ver "Factura por mensualidad ($0)" en el glosario.

**`POST /facturacion/factura`** (cierra HU-F1.9, transaccional; consumido por HU-F8.1):
```jsonc
// Request
{ "uuid_ingreso": "…", "uuid_salida": "…", "subtotal": 11345, "iva": 2155, "total": 13500,
  "medio_pago": "efectivo", "monto_recibido": 15000, "uuid_sesion": "…", "fe_con_datos": false }
// 201 Created
{ "uuid_factura": "…", "uuid_factura_electronica": "…", "estado_fe": "pendiente" }
```
En una sola transacción: `INSERT` en `facturas`+`factura_detalle`+`factura_impuestos`, y `UPDATE salidas SET estado='PAGADO'` — la única excepción documentada al patrón insert-only de `salidas`.

**`POST /facturacion/factura-electronica`** (cierra HU-F1.10): asigna `prefijo`+`consecutivo` vía `assign_consecutivo` (`SELECT ... FOR UPDATE` sobre `resolucion_facturacion`, ya implementado en backend hoy) y crea la fila inicial en `envio_dian` (`estado='pendiente'`). Error `409 numeracion_agotada` (dispara la alerta `fe_numbering_exhausted`, ya sembrada en `alert_types` desde `0013`).

**HU que dependen de él:** HU-F1.7, HU-F1.8, HU-F1.9, HU-F1.10 (cierran, Parte 1) · HU-F7.1, HU-F7.2, HU-F8.1 (consumen, Parte 1).

---

### 2. Orden de despliegue de esta Parte IV

Para evitar el mismo error de secuenciación que ya identificó RIESGO-ADM-01/02 (Parte 2) a escala de todo el backend transversal:

1. **Antes de cualquier fase de negocio de Parte 1 o Parte 2:** GAP-BE-02 (fix de `router_factory.py`, HU-F1.1) y GAP-BE-03/04 (migración de 9 permisos + reconciliación de `workflows.py`, HU-F13.1).
2. **Antes de HU-F1.13/HU-F18.1:** GAP-BE-05 (corrección del permiso mal asignado en `caja.py`/`caja_sesion.py`) — bajo costo, sin dependencias, se puede resolver en la misma rama que cualquiera de las dos HU.
3. **Antes de codificar HU-F23.3 (instalador):** GAP-BE-08 debe estar resuelto en Parte 2 (HU-F13.3 ya mergeada) para que el instalador siembre contra el path real.
4. **En paralelo, sin bloquear nada:** GAP-BE-06 (ya resuelto, solo pendiente en el instalador) y GAP-BE-07 (higiene documental).
## ANEXOS

### A. Catálogo consolidado de endpoints

Todos los endpoints mencionados en las 3 partes (existentes y nuevos), agrupados por dominio funcional. Estado: **Existe** (funciona hoy sin cambios) · **Modificado** (existe, cambia su lógica interna) · **Ampliación** (existe, se añade un filtro/campo sin cambiar el contrato base) · **Bloqueado→Desbloqueado** (existe pero 403 permanente hasta sembrar el permiso indicado, ver Parte IV §1.3) · **Nuevo** (se construye en la fase indicada) · **Incierto** (la propia parte admite no saber si acepta escritura hoy).

#### A.1 Autenticación

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `POST /auth/login` | Parte 1 (HU-F1.2 cierra cookie+lockout, HU-F3.1 consume) · Parte 2 (HU-F13.2 corrige emisor, HU-F13.6 consume) | Modificado | público |
| `POST /auth/refresh` | Parte 1 (HU-F2.2, HU-F3.2 — sin HU de backend propia que lo "cierre", ver nota) · Parte 2 (HU-F13.5) | Existe | requiere refresh token |
| `POST /auth/logout` | Parte 2 (HU-F13.5/F13.6) | Existe | autenticado |
| `GET /auth/me` | Parte 1 (HU-F1.2 cierra · HU-F3.1 consume) | Nuevo | `operador-` |
| `GET /admin/me` | Parte 2 (HU-F13.5) | Existe | `admin-` |

Nota: `/auth/me` (Parte 1, actor `operador-`) y `/admin/me` (Parte 2, actor `admin-`) son endpoints distintos para issuers de JWT distintos — no son duplicados, sirven a dos identidades de token diferentes.

#### A.2 Operación (ingreso, tarifa, salida)

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `POST /operacion/ingresos` | Parte 1 (HU-F1.6 cierra 4 validaciones · HU-F6.1 consume) | Modificado | — |
| `GET /operacion/ingresos?placa=&activo=` | Parte 1 (HU-F6.1 consume, redirect a salida) | Existe | — |
| `GET /operacion/ingresos/{uuid}/estado` | Parte 1 (uso interno) | Existe (rama "anulada" es stub) | — |
| `GET /operacion/cotizar?uuid_ingreso=` | Parte 1 (HU-F1.8 cierra · HU-F7.1 consume) | Nuevo — contrato consolidado en Parte IV §1.8 | — |
| `GET /operacion/ocupacion` | Parte 1 (HU-F1.5 cierra · HU-F4.3 consume) | Nuevo | — |
| `POST /operacion/salidas` | Parte 1 (HU-F1.7 cierra · HU-F7.2 consume) | Nuevo — contrato Parte IV §1.8 | — |
| `POST /operacion/salidas/mensualidad` | Parte 1 (HU-F1.7 cierra · HU-F7.2 consume) | Nuevo | — |
| `GET /operacion/mi-turno` | Parte 1 (HU-F12.1) | Nuevo | — |

#### A.3 Caja y sesión

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET /caja-sesion/sesion/me` | Parte 1 (HU-F1.3 cierra · HU-F3.3 consume) | Nuevo | — |
| `POST /caja-sesion/sesiones` | Parte 1 (HU-F1.3 cierra 409 · HU-F3.3 consume) | Modificado | — |
| `PUT /caja-sesion/sesion/{uuid}/cerrar` | Parte 1 (HU-F1.3 cierra 409 · HU-F3.3/F10.2 consume) | Modificado | — |
| `GET /caja-sesion/arqueos/{uuid}/diferencias` | Parte 2 (HU-F18.2 consume) | Existe (cálculo ad-hoc, sin vista SQL) | — |
| `GET /caja-sesion/sesion` (listado) | — | Existe, roto por GAP-BE-02 hasta que HU-F1.1 lo corrija | `abrir_cerrar_caja` (corregido por GAP-BE-05; hoy mal asignado a `emitir_factura`) |
| `GET /caja/caja`, `GET /caja/arqueo` (listado) | Parte 2 (HU-F18.1 amplía filtros · HU-F18.2 consume) | Existe, roto por GAP-BE-02 hasta que HU-F1.1 lo corrija | `realizar_arqueo` (corregido por GAP-BE-05; hoy mal asignado a `emitir_factura`) |
| `POST /caja/arqueo` | Parte 1 (HU-F1.13 cierra · HU-F10.1-F10.3 consume) | Nuevo | `realizar_arqueo` |
| `GET /caja/arqueo/resumen` | Parte 1 (HU-F1.13 cierra · HU-F10.3 consume) · Parte 2 (HU-F18.3 consume) | Nuevo — la intro de Fase 18 (Parte 2) lo da por existente pero el cuerpo de HU-F18.3 lo trata como nuevo (JOIN `sesion`+`arqueo`+suma de `factura_pagos`); prevalece "nuevo", cerrado por HU-F1.13 de Parte 1 | — |

#### A.4 Facturación y Factura Electrónica

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `POST /facturacion/factura` | Parte 1 (HU-F1.9 cierra · HU-F8.1 consume) | Nuevo (transaccional) — contrato Parte IV §1.8 | — |
| `POST /facturacion/factura-pagos` | Parte 1 (HU-F1.9 cierra · HU-F8.1 consume) | Nuevo | — |
| `POST /facturacion/factura-electronica` | Parte 1 (HU-F1.10 cierra · HU-F8.1 consume) | Nuevo — contrato Parte IV §1.8 | — |
| `GET /facturacion/factura-electronica/{uuid}` | Parte 1 (HU-F1.10 cierra · HU-F8.2 consume) | Nuevo | — |
| `POST /facturacion/factura-electronica/{uuid}/reintentar` | Parte 1 (HU-F1.10 cierra · HU-F8.2 consume) | Nuevo | — |
| `GET /facturacion/{facturas,factura-detalle,factura-impuestos,factura-otros-cobros,factura-pagos}` (solo lectura) | Parte 2 (HU-F17.3 reportería) | Existe | `emitir_factura` |
| `GET /admin/reporteria/facturas`, `/fe`, `/pagos` | Parte 2 (HU-F17.3) | Nuevo | — |

#### A.5 Workflows (alertas, anulaciones, reclamos, reimpresión)

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET /workflows/alerta` | Parte 1 (HU-F1.1 corrige bug de orden · HU-F11.2 consume) · Parte 2 (HU-F19.5 consume, añade `LEFT JOIN alert_types`) | Corregido (P1) + Ampliado (P2) — dos partes lo modifican, ver Parte IV §1.2 para el orden de despliegue | — |
| `POST /workflows/alerta/{uuid}/descartar` | Parte 2 (HU-F19.4 cierra · HU-F19.5 consume) | Nuevo | `descartar_alerta` |
| `GET /workflows/anulaciones` | Parte 1 (HU-F1.1 corrige bug) · Parte 2 (HU-F20.3, precondición) | Existe, solo lectura | — |
| `POST /workflows/anulaciones` | Parte 2 (HU-F20.3) | Nuevo | — |
| `POST /workflows/anulaciones/{uuid}/transicion` | Parte 2 (HU-F20.3) | Nuevo | `aprobar_anulacion` / `ejecutar_anulacion` (reconciliado, GAP-BE-04) |
| `GET /workflows/reclamos` | Parte 1 (HU-F1.1 corrige bug) · Parte 2 (HU-F20.3, precondición) | Existe, solo lectura | — |
| `POST /workflows/reclamos` | Parte 2 (HU-F20.3) | Nuevo | — |
| `POST /workflows/reclamos/{uuid}/transicion` | Parte 2 (HU-F20.3) | Nuevo | `registrar_reclamo` (nuevo, GAP-BE-04) |
| `GET /workflows/reimpresion-ticket` | Parte 1 (HU-F1.1 corrige bug · HU-F8.3 consume) | Existe, corregido | — |
| `POST /workflows/reimpresion-ticket` | Parte 1 (HU-F1.11 cierra · HU-F8.3 consume) | Nuevo | `reimprimir_ticket` (reconciliado, GAP-BE-04) |
| `POST /workflows/reimpresion-ticket/{uuid}/anular` | Parte 1 (HU-F1.11 cierra · HU-F8.3 consume) | Nuevo | — |
| `POST /facturacion/factura-servicio` | HU-F8.3 (ajuste 2026-09-25-c) | Nuevo — factura de servicio suelto sin `uuid_salida`, no modifica `POST /facturacion/factura` | — |

#### A.6 Empresa y configuración

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET/POST/PUT /empresa/sucursal` | Parte 2 (HU-F15.1) | Existe | `config_sucursal` |
| Filtro `vigente_en=` en `/empresa/tarifas-sucursal`, `/empresa/cantidad-vehiculos-sucursal`, `/empresa/resolucion-facturacion` | Parte 1 (HU-F1.4 cierra para tarifas) · Parte 2 (HU-F15.1 amplía a los 3) | Ampliación | — |
| `GET/POST/PUT /empresa/empresa` | Parte 2 (HU-F15.2) | Bloqueado→Desbloqueado | `config_empresa` (GAP-BE-03) |
| `GET/POST/PUT /empresa/resolucion-facturacion` | Parte 2 (HU-F15.3) | Bloqueado→Desbloqueado | `admin_resolucion_facturacion` (GAP-BE-03) |
| `GET /empresa/resolucion-facturacion/{uuid}/consecutivo-actual` | Parte 2 (HU-F15.3) | Nuevo | — |
| `GET/POST/PUT /empresa/documentos` | Parte 1 (HU-F6.2/F7.3 consumen lectura) · Parte 2 (HU-F15.4, CRUD) | Bloqueado→Desbloqueado (escritura) | `admin_documentos` (GAP-BE-03) |
| `GET/POST/PUT /empresa/tarifas-sucursal` | Parte 1 (HU-F1.4/F4.2 consumen) · Parte 2 (HU-F14.3, CRUD) | Bloqueado→Desbloqueado (escritura) | `config_tarifas` (GAP-BE-03) |
| `GET/POST/PUT /empresa/cantidad-vehiculos-sucursal` | Parte 2 (HU-F14.4) | Bloqueado→Desbloqueado | `config_cupos` (GAP-BE-03) |
| `GET/POST/PUT /configuracion/configuracion-tolerancias` (+ `.../efectiva`) | Parte 2 (HU-F15.5) | Bloqueado→Desbloqueado | `config_tolerancias` (GAP-BE-03) |
| `GET/POST/PUT /configuracion/configuracion-seguridad` (+ `.../efectiva`) | Parte 2 (HU-F15.5/F16.4) | Bloqueado→Desbloqueado | `config_seguridad` (GAP-BE-03) |
| `GET/POST/PUT /configuracion/configuracion-caja` (+ `.../efectiva`) | Parte 2 (HU-F13.3, crea la tabla) · Parte 3 (HU-F23.3, instalador — **asume un path distinto, `config-caja`; debe corregirse antes de codear**, ver Parte IV §1.7) | Nuevo | `config_caja` (GAP-BE-03) |

#### A.7 Usuarios y permisos

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET/POST /usuarios` | Parte 2 (HU-F16.1/F16.2) | Nuevo | — |
| `GET/PUT /usuarios/{uuid}` | Parte 2 (HU-F16.1) | Nuevo | — |
| `GET/POST /usuarios/{uuid}/permisos` | Parte 2 (HU-F16.1/F16.3) | Nuevo | — |
| `POST /usuarios/{uuid}/permisos/{uuid_permiso}/revocar` | Parte 2 (HU-F16.1/F16.3) | Nuevo | — |
| `POST /usuarios/{uuid}/reset-password` | Parte 2 (HU-F16.1/F16.4) | Nuevo | — |
| `GET/POST /usuarios/{uuid}/sucursales` | Parte 2 (HU-F16.1/F16.4) | Nuevo | — |
| `GET /usuarios/{uuid}/login` | **Parte 1 (HU-F1.15/HU-F1.2, "gap huérfano") Y Parte 2 (HU-F16.1/F16.5) — mismo recurso propuesto de forma independiente por las dos partes** | Nuevo, **duplicado** — construir una sola vez, backend compartido (ver nota) | — |
| `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` | Parte 2 (HU-F16.1/F16.5) | Nuevo | — |

Nota sobre el duplicado: Parte 1 (Sucursal) lo describe como gap huérfano de solo lectura para historial de intentos de login; Parte 2 (Admin) lo describe con router completo `usuarios.py` y filtros `?activo=&cursor=&limit=`. Es el **mismo endpoint de backend** — se construye una sola vez (se recomienda como parte del router `usuarios.py` de Parte 2, HU-F16.1, que ya lo dimensiona con filtros) y ambas partes lo consumen desde su frontend respectivo.

#### A.8 Reportería

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET /admin/sucursales/{uuid}/dashboard` | Parte 2 (HU-F13.5 consumo inicial · HU-F17.1 corrige placeholder `ingresos_monto_total`) | Existe, corregido | — |
| `GET /admin/dashboard/resumen` | Parte 2 (HU-F17.1) | Nuevo | — |
| `GET /admin/reporteria/operacional` | Parte 2 (HU-F17.2) | Nuevo | — |
| `GET /admin/reporteria/ocupacion` | Parte 2 (HU-F17.2) | Nuevo | — |
| `GET /admin/reporteria/suscripciones/cohorte` | Parte 2 (HU-F17.4) | Nuevo | — |

#### A.9 Sincronización y pairing

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET /sync/estado` | Parte 1 (HU-F1.14 cierra · HU-F11.1 consume) | Nuevo — distinto de `/admin/sync/estado` | — |
| `GET /admin/sync/log`, `/admin/sync/conflict`, `/admin/sync/estado` | Parte 2 (HU-F19.1/F19.2) | Nuevo | — |
| `POST /admin/pairing-tokens`, `GET .../{uuid}`, `POST .../revoke` | Parte 2 (HU-F19.3) | Existe, probado (`test_pairing_flow.py`) | `gestionar_dian` |
| `POST /admin/sucursales/{uuid}/revoke-sync` | Parte 2 (HU-F19.3) | Existe | `gestionar_dian` |
| `GET /envio-dian`, `GET /validacion-evento` | Parte 2 (HU-F13.4 cierra · HU-F19.6/F20.5 consumen) | Nuevo (solo lectura) | — |
| `POST /validacion-evento` | Parte 2 (HU-F19.6) | Existe | — |
| `POST /envio-dian` (reintento vía `uuid_envio_padre`) | Parte 2 (HU-F20.5) | Existe, reutilizado | — |
| `/sync/{hello,pair,push,pull,heartbeat,rotate-jwt,events}` | Parte 3 (heartbeat consumido en HU-F29.3) | Existe | — |

#### A.10 Catálogos

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| CRUD `/catalogos/{tipo-persona,tipos-vehiculo,tipo-subscripciones,tipo-tarifa,tipo-sucursal,tipo-arqueo,impuestos,otros-cobros,costos-servicios}` | Parte 2 (HU-F14.1/F14.2) | Existe | `config_catalogo` |
| `POST /api/v1/catalogos/{tabla}` (seed) | Parte 3 (HU-F23.2, instalador) | Existe (consumido como seed idempotente) | — |
| `GET /api/v1/impuestos?estado=VIGENTE` | Parte 3 (HU-F23.3) | Existe (lectura) | — |
| `POST /api/v1/impuestos` | Parte 3 (HU-F23.3) | **Incierto** — el propio texto de la HU admite que puede no aceptar escritura vía API en la versión instalada; fallback documentado a `INSERT ... ON CONFLICT` directo con la conexión de migración | — |

#### A.11 Clientes y suscripciones

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| CRUD `/clientes/{clientes,vehiculos,subscripciones-cliente,subscripcion-vehiculos}` | Parte 2 (HU-F20.1/F20.2) | Existe | `gestionar_clientes` |
| `POST /clientes/venta-suscripcion` | Parte 1 (HU-F1.12 cierra · HU-F9.1 consume) | Nuevo (transaccional) | — |

#### A.12 Bitácora

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET /admin/log-transaccional` | Parte 2 (HU-F20.4) | Nuevo | — |
| `GET /admin/log-transaccional/verify-chain` | Parte 2 (HU-F20.4) | Nuevo (envuelve `verify_chain_for_spec()`, ya real) | — |
| `GET /admin/log-transaccional/buscar` | Parte 2 (HU-F20.4) | Nuevo | — |

#### A.13 Infraestructura / instalador local

| Método + path | Consumido por | Estado | Permiso |
|---|---|---|---|
| `GET /health` | Parte 1 (HU-F2.3, polling 30s) · Parte 3 (Fase 24, healthcheck NSSM; HU-F28.2, `api_contract_version`) | Existe | — |
| `GET /openapi.json` | Parte 3 (Fase 24) | Existe | — |
| `GET http://127.0.0.1:9999/healthz` (job-sync-sucursal) | Parte 3 (diagnóstico local) | Existe, interno | — |

---

### B. Matriz CU → tablas ER

18 casos de uso de negocio + `FLUJO_CUS_ER` (documento de flujo transversal del corpus original, no es un CU propio — ver nota de conteo abajo).

| CU | Nombre | Tablas ER principales |
|---|---|---|
| CU-01 | Registrar ingreso vehicular | `ingreso`, `subscripcion_vehiculos`, `subscripciones_cliente`, `cantidad_vehiculos_sucursal`, `sucursal`, `tipos_vehiculo`, `sync_queue`, `login` |
| CU-02 | Calcular tarifa en salida | `ingreso`, `salidas`, `anulaciones`, `impuestos`, `tarifas_sucursal`, `subscripciones_cliente` |
| CU-03 | Registrar salida vehicular | `salidas`, `ingreso`, `anulaciones`, `sync_queue` |
| CU-03M | Registrar salida con mensualidad | `salidas`, `subscripciones_cliente`, `subscripcion_vehiculos`, `tipo_subscripciones`, `ingreso`, `sync_queue`, `facturas`, `factura_detalle`, `factura_impuestos`, `factura_pagos`, `factura_electronica`, `envio_dian` *(desde 2026-09-24, migration 0050: las últimas 6 tablas se agregaron porque la salida sin cobro ahora también emite una factura completa con descuento — antes CU-03M no tocaba facturación en absoluto)* |
| CU-04 | Procesar pago | `factura_pagos`, `facturas`, `factura_detalle`, `factura_impuestos`, `factura_electronica`, `salidas`, `sesion`, `clientes`, `impuestos`, `sync_queue` |
| CU-05 | Gestionar Factura Electrónica | `facturas`, `factura_electronica`, `envio_dian`, `resolucion_facturacion`, `sync_queue`, `clientes` |
| CU-06 | Gestionar suscripciones / mensualidades | `subscripciones_cliente`, `subscripcion_vehiculos`, `vehiculos`, `clientes`, `tipo_subscripciones`, `sucursal`, `tipos_vehiculo`, `sync_queue` |
| CU-07 | Sincronizar datos offline-first | `sync_queue`, `sync_log`, `sync_conflict`, `sync_queue_lw_buffer` (aplica a todas las tablas replicadas) |
| CU-08 | Gestionar usuarios y perfiles | `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal`, `login`, `sync_queue` |
| CU-09 | Generar reportería y analítica | `ingreso`, `salidas`, `facturas`, `factura_pagos`, `subscripciones_cliente`, `factura_electronica`, `alerta`, `sesion`, `arqueo`, `sucursal` |
| CU-10 | Realizar arqueos de caja y cierre diario | `sesion`, `factura_pagos`, `arqueo`, `tipo_arqueo`, `configuracion_tolerancias`, `alerta`, `sucursal`, `usuarios`, `sync_queue` (`configuracion_caja` ⚠️ ver GAP-BE-08, Parte IV) |
| CU-11 | Configurar sucursales, tarifas y capacidad | `sucursal`, `empresa`, `resolucion_facturacion`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `tipo_sucursal`, `tipos_vehiculo`, `sync_queue` |
| CU-12 | Configurar tipos de vehículo | `tipos_vehiculo`, `sync_queue` |
| CU-13 | Configurar base de caja parametrizable | `configuracion_caja` (⚠️ tabla nueva creada por Parte 2 — no existe en el ER canónico original, ver GAP-BE-08), `sucursal`, `sync_queue` |
| CU-14 | Monitorear y alertar | `alerta`, `alert_types`, `sync_log`, `sucursal`, `configuracion_tolerancias`, `ingreso`, `sync_queue`, `factura_electronica`, `envio_dian`, `subscripciones_cliente` |
| CU-15E | Tiquete de entrada | `sucursal`, `ingreso`, `tipos_vehiculo`, `tarifas_sucursal`, `usuarios` |
| CU-15S | Tiquete de salida | `sucursal`, `ingreso`, `salidas`, `facturas`, `factura_pagos`, `usuarios` |
| CU-15SM | Tiquete de salida-mensualidad | `sucursal`, `ingreso`, `salidas`, `subscripciones_cliente`, `usuarios` |

**Nota de conteo (corrección respecto al corpus original):** el corpus fuente son 19 archivos `.md`, pero solo 18 son casos de uso de negocio propios — el 19º archivo es `FLUJO_CUS_ER.md`, un documento transversal de flujo/matriz CU×tabla (el propio corpus lo declara: "Total de casos de uso: 18"). No es un CU independiente y no tiene fila propia en esta matriz.

---

### C. Matriz CU → HU

Trazabilidad de cada uno de los 18 CU hacia las HU de las 3 partes que lo implementan.

| CU | HU — Parte 1 (Sucursal) | HU — Parte 2 (Admin) | HU — Parte 3 (Instalador) |
|---|---|---|---|
| CU-01 | HU-F1.6, HU-F4.1, HU-F6.1 | — | HU-F23.2 (siembra regex de catálogos) |
| CU-02 | HU-F1.4, HU-F1.8, HU-F4.2, HU-F7.1 | — | HU-F23.3 (deslinde IVA vigente; prueba de integración) |
| CU-03 | HU-F1.7, HU-F7.2 | — | — |
| CU-03M | HU-F1.7, HU-F7.2 | — | — |
| CU-04 | HU-F1.9, HU-F8.1 | — | — |
| CU-05 | HU-F1.10, HU-F8.2 | — | HU-F29.4 (solo contraste de escala de backoff) |
| CU-06 | HU-F1.12, HU-F9.1, HU-F9.2 | HU-F14.2, HU-F17.4, HU-F20.1, HU-F20.2 | — |
| CU-07 | HU-F1.14, HU-F11.1 | HU-F13.4, HU-F19.1, HU-F19.2, HU-F19.3, HU-F19.6 | HU-F29.3, HU-F29.4, HU-F29.5 |
| CU-08 | — | HU-F13.2, HU-F16.1, HU-F16.2, HU-F16.3, HU-F16.4, HU-F16.5 | — |
| CU-09 | HU-F12.1 | HU-F17.1, HU-F17.2, HU-F17.3, HU-F17.4 | — |
| CU-10 | HU-F1.13, HU-F10.1, HU-F10.2, HU-F10.3 | HU-F15.5, HU-F18.1, HU-F18.2, HU-F18.3, HU-F18.4 | — |
| CU-11 | — (Fase 4 solo lectura, sin trazabilidad 1:1 declarada) | HU-F14.1, HU-F14.2, HU-F14.3, HU-F14.4, HU-F15.1, HU-F15.2, HU-F15.3, HU-F15.4 | — |
| CU-12 | HU-F4.1 (tangencial, catálogo de solo lectura) | HU-F14.1 | — |
| CU-13 | — | HU-F13.3, HU-F15.5 | HU-F23.3 |
| CU-14 | HU-F1.14, HU-F11.2 | HU-F19.4, HU-F19.5 | — |
| CU-15E | HU-F6.2 | — | — |
| CU-15S | HU-F7.3, HU-F8.1 | — | — |
| CU-15SM | HU-F7.3 | — | — |

Nota: CU-08, CU-13 y (CU-16 a CU-19, si existieran en el corpus — no aplica, son solo 18 CU) están explícitamente fuera del alcance declarado de Parte 1 (línea de alcance de su Sección 0). CU-11/CU-12 en Parte 1 son de solo lectura (cache local), sin HU que los "cierre" — su cierre real ocurre en Parte 2.

---

### D. Riesgos consolidados

Los 50 riesgos (`RIESGO-SUC-01..14`, `RIESGO-ADM-01..20`, `RIESGO-INST-01..16`) en una tabla única, ordenados por severidad descendente (Impacto, luego Probabilidad).

| # | ID | Riesgo | Probabilidad | Impacto |
|---|---|---|---|---|
| 1 | RIESGO-ADM-01 | Ninguna fase de negocio de Admin (14-20) puede completarse sin Fase 13 — punto único de secuenciación | Alta | Crítico |
| 2 | RIESGO-SUC-12 | Backend cae al secreto JWT de desarrollo hardcodeado si el instalador no provisiona `PARKOS_JWT_KEY_PATH` | Media | Crítico |
| 3 | RIESGO-ADM-04 | El despliegue de `web_admin` es infraestructura sin CU que lo pida — riesgo de quedar de último por prioridad de negocio | Media | Crítico |
| 4 | RIESGO-INST-12 | Restauración de backup (`pg_restore`) nunca probada fuera de CI en una ejecución real | Media | Crítico |
| 5 | RIESGO-SUC-06 | `api-sucursal` cae por ser servicio Windows sujeto a fallos de infraestructura | Baja | Crítico |
| 6 | RIESGO-INST-09 | `--force-cleanup`/`Uninstall-Parkos -PurgeData` ejecutado por error borra datos de producción irreversiblemente | Baja | Crítico |
| 7 | RIESGO-SUC-07 | Certificado de firma de código (EV/Trusted Signing) no listo antes del primer despliegue | Alta | Alto |
| 8 | RIESGO-SUC-09 | macOS: impresora USB requiere entitlements específicos | Alta (solo macOS) | Alto |
| 9 | RIESGO-INST-04 | Backend sin *rate limiting*/*lockout* en `/auth/login`/`/auth/refresh` | Alta | Alto |
| 10 | RIESGO-SUC-01 | Retraso de lockout real deja login expuesto a fuerza bruta | Media | Alto |
| 11 | RIESGO-SUC-13 | Sin gate de compatibilidad, auto-update de Electron podría desincronizarse de `api-sucursal` | Media | Alto |
| 12 | RIESGO-ADM-02 | Migración de 9 permisos y reconciliación de `workflows.py` deben desplegarse en cloud antes que cualquier PR de frontend dependiente | Media | Alto |
| 13 | RIESGO-ADM-05 | Reportería sobre >1 año de datos podría volverse lenta con agregación directa (sin vista materializada) | Media | Alta |
| 14 | RIESGO-ADM-08 | `dias_alerta_pre_vencimiento` y `configuracion_caja` son cambios de esquema compartido — riesgo de colisión de migraciones entre ramas paralelas | Media | Alta |
| 15 | RIESGO-INST-05 | JWT firmado con HS256 + secreto compartido con fallback a secreto de desarrollo hardcodeado | Media | Alto |
| 16 | RIESGO-INST-11 | Desalineación de versión entre auto-update de Electron y backend gestionado por el instalador | Media | Alto |
| 17 | RIESGO-SUC-04 | Bug en validación NIT módulo 11 bloquearía emisión de FE con datos del cliente | Baja | Alto |
| 18 | RIESGO-ADM-19 | El modelo de tenancy real asume una sola empresa — si crece a multiempresa, requiere revisión | Baja | Alta |
| 19 | RIESGO-INST-14 | Certificado de Azure Trusted Signing expira sin aviso, bloqueando un release | Baja | Alto |
| 20 | RIESGO-INST-01 | Sin mecanismo de licenciamiento/activación por sucursal definido en ningún documento | N/A (decisión de producto) | Alto |
| 21 | RIESGO-SUC-02 | Vista de ocupación (polling 10s) puede mostrar cupo desactualizado en alta rotación simultánea | Media | Medio |
| 22 | RIESGO-SUC-05 | Antivirus Windows marca el binario Electron como sospechoso por falta de firma | Media | Medio |
| 23 | RIESGO-SUC-08 | Impresoras térmicas económicas (clones Xprinter) con dialectos ESC/POS incompletos | Media | Medio |
| 24 | RIESGO-ADM-03 | `zustand` se activa por primera vez — riesgo de bugs de hidratación/persistencia | Media | Media |
| 25 | RIESGO-ADM-07 | Rol "Auditor" y permiso `audit_read` son independientes por diseño — nada impide asignar por error permisos de escritura | Media | Media |
| 26 | RIESGO-ADM-11 | `admin_resolucion_facturacion` es el único permiso con issuer `admin-` estricto — fricción de expectativa de un "Facturador" | Media | Media |
| 27 | RIESGO-ADM-12 | Bundle con TanStack Table + Recharts + PDF en cliente podría superar 800 KB gzipped | Media | Media |
| 28 | RIESGO-ADM-13 | Tablas densas (8-10 columnas) son más difíciles de hacer accesibles que formularios simples | Media | Media |
| 29 | RIESGO-ADM-20 | No hay mapeo por defecto entre los 6 roles de negocio y un set sugerido de permisos atómicos | Media | Media |
| 30 | RIESGO-INST-02 | Antivirus corporativo marca `nssm.exe` como falso positivo | Media | Media |
| 31 | RIESGO-INST-03 | `winget` ausente en equipos Windows 10 21H2 sin App Installer actualizado | Media | Media |
| 32 | RIESGO-INST-06 | `pg_partman` en Windows depende de binarios de terceros sincronizados por versión de Postgres | Media | Media |
| 33 | RIESGO-INST-10 | Binario standalone no arranca por ausencia del Visual C++ Redistributable | Media | Media |
| 34 | RIESGO-INST-15 | Conectividad muy pobre retrasa la detección de "sucursal silenciosa" del heartbeat | Media | Media |
| 35 | RIESGO-INST-16 | Matriz de impresoras no validada en CI para marcas no-Epson | Media | Baja a Media |
| 36 | RIESGO-ADM-10 | `verify_chain_for_spec()` sin paginación — verificación HTTP síncrona podría tardar en sucursales con mucho histórico | Baja | Media |
| 37 | RIESGO-ADM-16 | Límite real de 5 pairing tokens/hora/admin podría generar fricción en apertura masiva de sucursales | Baja | Media |
| 38 | RIESGO-ADM-18 | Sin pantalla de "reglas de alerta configurables" (`alert_rules`) — tabla nueva completa si el negocio la pide | Baja | Media |
| 39 | RIESGO-INST-07 | Espacio en disco agotado durante instalación (Postgres + binarios + payload > 1 GB) | Baja | Media |
| 40 | RIESGO-INST-08 | NSSM no confiable en Windows Server Core | Baja | Media |
| 41 | RIESGO-INST-13 | `sync_queue_lw_buffer` sin umbral de "dependencia nunca resuelta" (crecimiento no acotado) | Baja | Media a largo plazo |
| 42 | RIESGO-SUC-03 | Confusión operativa entre reimpresión gratuita inmediata y reimpresión con costo | Media | Bajo |
| 43 | RIESGO-ADM-06 | `alerta.uuid_arqueo` es la única FK de contexto estructurada — sin vínculo estructurado para FE/suscripción | Alta | Baja |
| 44 | RIESGO-ADM-09 | Reintento DIAN reutiliza `POST /envio-dian` sin `Idempotency-Key` verificado — doble click podría duplicar la transición | Media | Baja |
| 45 | RIESGO-SUC-10 | Lock de single-instance queda huérfano tras un crash | Baja | Bajo |
| 46 | RIESGO-SUC-11 | Modo kiosko evadible con conocimiento técnico suficiente | Baja | Bajo |
| 47 | RIESGO-SUC-14 | Reordenar impresión del tiquete de salida cambia hábito operativo previo | Baja | Bajo |
| 48 | RIESGO-ADM-14 | Corrección del emisor JWT podría afectar datos de prueba/QA que ya usan `rol='operador'` textual | Baja | Baja |
| 49 | RIESGO-ADM-15 | Reconciliación de permisos en `workflows.py` cambia qué código gatea cada escritura — riesgo con una integración externa | Baja | Baja |
| 50 | RIESGO-ADM-17 | No existe endpoint de "listar todos los pairing tokens de todas las sucursales" | Baja | Baja |

---

### E. Decisiones abiertas consolidadas

Los 29 `ABIERTO-*` de las 3 partes (`ABIERTO-01..08` Parte 1, `ABIERTO-50..60` Parte 2, `ABIERTO-100..109` Parte 3 — sin colisión, se conservan sus IDs originales) más 1 nuevo (`ABIERTO-200`) detectado al cruzar las 3 partes en esta integración, agrupados por tema.

#### E.1 Arquitectura y compatibilidad de versión

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-08 | Falta de gate de compatibilidad de versión entre auto-update de Electron y actualización del backend | **Resuelta por Parte 3**: DEC-INST-16 ya lo cierra (`web_sucursal` valida `api_contract_version` de `GET /health` en cada arranque). Se conserva el ID por trazabilidad histórica, sin acción pendiente. |
| ABIERTO-60 | ¿Se justifica extraer un paquete de workspace `apps/ui-kit` compartido entre `web_admin` y `web_sucursal`? | Sí, cuando exista una segunda pantalla verdaderamente idéntica entre ambos frontends (hoy `BranchSelector`/atomic design ya se referencian por convención, no por paquete); no bloquea ninguna fase actual. |

#### E.2 Auto-actualización y canales

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-03 | Canal único de auto-actualización (`latest`) vs. canal `beta` para pilotos | **Resuelta por Parte 3**: DEC-INST-06 fija canal único `latest`, descarta explícitamente una mención previa a canal piloto. Se conserva el ID por trazabilidad, sin acción pendiente. |
| ABIERTO-103 | ¿Política formal de "ventana de parche" para CVEs de Chromium/Electron? | Definir una ventana máxima (ej. 5 días hábiles) para CVE crítico, verificada con Dependabot/`npm audit` en CI; sin esto queda a criterio ad-hoc. |

#### E.3 Negocio y modelo comercial

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-57 | ¿El negocio proyecta multiempresa real en el horizonte de este sistema? | Definir antes de invertir en DEC-ADM-02 (hoy asume una sola empresa); si la respuesta es no en los próximos 12-18 meses, no priorizar. |
| ABIERTO-54 | ¿Cuándo se aborda `clientes_b2b` (convenios corporativos, CU-06 BR5 "fase 2")? | Confirmado fuera de alcance de este plan; requiere su propia ronda de HU cuando el negocio lo priorice. |
| ABIERTO-100 | Licenciamiento/activación por sucursal: ¿Opción A (de facto vía pairing) u Opción B (archivo firmado offline)? | Se recomienda Opción A (más simple, ya es requisito funcional de sincronización) salvo que el negocio exija bloquear la operación offline de una sucursal con contrato vencido — en ese caso, Opción B. |
| ABIERTO-101 | ¿Soportar instalación multi-sucursal en el mismo equipo físico? | No priorizar salvo pedido explícito de negocio — la arquitectura branch-pinned (`uuid_sucursal` en JWT) no lo impide, pero ninguna parte lo diseña ni lo prueba hoy. |
| ABIERTO-107 | ¿Soportar recuperación ante desastre con reemplazo de hardware (equipo distinto, mismo `PARKOS_SUCURSAL_UUID`)? | Documentar el procedimiento manual (restaurar backup + reinstalar con el mismo UUID) como parte de la Fase 29/Bloque de operación de Parte 3, sin necesidad de automatizarlo en v1. |

#### E.4 Facturación y numeración

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-01 | Contenido exacto del QR del tiquete de entrada | Folio (UUID del ingreso) + placa + hash corto de verificación — suficiente para trazabilidad sin exponer datos sensibles. |
| ABIERTO-02 | Relación entre numeración del recibo de pago y consecutivo DIAN de la FE | Mantenerlas independientes (recibo = `sucursal-YYYYMMDD-NNNNNN`, FE = prefijo+consecutivo de `resolucion_facturacion`); documentar explícitamente que no hay relación 1:1 esperada. |
| ABIERTO-55 | ¿Se construye un endpoint admin-iniciado para anular una FE antes del acuse DIAN? | Ya cubierto de hecho por la Fase 8.4 de Parte 2 (revocación completa); cerrar formalmente la pregunta remitiendo a esa fase. |

#### E.5 Caja y arqueo

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-04 | Valor `cierre_sesion` de `tipo_arqueo` sin flujo correspondiente en CU-10 | Ver Glosario reconciliado (front-matter): decidir si `cierre_sesion` es un duplicado a deprecar de `cierre_turno`, o si necesita su propio flujo distinto; no dejarlo como valor de catálogo sin uso. |
| ABIERTO-200 *(nuevo, esta integración)* | `configuracion_caja.redondeo`/`denominaciones_permitidas`: ¿deben aplicarse en el cálculo de vueltos (CU-04) o en el conteo de arqueo (CU-10), o quedan como configuración informativa sin efecto operativo en v1? | Ver GAP-BE-08 (Parte IV): si se decide que sí aplican, agregar una HU nueva a Parte 1 (candidata: extender HU-F3.3 o HU-F8.1); si no, documentarlo explícitamente para que no se asuma un efecto que no existe. |

#### E.6 Suscripciones

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-05 | `dias_alerta_pre_vencimiento` editable por suscripción individual vs. solo default global en el ER | Mantener el default global (`tipo_sucursal.caracteristicas`, ya resuelto y justificado en Parte 2 §6.8) salvo pedido explícito de override por suscripción. |
| ABIERTO-07 | ¿El prorrateo tras el día 15 (CU-06 BR3) aplica también a renovaciones, no solo a altas nuevas? | Aplicarlo también a renovaciones por consistencia de negocio, salvo que el equipo de producto decida explícitamente lo contrario. |

#### E.7 Alertas y monitoreo

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-06 | Coexistencia de 8 códigos técnicos y 11 de negocio en `alert_types`: ¿misma audiencia o separados? | Mismo catálogo, misma tabla (ya así en el diseño real); separar solo la vista/filtro de UI por rol (operador ve negocio, admin ve ambos). |
| ABIERTO-56 | ¿Se necesitan reglas de alerta configurables (`alert_rules`) más allá de los 19 tipos sembrados? | No construir `alert_rules` sin un caso de uso concreto que lo pida — hoy es especulativo (RIESGO-ADM-18). |
| ABIERTO-108 | ¿El umbral de "sucursal silenciosa" (15 min) debe ser configurable por perfil de conectividad? | Sí, como parámetro de `tipo_sucursal.caracteristicas` (mismo patrón ya usado para `dias_alerta_pre_vencimiento`), no hardcodeado. |

#### E.8 Sincronización

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-51 | ¿Se necesita resolución manual de `sync_conflict` más allá de "last-write-wins" automático? | No en v1; revisar si el volumen real de conflictos en producción lo justifica antes de construir UI de resolución manual. |
| ABIERTO-104 | Contradicción entre CU-07 ("60 s por defecto" en texto) y el código real (`PARKOS_SYNC_POLL_INTERVAL_S=10`) | El código real manda: corregir el texto de CU-07 a 10 s, no el default. |
| ABIERTO-105 | ¿Qué umbral y alerta debería tener una dependencia nunca resuelta en `sync_queue_lw_buffer`? | Definir un umbral de edad (ej. 24h) que dispare una alerta de tipo `sync_failure`, reutilizando el catálogo ya sembrado — no crear un tipo de alerta nuevo solo para esto. |

#### E.9 Usuarios, permisos y seguridad

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-59 | ¿Debe el alta de usuario sugerir un set de permisos por defecto según el rol de negocio elegido? | Sí — mejora de UX de bajo riesgo; implementar como sugerencia editable, nunca como asignación forzada (mantiene el desacople rol-de-negocio/permiso-atómico ya decidido). |
| ABIERTO-102 | ¿Verificar explícitamente el Visual C++ Redistributable en el pre-flight del instalador? | Sí — es una de las 6 verificaciones bloqueantes más baratas de agregar (RIESGO-INST-10 ya lo justifica). |
| ABIERTO-106 | ¿Debe rotarse periódicamente la contraseña de `svc-parkos`? | No en v1 (cuenta de servicio sin login interactivo, sin exposición directa); revisar solo si una auditoría de seguridad externa lo exige. |

#### E.10 Impresión

| ID | Tema | Recomendación |
|---|---|---|
| ABIERTO-50 | ¿Existe un campo "Título del ticket" por sucursal? (no tiene columna en el ER) | No agregar columna nueva; si se necesita, reutilizar `sucursal.nombre` o un campo de `documentos` (`tipo='plantilla_ticket'`). |
| ABIERTO-109 | ¿Automatizar en CI la validación de impresoras no-Epson, o dejarla como validación manual de campo? | Manual de campo en v1 (bajo el volumen esperado de marcas no-Epson); automatizar solo si RIESGO-INST-16 se materializa en producción. |

#### E.11 Reportería y UX

| ID | Tema | Recomendación |
|---|---|---|
| ~~ABIERTO-53~~ | ¿Modo oscuro en v1? | **Resuelto 2026-09-25**: sí — el operador lo pidió explícitamente (condición de reapertura de `DEC-ADM-19` cumplida). Ver `Fase 31`. |
| ABIERTO-58 | ¿Cuándo se justifica una vista materializada para reportería? | Cuando el volumen de datos de una sucursal supere ~1 año sin degradación aceptable (RIESGO-ADM-05); no construirla preventivamente. |
| ABIERTO-52 | ¿Hace falta un endpoint dedicado de "listar todos los pairing tokens" cuando crezca el número de sucursales? | Sí, cuando el número de sucursales supere ~20-30 (umbral operativo razonable); no es urgente hoy (RIESGO-ADM-17). |

---

### F. Glosario extendido

Términos técnicos o de negocio que no forman parte del glosario único del front-matter (por ser más específicos de un CU, de una convención del ER, o de la arquitectura interna) pero que un desarrollador nuevo necesita para leer el resto del documento sin abrir otro archivo.

- **`[V]` / `[L-E]` / `[L-S]` / `[L-W]` / `[A]`** — leyenda de clase de tabla usada en todo el ER y en las 3 partes: `[V]` catálogo versionado (bi-temporal, `vigente_desde`/`vigente_hasta`/`estado`); `[L-E]` tabla de eventos insert-only con lifecycle auditado; `[L-S]` tabla de sesiones con lifecycle de estados (`UPDATE` permitido solo en el cierre); `[L-W]` tabla de workflow donde cada transición es una fila nueva (nunca `UPDATE`); `[A]` datos transaccionales/auditables append-only. El propio `.mmd` no define esta leyenda como comentario formal — se reconstruye por convención observada.
- **Versionado bi-temporal / `close_and_insert`** — patrón de todas las tablas `[V]`: "editar" una fila es cerrar su vigencia (`vigente_hasta = NOW()`, `estado` no cambia salvo baja) e insertar una fila nueva con `vigente_desde = NOW()`. Nunca hay `UPDATE` de un valor de negocio ya vigente.
- **Configuración efectiva** — patrón default-global (`uuid_sucursal IS NULL`) + override-por-sucursal (`uuid_sucursal` no nulo), expuesto siempre como `GET .../efectiva?uuid_sucursal=X`. Ya real para `configuracion_tolerancias` y `configuracion_seguridad`; extendido a `configuracion_caja` (Parte 2).
- **Outbox / `sync_queue`** — patrón de sincronización: cada escritura local relevante encola un evento con UUID, prioridad e `next_retry_at`; un worker (`job-sync-sucursal`, Parte 3) lo empuja al cloud con backoff exponencial y regla "última escritura gana" (`sync_conflict` registra ambas versiones si hay choque).
- **`FLUJO_CUS_ER`** — documento transversal del corpus original de casos de uso (no es un CU): transcribe la arquitectura ASCII cloud/sucursal, una matriz CU×tabla y un anexo propio de tablas (desactualizado respecto al ER canónico actual — ver GAP-BE-07, Parte IV, para el porqué de sus "50 tablas" frente a las 51 reales).
- **CUFE** — código único de factura electrónica devuelto por el proveedor de facturación electrónica DIAN al aprobar un documento; se persiste en `envio_dian` (nunca en `factura_electronica`, que no tiene columna de estado propia).
- **Proveedor de facturación electrónica DIAN** — servicio externo certificado ante la DIAN, configurado vía variable de entorno (`PARKOS_DIAN_PROVIDER_URL` + token en archivo); el plan no fija ni depende de un proveedor específico por nombre.
- **Datáfono (MVP)** — medio de pago con voucher registrado manualmente en el sistema; sin integración SDK en el alcance de este plan.
- **Convenio (B2B)** — suscripción corporativa multi-vehículo con facturación a un tercero (`clientes_b2b`); declarado explícitamente fuera de alcance de este plan (ABIERTO-54).
- **Tolerancia de placa (O/0, I/1, B/8)** — corrección de ambigüedad de caracteres al **buscar** una placa en la salida (CU-02); nunca se aplica en el **registro** de un ingreso nuevo (CU-01), que usa siempre autodetección estricta por regex sin tolerancia (DEC-SUC-22) — son dos funciones distintas, no el mismo componente.
- **`tipo_entrada` (Mensualidad / Rotación)** — nunca es una columna persistida; siempre se deriva en cada respuesta a partir de `ingreso.uuid_subscripcion_cliente IS NOT NULL` (DEC-SUC-21).
- **Roles de negocio vs. permiso atómico** — un rol de negocio (Usuario/Cajero, Facturador, Supervisor, Administrador, Auditor, Desarrollo; "Owner" no es un rol formal, es un actor de KPIs) es un valor libre de `usuarios.rol`, sin `CHECK` en el ER; la autorización real y verificada en cada escritura vive en `permisos_usuario` (permiso atómico), nunca en el rol de negocio ni cacheada en el JWT.

---

## PARTE V — REDISEÑO VISUAL Y DE MARCA (web_sucursal)

### Fase 31 — Rediseño visual integral e identidad de marca EasyPunto (`apps/electron-sucursal`)

**Objetivo**: alinear la capa visual completa de `web_sucursal` con la identidad de marca real de EasyPunto (extraída de `https://easypunto.com/`, no inventada) y con estándares de accesibilidad, sin modificar la lógica de negocio ni el entry chain de `POST /operacion/ingresos` ni ninguna tabla del `.mmd`. Iniciativa solicitada explícitamente por el operador en sesión del 2026-09-25 vía un prompt maestro de rediseño; no deriva de ningún CU del corpus original.

**Reversa de `DEC-ADM-19` / `ABIERTO-53` (modo oscuro)**: `DEC-ADM-19` marcaba el modo oscuro como fuera de alcance v1, reabrible solo "ante pedido explícito de negocio". Esta fase ES ese pedido explícito (objetivo no negociable del prompt maestro del operador). Se resuelve `ABIERTO-53` con la opción (b): se construye modo oscuro completo. Ambas entradas quedan tachadas y enlazadas a esta fase en sus tres apariciones del documento.

**Alcance confirmado con el operador**: solo `apps/electron-sucursal` (no `web_admin`, no un sitio público separado). Sin proceso SDD formal — implementación directa/delegada.

**Responsive**: aunque `web_sucursal` es hoy una app Electron de kiosko instalada vía MSI/NSSM en hardware fijo de sucursal (Parte III, Fases 21-27), el operador confirmó explícitamente (2026-09-25) mantener el rango completo de breakpoints del prompt maestro (320px a 4K/ultrawide/plegables) para sostener flexibilidad real ante distintos monitores por sucursal y una eventual versión tablet — no se acota a la resolución actual del kiosko.

#### HU-F31.1 — Identidad de marca, design tokens y mecanismo de tema

**Historia**: Como operador de EasyPunto, quiero que `electron-sucursal` refleje la identidad visual real de la marca (color, tipografía, formas) en vez de un tema genérico "Apple blue", y que soporte modo claro/oscuro completo con persistencia y sin flash, para que el producto se sienta consistente con la marca y sea usable en cualquier condición de iluminación del puesto de trabajo.

**Estado**: hecho (esta sesión). Activos de marca en `src/assets/brand/` + `inventory.json`; tokens primitivos/semánticos en `src/renderer/styles/tokens.css` e `src/renderer/index.css`; mecanismo de tema (detección de sistema, persistencia, anti-flash) en `src/renderer/lib/theme.ts` + script inline en `index.html`. Sin botón de toggle visible todavía (ver HU-F31.3).

**Criterios de aceptación**:
- Colores de marca reales (`#E85F24` primario, `#323133` secundario, `#636363` texto, `#F6F6F8`/`#222222` superficies) reemplazan el placeholder azul previo, en ambos modos.
- Tipografía Poppins (400/500/600/700) aplicada vía tokens tipográficos fluidos (`clamp()`).
- Contraste AA (4.5:1 texto normal, 3:1 texto grande/UI) verificado para cada combinación texto/fondo semántica, en ambos modos.
- Preferencia de tema persistida en `localStorage`, con `prefers-color-scheme` como fallback y aplicación pre-render (sin flash del tema incorrecto).
- Logos reales de EasyPunto (bitmap, sin versión vectorial ni variante oscura provista por la marca — decisión del operador: usar el PNG tal cual, sobre contenedor de superficie clara en modo oscuro).

**Pendiente marcado**: `[PENDIENTE_VALIDAR]` — no existe gradiente CSS propio verificable en el sitio fuente; no hay variante de logo para fondo oscuro ni versión vectorial (5 archivos bajo `--REQUIERE-VECTOR` en `inventory.json`).

#### HU-F31.2 — Auditoría de bugs visuales heredados

**Estado**: auditoría hecha (esta sesión), corrección pendiente (se aplica en HU-F31.3).

Encontrado recorriendo dashboard, ingreso, suscripciones y arqueo: paneles laterales (Ingreso/Suscripciones/Arqueo) con un tercio inferior vacío; la barra inferior de cupos libres visualmente desconectada del resto (otro radio, otra paleta); cuatro paletas de color de "estado" ad hoc sin sistema semántico único; cero modo oscuro. Sin errores ni warnings de consola en ninguna de las vistas recorridas — no hay bugs funcionales nuevos, solo deuda visual.

#### HU-F31.3 — Rediseño de componentes, toggle de tema y responsive real

**Historia**: Como operador, quiero que cada vista y componente use el nuevo sistema de tokens, incluyendo un selector de tema visible (claro/oscuro/sistema), y que la corrección de los bugs de HU-F31.2 quede aplicada, para operar con una interfaz consistente y sin deuda visual heredada.

**Alcance**: header/sidebar, paneles de Ingreso/Salida/Suscripciones/Arqueo, componente de toggle de tema, catálogo de estados de componente (hover/focus/active/disabled/loading/error) sobre los componentes reales del inventario de `apps/electron-sucursal`. Breakpoints: rango completo del prompt maestro (320px–4K/ultrawide), confirmado por el operador.

**Estado**: hecho (esta sesión) — shell (header/sidebar/layout) + los ~78 componentes del inventario (agrupados por dominio: caja, operación, auth+facturación+catálogos+reimpresión, suscripciones+sync+alertas), toggle de tema visible, logo real integrado (header + login + favicons), y los bugs de HU-F31.2 corregidos. Breakpoints reales probados: 320 a 3840px + ultrawide, claro y oscuro, vía Chrome DevTools (`resize_page`/`emulate`). `tsc -b`/`eslint` limpios, 947/947 tests. Estados de componente (hover/focus/active/disabled/loading/error) cubiertos donde ya existía la lógica — no se agregó ningún estado de negocio nuevo.

Bugs funcionales reales encontrados y corregidos en el camino (no solo visuales): `CierreDiarioDialog.tsx` mostraba texto roto por una key de i18n mal usada (`t('cierreDiario')` devolvía el objeto del namespace, no un string); `ResolverAlertaButton` tragaba errores 403/red en silencio; `ReimprimirTiquete.tsx` tenía un `<label for>` apuntando a un `<div>` (bug real de accesibilidad, confirmado por Chrome DevTools); varios estados de éxito/warning en modo oscuro eran ilegibles por colores Tailwind sueltos sin variante dark (`IngresoPanel.tsx`, `TiqueteModal.tsx`, `AlertaCard.tsx`, `OcupacionPanel.tsx`, `TurnoActivoToggle.tsx`). Un bug estructural de layout (doble cálculo de alto basado en viewport, `App.tsx` vs `Dashboard.tsx`, sin relación entre sí) causaba scroll de página — corregido con un modelo de alto real acotado (flex + `h-dvh`), no un ajuste de valores mágicos.

Componentes confirmados huérfanos (sin ruta ni import activo hoy, auditados igual por estar en el inventario, no se pudieron validar en vivo): `Principal.tsx`, `MiTurnoPanel.tsx`, `OcupacionPanel.tsx`, `TurnoActivoPanel.tsx`, `TarifaBadge.tsx`. No se eliminaron (fuera del alcance de esta HU decidir si son código muerto a retirar).

Pendiente real, no inventado, requiere decisión del operador: el tiquete de **arqueo** (cierre de turno) nunca imprime de verdad — el bridge de impresión solo manda `{uuid}`, nunca un buffer ESC/POS real, pese a que existe un builder ya armado y testeado (`escposBuilder.buildArqueoBuffer`) sin conectar. Documentado en detalle en memoria de sesión (Engram), no en este plan para no duplicar. Mismo patrón roto en `SalidaMensualidad.tsx`/`PagoSheet.tsx`.

#### HU-F31.4 — Accesibilidad y performance sobre el rediseño

**Historia**: Como operador, quiero que el rediseño no degrade la accesibilidad ni el rendimiento ya exigidos transversalmente por el resto del proyecto (Anexo F/G de Parte I: `axe-core` sin violaciones serias/críticas).

**Alcance**: contraste AA final sobre componentes reales (no solo tokens aislados), navegación por teclado, foco visible en ambos modos, Core Web Vitals (LCP/CLS/INP) antes/después.

**Estado**: no iniciado.

---

**Fin del plan maestro.**
