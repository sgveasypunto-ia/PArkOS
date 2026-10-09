# Flujo de turno — Sucursal (v1.0)

Parqueadero con atención por turnos. El control de caja se hace **solo sobre el efectivo**; el datáfono queda en base de datos para auditoría y no entra al conteo ni al cuadre.

## Conceptos

- **Base de caja**: efectivo fijo con el que abre cada turno. Es un parámetro de la sucursal (`configuracion_caja.base_inicial_sugerida`: override por sucursal o default global), configurado en `web_admin` y replicado a la sucursal por sync (`cloud_to_branch`). El operador no la digita.
- **Producido** = efectivo contado al cierre − base de caja. Es un valor derivado (no se almacena como estado); un faltante se informa en negativo.
- **Base entregada**: la base con la que abrió el turno; pasa al siguiente operador.

## Pasos

1. El operador inicia sesión y abre turno. El servidor resuelve la base de la sucursal y la registra en `sesion.valor_inicial_efectivo` (el valor que envíe el cliente solo se usa si la sucursal no tiene base configurada). El datáfono inicial es siempre 0.
2. Durante el turno, cada ingreso/salida se cobra en efectivo (entra a caja) o datáfono (solo BD).
3. Al cerrar, el operador cuenta el efectivo a ciegas (no ve el esperado) y la pantalla le muestra el **producido a consignar** (contado − base).
4. Al confirmar, el sistema registra el arqueo, compara el conteo contra el esperado del servidor (tolerancia + alerta `descuadre_critico`) y cierra el turno. El log de cierre incluye `base_entregada` y `producido`.
5. El resumen posterior muestra base, esperado, contado, diferencia, producido consignado y base entregada al siguiente turno.
6. El siguiente operador abre turno y recibe la misma base parametrizada.

## Decisiones

- El paso "datáfono acumulado" del documento de negocio se **ignora** (decisión del usuario): no se digita, no se muestra ni se compara en el cierre.
- Producido y base entregada se derivan; no hay migración de columnas en `sesion`.

## Pendiente (fuera de alcance)

- `PUT /caja-sesion/sesion/{uuid}/cerrar` no exige que exista un arqueo: hoy el cliente encadena ambas llamadas. Acoplarlo en el servidor requiere una decisión aparte.
