/**
 * Automatic job scan: a chrome.alarms job that runs the user's active search queries through the
 * same hidden-tab scrape as the History buttons and sends the cards to /job-queue/ingest.
 *
 * Pacing mirrors the proposal import: 6–10 s between queries, at most N queries per run
 * (round-robin cursor), stop on Upwork's error toast / login page / challenge and back off the
 * next scheduled runs. Progress is persisted after every query so a killed worker resumes.
 */
import { apiClient, ApiError } from '../lib/api-client';
import { logger } from '../lib/logger';
import { randomDetailDelayMs } from '../lib/proposal-scrape';
import {
  GATHER_ALARM_NAME, GATHER_MAX_PAGES, INGEST_CHUNK_SIZE,
  addIngestResult, alarmMatches, alarmPlan, backoffMs, blockMessage, cardsToIngestJobs, chunk,
  emptyTotals, isLockFree, normalizeGatherSettings, pickQueries,
} from '../lib/job-gather';
import type {
  BlockReason, GatherLastRun, GatherLock, GatherQuery, GatherRunProgress, GatherSettings, GatherTrigger,
  ScrapedJobCardLike,
} from '../lib/job-gather';

export interface SearchScrapeOptions {
  maxPages?: number;
  onTabOpened?: (tabId: number) => void | Promise<void>;
  onTabClosed?: () => void | Promise<void>;
}

export interface SearchScrapeResult {
  success: boolean;
  data?: unknown;
  error?: string;
  blocked?: BlockReason | null;
}

export interface GathererDeps {
  scrapeSearch: (query: string, urlParams: string | null | undefined, opts: SearchScrapeOptions) => Promise<SearchScrapeResult>;
  keepAlive: { start: () => void; stop: () => void };
}

/** chrome.storage.local keys */
export const GATHER_KEYS = {
  settings: 'gatherSettings',
  cursor: 'gatherCursor',
  lock: 'gatherLock',
  run: 'gatherRun',
  lastRun: 'gatherLastRun',
  backoff: 'gatherBackoff',
} as const;

interface GatherBackoff { streak: number; until: number }

export interface GatherStatus {
  settings: GatherSettings;
  lastRun: GatherLastRun | null;
  running: GatherRunProgress | null;
  backoffUntil: number | null;
}

// Only one service worker runs per extension; a lock from another instance id is from a dead worker.
const INSTANCE_ID = Math.random().toString(36).slice(2);

const get = async <T>(key: string): Promise<T | undefined> =>
  (await chrome.storage.local.get(key))[key] as T | undefined;
const set = (items: Record<string, unknown>) => chrome.storage.local.set(items);

export function initGatherer(deps: GathererDeps) {
  let running = false; // in-memory guard: the storage lock is read-then-write, not atomic
  let startChain: Promise<unknown> = Promise.resolve();

  async function loadSettings(): Promise<GatherSettings> {
    return normalizeGatherSettings(await get<Partial<GatherSettings>>(GATHER_KEYS.settings));
  }

  async function syncAlarm(settings?: GatherSettings): Promise<void> {
    const s = settings ?? await loadSettings();
    const plan = alarmPlan(s);
    const existing = await chrome.alarms.get(GATHER_ALARM_NAME);
    if (alarmMatches(existing, plan)) return;
    if (plan.action === 'clear') {
      await chrome.alarms.clear(GATHER_ALARM_NAME);
    } else {
      await chrome.alarms.create(GATHER_ALARM_NAME, {
        periodInMinutes: plan.periodInMinutes,
        delayInMinutes: plan.delayInMinutes,
      });
    }
  }

  async function saveGatherSettings(patch: Partial<GatherSettings>): Promise<GatherSettings> {
    const current = await loadSettings();
    const next = normalizeGatherSettings({ ...current, ...patch });
    await set({ [GATHER_KEYS.settings]: next });
    if (next.enabled !== current.enabled || next.intervalMinutes !== current.intervalMinutes) {
      // Interval change: recreate so the new period takes effect now.
      await chrome.alarms.clear(GATHER_ALARM_NAME);
    }
    await syncAlarm(next);
    return next;
  }

  async function getGatherStatus(): Promise<GatherStatus> {
    const [settings, lastRun, run, backoff] = await Promise.all([
      loadSettings(),
      get<GatherLastRun>(GATHER_KEYS.lastRun),
      get<GatherRunProgress>(GATHER_KEYS.run),
      get<GatherBackoff>(GATHER_KEYS.backoff),
    ]);
    return {
      settings,
      lastRun: lastRun ?? null,
      running: run ?? null,
      backoffUntil: backoff && backoff.until > Date.now() ? backoff.until : null,
    };
  }

  async function heartbeat(runId: string): Promise<void> {
    const lock: GatherLock = { run_id: runId, instance_id: INSTANCE_ID, heartbeat_at: Date.now() };
    await set({ [GATHER_KEYS.lock]: lock });
  }

  async function finish(progress: GatherRunProgress, error: string | null, blocked: BlockReason | null) {
    const settings = await loadSettings();
    const lastRun: GatherLastRun = {
      trigger: progress.trigger,
      started_at: progress.started_at,
      finished_at: new Date().toISOString(),
      queries_run: progress.queries_run,
      jobs_sent: progress.jobs_sent,
      suggested: progress.suggested,
      duplicates: progress.duplicates,
      pre_filtered: progress.pre_filtered,
      error: error ?? progress.warning,
      blocked,
    };
    const prev = (await get<GatherBackoff>(GATHER_KEYS.backoff)) ?? { streak: 0, until: 0 };
    const streak = blocked ? prev.streak + 1 : 0;
    const backoff: GatherBackoff = { streak, until: streak ? Date.now() + backoffMs(streak, settings.intervalMinutes) : 0 };
    await set({ [GATHER_KEYS.lastRun]: lastRun, [GATHER_KEYS.backoff]: backoff });
    await chrome.storage.local.remove([GATHER_KEYS.run, GATHER_KEYS.lock]);
    logger.log('UpApply gather: run finished', lastRun);
  }

  /** Builds a fresh run, or returns the interrupted one (closing its orphaned tab). */
  async function loadOrCreateRun(trigger: GatherTrigger): Promise<GatherRunProgress | { skip: string }> {
    const existing = await get<GatherRunProgress>(GATHER_KEYS.run);
    if (existing && existing.index < existing.queries.length) {
      if (existing.tab_id != null) {
        try { await chrome.tabs.remove(existing.tab_id); } catch { /* already gone */ }
        existing.tab_id = null;
      }
      logger.log(`UpApply gather: resuming run ${existing.run_id} at query ${existing.index + 1}/${existing.queries.length}`);
      return existing;
    }
    const settings = await loadSettings();
    const all = await apiClient.getSearchQueries();
    const cursor = (await get<string>(GATHER_KEYS.cursor)) ?? null;
    const queries: GatherQuery[] = pickQueries(all, cursor, settings.maxQueriesPerRun)
      .map((q) => ({ id: q.id, query: q.query, url_params: q.url_params ?? null }));
    if (queries.length === 0) return { skip: 'No active search queries. Add some on the Find page.' };
    return {
      run_id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      trigger,
      started_at: new Date().toISOString(),
      queries,
      index: 0,
      tab_id: null,
      warning: null,
      ...emptyTotals(),
    };
  }

  async function recordSkip(trigger: GatherTrigger, error: string) {
    const now = new Date().toISOString();
    const lastRun: GatherLastRun = { trigger, started_at: now, finished_at: now, ...emptyTotals(), error, blocked: null };
    await set({ [GATHER_KEYS.lastRun]: lastRun });
  }

  async function runLoop(progress: GatherRunProgress): Promise<void> {
    const save = () => set({ [GATHER_KEYS.run]: progress });
    await save();
    while (progress.index < progress.queries.length) {
      const q = progress.queries[progress.index];
      if (progress.queries_run > 0) await new Promise((r) => setTimeout(r, randomDetailDelayMs()));
      await heartbeat(progress.run_id);

      let result: SearchScrapeResult;
      try {
        result = await deps.scrapeSearch(q.query, q.url_params, {
          maxPages: GATHER_MAX_PAGES,
          onTabOpened: async (tabId) => { progress.tab_id = tabId; await save(); },
          onTabClosed: async () => { progress.tab_id = null; await save(); },
        });
      } catch (e) {
        // A rejected scrape (tab load timeout, tab create) is one failed query, not a stopped run.
        result = { success: false, error: e instanceof Error ? e.message : String(e) };
      }

      const cards = result.success && Array.isArray(result.data) ? (result.data as ScrapedJobCardLike[]) : [];
      const jobs = cardsToIngestJobs(cards);
      for (const part of chunk(jobs, INGEST_CHUNK_SIZE)) {
        try {
          const r = await apiClient.ingestJobQueue({ query_id: q.id, query: q.query, jobs: part });
          addIngestResult(progress, part.length, r);
        } catch (e) {
          // Cursor stays before this query, so the next run retries it.
          const signedOut = e instanceof ApiError && e.status === 401;
          await finish(progress, signedOut ? 'Signed out of UpApply. Sign in again to resume scanning.' : `Could not send jobs to UpApply: ${e instanceof Error ? e.message : String(e)}`, null);
          return;
        }
      }

      if (!result.success && !result.blocked) {
        progress.warning = `"${q.query}": ${result.error || 'scrape failed'}`;
        logger.log('UpApply gather: query failed, continuing', progress.warning);
      }
      if (result.blocked && cards.length === 0) {
        // Nothing read for this query: leave the cursor so it is first next time.
        await finish(progress, blockMessage(result.blocked), result.blocked);
        return;
      }

      progress.queries_run++;
      progress.index++;
      await set({ [GATHER_KEYS.cursor]: q.id });
      await save();

      if (result.blocked) {
        await finish(progress, blockMessage(result.blocked), result.blocked);
        return;
      }
    }
    await finish(progress, null, null);
  }

  /**
   * Starts (or resumes) a run unless one is already going. Resolves once the run has started;
   * the run itself continues in the background and writes gatherLastRun when done.
   */
  function startGatherRun(trigger: GatherTrigger | 'resume'): Promise<{ started: boolean; reason?: string }> {
    // Start attempts are serialized: the startup resume, an alarm and "Run now" can all arrive on
    // the same worker wake, and each must see whether the previous one started a run.
    const attempt = startChain.then(() =>
      running ? { started: false, reason: 'A scan is already running.' } : tryStart(trigger));
    startChain = attempt.catch(() => {});
    return attempt;
  }

  async function tryStart(trigger: GatherTrigger | 'resume'): Promise<{ started: boolean; reason?: string }> {
    const settings = await loadSettings();
    const existingRun = await get<GatherRunProgress>(GATHER_KEYS.run);
    if (trigger === 'resume' && !existingRun) return { started: false, reason: 'Nothing to resume.' };
    const effective: GatherTrigger = trigger === 'resume' ? (existingRun?.trigger ?? 'alarm') : trigger;
    if (effective === 'alarm' && !settings.enabled) {
      if (existingRun) await chrome.storage.local.remove(GATHER_KEYS.run);
      return { started: false, reason: 'Automatic scan is off.' };
    }

    const lock = await get<GatherLock>(GATHER_KEYS.lock);
    if (!isLockFree(lock, INSTANCE_ID, Date.now())) return { started: false, reason: 'A scan is already running.' };

    if (!(await apiClient.getToken())) {
      await recordSkip(effective, 'Not signed in to UpApply.');
      return { started: false, reason: 'Not signed in to UpApply.' };
    }

    if (trigger === 'alarm' && !existingRun) {
      const backoff = await get<GatherBackoff>(GATHER_KEYS.backoff);
      if (backoff && backoff.until > Date.now()) {
        logger.log('UpApply gather: backing off until', new Date(backoff.until).toISOString());
        return { started: false, reason: 'Backing off after Upwork blocked the last scan.' };
      }
    }

    await heartbeat('pending');
    let progress: GatherRunProgress | { skip: string };
    try {
      progress = await loadOrCreateRun(effective);
    } catch (e) {
      progress = {
        skip: e instanceof ApiError && e.status === 401
          ? 'Signed out of UpApply. Sign in again to resume scanning.'
          : `Could not load search queries: ${e instanceof Error ? e.message : String(e)}`,
      };
    }
    if ('skip' in progress) {
      await chrome.storage.local.remove(GATHER_KEYS.lock);
      await recordSkip(effective, progress.skip);
      return { started: false, reason: progress.skip };
    }

    const run = progress;
    running = true;
    deps.keepAlive.start();
    runLoop(run)
      .catch(async (e) => {
        logger.warn('UpApply gather: run crashed', e);
        try { await finish(run, `Scan stopped: ${e instanceof Error ? e.message : String(e)}`, null); } catch { /* ignore */ }
      })
      .finally(() => { running = false; deps.keepAlive.stop(); });
    return { started: true };
  }

  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name !== GATHER_ALARM_NAME) return;
    startGatherRun('alarm').then((r) => {
      if (!r.started) logger.log('UpApply gather: alarm run skipped —', r.reason);
    }).catch((e) => logger.warn('UpApply gather: alarm run failed', e));
  });

  // Every worker start: make the alarm match the settings, and pick up a run a killed worker left.
  syncAlarm().catch(() => {});
  startGatherRun('resume').catch(() => {});

  return { startGatherRun, getGatherStatus, saveGatherSettings };
}
