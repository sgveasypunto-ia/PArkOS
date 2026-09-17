import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import common from './locales/common.json';
import auth from './locales/auth.json';
import operacion from './locales/operacion.json';
import caja from './locales/caja.json';
import facturacion from './locales/facturacion.json';
import reimpresion from './locales/reimpresion.json';
import suscripciones from './locales/suscripciones.json';
import sync from './locales/sync.json';
import errors from './locales/errors.json';

/**
 * i18n bootstrap — 9 namespaces per DEC-ELEC-06 + PR-4 (reimpresion)
 * + PR-5 (suscripciones).
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
      suscripciones,
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
    'suscripciones',
    'sync',
    'errors',
  ],
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
