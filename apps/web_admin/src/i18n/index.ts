import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import esCO from './locales/es-CO.json';

void i18n.use(initReactI18next).init({
  resources: {
    'es-CO': { translation: esCO },
  },
  lng: 'es-CO',
  fallbackLng: 'es-CO',
  defaultNS: 'translation',
  // Dot-path keys: `auth.email` resolves through the `translation`
  // namespace which has `auth` as a nested object. We don't declare
  // a separate `auth` namespace — the JSON stays a single source
  // of truth and components either use the default namespace
  // (`useTranslation()`) and dot-path keys, or split into their own
  // namespace if the bundle grows.
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
