# Documentación — easypunto_parkos

> Sistema de gestión de parqueaderos con arquitectura multi-tenant cloud-edge y sincronización
> bidireccional entre un nodo cloud y múltiples sucursales, cada una con su propia base de datos
> local. Cumplimiento DIAN (Colombia) para facturación electrónica.

Esta documentación describe **el estado real del proyecto**, verificado contra el código, las
migraciones y la suite de pruebas — no el plan original. Todo lo que aparece marcado como
**[Por definir]** o **[Roadmap]** está planeado pero no implementado todavía, con su fuente citada.

## 00 · General

- [Visión general](00-general/README.md) — qué es el proyecto, para quién, cómo se compone.
- [Roadmap](00-general/roadmap.md) — fases e iteraciones planeadas vs. estado real de avance.
- [Changelog](00-general/changelog.md) — historial de cambios agrupado por época.

## 01 · Requisitos

- [Historias de usuario](01-requisitos/historias-usuario.md)
- [Requisitos funcionales](01-requisitos/funcionales.md)
- [Requisitos no funcionales](01-requisitos/no-funcionales.md) — compliance, seguridad, rendimiento, disponibilidad.

## 02 · Arquitectura

- [Decisiones técnicas (ADR)](02-arquitectura/decisiones-tecnicas.md)
- [Modelo de datos](02-arquitectura/modelo-datos.md) — diccionario completo de las 54 tablas físicas.
- [Seguridad](02-arquitectura/seguridad.md) — autenticación, autorización, pairing, protección de datos.
- Diagramas UML ([`diagramas-uml/`](02-arquitectura/diagramas-uml/)):
  [Casos de uso](02-arquitectura/diagramas-uml/01-casos-uso.mermaid) ·
  [Clases](02-arquitectura/diagramas-uml/02-clases.mermaid) ·
  [Objetos](02-arquitectura/diagramas-uml/03-objetos.mermaid) ·
  [Componentes](02-arquitectura/diagramas-uml/04-componentes.mermaid) ·
  [Despliegue](02-arquitectura/diagramas-uml/05-despliegue.mermaid) ·
  [Secuencia](02-arquitectura/diagramas-uml/06-secuencia.mermaid) ·
  [Actividades](02-arquitectura/diagramas-uml/07-actividades.mermaid) ·
  [Estados](02-arquitectura/diagramas-uml/08-estados.mermaid) ·
  [Temporal](02-arquitectura/diagramas-uml/09-temporal.mermaid)

## 03 · Desarrollo

- [Instalación y ejecución local](03-desarrollo/setup.md)
- [Estándares de código](03-desarrollo/estandares.md)
- [Referencia de API](03-desarrollo/api-reference.md)

## 04 · QA y Testing

- [Plan de pruebas](04-qa-testing/plan-pruebas.md) — estrategia, cobertura real, concurrencia y condiciones de carrera.
- [Casos de prueba](04-qa-testing/casos-prueba.md) — casos reales extraídos de la suite existente.

## 05 · Manuales

- [Manual de usuario final](05-manuales/usuario-final.md) — panel `web_admin`.
- [Manual de operaciones](05-manuales/operaciones.md) — despliegue, variables de entorno, observabilidad.

## Runbooks operacionales

No forman parte de esta generación — ya existían y se mantienen sin modificar:
[`runbooks/sync/`](runbooks/sync/) (backfill_stalled, chain_break, client_volume, conflict_rate,
dependency_wait, import_error, orphan_workflow, sync_backlog). `05-manuales/operaciones.md` los
indexa con el criterio de cuándo usar cada uno.

## Cómo se generó esta documentación

Generada a partir del código, tests y migraciones reales del repositorio (no del plan de
planeación temprana en `openspec/`, que se usó solo como contexto de intención y se contrastó
contra el estado actual). Cada afirmación técnica cita su archivo fuente; los huecos de
información quedan marcados explícitamente en vez de completarse por inferencia.
