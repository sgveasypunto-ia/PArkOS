/**
 * `EmpresaMensajesTab` — placeholder para T4 (HU-F15.2).
 * En T4 se llena con los textareas para `mensaje_bienvenida` y
 * `mensaje_salida` + preview de ticket (placeholder, no toca
 * `web_sucursal`).
 */
export function EmpresaMensajesTab(): JSX.Element {
  return (
    <section
      aria-label="Mensajes de ticket"
      data-testid="empresa-mensajes-placeholder"
      className="text-sm text-muted-foreground"
    >
      Form de mensajes de ticket (T4).
    </section>
  );
}
