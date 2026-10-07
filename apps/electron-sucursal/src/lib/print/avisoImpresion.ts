/**
 * `avisoImpresion.ts` — a failed print is never silent and never blocking.
 *
 * Every caller of `bridge.imprimir` goes through `ejecutarImpresion(etiqueta,
 * fn)`: it runs the print, swallows any rejection and, when the document did
 * not print, leaves a non-blocking Spanish notice ("No se pudo imprimir …")
 * with a "Reintentar" action in `useAvisosImpresion`. `<AvisosImpresion />`
 * (mounted once in `App`) renders those notices. The caller's own flow (closing
 * the drawer, closing the turno) never waits on, nor depends on, the outcome.
 */
import { create } from 'zustand';

import type { ResultadoImpresion } from './facturaPrint';

export interface AvisoImpresion {
  id: string;
  /** Document label the notice belongs to; a later print of the same label supersedes it. */
  etiqueta: string;
  mensaje: string;
  /** Re-runs the same print; resolves the outcome (the notice clears on success). */
  reintentar: () => Promise<ResultadoImpresion>;
}

interface AvisosState {
  avisos: AvisoImpresion[];
  agregar: (aviso: AvisoImpresion) => void;
  descartar: (id: string) => void;
}

export const useAvisosImpresion = create<AvisosState>((set) => ({
  avisos: [],
  agregar: (aviso) => set((s) => ({ avisos: [...s.avisos, aviso] })),
  descartar: (id) => set((s) => ({ avisos: s.avisos.filter((a) => a.id !== id) })),
}));

let contador = 0;

type ImpresionFn = () => Promise<{ ok: boolean; motivo?: string }>;

/**
 * Run `fn` (a print attempt). Never throws. On failure registers one notice
 * (`reintentar` replaces it, so retries never stack duplicates).
 */
export async function ejecutarImpresion(
  etiqueta: string,
  fn: ImpresionFn,
  reemplazaId?: string,
): Promise<ResultadoImpresion> {
  let res: ResultadoImpresion;
  try {
    const r = await fn();
    res = r && r.ok === false ? { ok: false, motivo: r.motivo ?? 'print_failed' } : { ok: true };
  } catch (err) {
    console.warn(`[imprimir] ${etiqueta}: falló la impresión`, err);
    res = { ok: false, motivo: 'excepcion' };
  }
  const { agregar, descartar } = useAvisosImpresion.getState();
  if (reemplazaId !== undefined) descartar(reemplazaId);
  // A new outcome for the same document supersedes any earlier notice of it: a
  // success clears a stale failure, a new failure replaces (never stacks) it.
  for (const previo of useAvisosImpresion.getState().avisos) {
    if (previo.etiqueta === etiqueta) descartar(previo.id);
  }
  if (!res.ok) {
    contador += 1;
    const id = `aviso-impresion-${contador}`;
    agregar({
      id,
      etiqueta,
      mensaje: `No se pudo imprimir ${etiqueta}. Revise la impresora y reintente.`,
      reintentar: () => ejecutarImpresion(etiqueta, fn, id),
    });
  }
  return res;
}
