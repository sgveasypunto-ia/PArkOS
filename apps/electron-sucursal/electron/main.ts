import { app, BrowserWindow, ipcMain, Menu, shell } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import path from 'node:path';
import Store from 'electron-store';

import { initUpdater } from './services/updater';
import { initLogConfig, type LogLike, type AppLike } from './services/log-config';
import { initApiStatus, getApiStatus } from './services/api-status';
import { applyKiosko, tryUnlockKiosko, type StoreLike } from './services/kiosko';
import { PrintQueue } from './services/printQueue';
import { print, mapEscposError, PrinterError } from './services/printer';
import { registerImprimirHandlers } from './ipc/imprimir';
import {
  readTarifasValue,
  writeTarifasValue,
  removeTarifasValue,
} from './services/tarifas-store';

const isDev = !app.isPackaged;

// DEC-UPD-07: SINGLE-INSTANCE LOCK — before any other init so a second
// invocation never touches the filesystem of the primary process.
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

// DEC-UPD-11: configure electron-log rotation BEFORE any other init so we
// capture boot-time crashes (uncaughtException / unhandledRejection).
//
// `initLogConfig` (electron/services/log-config.ts, out of scope for this
// fix batch) types its two parameters against interfaces that don't
// actually match the real APIs they wrap — this is NOT a stale `@types`
// version mismatch, both gaps are confirmed against the installed
// packages' own type declarations:
//
//   - `LogLike` declares a top-level `formats: { json: string }` +
//     `format: string`, plus `transports.file.backups: number`. Real
//     electron-log 5.4.4 (node_modules/electron-log/src/index.d.ts) has
//     NEITHER a top-level `formats`/`format` (its only "format" knob is
//     per-transport: `log.transports.file.format`, see the package
//     README, "You can set transport options...") NOR a `backups`
//     rotation-count option anywhere (exceeding `maxSize` keeps exactly
//     one `<name>.old.log`, not a configurable count).
//   - `AppLike.getPath: (name: string) => string` accepts ANY string,
//     but Electron's real `app.getPath` only accepts a fixed literal
//     union of path names and throws for anything else.
//
// Passing `log`/`app` straight through both fails to type-check AND
// would throw at runtime the instant `initLogConfig` read
// `logImpl.formats.json` (`Cannot read properties of undefined`) —
// before either exception handler below is even registered, crashing
// app boot outright. Adapt at this boundary instead of weakening the
// types: forward real behavior for everything `initLogConfig` actually
// uses (maxSize/resolvePathFn land on the real file transport; format
// triggers the real per-transport JSON formatter; getPath forwards to
// the real Electron API for every name Electron actually supports), and
// fail loudly — not silently via `any`/a cast — for the one input shape
// neither real API supports (`backups`, unsupported `getPath` names).
type AppPathName = Parameters<typeof app.getPath>[0];
const APP_PATH_NAMES: readonly AppPathName[] = [
  'home', 'appData', 'userData', 'sessionData', 'temp', 'exe', 'module',
  'desktop', 'documents', 'downloads', 'music', 'pictures', 'videos',
  'recent', 'logs', 'crashDumps',
];
function isAppPathName(name: string): name is AppPathName {
  return (APP_PATH_NAMES as readonly string[]).includes(name);
}
const appConfigAdapter: AppLike = {
  getPath: (name: string): string => {
    if (!isAppPathName(name)) {
      throw new Error(`Unsupported Electron app.getPath name: "${name}"`);
    }
    return app.getPath(name);
  },
};

const logConfigAdapter: LogLike = {
  transports: {
    file: {
      get maxSize() {
        return log.transports.file.maxSize;
      },
      set maxSize(value: number) {
        log.transports.file.maxSize = value;
      },
      // electron-log has no `backups` (rotation-count) option — inert
      // placeholder, see comment above.
      backups: 0,
      get resolvePathFn(): (() => string) | undefined {
        return undefined;
      },
      set resolvePathFn(fn: (() => string) | undefined) {
        if (fn) log.transports.file.resolvePathFn = fn;
      },
    },
  },
  formats: { json: 'json' },
  get format(): string {
    return 'json';
  },
  set format(_value: string) {
    log.transports.file.format = (params) => [
      JSON.stringify({
        date: params.message.date.toISOString(),
        level: params.level,
        data: params.data,
      }),
    ];
  },
  info: (...args: unknown[]) => log.info(...args),
  error: (...args: unknown[]) => log.error(...args),
};
initLogConfig(logConfigAdapter, appConfigAdapter);
process.on('uncaughtException', (err) => log.error('uncaughtException', err));
process.on('unhandledRejection', (reason) => log.error('unhandledRejection', reason));

// DEC-UPD-07: SECOND-INSTANCE LISTENER — focus the existing window when a
// second invocation tries to start; prevents DB / lock races.
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

let mainWindow: BrowserWindow | null = null;

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    title: 'Parkos Sucursal',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // External links open in the OS browser, not in-app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    void mainWindow.loadURL('http://localhost:5173');
  } else {
    void mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'renderer', 'index.html'));
  }
}

// Single, named electron-store instance shared by kiosko + F5.1 queue.
// (F5.1 T3.3: previously the kiosko handler received an inline stub;
// replacing it with the real store is harmless because kiosko only
// reads/writes the `kiosk.*` keys and PrintQueue only reads/writes
// the `parkos.print.queue.v1` key — they do not overlap.)
const electronStore = new Store();

const printQueue = new PrintQueue(
  electronStore,
  log,
  async (item) => {
    const buf = Buffer.from(item.buffer, 'base64');
    try {
      await print(buf, item.vid, item.pid, log);
    } catch (err) {
      if (err instanceof PrinterError) throw err;
      throw new PrinterError(mapEscposError(err), String(err), { cause: err });
    }
  },
  (event) => {
    mainWindow?.webContents.send('print:status', event);
  },
);

app.whenReady().then(() => {
  initUpdater(autoUpdater, process.env, log);
  initApiStatus(
    process.env['PARKOS_API_BASE'] ?? 'http://127.0.0.1:8000/health',
    30_000,
    5_000,
    log,
  );
  createMainWindow();

  // DEC-UPD-08: kiosko mode is a deploy-time decision (env var), not an
  // operator toggle. Activating it locks the window into full-screen
  // and blocks Ctrl+W / Alt+F4.
  const kioskoStore: StoreLike = electronStore;
  if (process.env['PARKOS_KIOSK_MODE'] === '1' && mainWindow) {
    applyKiosko(mainWindow, Menu, true, log);
  }

  // F5.1 — wire the print IPC handlers BEFORE the legacy `registerIpcHandlers`
  // so the same `ipcMain.handle` batch contains both new and legacy channels.
  registerImprimirHandlers({ ipcMain, queue: printQueue, mainWindow, log });
  registerIpcHandlers(kioskoStore);
  printQueue.start();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

function registerIpcHandlers(kioskoStore: StoreLike): void {
  ipcMain.handle('api:status', () => getApiStatus());
  ipcMain.handle('kiosk:unlock', (_e, pin: string) =>
    tryUnlockKiosko(pin, kioskoStore, log),
  );
  ipcMain.on('kiosk:toggle', (_e, on: boolean) => {
    if (!mainWindow) return;
    if (on) {
      applyKiosko(mainWindow, Menu, true, log);
    } else {
      mainWindow.setKiosk(false);
      Menu.setApplicationMenu(null);
    }
  });
  ipcMain.on('app:quit', () => app.quit());

  // F4.2 (2026-09-17 closure) — wire IPC handlers for the tarifas electron-store
  // cache layer. Thin shells that delegate to `services/tarifas-store.ts`
  // (mirrors `tryUnlockKiosko` precedent — persistence logic in a unit-testable
  // service module, IPC handler is the contract carrier). The service module
  // is JSON-string-safe (defensive coercion) and a no-op for missing keys.
  ipcMain.handle('tarifas-store:get', (_e, key: string) =>
    readTarifasValue(kioskoStore, key),
  );
  ipcMain.handle('tarifas-store:set', (_e, key: string, value: string) => {
    writeTarifasValue(kioskoStore, key, value);
  });
  ipcMain.handle('tarifas-store:delete', (_e, key: string) => {
    removeTarifasValue(kioskoStore, key);
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  // F5.1 — cancel the drain timer so the process can exit cleanly even
  // if the OS is mid-sleep when the user clicks "Quit".
  printQueue.stop();
});