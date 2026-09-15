/**
 * Unit tests for `electron/services/log-config.ts` (F2.3 — T5, DEC-UPD-11).
 *
 * RED → GREEN → REFACTOR coverage:
 *   L1: transports.file.maxSize === 10 * 1024 * 1024 (10 MB).
 *   L2: transports.file.backups === 5.
 *   L3: log.format === log.formats.json.
 *   L4: process.on('uncaughtException', ...) registrado.
 *   L5: process.on('unhandledRejection', ...) registrado.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initLogConfig,
  MAX_SIZE_BYTES,
  MAX_BACKUPS,
} from './log-config';

interface LogStub {
  transports: {
    file: {
      maxSize: number;
      backups: number;
      resolvePathFn?: () => string;
    };
  };
  formats: { json: string };
  format: string;
  info: ReturnType<typeof vi.fn>;
  error: ReturnType<typeof vi.fn>;
}

interface AppStub {
  getPath: (name: string) => string;
}

function makeLog(): LogStub {
  return {
    transports: {
      file: {
        maxSize: 0,
        backups: 0,
      },
    },
    formats: { json: '<json>' },
    format: '<default>',
    info: vi.fn(),
    error: vi.fn(),
  };
}

function makeApp(): AppStub {
  return { getPath: (name: string) => `/tmp/parkos-test/${name}` };
}

describe('initLogConfig', () => {
  let log: LogStub;
  let app: AppStub;

  beforeEach(() => {
    log = makeLog();
    app = makeApp();
    vi.spyOn(process, 'on').mockImplementation(() => process);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('L1: transports.file.maxSize = 10 MB', () => {
    initLogConfig(log, app);
    expect(log.transports.file.maxSize).toBe(10 * 1024 * 1024);
    expect(log.transports.file.maxSize).toBe(MAX_SIZE_BYTES);
  });

  it('L2: transports.file.backups = 5', () => {
    initLogConfig(log, app);
    expect(log.transports.file.backups).toBe(5);
    expect(log.transports.file.backups).toBe(MAX_BACKUPS);
  });

  it('L3: log.format = log.formats.json', () => {
    initLogConfig(log, app);
    expect(log.format).toBe(log.formats.json);
  });

  it('L4: process.on captura uncaughtException', () => {
    const onSpy = vi.spyOn(process, 'on');
    initLogConfig(log, app);
    expect(onSpy).toHaveBeenCalledWith('uncaughtException', expect.any(Function));
  });

  it('L5: process.on captura unhandledRejection', () => {
    const onSpy = vi.spyOn(process, 'on');
    initLogConfig(log, app);
    expect(onSpy).toHaveBeenCalledWith('unhandledRejection', expect.any(Function));
  });
});