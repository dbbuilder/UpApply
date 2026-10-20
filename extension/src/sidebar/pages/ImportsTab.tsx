/**
 * ImportsTab — master checklist of all data imports.
 *
 * Each row shows: description, last-run date, inline progress, and a
 * Run / ↻ Sync button. Last-run records are persisted in chrome.storage.local
 * so they survive sidebar reloads.
 */
import { useState, useEffect, useRef } from 'react';
import { apiClient } from '../../lib/api-client';

// ── Types ────────────────────────────────────────────────────────────────────

interface LastRun {
  ts: number;
  result: string;
}

interface RowState {
  running: boolean;
  message: string | null;
  lastRun: LastRun | null;
}

const STORAGE_KEY = (id: string) => `importLastRun_${id}`;

function formatTs(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffH = Math.floor(diffMin / 60);
  const diffD = Math.floor(diffH / 24);
  if (diffMin < 2) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffH < 24) return `${diffH}h ago`;
  if (diffD < 7) return `${diffD}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

async function loadLastRun(id: string): Promise<LastRun | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get(STORAGE_KEY(id), (result) => {
      resolve((result[STORAGE_KEY(id)] as LastRun) || null);
    });
  });
}

async function saveLastRun(id: string, result: string): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_KEY(id)]: { ts: Date.now(), result } }, resolve);
  });
}

// ── Import runners ────────────────────────────────────────────────────────────

async function runProposals(
  setMsg: (m: string) => void,
): Promise<string> {
  chrome.storage.local.remove('proposalImportProgress');
  // A new import reads the proposal lists afresh; its later chunks reuse them.
  chrome.storage.local.remove('proposalListCache');
  chrome.storage.local.remove('proposalListProgress');

  // Poll progress storage for live updates
  const interval = setInterval(() => {
    chrome.storage.local.get(['proposalImportProgress', 'proposalListProgress'], (r) => {
      const p = r.proposalImportProgress as Record<string, unknown> | undefined;
      const lp = r.proposalListProgress as { page: number; totalPages: number | null } | undefined;
      if (!p) return;
      if (p.stage === 'scraping_active' || p.stage === 'scraping_archived') {
        const label = p.stage === 'scraping_active' ? 'active' : 'archived';
        const pageInfo = lp
          ? ` — Page ${lp.page}${lp.totalPages ? ` of ${lp.totalPages}` : ''}`
          : '';
        setMsg(`Scraping ${label} proposals${pageInfo}…`);
      } else if (p.stage === 'detail' || p.stage === 'throttled') {
        const cur = p.current as number;
        const tot = p.total as number;
        const grand = p.grandTotal as number | undefined;
        const skipped = p.skipped as number | undefined;
        const saved = p.saved as number | undefined;
        const sfx = grand && grand > tot ? ` of ${grand} total` : '';
        const extra = [
          skipped ? `skipped ${skipped} already complete` : '',
          saved ? `${saved} saved` : '',
        ].filter(Boolean).join(' · ');
        const counts = `(${cur}/${tot}${sfx})${extra ? ` · ${extra}` : ''}`;
        setMsg(p.stage === 'throttled'
          ? `Upwork is slowing us down — waiting ${p.waitSec as number} s… ${counts}`
          : `Fetching cover letters… ${counts}`);
      }
    });
  }, 800);

  try {
    type ScrapeResult = {
      success: boolean;
      data?: unknown[];
      error?: string;
      summary?: {
        scraped: number; saved: number; created: number; withLetters: number;
        skippedComplete: number; stoppedAt: number | null; paused?: boolean; total: number;
      };
    };
    // Each background run works for a bounded time (Chrome ends long requests) and replies
    // `paused`; keep starting chunks until it finishes. Saved batches persist between chunks
    // and completed proposals are skipped, so every chunk carries on where the last stopped.
    const MAX_CHUNKS = 25;
    let scraped = 0, created = 0, withLetters = 0, interrupted = 0;
    let last: NonNullable<ScrapeResult['summary']> | null = null;
    for (let chunk = 1; chunk <= MAX_CHUNKS; chunk++) {
      if (chunk > 1) setMsg(`Continuing (part ${chunk})…`);
      const scrapeResult = await new Promise<ScrapeResult | undefined>(
        (resolve) => chrome.runtime.sendMessage({ type: 'IMPORT_PROPOSALS' }, (r) => {
          void chrome.runtime.lastError;
          resolve(r);
        })
      );
      if (!scrapeResult) {
        // The background worker ended mid-run; what it saved is kept, so try once more.
        if (++interrupted > 1) throw new Error('The import was interrupted twice — run it again; completed proposals are skipped.');
        continue;
      }
      interrupted = 0;
      if (!scrapeResult.success || !scrapeResult.summary) {
        throw new Error(scrapeResult.error || 'No proposals found.');
      }
      const s = scrapeResult.summary;
      last = s;
      scraped += s.scraped; created += s.created; withLetters += s.withLetters;
      // The background saves in batches as it goes; only rows whose save failed come back in data.
      const unsaved = (scrapeResult.data || []) as Record<string, unknown>[];
      if (unsaved.length) {
        setMsg(`Saving ${unsaved.length} proposals…`);
        created += (await apiClient.importProposalsFromUpwork(unsaved)).length;
      }
      if (!s.paused) break;
    }
    if (!last) throw new Error('No proposals found.');
    const summary = `${scraped} scraped · ${created} new · ${withLetters} with cover letters`
      + (last.skippedComplete ? ` · ${last.skippedComplete} already complete` : '');
    if (last.stoppedAt !== null) {
      return `Upwork is rate-limiting; stopped — run again later, completed ones are skipped. ${summary}`;
    }
    if (last.paused) return `Paused after ${MAX_CHUNKS} parts — run again to continue. ${summary}`;
    return summary;
  } finally {
    clearInterval(interval);
    chrome.storage.local.remove('proposalListProgress');
  }
}

async function runContracts(
  setMsg: (m: string) => void,
): Promise<string> {
  chrome.storage.local.remove('contractImportProgress');

  const interval = setInterval(() => {
    chrome.storage.local.get('contractImportProgress', (r) => {
      const p = r.contractImportProgress as Record<string, unknown> | undefined;
      if (!p) return;
      if (p.stage === 'navigating') setMsg('Navigating to contracts page…');
      else if (p.stage === 'scraping') setMsg(`Scraping page ${p.page as number}…`);
      else if (p.stage === 'saving') setMsg('Saving contracts…');
    });
  }, 800);

  try {
    const resp = await new Promise<{ success: boolean; imported?: number; updated?: number; total?: number; error?: string }>(
      (resolve) => chrome.runtime.sendMessage({ type: 'NAVIGATE_AND_IMPORT_CONTRACTS' }, resolve)
    );
    clearInterval(interval);

    if (!resp?.success) throw new Error(resp?.error || 'Contract import failed.');
    return `${resp.imported ?? 0} new · ${resp.updated ?? 0} updated of ${resp.total ?? 0} total`;
  } finally {
    clearInterval(interval);
  }
}

async function runSavedJobs(
  setMsg: (m: string) => void,
): Promise<string> {
  setMsg('Opening saved jobs page…');
  const scrapeResult = await new Promise<{ success: boolean; data?: unknown[]; error?: string }>(
    (resolve) => chrome.runtime.sendMessage({ type: 'IMPORT_SAVED_JOBS' }, resolve)
  );

  if (!scrapeResult?.success || !scrapeResult.data?.length) {
    throw new Error(scrapeResult?.error || 'No saved jobs found.');
  }

  setMsg(`Analyzing ${scrapeResult.data.length} jobs…`);
  const rawCards = scrapeResult.data as Array<{
    upworkJobId: string; upworkUrl: string; title: string; description: string;
    jobType?: string; experienceLevel?: string; postedDateRaw?: string;
    clientInfo?: Record<string, unknown>;
  }>;
  const SAVED_JOBS_MAX_AGE_DAYS = 14;
  const recentCards = rawCards.filter((c) => parseDaysAgo(c.postedDateRaw) <= SAVED_JOBS_MAX_AGE_DAYS);
  const skipped = rawCards.length - recentCards.length;
  const items = recentCards.map((c) => ({
    upwork_job_id: c.upworkJobId,
    upwork_url: c.upworkUrl,
    title: c.title,
    description: c.description,
    job_type: c.jobType,
    experience_level: c.experienceLevel,
    posted_date_raw: c.postedDateRaw,
    client_info: c.clientInfo,
  }));
  const imported = await apiClient.importBulkJobs(items, 'saved');
  const skipNote = skipped > 0 ? ` · ${skipped} older than 14d skipped` : '';
  return `${imported.length} new jobs added to Queue${skipNote}`;
}

async function runBackfill(
  setMsg: (m: string) => void,
): Promise<string> {
  setMsg('Backfilling proposal corpus…');
  const r = await apiClient.backfillProposalsCorpus();
  return `${r.created} new · ${r.updated} updated · ${r.skipped} skipped`;
}

async function runSavedSearches(
  setMsg: (m: string) => void,
): Promise<string> {
  setMsg('Opening Upwork saved searches…');
  const result = await new Promise<{
    success: boolean;
    data?: Array<{ query: string; url_params: string; label: string }>;
    error?: string;
  }>((resolve) => chrome.runtime.sendMessage({ type: 'IMPORT_UPWORK_SAVED_SEARCHES' }, resolve));

  if (!result?.success || !result.data?.length) {
    throw new Error(result?.error || 'No saved searches found on Upwork.');
  }

  const toImport = result.data.map((s) => ({
    query: s.query,
    url_params: s.url_params || undefined,
    source: 'imported' as const,
  }));
  const imported = await apiClient.bulkImportSearchQueries(toImport);
  return `${imported.length} searches imported`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// Parse relative date strings to approximate days ago
function parseDaysAgo(raw: string | undefined): number {
  if (!raw) return 0;
  const s = raw.toLowerCase();
  if (s.includes('just now') || s.includes('minute') || s.includes('hour')) return 0;
  if (s.includes('yesterday')) return 1;
  const daysMatch = s.match(/(\d+)\s*day/);
  if (daysMatch) return parseInt(daysMatch[1], 10);
  const weeksMatch = s.match(/(\d+)\s*week/);
  if (weeksMatch) return parseInt(weeksMatch[1], 10) * 7;
  if (s.includes('month') || s.includes('year')) return 999;
  return 0;
}

// ── Import definitions ────────────────────────────────────────────────────────

interface ImportDef {
  id: string;
  icon: string;
  title: string;
  description: string;
  note?: string;
  run: (setMsg: (m: string) => void) => Promise<string>;
}

const IMPORT_DEFS: ImportDef[] = [
  {
    id: 'proposals',
    icon: '📝',
    title: 'Proposals',
    description: 'Active + archived proposals with cover letters. Scrapes the last 150 most recent.',
    run: runProposals,
  },
  {
    id: 'contracts',
    icon: '✅',
    title: 'Won Contracts',
    description: 'Your full contract history — marks each as a won job in the corpus.',
    note: 'Navigates your active Upwork tab.',
    run: runContracts,
  },
  {
    id: 'saved_jobs',
    icon: '⭐',
    title: 'Saved Jobs',
    description: 'Jobs you\'ve bookmarked on Upwork. Only imports jobs posted in the last 14 days. Adds them to your Queue for scoring.',
    run: runSavedJobs,
  },
  {
    id: 'saved_searches',
    icon: '🔍',
    title: 'Saved Searches',
    description: 'Your Upwork saved search filters → imports as Search Queries you can re-run.',
    run: runSavedSearches,
  },
  {
    id: 'backfill_corpus',
    icon: '🔄',
    title: 'Backfill was_hired',
    description: 'Sets hired/declined status on proposals already in corpus. Run after importing proposals.',
    run: runBackfill,
  },
];

// ── ImportRow ─────────────────────────────────────────────────────────────────

function ImportRow({ def }: { def: ImportDef }) {
  const [state, setState] = useState<RowState>({ running: false, message: null, lastRun: null });
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    loadLastRun(def.id).then((lr) => {
      if (mountedRef.current) setState((s) => ({ ...s, lastRun: lr }));
    });
    return () => { mountedRef.current = false; };
  }, [def.id]);

  const setMsg = (message: string) => {
    if (mountedRef.current) setState((s) => ({ ...s, message }));
  };

  const handleRun = async () => {
    setState((s) => ({ ...s, running: true, message: 'Starting…' }));
    try {
      const result = await def.run(setMsg);
      await saveLastRun(def.id, result);
      if (mountedRef.current) {
        setState({ running: false, message: null, lastRun: { ts: Date.now(), result } });
      }
    } catch (err) {
      if (mountedRef.current) {
        setState((s) => ({ ...s, running: false, message: `Error: ${String(err).replace(/^Error:\s*/, '')}` }));
        setTimeout(() => {
          if (mountedRef.current) setState((s) => ({ ...s, message: null }));
        }, 8000);
      }
    }
  };

  const { running, message, lastRun } = state;
  const hasRun = !!lastRun;
  const isError = message?.startsWith('Error:');

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-3 space-y-2">
      <div className="flex items-start gap-2">
        <span className="text-xl leading-none mt-0.5 flex-shrink-0">{def.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold text-gray-800">{def.title}</p>
            <button
              type="button"
              onClick={handleRun}
              disabled={running}
              className={`flex-shrink-0 text-[11px] font-medium px-2.5 py-1 rounded-full transition-colors disabled:opacity-50 ${
                hasRun
                  ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  : 'bg-emerald-500 text-white hover:bg-emerald-600'
              }`}
            >
              {running ? '…' : hasRun ? '↻ Sync' : '↓ Run'}
            </button>
          </div>
          <p className="text-[10px] text-gray-400 leading-tight mt-0.5">{def.description}</p>
          {def.note && (
            <p className="text-[10px] text-amber-600 mt-0.5">⚠ {def.note}</p>
          )}
        </div>
      </div>

      {/* Status line */}
      {(message || lastRun) && (
        <div className={`text-[10px] px-2 py-1 rounded-md ${
          isError
            ? 'bg-red-50 text-red-600'
            : running
            ? 'bg-blue-50 text-blue-600 animate-pulse'
            : 'bg-gray-50 text-gray-500'
        }`}>
          {message ?? (lastRun ? `✓ ${lastRun.result} · ${formatTs(lastRun.ts)}` : '')}
        </div>
      )}
    </div>
  );
}

// ── ImportsTab ────────────────────────────────────────────────────────────────

export default function ImportsTab() {
  return (
    <div className="p-4 space-y-3">
      <p className="text-[11px] text-gray-400 leading-snug">
        Run each import once to seed UpApply with your history. After that, use{' '}
        <span className="font-medium text-gray-600">↻ Sync</span> to pick up new activity.
      </p>
      {IMPORT_DEFS.map((def) => (
        <ImportRow key={def.id} def={def} />
      ))}
      <p className="text-[10px] text-gray-300 text-center pt-1">
        Imports deduplicate — safe to run multiple times
      </p>
      <p className="text-[9px] text-gray-200 text-center select-none">
        v{chrome.runtime.getManifest().version} · {new Date(__BUILD_DATE__).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
      </p>
    </div>
  );
}
