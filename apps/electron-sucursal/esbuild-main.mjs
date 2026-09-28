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
 *
 * `usb` (HU-F5.1 thermal printer USB detection, pulled in via
 * `escpos-usb`) ships a native `.node` binding
 * (`@node-usb/usb-win32-x64-msvc`) that esbuild cannot bundle - no loader
 * exists for compiled binary files. Marking it external leaves
 * `require('usb')` untouched in the bundled output; Node resolves it from
 * `node_modules` at runtime, same as it always does for native addons.
 */

const watch = process.argv.includes('--watch');

const common = {
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node20',
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
