import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';
import { Login } from '../features/auth/pages/Login';

/**
 * App — F2.1 placeholder router + F2.3 StatusBar mount + F3.1 Login route.
 *
 * The root renders a semantic `<main>` with one `<h1>` so axe-core's
 * WCAG 2.1 AA audit (RNF-022) is satisfied from day one. Subsequent
 * HU (F2.2+, F3.x) attach their routes here. F2.3 mounts the
 * `<StatusBar />` above `<main>` so backend health is always visible
 * (DEC-UPD-12). F3.1 añade `<Route path="/login">` — entry point del
 * flujo de autenticación (post-`POST /auth/login` con credentials:'include',
 * `useAuth()` hidrata y redirige a `/` con `user` resuelto, sin flash).
 */
export default function App() {
  const { t } = useTranslation('common');

  return (
    <>
      <StatusBar />
      <main lang="es-CO">
        <h1>{t('appName')}</h1>
        <p>{t('bootstrapNotice')}</p>
        <Routes>
          <Route path="/" element={null} />
          <Route path="/login" element={<Login />} />
          <Route
            path="*"
            element={
              <p role="status">{t('error', { defaultValue: '404' })}</p>
            }
          />
        </Routes>
      </main>
    </>
  );
}
