import { contextBridge } from 'electron';

/**
 * Preload — exposes a typed bridge to the renderer via contextBridge.
 *
 * F2.1 ships an EMPTY placeholder (`window.bridge = {}`). F2.2 expands
 * the surface with `{imprimir, usb, app, kiosk, apiStatus}` per
 * DEC-ELEC-10 and proposal.md §9.1. Keeping the contract empty here
 * means F2.1 has zero behavior to ship, only the IPC seam.
 */
contextBridge.exposeInMainWorld('bridge', {});
