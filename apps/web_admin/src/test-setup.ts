import '@testing-library/jest-dom/vitest';
// Initialize i18n with the es-CO locale so `useTranslation()` resolves
// real strings (not just keys) in test assertions. The i18n module
// already calls `init` at import time with the bundled es-CO resource.
import './i18n';

// jsdom (Vitest default) doesn't implement the Pointer Capture API
// (hasPointerCapture / releasePointerCapture / setPointerCapture).
// Radix UI primitives call these on every pointer interaction; without
// the polyfill the test crashes inside Radix's select.tsx:371. Real
// browsers always have these methods on Element, so a no-op polyfill
// is safe and matches the production behavior for non-pointer flows.
if (typeof Element !== 'undefined' && !Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.setPointerCapture = () => {};
}

// jsdom doesn't implement scrollIntoView / scrollIntoViewIfNeeded;
// Radix Select calls them on every highlighted option when the
// dropdown opens. Real browsers always have scrollIntoView on
// Element, so a no-op polyfill mirrors that for the test env.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
