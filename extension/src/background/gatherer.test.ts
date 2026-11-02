import { beforeEach, describe, expect, it, vi } from 'vitest';

// The real api-client module reads chrome.storage when it loads (for ApiError); give it a stub.
vi.hoisted(() => {
  (globalThis as unknown as { chrome: unknown }).chrome = { storage: { local: { get: async () => ({}) } } };
});

const api = vi.hoisted(() => ({
  getToken: vi.fn(),
  getSearchQueries: vi.fn(),
  ingestJobQueue: vi.fn(),
}));

vi.mock('../lib/api-client', async (orig) => ({
  ...(await orig<typeof import('../lib/api-client')>()),
  apiClient: api,
}));
vi.mock('../lib/proposal-scrape', async (orig) => ({
  ...(await orig<typeof import('../lib/proposal-scrape')>()),
  randomDetailDelayMs: () => 0,
}));

import { GATHER_KEYS, initGatherer, type SearchScrapeResult } from './gatherer';
import { ApiError } from '../lib/api-client';
import type { GatherLastRun, GatherRunProgress } from '../lib/job-gather';

let store: Record<string, unknown>;
let alarms: Record<string, { periodInMinutes?: number }>;
const removedTabs: number[] = [];

function installChrome() {
  store = {};
  alarms = {};
  removedTabs.length = 0;
  const local = {
    get: vi.fn(async (k: string) => (k in store ? { [k]: structuredClone(store[k]) } : {})),
    set: vi.fn(async (items: Record<string, unknown>) => { Object.assign(store, structuredClone(items)); }),
    remove: vi.fn(async (k: string | string[]) => { for (const key of [k].flat()) delete store[key]; }),
  };
  (globalThis as unknown as { chrome: unknown }).chrome = {
    storage: { local },
    alarms: {
      get: vi.fn(async (n: string) => alarms[n]),
      create: vi.fn(async (n: string, o: { periodInMinutes?: number }) => { alarms[n] = o; }),
      clear: vi.fn(async (n: string) => { delete alarms[n]; return true; }),
      onAlarm: { addListener: vi.fn() },
    },
    tabs: { remove: vi.fn(async (id: number) => { removedTabs.push(id); }) },
  };
}

const card = (n: number) => ({ upworkUrl: `https://www.upwork.com/jobs/~0${n}`, title: `Job ${n}`, description: 'd' });
const queries = ['a', 'b', 'c'].map((id, i) => ({ id, query: `q-${id}`, active: true, created_at: `2026-01-0${i + 1}` }));

async function lastRun(): Promise<GatherLastRun> {
  await vi.waitFor(() => { if (!store[GATHER_KEYS.lastRun]) throw new Error('not finished'); });
  return store[GATHER_KEYS.lastRun] as GatherLastRun;
}

function setup(scrape: (q: string) => SearchScrapeResult) {
  const scrapeSearch = vi.fn(async (q: string, _p: unknown, opts: { onTabOpened?: (id: number) => unknown; onTabClosed?: () => unknown }) => {
    await opts.onTabOpened?.(77);
    try { return scrape(q); } finally { await opts.onTabClosed?.(); }
  });
  const keepAlive = { start: vi.fn(), stop: vi.fn() };
  const g = initGatherer({ scrapeSearch, keepAlive });
  return { g, scrapeSearch, keepAlive };
}

beforeEach(() => {
  vi.clearAllMocks();
  installChrome();
  api.getToken.mockResolvedValue('tok');
  api.getSearchQueries.mockResolvedValue(queries);
  api.ingestJobQueue.mockImplementation(async (b: { jobs: unknown[] }) => ({
    received: b.jobs.length, duplicates: 1, pre_filtered: 2, scored: 3, suggested: 1, below_threshold: 0, queued_ids: [],
  }));
});

describe('gatherer run', () => {
  it('runs each query, sends cards in chunks of 25 with the query id, and records the summary', async () => {
    const { g, keepAlive } = setup((q) => ({ success: true, data: q === 'q-a' ? Array.from({ length: 120 }, (_, i) => card(i)) : [card(900)] }));
    expect(await g.startGatherRun('manual')).toEqual({ started: true });
    const r = await lastRun();

    const sizes = api.ingestJobQueue.mock.calls.map(([b]) => [b.query_id, b.query, b.jobs.length]);
    expect(sizes).toEqual([['a', 'q-a', 25], ['a', 'q-a', 25], ['a', 'q-a', 25], ['a', 'q-a', 25], ['a', 'q-a', 20], ['b', 'q-b', 1], ['c', 'q-c', 1]]);
    expect(r).toMatchObject({ trigger: 'manual', queries_run: 3, jobs_sent: 122, suggested: 7, duplicates: 7, pre_filtered: 14, error: null, blocked: null });
    expect(store[GATHER_KEYS.cursor]).toBe('c');
    expect(store[GATHER_KEYS.run]).toBeUndefined();
    expect(store[GATHER_KEYS.lock]).toBeUndefined();
    await vi.waitFor(() => expect(keepAlive.stop).toHaveBeenCalled());
  });

  it('honours maxQueriesPerRun and continues from the cursor next run', async () => {
    store[GATHER_KEYS.settings] = { enabled: true, intervalMinutes: 180, maxQueriesPerRun: 2 };
    store[GATHER_KEYS.cursor] = 'b';
    const { g, scrapeSearch } = setup(() => ({ success: true, data: [card(1)] }));
    await g.startGatherRun('manual');
    await lastRun();
    expect(scrapeSearch.mock.calls.map(([q]) => q)).toEqual(['q-c', 'q-a']);
    expect(store[GATHER_KEYS.cursor]).toBe('a');
  });

  it('stops on a blocked page, keeps the cursor on that query and backs off the next alarm', async () => {
    store[GATHER_KEYS.settings] = { enabled: true, intervalMinutes: 60, maxQueriesPerRun: 10 };
    const { g, scrapeSearch } = setup((q) => (q === 'q-b'
      ? { success: false, error: 'Upwork showed a security check (page title: "Challenge - Upwork"). Open Upwork, complete it, then run again.', blocked: 'captcha' }
      : { success: true, data: [card(1)] }));
    await g.startGatherRun('alarm');
    const r = await lastRun();
    expect(scrapeSearch).toHaveBeenCalledTimes(2);
    expect(r).toMatchObject({ queries_run: 1, blocked: 'captcha' });
    expect(r.error).toMatch(/security check/);
    expect(store[GATHER_KEYS.cursor]).toBe('a');
    const backoff = store[GATHER_KEYS.backoff] as { streak: number; until: number };
    expect(backoff.streak).toBe(1);
    expect(backoff.until).toBeGreaterThan(Date.now() + 59 * 60_000);

    expect(await g.startGatherRun('alarm')).toMatchObject({ started: false, reason: expect.stringMatching(/Backing off/) });
  });

  it('sends what a toast-interrupted query read, then stops', async () => {
    const { g } = setup(() => ({ success: true, data: [card(1), card(2)], blocked: 'error_toast' }));
    await g.startGatherRun('manual');
    const r = await lastRun();
    expect(r).toMatchObject({ queries_run: 1, jobs_sent: 2, blocked: 'error_toast' });
    expect(store[GATHER_KEYS.cursor]).toBe('a');
  });

  it('stops when the API signs the user out', async () => {
    api.ingestJobQueue.mockRejectedValue(new ApiError(401, 'Unauthorized'));
    const { g } = setup(() => ({ success: true, data: [card(1)] }));
    await g.startGatherRun('manual');
    const r = await lastRun();
    expect(r.error).toMatch(/Signed out of UpApply/);
    expect(r.queries_run).toBe(0);
    expect(store[GATHER_KEYS.cursor]).toBeUndefined();
  });

  it('keeps going when one query fails to scrape and reports it', async () => {
    const { g } = setup((q) => (q === 'q-a' ? { success: false, error: 'Tab load timeout' } : { success: true, data: [card(1)] }));
    await g.startGatherRun('manual');
    const r = await lastRun();
    expect(r.queries_run).toBe(3);
    expect(r.error).toMatch(/q-a.*Tab load timeout/);
  });

  it('keeps going when the scraper rejects for one query', async () => {
    const { g } = setup((q) => { if (q === 'q-a') throw new Error('Tab load timeout'); return { success: true, data: [card(1)] }; });
    await g.startGatherRun('manual');
    const r = await lastRun();
    expect(r.queries_run).toBe(3);
    expect(r.error).toMatch(/q-a.*Tab load timeout/);
    expect(store[GATHER_KEYS.cursor]).toBe('c');
  });
});

describe('gatherer guards', () => {
  it('skips alarm runs while disabled (the default)', async () => {
    const { g, scrapeSearch } = setup(() => ({ success: true, data: [] }));
    expect(await g.startGatherRun('alarm')).toMatchObject({ started: false });
    expect(scrapeSearch).not.toHaveBeenCalled();
  });

  it('starts "Run now" that arrives while the startup resume check is still going', async () => {
    const { g } = setup(() => ({ success: true, data: [card(1)] })); // init's resume attempt is in flight
    expect(await g.startGatherRun('manual')).toEqual({ started: true });
    await lastRun();
  });

  it('records a skip when not signed in to UpApply', async () => {
    api.getToken.mockResolvedValue(null);
    const { g, scrapeSearch } = setup(() => ({ success: true, data: [] }));
    expect(await g.startGatherRun('manual')).toMatchObject({ started: false, reason: 'Not signed in to UpApply.' });
    expect(scrapeSearch).not.toHaveBeenCalled();
    expect((store[GATHER_KEYS.lastRun] as GatherLastRun).error).toBe('Not signed in to UpApply.');
  });

  it('refuses a second run while one is going', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const scrapeSearch = vi.fn(async () => { await gate; return { success: true, data: [] }; });
    const g = initGatherer({ scrapeSearch, keepAlive: { start: vi.fn(), stop: vi.fn() } });
    expect(await g.startGatherRun('manual')).toEqual({ started: true });
    expect(await g.startGatherRun('manual')).toMatchObject({ started: false, reason: expect.stringMatching(/already running/) });
    release();
    await lastRun();
  });

  it('resumes an interrupted run at its saved index and closes its orphaned tab', async () => {
    const interrupted: GatherRunProgress = {
      run_id: 'r1', trigger: 'manual', started_at: '2026-11-01T00:00:00Z',
      queries: queries.map((q) => ({ id: q.id, query: q.query, url_params: null })),
      index: 2, tab_id: 55, warning: null,
      queries_run: 2, jobs_sent: 9, suggested: 1, duplicates: 0, pre_filtered: 0,
    };
    store[GATHER_KEYS.run] = interrupted;
    store[GATHER_KEYS.lock] = { run_id: 'r1', instance_id: 'dead-worker', heartbeat_at: Date.now() };
    const { scrapeSearch } = setup(() => ({ success: true, data: [card(1)] })); // init resumes on its own
    const r = await lastRun();
    expect(removedTabs).toContain(55);
    expect(scrapeSearch.mock.calls.map(([q]) => q)).toEqual(['q-c']);
    expect(r).toMatchObject({ started_at: '2026-11-01T00:00:00Z', queries_run: 3, jobs_sent: 10 });
    expect(api.getSearchQueries).not.toHaveBeenCalled();
  });
});

describe('gatherer settings', () => {
  it('creates the alarm when enabled and clears it when disabled', async () => {
    const { g } = setup(() => ({ success: true, data: [] }));
    const s = await g.saveGatherSettings({ enabled: true, intervalMinutes: 240 });
    expect(s).toEqual({ enabled: true, intervalMinutes: 240, maxQueriesPerRun: 10 });
    expect(alarms['upapply-job-gather']).toEqual({ periodInMinutes: 240, delayInMinutes: 240 });
    await g.saveGatherSettings({ intervalMinutes: 9999 });
    expect(alarms['upapply-job-gather'].periodInMinutes).toBe(720);
    await g.saveGatherSettings({ enabled: false });
    expect(alarms['upapply-job-gather']).toBeUndefined();
  });

  it('reports status with defaults before anything ran', async () => {
    const { g } = setup(() => ({ success: true, data: [] }));
    expect(await g.getGatherStatus()).toEqual({
      settings: { enabled: false, intervalMinutes: 180, maxQueriesPerRun: 10 },
      lastRun: null, running: null, backoffUntil: null,
    });
  });
});
