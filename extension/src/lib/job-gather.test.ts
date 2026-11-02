import { describe, expect, it } from 'vitest';
import {
  DEFAULT_GATHER_SETTINGS, DEFAULT_INTERVAL_MINUTES, LOCK_STALE_MS, MAX_INTERVAL_MINUTES, MIN_INTERVAL_MINUTES,
  addIngestResult, alarmMatches, alarmPlan, backoffMs, buildSearchUrl, cardToIngestJob, cardsToIngestJobs, chunk,
  SETTLE_EMPTY_MS, SETTLE_MAX_MS, blockMessage, describeEmptyPage, settleStep,
  defaultLookbackDays, effectiveLookbackDays, pageDecision, parsePostedAt, parseTileText, withinLookback,
  detectBlockedPage, emptyTotals, isLockFree, normalizeGatherSettings, parseRating, pickQueries,
} from './job-gather';
import { THROTTLE_PAGE_TEXT } from './proposal-scrape';

const card = {
  upworkJobId: '0123456789012345678',
  upworkUrl: 'https://www.upwork.com/jobs/~0123456789012345678',
  title: 'Build a SaaS dashboard',
  description: 'We need a React dashboard…',
  jobType: 'hourly',
  experienceLevel: 'Expert',
  postedDateRaw: 'Posted 2 hours ago',
  clientInfo: { paymentVerified: true, rating: '4.9', totalSpent: '$10K+' },
};

describe('cardToIngestJob', () => {
  it('maps only the fields the card scraper reads', () => {
    expect(cardToIngestJob(card)).toEqual({
      upwork_url: card.upworkUrl,
      title: card.title,
      description: card.description,
      skills: [],
      budget_amount: null,
      budget_type: 'hourly',
      posted_at: null,
      posted_text: 'Posted 2 hours ago',
      client_info: { payment_verified: true, rating: 4.9, total_spent: '$10K+' },
      proposals_text: null,
    });
  });

  it('leaves out client fields the card did not have', () => {
    const j = cardToIngestJob({ ...card, clientInfo: { paymentVerified: false, rating: null, totalSpent: null } });
    expect(j.client_info).toEqual({ payment_verified: false });
  });

  it('nulls unknown job types, missing description, posted text and client info', () => {
    const j = cardToIngestJob({ upworkUrl: card.upworkUrl, title: 't', jobType: 'weird', clientInfo: null });
    expect(j.budget_type).toBeNull();
    expect(j.description).toBe('');
    expect(j.posted_text).toBeNull();
    expect(j.client_info).toBeNull();
  });

  it('keeps fixed price', () => {
    expect(cardToIngestJob({ ...card, jobType: 'fixed' }).budget_type).toBe('fixed');
  });
});

describe('parseRating', () => {
  it('reads the first 0–5 number', () => {
    expect(parseRating('4.85')).toBe(4.85);
    expect(parseRating('Rating is 5 out of 5.')).toBe(5);
  });
  it('ignores missing or out-of-range values', () => {
    expect(parseRating(null)).toBeUndefined();
    expect(parseRating('no feedback yet')).toBeUndefined();
    expect(parseRating('120 reviews')).toBeUndefined();
  });
});

describe('cardsToIngestJobs', () => {
  it('drops cards without url or title and duplicate urls', () => {
    const jobs = cardsToIngestJobs([card, { ...card }, { ...card, upworkUrl: '' }, { ...card, upworkUrl: 'https://x/~2', title: '' }]);
    expect(jobs).toHaveLength(1);
  });
});

describe('chunk', () => {
  it('splits into groups of at most size', () => {
    const items = Array.from({ length: 120 }, (_, i) => i);
    const parts = chunk(items, 50);
    expect(parts.map((p) => p.length)).toEqual([50, 50, 20]);
    expect(parts.flat()).toEqual(items);
  });
  it('returns no chunks for no items', () => {
    expect(chunk([], 50)).toEqual([]);
  });
  it('rejects a size below 1', () => {
    expect(() => chunk([1], 0)).toThrow();
  });
});

describe('pickQueries', () => {
  const qs = ['a', 'b', 'c', 'd', 'e'].map((id, i) => ({
    id, query: `q-${id}`, active: true, created_at: `2026-01-0${i + 1}T00:00:00Z`,
  }));

  it('starts at the top without a cursor', () => {
    expect(pickQueries(qs, null, 2).map((q) => q.id)).toEqual(['a', 'b']);
  });

  it('continues after the cursor and wraps around', () => {
    expect(pickQueries(qs, 'b', 2).map((q) => q.id)).toEqual(['c', 'd']);
    expect(pickQueries(qs, 'd', 3).map((q) => q.id)).toEqual(['e', 'a', 'b']);
  });

  it('gives every query a turn across runs', () => {
    let cursor: string | null = null;
    const seen: string[] = [];
    for (let run = 0; run < 3; run++) {
      const batch: typeof qs = pickQueries(qs, cursor, 2);
      seen.push(...batch.map((q) => q.id));
      cursor = batch[batch.length - 1].id;
    }
    expect(new Set(seen)).toEqual(new Set(['a', 'b', 'c', 'd', 'e']));
  });

  it('never repeats a query within one run and restarts on an unknown cursor', () => {
    expect(pickQueries(qs, 'c', 10).map((q) => q.id)).toEqual(['d', 'e', 'a', 'b', 'c']);
    expect(pickQueries(qs, 'deleted', 1).map((q) => q.id)).toEqual(['a']);
  });

  it('skips inactive and blank queries and orders by creation', () => {
    const mixed = [qs[2], { ...qs[0], active: false }, qs[1], { ...qs[3], query: '  ' }];
    expect(pickQueries(mixed, null, 10).map((q) => q.id)).toEqual(['b', 'c']);
    expect(pickQueries([], null, 10)).toEqual([]);
  });
});

describe('detectBlockedPage', () => {
  const search = 'https://www.upwork.com/nx/search/jobs/?q=react&sort=recency';

  it('passes a normal results page', () => {
    expect(detectBlockedPage({ url: search, title: 'React Jobs | Upwork', text: 'Jobs you might like', hasJobTiles: true })).toBeNull();
  });

  it("stops on Upwork's error toast", () => {
    expect(detectBlockedPage({ url: search, text: `x ${THROTTLE_PAGE_TEXT} y`, hasJobTiles: true })).toBe('error_toast');
  });

  it('stops on a login redirect', () => {
    expect(detectBlockedPage({ url: 'https://www.upwork.com/ab/account-security/login?redir=%2Fnx%2Fsearch' })).toBe('login');
  });

  it('stops on a challenge page', () => {
    expect(detectBlockedPage({ url: search, title: 'Just a moment...' })).toBe('captcha');
    expect(detectBlockedPage({ url: 'https://www.upwork.com/cdn-cgi/challenge-platform/h/b' })).toBe('captcha');
    expect(detectBlockedPage({ url: search, text: 'Verify you are human by completing the action below.' })).toBe('captcha');
  });

  it("stops on Upwork's own Cloudflare page (served at the search URL)", () => {
    // Title and text from a captured Upwork challenge response (403, path unchanged).
    expect(detectBlockedPage({ url: search, title: 'Challenge - Upwork',
      text: 'Enable JavaScript and cookies to continue Cloudflare Ray ID: 9d90166a1f19769f' })).toBe('captcha');
    expect(detectBlockedPage({ url: search, title: 'Challenge - Upwork' })).toBe('captcha');
    expect(detectBlockedPage({ url: search, text: 'Cloudflare Ray ID: 9d90166a1f19769f' })).toBe('captcha');
  });

  it('does not treat a search for "challenge" as a challenge page', () => {
    expect(detectBlockedPage({ url: search, title: 'Coding challenge Jobs | Upwork', text: 'No jobs found' })).toBeNull();
  });

  it('does not treat job posts that mention captchas as a challenge', () => {
    expect(detectBlockedPage({
      url: 'https://www.upwork.com/nx/search/jobs/?q=captcha%20solver',
      title: 'Captcha solver Jobs | Upwork',
      text: 'Need a dev to bypass captcha; verify you are human flows',
      hasJobTiles: true,
    })).toBeNull();
  });

  it('does not treat a login word in the search query as a login page', () => {
    expect(detectBlockedPage({ url: 'https://www.upwork.com/nx/search/jobs/?q=login%20page' })).toBeNull();
  });
});

describe('isLockFree', () => {
  const now = 1_000_000_000;
  it('is free with no lock', () => {
    expect(isLockFree(null, 'me', now)).toBe(true);
  });
  it('is held by a live run in this worker', () => {
    expect(isLockFree({ run_id: 'r', instance_id: 'me', heartbeat_at: now - 1000 }, 'me', now)).toBe(false);
  });
  it('is free once the heartbeat is stale', () => {
    expect(isLockFree({ run_id: 'r', instance_id: 'me', heartbeat_at: now - LOCK_STALE_MS - 1 }, 'me', now)).toBe(true);
  });
  it('is free when an earlier (killed) worker took it', () => {
    expect(isLockFree({ run_id: 'r', instance_id: 'old', heartbeat_at: now }, 'me', now)).toBe(true);
  });
});

describe('settings and alarm', () => {
  it('defaults to off, every 180 minutes, 10 queries', () => {
    expect(normalizeGatherSettings(undefined)).toEqual(DEFAULT_GATHER_SETTINGS);
    expect(DEFAULT_GATHER_SETTINGS).toEqual({ enabled: false, intervalMinutes: 180, maxQueriesPerRun: 10, lookbackDays: null, maxPages: 5 });
  });

  it('clamps the interval to 60–720 minutes', () => {
    expect(normalizeGatherSettings({ intervalMinutes: 5 }).intervalMinutes).toBe(MIN_INTERVAL_MINUTES);
    expect(normalizeGatherSettings({ intervalMinutes: 5000 }).intervalMinutes).toBe(MAX_INTERVAL_MINUTES);
    expect(normalizeGatherSettings({ intervalMinutes: Number.NaN }).intervalMinutes).toBe(DEFAULT_INTERVAL_MINUTES);
    expect(normalizeGatherSettings({ enabled: 'yes' as unknown as boolean }).enabled).toBe(false);
  });

  it('plans a periodic alarm only when enabled', () => {
    expect(alarmPlan({ ...DEFAULT_GATHER_SETTINGS })).toEqual({ action: 'clear' });
    expect(alarmPlan({ ...DEFAULT_GATHER_SETTINGS, enabled: true, intervalMinutes: 240 }))
      .toEqual({ action: 'create', periodInMinutes: 240, delayInMinutes: 240 });
  });

  it('keeps a matching alarm instead of resetting it', () => {
    const plan = alarmPlan({ ...DEFAULT_GATHER_SETTINGS, enabled: true });
    expect(alarmMatches({ periodInMinutes: 180 }, plan)).toBe(true);
    expect(alarmMatches({ periodInMinutes: 60 }, plan)).toBe(false);
    expect(alarmMatches(undefined, plan)).toBe(false);
    expect(alarmMatches(undefined, { action: 'clear' })).toBe(true);
    expect(alarmMatches({ periodInMinutes: 180 }, { action: 'clear' })).toBe(false);
  });
});

describe('backoffMs', () => {
  it('doubles per blocked run, capped at 4 intervals', () => {
    const h = 60 * 60_000;
    expect(backoffMs(0, 60)).toBe(0);
    expect(backoffMs(1, 60)).toBe(h);
    expect(backoffMs(2, 60)).toBe(2 * h);
    expect(backoffMs(3, 60)).toBe(4 * h);
    expect(backoffMs(9, 60)).toBe(4 * h);
  });
});

describe('buildSearchUrl', () => {
  it('encodes the query, sorts by recency and appends saved params', () => {
    expect(buildSearchUrl('react & node', 'hourly_rate=50-')).toBe(
      'https://www.upwork.com/nx/search/jobs/?q=react%20%26%20node&sort=recency&hourly_rate=50-',
    );
    expect(buildSearchUrl('sql', null)).toBe('https://www.upwork.com/nx/search/jobs/?q=sql&sort=recency');
  });
});

describe('addIngestResult', () => {
  it('sums ingest counts', () => {
    const t = emptyTotals();
    addIngestResult(t, 50, { suggested: 3, duplicates: 10, pre_filtered: 7, below_threshold: 5 });
    addIngestResult(t, 20, { suggested: 1, duplicates: 0, pre_filtered: 2 });
    expect(t).toEqual({ queries_run: 0, jobs_sent: 70, suggested: 4, duplicates: 10, pre_filtered: 9, below_threshold: 5 });
  });
});

describe('settleStep', () => {
  const search = 'https://www.upwork.com/nx/search/jobs/?q=sql&sort=recency';
  const challenge = { url: search, title: 'Challenge - Upwork', text: 'Enable JavaScript and cookies to continue' };

  it('proceeds as soon as job tiles render', () => {
    expect(settleStep({ url: search, title: 'SQL Jobs | Upwork', hasJobTiles: true }, 1500)).toEqual({ action: 'proceed' });
  });

  it('waits out a challenge that may clear itself, and stops only when it is still there at the limit', () => {
    expect(settleStep(challenge, 1500)).toEqual({ action: 'wait' });
    expect(settleStep(challenge, SETTLE_MAX_MS - 1)).toEqual({ action: 'wait' });
    expect(settleStep(challenge, SETTLE_MAX_MS)).toEqual({ action: 'stop', reason: 'captcha' });
  });

  it('waits for a page that is still drawing, then treats it as an empty result page', () => {
    const blank = { url: search, title: 'SQL Jobs | Upwork', text: '' };
    expect(settleStep(blank, 1500)).toEqual({ action: 'wait' });
    expect(settleStep(blank, SETTLE_EMPTY_MS)).toEqual({ action: 'proceed' });
  });

  it('stops at once on a login page', () => {
    expect(settleStep({ url: 'https://www.upwork.com/ab/account-security/login' }, 1500)).toEqual({ action: 'stop', reason: 'login' });
  });

  it('names the page it saw when it stops', () => {
    expect(blockMessage('captcha', 'Challenge - Upwork')).toContain('(page title: "Challenge - Upwork")');
    expect(blockMessage('captcha')).not.toContain('page title');
  });
});

describe('describeEmptyPage', () => {
  it('summarises what an empty search page showed', () => {
    const line = describeEmptyPage({
      url: 'https://www.upwork.com/nx/search/jobs/?q=%22SQL%20Server%22&sort=recency',
      title: '"SQL Server" Jobs | Upwork', jobTiles: 0, articles: 12, titleLinks: 0, jobLinks: 24,
      dataTests: ['job-tile', 'job-title'], text: '  There are no results\n that match your search ',
    });
    expect(line).toContain('title ""SQL Server" Jobs | Upwork"');
    expect(line).toContain('url /nx/search/jobs/?q=%22SQL%20Server%22&sort=recency');
    expect(line).toContain('0 JobTile, 12 article, 0 title links, 24 /jobs/ links');
    expect(line).toContain('data-test: job-tile, job-title');
    expect(line).toContain('text "There are no results that match your search"');
    expect(line).not.toContain('first tile');
  });

  it('adds the first tile when tiles rendered but none was read', () => {
    const line = describeEmptyPage({ url: 'https://www.upwork.com/nx/search/jobs/', title: 'T', jobTiles: 10, articles: 10,
      titleLinks: 0, jobLinks: 15, dataTests: [], text: '', tileTests: ['UpLink', 'job-type-label'], tileLink: '/jobs/x_~021/' });
    expect(line).toContain('first tile data-test: UpLink, job-type-label; link /jobs/x_~021/');
  });
});

describe('lookback and paging', () => {
  const now = new Date('2026-11-03T12:00:00');

  it('defaults to 14 days until Nov 5, 2026, then 7; a set value wins', () => {
    expect(defaultLookbackDays(new Date('2026-11-04T23:59:00'))).toBe(14);
    expect(defaultLookbackDays(new Date('2026-11-05T00:00:00'))).toBe(7);
    expect(effectiveLookbackDays({ ...DEFAULT_GATHER_SETTINGS }, now)).toBe(14);
    expect(effectiveLookbackDays({ ...DEFAULT_GATHER_SETTINGS, lookbackDays: 21 }, now)).toBe(21);
    expect(normalizeGatherSettings({ lookbackDays: 99, maxPages: 50 })).toMatchObject({ lookbackDays: 30, maxPages: 10 });
    expect(normalizeGatherSettings({})).toMatchObject({ lookbackDays: null, maxPages: 5 });
  });

  it('reads Upwork posted text', () => {
    expect(parsePostedAt('Posted 3 hours ago', now)?.getTime()).toBe(now.getTime() - 3 * 3_600_000);
    expect(parsePostedAt('Posted yesterday', now)?.getTime()).toBe(now.getTime() - 86_400_000);
    expect(parsePostedAt('2 weeks ago', now)?.getTime()).toBe(now.getTime() - 14 * 86_400_000);
    expect(parsePostedAt('Posted an hour ago', now)?.getTime()).toBe(now.getTime() - 3_600_000);
    expect(parsePostedAt('sometime', now)).toBeNull();
  });

  it('pages until nothing new, the lookback window or the cap', () => {
    const cutoff = new Date(now.getTime() - 14 * 86_400_000);
    const base = { page: 1, maxPages: 5, newCount: 10, oldestPostedAt: new Date(now.getTime() - 86_400_000), cutoff };
    expect(pageDecision(base)).toEqual({ next: true, reason: 'more' });
    expect(pageDecision({ ...base, newCount: 0 })).toEqual({ next: false, reason: 'no_new' });
    expect(pageDecision({ ...base, oldestPostedAt: new Date(now.getTime() - 15 * 86_400_000) })).toEqual({ next: false, reason: 'past_lookback' });
    expect(pageDecision({ ...base, page: 5 })).toEqual({ next: false, reason: 'page_cap' });
    expect(pageDecision({ ...base, oldestPostedAt: null })).toEqual({ next: true, reason: 'more' });
  });

  it('builds page URLs and drops cards older than the window', () => {
    expect(buildSearchUrl('sql', null, 2)).toBe('https://www.upwork.com/nx/search/jobs/?q=sql&sort=recency&page=2');
    expect(buildSearchUrl('sql', null, 1)).toBe('https://www.upwork.com/nx/search/jobs/?q=sql&sort=recency');
    const cards = [{ postedDateRaw: 'Posted 2 days ago' }, { postedDateRaw: 'Posted 3 weeks ago' }, { postedDateRaw: null }];
    expect(withinLookback(cards, 14, now)).toEqual([cards[0], cards[2]]);
  });
});

describe('parseTileText', () => {
  it('reads hourly ranges, posted time and proposals', () => {
    expect(parseTileText('Posted 3 hours ago  Senior Software Consultant Hourly: $70-$80 Expert Proposals: Fewer than 5'))
      .toEqual({ budgetType: 'hourly', budgetAmount: '$70-$80', postedText: 'Posted 3 hours ago', proposalsText: 'Fewer than 5' });
  });

  it('reads fixed-price budgets', () => {
    expect(parseTileText('Posted yesterday Fixed price - Intermediate - Est. budget: $1,500 Proposals: 20 to 50'))
      .toEqual({ budgetType: 'fixed', budgetAmount: '$1,500', postedText: 'Posted yesterday', proposalsText: '20 to 50' });
  });

  it('knows the type when no amount is shown', () => {
    expect(parseTileText('Posted 1 hour ago Hourly Expert Est. Time: Less than 1 week')).toMatchObject({ budgetType: 'hourly', budgetAmount: null });
    expect(parseTileText('nothing here')).toEqual({ budgetType: null, budgetAmount: null, postedText: null, proposalsText: null });
  });
});
