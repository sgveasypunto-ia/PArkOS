# Procedimiento: documentos compensatorios ante un consecutivo duplicado

> **ESTADO: BORRADOR — PENDIENTE DE DECISIÓN DEL CONTADOR.**
> Este documento propone una ruta; no es una instrucción vigente. Ninguna de las acciones aquí
> descritas se ejecuta hasta que el contador legal responda las decisiones de la sección 5.

**Audiencia**: contador legal de la empresa. Apoyo técnico: equipo de ingeniería.
**Ubicación**: esta nota vive en `05-manuales` porque no existe una carpeta `05-operacion`; los
runbooks técnicos están en [`../runbooks/`](../runbooks/).

## 1. Hechos

- En el entorno de desarrollo, dos facturas electrónicas distintas quedaron con el **mismo
  consecutivo (1) dentro de la misma resolución de facturación**: una emitida desde la nube y otra
  emitida desde la sucursal.
- La numeración de facturas es **local a la sucursal**: cada sucursal asigna el consecutivo dentro
  del rango autorizado de su resolución, y la nube solo valida y reenvía a la DIAN. La base de datos
  lo hace cumplir con una restricción de unicidad sobre `(resolución, consecutivo)`.
- Como la restricción rechazó la segunda copia al sincronizar, **dos filas de la cola de
  sincronización quedaron atascadas**: nunca se aplicaban y se reintentaban sin fin.
- Causa: la ruta de emisión en la nube asignaba un consecutivo dentro de una resolución que
  pertenece a una sucursal. Esa ruta ya fue cerrada (la nube se niega a numerar). Desde esta
  corrección, una colisión que llegue por sincronización queda registrada como **conflicto
  recuperable** (registro `sync_conflict` de política `consecutivo_duplicado` y una alerta
  `fe_consecutivo_duplicado`), en lugar de reintentarse indefinidamente.
- Los dos documentos existentes se conservan **sin cambios**.

## 2. Por qué no se pueden alterar las filas existentes

- Las facturas electrónicas y sus envíos a la DIAN son registros **inmutables** (clase `[A]`):
  el rol de la aplicación no tiene permiso de modificar ni borrar, y un disparador en la base de
  datos bloquea cualquier cambio fuera de las rutas permitidas.
- Los documentos cuentan con **cadena de hash** por sucursal (`hash_anterior` / `hash_actual`):
  alterar una fila rompe la verificación de toda la cadena posterior.
- Aplican la **retención mínima de cinco años** y el principio de **borrado solo lógico**: una
  corrección se expresa como un registro nuevo que compensa al anterior, nunca como una edición
  ni una eliminación.
- Renumerar uno de los dos documentos equivaldría a modificar un documento ya emitido; no es una
  opción técnica ni contable.

## 3. Ruta compensatoria propuesta

Pendiente de aprobación del contador (sección 5):

1. **Identificar** cuál de los dos documentos se considera el válido (el que conserva el
   consecutivo) y cuál debe compensarse.
2. **Emitir una nota crédito** (o el documento compensatorio que el contador determine) que
   anule contablemente el documento a compensar, con **referencia explícita al documento
   original** (su CUFE o identificador interno).
3. **Emitir el documento de reemplazo** con un **consecutivo nuevo tomado del rango de la
   sucursal** (numeración local, dentro de la resolución vigente), vinculado al original.
4. **Enviar a la DIAN** ambos documentos nuevos por el flujo normal (la nube valida el consecutivo
   contra el rango autorizado y reenvía).
5. **Cerrar la alerta** `fe_consecutivo_duplicado` dejando constancia de la decisión y de los
   documentos que la resolvieron. La fila de conflicto no se borra: queda como evidencia.

## 4. Qué debe decidir el contador

1. ¿Es válida la ruta nota crédito + documento de reemplazo, o corresponde otro documento
   compensatorio?
2. ¿Qué documento de los dos se conserva y cuál se compensa?
3. ¿Se requiere autorización o comunicación previa a la DIAN, o un concepto formal, por tratarse
   de dos documentos con el mismo número?
4. ¿Los documentos de este caso fueron emitidos en un entorno de pruebas (sin efecto tributario)?
   Si es así, ¿basta con documentar el caso y no emitir compensatorios?
5. ¿Qué texto de motivo y qué referencias deben llevar los documentos compensatorios?

## 5. Qué hará ingeniería tras la decisión

- Implementar, solo si la decisión lo exige, el flujo de emisión del documento compensatorio con
  vínculo al original y consecutivo local nuevo, con pruebas.
- Resolver el conflicto y la alerta con la anotación de la decisión, sin tocar los registros
  inmutables.
- Verificar que las dos filas de la cola de sincronización queden asentadas como conflicto
  (y no reintentándose) y que la cadena de hash se mantenga íntegra.
- Actualizar este documento de borrador a procedimiento vigente, con la fecha y el responsable
  de la aprobación.

## 6. Registros históricos sin modificar

> **Pendiente de decisión del contador**: estos registros se documentan, **no se reparan**.

Se identificaron dos conjuntos históricos que **permanecen intactos**:

1. **Pagos históricos sin sesión de caja**: filas de `factura_pagos` cuya sesión (`uuid_sesion`)
   es nula, anteriores a que la sesión fuera obligatoria al registrar un pago.
2. **28 registros de envío DIAN cerrados por un barrido**: filas de `envio_dian` que quedaron en
   curso porque el proceso de envío se interrumpió, y que el barrido de recuperación cerró
   agregando una fila de error de interrupción. El conteo (28) es el observado al redactar este
   borrador y debe reconfirmarse con la consulta de abajo.

**Regla de inmutabilidad que los mantiene intactos**: ambas tablas son `[A]` (solo inserción).
No se permite `UPDATE` ni `DELETE` por permisos del rol de la aplicación y por disparador
`BEFORE UPDATE OR DELETE`; cualquier corrección se expresaría como filas nuevas compensatorias
en una tabla de flujo de trabajo, y solo después de la decisión del contador. Nunca se
reasignará sesión a un pago histórico ni se reescribirá un envío cerrado.

**Consultas de solo lectura** (ejecutar con un rol de consulta; no modifican datos):

```sql
-- Pagos históricos sin sesión
SELECT uuid, uuid_sucursal, uuid_factura, medio_pago, valor, timestamp_evento
FROM prod.factura_pagos
WHERE uuid_sesion IS NULL
ORDER BY timestamp_evento;

-- Envíos DIAN cerrados por el barrido por interrupción del proceso
SELECT uuid, uuid_factura_electronica, estado, timestamp_evento,
       respuesta_proveedor->>'motivo_rechazo' AS motivo
FROM prod.envio_dian
WHERE payload->>'interrupted' = 'true'
  AND respuesta_proveedor->>'motivo_rechazo' LIKE 'dispatch_interrupted:%'
ORDER BY timestamp_evento;
```

Nota: el criterio del segundo listado (`payload.interrupted` y el motivo
`dispatch_interrupted`) es el que escribe el código del barrido (`_close_orphan` en el
despachador DIAN). Ingeniería debe confirmar que el resultado coincide con las 28 filas
reportadas antes de citar la cifra ante terceros.
