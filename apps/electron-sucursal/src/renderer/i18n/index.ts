import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import common from './locales/common.json';
import auth from './locales/auth.json';
import operacion from './locales/operacion.json';
import caja from './locales/caja.json';
import facturacion from './locales/facturacion.json';
import reimpresion from './locales/reimpresion.json';
import sync from './locales/sync.json';
import errors from './locales/errors.json';

/**
 * i18n bootstrap — 8 namespaces per DEC-ELEC-06 + PR-4 (reimpresion).
 *
 * F2.1 ships the registry with placeholder keys; Fase 3+ populates each
 * namespace as features land. Namespaces follow the bounded contexts
 * declared in proposal.md §6.6.
 */
void i18n.use(initReactI18next).init({
  resources: {
    'es-CO': {
      common,
      auth,
      operacion,
      caja,
      facturacion,
      reimpresion,
      sync,
      errors,
    },
  },
  lng: 'es-CO',
  fallbackLng: 'es-CO',
  defaultNS: 'common',
  ns: [
    'common',
    'auth',
    'operacion',
    'caja',
    'facturacion',
    'reimpresion',
    'sync',
    'errors',
  ],
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
