import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import './i18n';
import './index.css';

import App from './App';

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
