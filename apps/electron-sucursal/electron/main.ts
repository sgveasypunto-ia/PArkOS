import { app, BrowserWindow, ipcMain, Menu, shell } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import path from 'node:path';
import Store from 'electron-store';

import { initUpdater } from './services/updater';
import { initLogConfig } from './services/log-config';
import { initApiStatus, getApiStatus } from './services/api-status';
import { applyKiosko, tryUnlockKiosko, type StoreLike } from './services/kiosko';
import { PrintQueue } from './services/printQueue';
import { print, mapEscposError, PrinterError } from './services/printer';
import { registerImprimirHandlers } from './ipc/imprimir';

const isDev = !app.isPackaged;

// DEC-UPD-07: SINGLE-INSTANCE LOCK — before any other init so a second
// invocation never touches the filesystem of the primary process.
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

// DEC-UPD-11: configure electron-log rotation BEFORE any other init so we
// capture boot-time crashes (uncaughtException / unhandledRejection).
initLogConfig(log, app);
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