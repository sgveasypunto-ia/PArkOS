import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import './i18n';
import './index.css';
import { initTheme } from './lib/theme';

import App from './App';

/**
 * Theme mechanism (Fase 2+3): the inline script in `index.html` already
 * applied the resolved theme before this module even loaded (anti-flash).
 * `initTheme()` here is a cheap, idempotent re-apply plus it subscribes to
 * live `prefers-color-scheme` changes for the rest of the app's lifetime
 * (e.g. the OS switches to dark mode while the window is open). No UI
 * toggle yet — see `src/renderer/lib/theme.ts`.
 */
initTheme();

/**
 * Renderer entry — boots the React tree inside the Electron BrowserWindow.
 *
 * F2.1 ships a router placeholder; F2.2 wires `authStore` and the
 * `<SucursalProvider>` once the IPC seam is populated.
 */
export function Root() {
  return (
    <StrictMode>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </StrictMode>
  );
}

createRoot(document.getElementById('root')!).render(<Root />);
