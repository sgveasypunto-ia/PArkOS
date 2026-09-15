import { app, BrowserWindow, ipcMain, shell } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import path from 'node:path';

import { initUpdater } from './services/updater';
import { initLogConfig } from './services/log-config';
import { initApiStatus, getApiStatus } from './services/api-status';

const isDev = !app.isPackaged;

// DEC-UPD-11: configure electron-log rotation BEFORE any other init so we
// capture boot-time crashes (uncaughtException / unhandledRejection).
initLogConfig(log, app);
process.on('uncaughtException', (err) => log.error('uncaughtException', err));
process.on('unhandledRejection', (reason) => log.error('unhandledRejection', reason));

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
  registerIpcHandlers();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

function registerIpcHandlers(): void {
  ipcMain.handle('api:status', () => getApiStatus());
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
