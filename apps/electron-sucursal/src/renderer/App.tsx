import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

/**
 * App — F2.1 placeholder router.
 *
 * The root renders a semantic `<main>` with one `<h1>` so axe-core's
 * WCAG 2.1 AA audit (RNF-022) is satisfied from day one. Subsequent
 * HU (F2.2+, F3.x) attach their routes here.
 */
export default function App() {
  const { t } = useTranslation('common');

  return (
    <main lang="es-CO">
      <h1>{t('appName')}</h1>
      <p>{t('bootstrapNotice')}</p>
      <Routes>
        <Route path="/" element={null} />
        <Route
          path="*"
          element={
            <p role="status">{t('error', { defaultValue: '404' })}</p>
          }
        />
      </Routes>
    </main>
  );
}
