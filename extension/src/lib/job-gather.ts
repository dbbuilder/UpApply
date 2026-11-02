// Pure helpers for the automatic job scan (background/gatherer.ts).
// No chrome.* calls here so they can be unit-tested.
import type { JobQueueIngestClientInfo, JobQueueIngestJob } from './api-client';
import { THROTTLE_PAGE_TEXT } from './proposal-scrape';

export const GATHER_ALARM_NAME = 'upapply-job-gather';
export const DEFAULT_INTERVAL_MINUTES = 180;
export const MIN_INTERVAL_MINUTES = 60;
export const MAX_INTERVAL_MINUTES = 720;
export const INTERVAL_OPTIONS = [60, 120, 180, 240, 360, 480, 720];
export const DEFAULT_MAX_QUERIES_PER_RUN = 10;
/** The ingest endpoint takes at most this many jobs per call. */
export const INGEST_CHUNK_SIZE = 50;
/** Search results are sorted by recency, so a run reads only the first few pages of each query. */
export const GATHER_MAX_PAGES = 3;
/** A lock whose heartbeat is older than this belongs to a run that died. */
export const LOCK_STALE_MS = 10 * 60_000;
/** After a blocked run, skip alarms for interval × 2^(streak-1), capped at this many intervals. */
export const MAX_BACKOFF_INTERVALS = 4;

export interface GatherSettings {
  enabled: boolean;
  intervalMinutes: number;
  maxQueriesPerRun: number;
}

export const DEFAULT_GATHER_SETTINGS: GatherSettings = {
  enabled: false,
  intervalMinutes: DEFAULT_INTERVAL_MINUTES,
  maxQueriesPerRun: DEFAULT_MAX_QUERIES_PER_RUN,
};

/** Fills defaults and clamps a stored (possibly partial or stale) settings object. */
export function normalizeGatherSettings(raw: Partial<GatherSettings> | null | undefined): GatherSettings {
  const r = raw ?? {};
  const interval = Number(r.intervalMinutes);
  const maxQ = Number(r.maxQueriesPerRun);
  return {
    enabled: r.enabled === true,
    intervalMinutes: Number.isFinite(interval)
      ? Math.min(MAX_INTERVAL_MINUTES, Math.max(MIN_INTERVAL_MINUTES, Math.round(interval)))
      : DEFAULT_INTERVAL_MINUTES,
    maxQueriesPerRun: Number.isFinite(maxQ) && maxQ >= 1 ? Math.round(maxQ) : DEFAULT_MAX_QUERIES_PER_RUN,
  };
}

export type AlarmPlan = { action: 'clear' } | { action: 'create'; periodInMinutes: number; delayInMinutes: number };

/** What the periodic alarm should look like for these settings. */
export function alarmPlan(settings: GatherSettings): AlarmPlan {
  if (!settings.enabled) return { action: 'clear' };
  return { action: 'create', periodInMinutes: settings.intervalMinutes, delayInMinutes: settings.intervalMinutes };
}

/** True when an existing alarm already matches the plan (so it is not reset on every worker start). */
export function alarmMatches(existing: { periodInMinutes?: number } | null | undefined, plan: AlarmPlan): boolean {
  if (plan.action === 'clear') return !existing;
  return !!existing && existing.periodInMinutes === plan.periodInMinutes;
}

export function buildSearchUrl(query: string, urlParams?: string | null): string {
  const extra = urlParams ? `&${urlParams}` : '';
  return `https://www.upwork.com/nx/search/jobs/?q=${encodeURIComponent(query || '')}&sort=recency${extra}`;
}

// ── Card → ingest job ─────────────────────────────────────────────────────────

/** Shape returned by the content script's SCRAPE_JOB_CARDS (content/index.ts ScrapedJobCard). */
export interface ScrapedJobCardLike {
  upworkJobId?: string;
  upworkUrl: string;
  title: string;
  description?: string | null;
  jobType?: string | null;
  experienceLevel?: string | null;
  postedDateRaw?: string | null;
  clientInfo?: {
    paymentVerified?: boolean;
    rating?: string | null;
    totalSpent?: string | null;
  } | null;
}

/** First 0–5 number in the card's feedback text ("4.9", "Rating is 4.9 out of 5"). */
export function parseRating(text: string | null | undefined): number | undefined {
  const m = (text || '').match(/\d+(?:\.\d+)?/);
  if (!m) return undefined;
  const n = parseFloat(m[0]);
  return n >= 0 && n <= 5 ? n : undefined;
}

/**
 * Maps a scraped search card to the ingest shape. Only fields the card scraper reads are filled;
 * skills, budget amount, posted_at, location and proposals are not on the card scraper, so they
 * go as empty / null rather than guessed.
 */
export function cardToIngestJob(card: ScrapedJobCardLike): JobQueueIngestJob {
  const ci = card.clientInfo;
  let clientInfo: JobQueueIngestClientInfo | null = null;
  if (ci) {
    clientInfo = {};
    if (typeof ci.paymentVerified === 'boolean') clientInfo.payment_verified = ci.paymentVerified;
    const rating = parseRating(ci.rating);
    if (rating !== undefined) clientInfo.rating = rating;
    if (ci.totalSpent) clientInfo.total_spent = ci.totalSpent;
  }
  const jt = (card.jobType || '').toLowerCase();
  return {
    upwork_url: card.upworkUrl,
    title: card.title,
    description: card.description || '',
    skills: [],
    budget_amount: null,
    budget_type: jt === 'fixed' || jt === 'hourly' ? jt : null,
    posted_at: null,
    posted_text: card.postedDateRaw || null,
    client_info: clientInfo,
    proposals_text: null,
  };
}

/** Cards without a URL or title cannot be queued; duplicates within one scrape are dropped. */
export function cardsToIngestJobs(cards: ScrapedJobCardLike[]): JobQueueIngestJob[] {
  const seen = new Set<string>();
  const out: JobQueueIngestJob[] = [];
  for (const c of cards) {
    if (!c?.upworkUrl || !c.title || seen.has(c.upworkUrl)) continue;
    seen.add(c.upworkUrl);
    out.push(cardToIngestJob(c));
  }
  return out;
}

export function chunk<T>(items: T[], size: number): T[][] {
  if (size < 1) throw new Error('chunk size must be >= 1');
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

// ── Round-robin over the user's queries ───────────────────────────────────────

export interface GatherQuery {
  id: string;
  query: string;
  url_params?: string | null;
  active?: boolean;
  created_at?: string;
}

/**
 * Picks up to `max` active queries starting after `cursor` (the id of the last query run),
 * wrapping around, so every query gets its turn across runs. An unknown cursor starts at the top.
 */
export function pickQueries<T extends GatherQuery>(queries: T[], cursor: string | null | undefined, max: number): T[] {
  const active = queries
    .filter((q) => q.active !== false && q.query?.trim())
    .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || '') || a.id.localeCompare(b.id));
  if (active.length === 0 || max < 1) return [];
  const at = cursor ? active.findIndex((q) => q.id === cursor) : -1;
  const start = at + 1; // -1 → 0
  const n = Math.min(max, active.length);
  return Array.from({ length: n }, (_, i) => active[(start + i) % active.length]);
}

// ── Stop conditions ───────────────────────────────────────────────────────────

export type BlockReason = 'error_toast' | 'login' | 'captcha';

export interface PageSnapshot {
  url: string;
  title?: string | null;
  text?: string | null;
  /** The page shows job tiles (article[data-test="JobTile"]). */
  hasJobTiles?: boolean;
}

const LOGIN_PATHS = ['/ab/account-security/login', '/account-security/login', '/login'];
const CAPTCHA_PATH = /\/cdn-cgi\/|challenge|captcha/i;
const CAPTCHA_TITLE = /just a moment|attention required|captcha|security check|are you a robot/i;
const CAPTCHA_TEXT = /verify you are human|checking if the site connection is secure|complete the security check|press (and|&) hold|i'?m not a robot/i;

/**
 * Why a loaded search tab must stop the run, or null when it looks like a normal page.
 * Login and challenge checks apply only when no job tiles rendered: job posts and the page
 * title (which repeats the search words) can contain words like "captcha".
 */
export function detectBlockedPage(page: PageSnapshot): BlockReason | null {
  const text = page.text || '';
  if (text.includes(THROTTLE_PAGE_TEXT)) return 'error_toast';
  if (page.hasJobTiles) return null;
  let path = '';
  try { path = new URL(page.url).pathname; } catch { /* keep '' */ }
  if (LOGIN_PATHS.some((p) => path.includes(p))) return 'login';
  if (CAPTCHA_PATH.test(path) || CAPTCHA_TITLE.test(page.title || '') || CAPTCHA_TEXT.test(text)) return 'captcha';
  return null;
}

export function blockMessage(reason: BlockReason): string {
  switch (reason) {
    case 'error_toast': return 'Upwork showed "There was an error loading this page" (rate limit). Stopped; the next scheduled scan backs off.';
    case 'login': return 'Upwork asked you to sign in. Sign in to Upwork in this browser, then run again.';
    case 'captcha': return 'Upwork showed a security check. Open Upwork, complete it, then run again.';
  }
}

/** How long to skip scheduled runs after `streak` blocked runs in a row (0 → no backoff). */
export function backoffMs(streak: number, intervalMinutes: number): number {
  if (streak <= 0) return 0;
  const factor = Math.min(2 ** (streak - 1), MAX_BACKOFF_INTERVALS);
  return factor * intervalMinutes * 60_000;
}

// ── Run lock ──────────────────────────────────────────────────────────────────

export interface GatherLock {
  run_id: string;
  /** Random id of the service-worker instance holding the lock. */
  instance_id: string;
  heartbeat_at: number;
}

/**
 * A lock is free when there is none, its heartbeat is stale, or it was taken by an earlier
 * service-worker instance (there is only one worker per extension, so that instance is gone).
 */
export function isLockFree(lock: GatherLock | null | undefined, instanceId: string, now: number): boolean {
  if (!lock) return true;
  if (now - lock.heartbeat_at > LOCK_STALE_MS) return true;
  return lock.instance_id !== instanceId;
}

// ── Run state ─────────────────────────────────────────────────────────────────

export type GatherTrigger = 'alarm' | 'manual';

export interface GatherTotals {
  queries_run: number;
  jobs_sent: number;
  suggested: number;
  duplicates: number;
  pre_filtered: number;
}

/** In-flight run, persisted after every query so a killed worker resumes where it stopped. */
export interface GatherRunProgress extends GatherTotals {
  run_id: string;
  trigger: GatherTrigger;
  started_at: string;
  queries: GatherQuery[];
  /** Index into `queries` of the next query to run. */
  index: number;
  /** Search tab open for the current query (closed on resume if the worker died). */
  tab_id: number | null;
  /** Last non-fatal per-query problem (one query's scrape failing does not stop the run). */
  warning: string | null;
}

export interface GatherLastRun extends GatherTotals {
  trigger: GatherTrigger;
  started_at: string;
  finished_at: string;
  error: string | null;
  blocked: BlockReason | null;
}

export function emptyTotals(): GatherTotals {
  return { queries_run: 0, jobs_sent: 0, suggested: 0, duplicates: 0, pre_filtered: 0 };
}

export function addIngestResult(
  totals: GatherTotals,
  sent: number,
  r: { suggested?: number; duplicates?: number; pre_filtered?: number },
): void {
  totals.jobs_sent += sent;
  totals.suggested += r.suggested ?? 0;
  totals.duplicates += r.duplicates ?? 0;
  totals.pre_filtered += r.pre_filtered ?? 0;
}
