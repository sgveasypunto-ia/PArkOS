import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './i18n';
import './index.css';
import App from './App';
import { SucursalProvider } from '@/lib/sucursal-context';
import { useInvalidateOnBranchSwitch } from '@/lib/swr-mutate-on-switch';

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
