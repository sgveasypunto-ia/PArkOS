/**
 * electron-log configuration wrapper (F2.3 — T5, DEC-UPD-11).
 *
 * Configures:
 *   - File rotation: 10 MB per file × 5 backups (50 MB cap).
 *   - JSON structured format (parseable with `jq`).
 *   - Resolves log path under `userData/logs/main.log` (Windows:
 *     %APPDATA%/parkos/logs/main.log).
 *   - Captures `uncaughtException` + `unhandledRejection` from the
 *     process-level event loop. Called from `main.ts` BEFORE
 *     `app.whenReady()` to capture boot-time crashes.
 */

import path from 'node:path';

/** Per-file rotation cap. 10 MB × 5 backups = 50 MB ceiling. */
export const MAX_SIZE_BYTES = 10 * 1024 * 1024;

/** Number of backup files retained. */
export const MAX_BACKUPS = 5;

/** Minimal log interface — accepts electron-log's default export. */
export interface LogLike {
  transports: {
    file: {
      maxSize: number;
      backups: number;
      resolvePathFn?: () => string;
    };
  };
  formats: { json: string };
  format: string;
  info: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

/** Minimal Electron App interface — only `getPath` is required. */
export interface AppLike {
  getPath: (name: string) => string;
}

export function initLogConfig(logImpl: LogLike, app: AppLike): void {
  logImpl.transports.file.maxSize = MAX_SIZE_BYTES;
  logImpl.transports.file.backups = MAX_BACKUPS;
  logImpl.transports.file.resolvePathFn = (): string =>
    path.join(app.getPath('userData'), 'logs', 'main.log');
  logImpl.format = logImpl.formats.json;

  process.on('uncaughtException', (err) => {
    logImpl.error('uncaughtException', err);
  });
  process.on('unhandledRejection', (reason) => {
    logImpl.error('unhandledRejection', reason);
  });

  logImpl.info('log-config.init', {
    path: path.join(app.getPath('userData'), 'logs', 'main.log'),
    maxSizeBytes: MAX_SIZE_BYTES,
    maxBackups: MAX_BACKUPS,
  });
}