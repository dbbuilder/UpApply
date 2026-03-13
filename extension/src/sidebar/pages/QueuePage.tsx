import { useState, useEffect, useCallback } from 'react';
import { apiClient, Job, Application, CoverLetter } from '../../lib/api-client';

// ── Types ─────────────────────────────────────────────────────────────────────

type JobState = 'saved' | 'queued' | 'applied' | 'won' | 'lost';

interface QueueItem {
  job: Job;
  application: Application | null;
  coverLetters: CoverLetter[];
  state: JobState; // null items are filtered out before storage
  refDate: Date; // used for 14-day cutoff
}

type FilterTab = 'active' | 'all' | 'closed';

const CUTOFF_DAYS = 14;

// ── Helpers ───────────────────────────────────────────────────────────────────

function deriveState(job: Job, app: Application | null): JobState | null {
  if (app) {
    const s = app.status;
    if (s === 'hired' || s === 'offered') return 'won';
    if (s === 'declined' || s === 'withdrawn' || s === 'no_response') return 'lost';
    if (s === 'submitted' || s === 'viewed' || s === 'responded' || s === 'interviewed') return 'applied';
    return 'queued'; // 'draft'
  }
  // No application — only show if explicitly saved from Upwork's saved-jobs page
  if (job.is_saved || job.source === 'saved') return 'saved';
  return null; // scored-only or search-imported with no user action → exclude
}

function refDate(job: Job, app: Application | null): Date {
  // Use most recent relevant timestamp
  if (app?.updated_at) return new Date(app.updated_at);
  return new Date(job.created_at);
}

const STATE_ORDER: Record<JobState, number> = {
  queued: 0,
  saved: 1,
  applied: 2,
  won: 3,
  lost: 4,
};

const STATE_LABEL: Record<JobState, string> = {
  saved: 'Saved',
  queued: 'Queued',
  applied: 'Applied',
  won: 'Won',
  lost: 'Lost',
};

const STATE_COLOR: Record<JobState, string> = {
  saved: 'bg-gray-100 text-gray-600',
  queued: 'bg-blue-100 text-blue-700',
  applied: 'bg-amber-100 text-amber-700',
  won: 'bg-emerald-100 text-emerald-700',
  lost: 'bg-red-100 text-red-500',
};

function scoreColor(score: number | undefined): string {
  if (score === undefined) return 'text-gray-400';
  if (score >= 70) return 'text-emerald-600';
  if (score >= 50) return 'text-amber-600';
  return 'text-red-500';
}

function starsDisplay(score: number | undefined): string {
  if (score === undefined) return '—';
  if (score >= 80) return '★★★★★';
  if (score >= 65) return '★★★★';
  if (score >= 50) return '★★★';
  if (score >= 35) return '★★';
  return '★';
}

function formatDate(d: string | undefined): string {
  if (!d) return '';
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── Row Component ─────────────────────────────────────────────────────────────

function QueueRow({ item, applyStatus, onApply }: {
  item: QueueItem;
  applyStatus: string | null;
  onApply: () => void;
}) {
  const { job, application, coverLetters, state } = item;
  const jobSlug = job.upwork_url?.match(/(~[a-zA-Z0-9]+)/)?.[1];
  const applyUrl = jobSlug
    ? `https://www.upwork.com/nx/proposals/job/${jobSlug}/apply/`
    : job.upwork_url;

  const dateStr = application?.submitted_at
    ? formatDate(application.submitted_at)
    : formatDate(job.created_at);

  return (
    <div className={`card py-2 px-3 space-y-1.5 ${state === 'won' ? 'border-emerald-200 bg-emerald-50' : ''}`}>
      {/* Title + score */}
      <div className="flex items-start gap-2">
        <a
          href={job.upwork_url}
          target="_blank"
          rel="noreferrer"
          className="flex-1 min-w-0 text-xs font-medium text-gray-900 hover:text-blue-700 line-clamp-2 leading-snug"
        >
          {job.title}
        </a>
        <span className={`text-xs font-bold shrink-0 ${scoreColor(job.match_score)}`}>
          {starsDisplay(job.match_score)}
        </span>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${STATE_COLOR[state]}`}>
          {STATE_LABEL[state]}
        </span>
        {job.budget_amount && (
          <span className="text-[10px] text-gray-500">
            {job.budget_amount}{job.budget_type === 'hourly' ? '/hr' : ''}
          </span>
        )}
        {coverLetters.length > 0 && (
          <span className="text-[10px] text-purple-500">📄</span>
        )}
        {dateStr && <span className="text-[10px] text-gray-400">{dateStr}</span>}
      </div>

      {/* Action */}
      {(state === 'queued' || state === 'saved') && (
        <button
          type="button"
          onClick={onApply}
          disabled={!!applyStatus}
          className="btn-primary w-full text-xs py-1 disabled:opacity-60"
        >
          {applyStatus || (coverLetters.length > 0 ? 'Apply with Letter →' : 'Apply →')}
        </button>
      )}
      {state === 'applied' && applyUrl && (
        <a
          href={applyUrl}
          target="_blank"
          rel="noreferrer"
          className="btn-outline w-full text-xs py-1 text-center block"
        >
          View on Upwork ↗
        </a>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function QueuePage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterTab>('active');
  const [applyStatuses, setApplyStatuses] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [jobs, applications, letters] = await Promise.all([
        apiClient.getJobs(),
        apiClient.getApplications(),
        apiClient.getCoverLetters(),
      ]);

      const appByJob = new Map<string, Application>();
      for (const app of applications) appByJob.set(app.job_id, app);

      const lettersByJob = new Map<string, CoverLetter[]>();
      for (const l of letters) {
        const arr = lettersByJob.get(l.job_id) ?? [];
        arr.push(l);
        lettersByJob.set(l.job_id, arr);
      }

      const cutoff = new Date(Date.now() - CUTOFF_DAYS * 24 * 60 * 60 * 1000);

      const merged: QueueItem[] = jobs
        .flatMap((job) => {
          const app = appByJob.get(job.id) ?? null;
          const state = deriveState(job, app);
          if (!state) return []; // scored-only / search-import with no user action
          const jobLetters = lettersByJob.get(job.id) ?? [];
          const rd = refDate(job, app);
          if (rd < cutoff) return []; // older than 14 days
          return [{ job, application: app, coverLetters: jobLetters, state, refDate: rd }];
        });

      // Sort: by state priority, then by score desc
      merged.sort((a, b) => {
        const sd = STATE_ORDER[a.state] - STATE_ORDER[b.state];
        if (sd !== 0) return sd;
        return (b.job.match_score ?? 0) - (a.job.match_score ?? 0);
      });

      setItems(merged);
    } catch {
      setError('Failed to load queue.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApply = async (item: QueueItem) => {
    const { job, coverLetters } = item;
    setApplyStatuses((p) => ({ ...p, [job.id]: 'Opening…' }));
    try {
      const jobSlug = job.upwork_url?.match(/(~[a-zA-Z0-9]+)/)?.[1];
      const applyUrl = jobSlug
        ? `https://www.upwork.com/nx/proposals/job/${jobSlug}/apply/`
        : job.upwork_url;

      if (coverLetters.length > 0) {
        const latest = coverLetters[coverLetters.length - 1];
        await chrome.storage.local.set({
          pendingAutoFill: {
            jobUrl: job.upwork_url,
            jobId: job.id,
            coverLetter: latest.content,
            timestamp: Date.now(),
          },
        });
        setApplyStatuses((p) => ({ ...p, [job.id]: 'Opening with letter…' }));
      }

      await chrome.tabs.create({ url: applyUrl || job.upwork_url, active: true });
      setTimeout(() => setApplyStatuses((p) => { const n = { ...p }; delete n[job.id]; return n; }), 4000);
    } catch {
      setApplyStatuses((p) => ({ ...p, [job.id]: 'Error' }));
      setTimeout(() => setApplyStatuses((p) => { const n = { ...p }; delete n[job.id]; return n; }), 3000);
    }
  };

  const ACTIVE_STATES: JobState[] = ['queued', 'saved'];
  const CLOSED_STATES: JobState[] = ['won', 'lost'];

  const visible = items.filter((it) => {
    if (filter === 'active') return ACTIVE_STATES.includes(it.state);
    if (filter === 'closed') return CLOSED_STATES.includes(it.state);
    return true; // 'all'
  });

  const counts = {
    active: items.filter((it) => ACTIVE_STATES.includes(it.state)).length,
    all: items.length,
    closed: items.filter((it) => CLOSED_STATES.includes(it.state)).length,
  };

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white border-b px-4 pt-3 pb-2 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h1 className="font-bold text-gray-900 text-sm">Queue</h1>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="text-xs text-gray-400 hover:text-gray-600 disabled:opacity-40"
          >
            {loading ? '…' : '↺'}
          </button>
        </div>
        <div className="flex gap-1">
          {([
            ['active', `Active (${counts.active})`],
            ['all', `All (${counts.all})`],
            ['closed', `Closed (${counts.closed})`],
          ] as [FilterTab, string][]).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === id
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3">
        {loading && <div className="text-center py-10 text-gray-400 text-sm">Loading…</div>}
        {error && !loading && (
          <div className="text-center py-8">
            <p className="text-sm text-red-600">{error}</p>
            <button type="button" onClick={load} className="btn-outline text-xs mt-2">Retry</button>
          </div>
        )}
        {!loading && !error && visible.length === 0 && (
          <div className="text-center py-10 text-gray-400 text-sm">
            {filter === 'active'
              ? 'No active jobs.\nScore jobs on Upwork, then check Queue or Apply.'
              : 'Nothing here.'}
          </div>
        )}
        {!loading && !error && visible.length > 0 && (
          <div className="space-y-2">
            {visible.map((item) => (
              <QueueRow
                key={item.job.id}
                item={item}
                applyStatus={applyStatuses[item.job.id] ?? null}
                onApply={() => handleApply(item)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
