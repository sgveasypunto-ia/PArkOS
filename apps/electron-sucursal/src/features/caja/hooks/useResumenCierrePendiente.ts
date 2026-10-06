/**
 * `useResumenCierrePendiente` — tiny Zustand flag (PT-5).
 *
 * `true` from the moment the sesion is closed on the backend until the
 * operator dismisses the read-only post-close summary (which is when the
 * deferred logout runs). While it is `true` the Dashboard must NOT redirect
 * to "abrir turno" when `GET /caja-sesion/sesion/me` starts answering 404
 * (SWR revalidates on window focus, e.g. right after the PDF download
 * dialog) — that redirect would unmount the summary.
 */
import { create } from 'zustand';

interface ResumenCierrePendienteState {
  pendiente: boolean;
  setPendiente: (value: boolean) => void;
}

export const useResumenCierrePendiente = create<ResumenCierrePendienteState>((set) => ({
  pendiente: false,
  setPendiente: (value) => set({ pendiente: value }),
}));
