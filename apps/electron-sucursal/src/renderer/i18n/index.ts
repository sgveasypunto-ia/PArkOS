import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import common from './locales/common.json';
import auth from './locales/auth.json';
import operacion from './locales/operacion.json';
import caja from './locales/caja.json';
import facturacion from './locales/facturacion.json';
import suscripciones from './locales/suscripciones.json';
import alertas from './locales/alertas.json';
import sync from './locales/sync.json';
import errors from './locales/errors.json';

/**
 * i18n bootstrap — 9 namespaces per DEC-ELEC-06 + PR-5 (suscripciones)
 * + PR-6 (alertas). El namespace `reimpresion` (PR-4) se retiró
 * 2026-09-25 junto con la implementación vieja del drawer (que
 * apuntaba a un endpoint inexistente) — el flujo de reimpresión con
 * costo (HU-F8.3, `<ReimprimirTiqueteSheet />`) usa el namespace
 * `facturacion` (mismas claves `reimprimir.*`).
 */
void i18n.use(initReactI18next).init({
  resources: {
    'es-CO': {
      common,
      auth,
      operacion,
      caja,
      facturacion,
      suscripciones,
      alertas,
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
    'suscripciones',
    'alertas',
    'sync',
    'errors',
  ],
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
