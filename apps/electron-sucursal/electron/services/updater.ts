/**
 * electron-updater wrapper (F2.3 — T1, DEC-UPD-01..04).
 *
 * Initializes electron-updater with:
 *   - Feed URL configurable via env.PARKOS_UPDATE_FEED_URL (DEC-UPD-01).
 *   - autoDownload:true + autoInstallOnAppQuit:true (DEC-UPD-02).
 *   - allowDowngrade:false (DEC-UPD-03).
 *   - 5 listeners: update-available / update-not-available / download-progress /
 *     update-downloaded / error (DEC-UPD-04 signature detection).
 *   - Periodic check every 6h (DEC-UPD-01 cadence).
 *
 * Returns an `UpdaterHandle` whose `dispose()` clears the interval. This
 * shape makes the service easy to drive from tests (injected autoUpdater +
 * log) and from production (real electron-updater + electron-log).
 */

/**
 * Minimal subset of `electron-updater`'s AutoUpdater that this module
 * depends on. The structural type keeps tests independent from the real
 * module shape while staying compatible at runtime.
 */
export interface AutoUpdaterLike {
  setFeedURL: (url: string) => void;
  autoDownload: boolean;
  autoInstallOnAppQuit: boolean;
  allowDowngrade: boolean;
  checkForUpdates: () => Promise<unknown>;
  on: (event: string, listener: (...args: unknown[]) => void) => void;
}

/** Minimal logger interface — accepts electron-log's default export. */
export interface LogLike {
  info: (...args: unknown[]) => void;
  debug: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

export interface UpdaterHandle {
  dispose(): void;
}

/** GitHub releases feed used when env.PARKOS_UPDATE_FEED_URL is absent. */
export const DEFAULT_FEED = 'https://github.com/easypunto_parkos/easypunto_parkos/releases';

/** Recurring check cadence — DEC-UPD-01. */
export const DEFAULT_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

function resolveFeedUrl(env: NodeJS.ProcessEnv): string {
  const fromEnv = env['PARKOS_UPDATE_FEED_URL'];
  return typeof fromEnv === 'string' && fromEnv.length > 0 ? fromEnv : DEFAULT_FEED;
}

/**
 * Configure electron-updater and wire 5 listeners. Performs an immediate
 * `checkForUpdates()` and a recurring check on the supplied interval.
 */
export function initUpdater(
  autoUpdater: AutoUpdaterLike,
  env: NodeJS.ProcessEnv,
  log: LogLike,
  checkIntervalMs: number = DEFAULT_CHECK_INTERVAL_MS,
): UpdaterHandle {
  const feedUrl = resolveFeedUrl(env);
  autoUpdater.setFeedURL(feedUrl);
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowDowngrade = false;

  log.info('updater.init', { feedUrl, checkIntervalMs });

  autoUpdater.on('update-available', (info: unknown) => {
    log.info('updater.update-available', { info });
  });
  autoUpdater.on('update-not-available', (info: unknown) => {
    log.debug('updater.update-not-available', { info });
  });
  autoUpdater.on('download-progress', (progress: unknown) => {
    log.debug('updater.download-progress', { progress });
  });
  autoUpdater.on('update-downloaded', (info: unknown) => {
    log.info('updater.update-downloaded', { info });
  });
  autoUpdater.on('error', (err: unknown) => {
    const message = err instanceof Error ? err.message : String(err);
    const isSignature = /signature/i.test(message);
    log.error('updater.error', { message, signature: isSignature });
    // DO NOT install on signature failure — retry next 6h cycle (DEC-UPD-04).
  });

  void autoUpdater.checkForUpdates();
  const intervalId = setInterval(() => {
    void autoUpdater.checkForUpdates();
  }, checkIntervalMs);

  return {
    dispose(): void {
      clearInterval(intervalId);
    },
  };
}