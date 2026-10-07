/**
 * `<AvisosImpresion />` — non-blocking notices for prints that failed
 * ("No se pudo imprimir …") with "Reintentar". Mounted once in `App`; the
 * flows that print (cierre, tiquete, factura) never wait on it.
 */
import { useAvisosImpresion } from '../../lib/print/avisoImpresion';

export function AvisosImpresion(): JSX.Element | null {
  const avisos = useAvisosImpresion((s) => s.avisos);
  const descartar = useAvisosImpresion((s) => s.descartar);
  if (avisos.length === 0) return null;
  return (
    <div
      className="pointer-events-none fixed bottom-10 right-4 z-[100] flex max-w-sm flex-col gap-2"
      data-testid="avisos-impresion"
    >
      {avisos.map((a) => (
        <div
          key={a.id}
          role="alert"
          className="pointer-events-auto rounded border border-destructive bg-background p-3 text-sm shadow-lg"
        >
          <p className="font-medium text-destructive">{a.mensaje}</p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="rounded border border-input px-2 py-1 text-xs hover:bg-muted"
              onClick={() => {
                void a.reintentar();
              }}
            >
              Reintentar
            </button>
            <button
              type="button"
              className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
              onClick={() => descartar(a.id)}
            >
              Cerrar
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
