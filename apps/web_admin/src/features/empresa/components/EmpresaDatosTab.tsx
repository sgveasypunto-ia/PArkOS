/**
 * `EmpresaDatosTab` — placeholder para T4 (HU-F15.2).
 * En T4 se llena con el form de `nombre`, `nit` (con validación
 * módulo 11 inline) y `regimen` + integración con
 * `useEmpresa`/`updateEmpresa`.
 */
export function EmpresaDatosTab(): JSX.Element {
  return (
    <section
      aria-label="Datos de la empresa"
      data-testid="empresa-datos-placeholder"
      className="text-sm text-muted-foreground"
    >
      Form de datos (T4).
    </section>
  );
}
