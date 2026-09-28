/**
 * `Tarifas.tsx` — placeholder; D-02.3 ships the real implementation.
 *
 * Renders the page shell so the route is navigable in this commit (the
 * shared commit wires `App.tsx` with the route + the `ADMIN_SECTIONS`
 * entry + the i18n strings; the test layer references `data-testid=
 * "page-tarifas"`).
 */
export default function Tarifas(): JSX.Element {
  return (
    <main
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-tarifas"
    >
      <h1 className="text-2xl font-semibold">Tarifas</h1>
      <p className="text-sm text-muted-foreground">PR-D.3 — implementación pendiente.</p>
    </main>
  );
}
