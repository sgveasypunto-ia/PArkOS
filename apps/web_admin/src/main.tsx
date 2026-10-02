import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './i18n';
import './index.css';
import App from './App';
import { SucursalProvider } from '@/lib/sucursal-context';
import { useInvalidateOnBranchSwitch } from '@/lib/swr-mutate-on-switch';
import { initTheme } from '@/lib/theme';

/**
 * `initTheme()` here is a cheap, idempotent re-apply (the anti-flash
 * script in `index.html` already set the right class before this module
 * even loads) plus it subscribes to live `prefers-color-scheme` changes
 * while the preference is 'system'.
 */
initTheme();

/**
 * AdminShell — root of the admin tree.
 *
 * Mounts the `<SucursalProvider>` so the BranchSelector can read/write
 * the selected branch, and the SWR invalidator hook so every
 * dashboard re-fetch is triggered when the user switches branches.
 */
function AdminShell() {
  useInvalidateOnBranchSwitch();
  return <App />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SucursalProvider>
        <AdminShell />
      </SucursalProvider>
    </BrowserRouter>
  </StrictMode>,
);
