import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
 * Most of the app fetches data with `useSWR`, but a handful of features
 * (e.g. `ArqueosPage`'s `useQueries`) use `@tanstack/react-query` directly.
 * Those hooks need a `QueryClient` in context — without this provider they
 * crash with "No QueryClient set, use QueryClientProvider to set one."
 * Default options are fine here; nothing in the react-query usage so far
 * needs a non-default retry/staleTime policy.
 */
const queryClient = new QueryClient();

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
      <QueryClientProvider client={queryClient}>
        <SucursalProvider>
          <AdminShell />
        </SucursalProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
);
