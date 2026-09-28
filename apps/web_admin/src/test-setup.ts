import '@testing-library/jest-dom/vitest';
// Initialize i18n with the es-CO locale so `useTranslation()` resolves
// real strings (not just keys) in test assertions. The i18n module
// already calls `init` at import time with the bundled es-CO resource.
import './i18n';
