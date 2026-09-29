/**
 * `EmpresaBitacoraTab` — placeholder para T5 (HU-F15.2).
 * En T5 se llena con la lista de cambios del singleton Empresa
 * (filtrados por `log_transaccional.tabla_afectada = 'empresa'`) +
 * badge `HashChainStatus` por fila.
 */
export function EmpresaBitacoraTab(): JSX.Element {
  return (
    <section
      aria-label="Bitácora de cambios"
      data-testid="empresa-bitacora-placeholder"
      className="text-sm text-muted-foreground"
    >
      Bitácora de cambios con hash chain (T5).
    </section>
  );
}
