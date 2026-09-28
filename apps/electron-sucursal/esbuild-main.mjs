import { build, context } from 'esbuild';
import process from 'node:process';

/**
 * esbuild config — bundles Electron's main + preload processes to CJS.
 *
 * Output:
 *   - out/main.js     (entryPoint: electron/main.ts)
 *   - out/preload.js  (entryPoint: electron/preload.ts)
 *
 * Both targets:
 *   - target: node20 (matches Electron 30 Node runtime)
 *   - format: cjs    (Electron's main process expects CommonJS)
 *   - external: electron (Node-builtin and Electron itself stay external)
 *   - bundle: true   (esbuild resolves all TS source into a single file)
 *
 * DEC-ELEC-03: vite owns the renderer, esbuild owns main+preload.
 */

const watch = process.argv.includes('--watch');

const common = {
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node20',
  // `electron` is provided by the runtime. The printer chain must stay
  // external too: `electron/services/printer.ts` statically imports
  // `escpos-usb`, which depends on `usb` -> `@node-usb/usb-win32-*`, and
  // that package ships a platform-compiled `.node` addon. esbuild cannot
  // bundle a native addon, so the whole chain is left external and Node
  // resolves it from node_modules at runtime. Without this the main build
  // fails with: "No loader is configured for .node files".
  external: ['electron', 'escpos-usb', 'usb', '@node-usb/*', '*.node'],
  logLevel: 'info',
  sourcemap: true,
};

async function buildMain() {
  const opts = {
    ...common,
    entryPoints: ['electron/main.ts'],
    outfile: 'out/main.js',
  };
  if (watch) {
    const ctx = await context(opts);
    await ctx.watch();
  } else {
    await build(opts);
  }
}

async function buildPreload() {
  const opts = {
    ...common,
    entryPoints: ['electron/preload.ts'],
    outfile: 'out/preload.js',
  };
  if (watch) {
    const ctx = await context(opts);
    await ctx.watch();
  } else {
    await build(opts);
  }
}

await Promise.all([buildMain(), buildPreload()]);
