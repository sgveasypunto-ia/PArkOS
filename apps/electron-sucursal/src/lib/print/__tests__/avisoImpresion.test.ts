/**
 * Fallos de impresión visibles: un aviso no bloqueante con reintento. Nunca
 * lanza y nunca impide que el flujo (cierre, drawer) continúe.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ejecutarImpresion, useAvisosImpresion } from '../avisoImpresion';

describe('ejecutarImpresion', () => {
  beforeEach(() => {
    useAvisosImpresion.setState({ avisos: [] });
  });

  it('éxito: devuelve ok y no deja aviso', async () => {
    const res = await ejecutarImpresion('el tiquete', async () => ({ ok: true }));
    expect(res.ok).toBe(true);
    expect(useAvisosImpresion.getState().avisos).toHaveLength(0);
  });

  it('ok=false: deja un aviso en español con el motivo; no lanza', async () => {
    const res = await ejecutarImpresion('el tiquete', async () => ({ ok: false, motivo: 'printer_offline' }));
    expect(res.ok).toBe(false);
    const [aviso] = useAvisosImpresion.getState().avisos;
    expect(aviso?.mensaje).toMatch(/^No se pudo imprimir el tiquete/);
  });

  it('rechazo: lo captura y avisa', async () => {
    const res = await ejecutarImpresion('el cierre de turno', async () => {
      throw new Error('boom');
    });
    expect(res.ok).toBe(false);
    expect(useAvisosImpresion.getState().avisos[0]?.mensaje).toContain('el cierre de turno');
  });

  it('reintentar vuelve a ejecutar; al tener éxito el aviso desaparece', async () => {
    const fn = vi
      .fn<() => Promise<{ ok: boolean }>>()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true });
    await ejecutarImpresion('el tiquete', fn);
    const [aviso] = useAvisosImpresion.getState().avisos;
    await aviso!.reintentar();
    expect(fn).toHaveBeenCalledTimes(2);
    expect(useAvisosImpresion.getState().avisos).toHaveLength(0);
  });

  it('reintento que vuelve a fallar deja un solo aviso (sin duplicar)', async () => {
    const fn = vi.fn(async () => ({ ok: false }));
    await ejecutarImpresion('el tiquete', fn);
    await useAvisosImpresion.getState().avisos[0]!.reintentar();
    expect(useAvisosImpresion.getState().avisos).toHaveLength(1);
  });

  it('descartar quita el aviso', async () => {
    await ejecutarImpresion('el tiquete', async () => ({ ok: false }));
    const [aviso] = useAvisosImpresion.getState().avisos;
    useAvisosImpresion.getState().descartar(aviso!.id);
    expect(useAvisosImpresion.getState().avisos).toHaveLength(0);
  });
});
