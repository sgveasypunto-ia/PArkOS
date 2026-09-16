import { app, BrowserWindow, ipcMain, Menu, shell } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import path from 'node:path';

import { initUpdater } from './services/updater';
import { initLogConfig } from './services/log-config';
import { initApiStatus, getApiStatus } from './services/api-status';
import { applyKiosko, tryUnlockKiosko, type StoreLike } from './services/kiosko';

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
  const store: StoreLike = {
    get: (key: string): unknown => null,
    set: (key: string, value: unknown): void => {
      log.warn('kiosko.store.unbacked_write', { key, type: typeof value });
    },
  };
  if (process.env['PARKOS_KIOSK_MODE'] === '1' && mainWindow) {
    applyKiosko(mainWindow, Menu, true, log);
  }

  registerIpcHandlers(store);
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
