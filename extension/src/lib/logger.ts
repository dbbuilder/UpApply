const DEBUG = import.meta.env.DEV;

export const logger = {
  log: (...args: unknown[]) => { if (DEBUG) console.log('[UpApply]', ...args); },
  warn: (...args: unknown[]) => { if (DEBUG) console.warn('[UpApply]', ...args); },
  error: (...args: unknown[]) => console.error('[UpApply]', ...args),
};
