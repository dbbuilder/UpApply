/**
 * SuggestionsTab — shows agent-discovered jobs awaiting user review.
 *
 * Each card shows: title, AI score badge, chips, AI reasoning, budget, posted date.
 * Approve (green check) / Reject (red X) buttons update the job's status via API.
 */
import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError, JobQueueItem } from '../../lib/api-client';

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 75) return 'bg-emerald-100 text-emerald-700';
  if (score >= 55) return 'bg-amber-100 text-amber-700';
  return 'bg-red-100 text-red-600';
}

function formatRelative(isoStr: string): string {
  const d = new Date(isoStr);
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffH = Math.floor(diffMin / 60);
  const diffD = Math.floor(diffH / 24);
  if (diffMin < 2) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffH < 24) return `${diffH}h ago`;
  if (diffD < 7) return `${diffD}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── Job card ──────────────────────────────────────────────────────────────────

interface JobCardProps {
  item: JobQueueItem;
  onAction: (id: string, action: 'approve' | 'reject') => Promise<void>;
}

function JobCard({ item, onAction }: JobCardProps) {
  const [acting, setActing] = useState<'approve' | 'reject' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isReviewed = item.status === 'approved' || item.status === 'rejected';

  const handleAction = async (action: 'approve' | 'reject') => {
    if (acting) return;
    setActing(action);
    setError(null);
    try {
      await onAction(item.id, action);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setActing(null);
    }
  };

  return (
    <div
      className={`bg-white border rounded-xl p-3 space-y-2 transition-opacity ${
        isReviewed ? 'opacity-50' : 'border-gray-100'
      }`}
    >
      {/* Title + score */}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <a
            href={item.upwork_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-semibold text-gray-800 hover:text-emerald-700 leading-snug line-clamp-2 block"
          >
            {item.title}
          </a>
        </div>
        {item.ai_score != null && (
          <span
            className={`flex-shrink-0 text-[11px] font-bold px-2 py-0.5 rounded-full leading-none ${scoreColor(item.ai_score)}`}
          >
            {Math.round(item.ai_score)}
          </span>
        )}
      </div>

      {/* Chips */}
      {item.chips && item.chips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.chips.map((chip) => (
            <span
              key={chip}
              className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded-full leading-none"
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {/* AI reasoning */}
      {item.ai_reasoning && (
        <p className="text-[10px] text-gray-500 leading-snug line-clamp-3">
          {item.ai_reasoning}
        </p>
      )}

      {/* Budget + date row */}
      <div className="flex items-center justify-between gap-2 text-[10px] text-gray-400">
        <span>
          {item.budget_amount
            ? `${item.budget_amount}${item.budget_type === 'hourly' ? '/hr' : ''}`
            : 'Budget not listed'}
        </span>
        <span>{formatRelative(item.created_at)}</span>
      </div>

      {/* Action buttons — hidden once reviewed */}
      {!isReviewed && (
        <div className="flex gap-2 pt-0.5">
          <button
            type="button"
            disabled={!!acting}
            onClick={() => handleAction('approve')}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg
              bg-emerald-50 text-emerald-700 hover:bg-emerald-100 active:scale-95
              text-[11px] font-medium transition-all disabled:opacity-50"
          >
            {acting === 'approve' ? '…' : '✓ Approve'}
          </button>
          <button
            type="button"
            disabled={!!acting}
            onClick={() => handleAction('reject')}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg
              bg-red-50 text-red-600 hover:bg-red-100 active:scale-95
              text-[11px] font-medium transition-all disabled:opacity-50"
          >
            {acting === 'reject' ? '…' : '✕ Pass'}
          </button>
        </div>
      )}

      {/* Reviewed badge */}
      {isReviewed && (
        <div
          className={`text-[10px] text-center py-1 rounded-md font-medium ${
            item.status === 'approved'
              ? 'bg-emerald-50 text-emerald-600'
              : 'bg-gray-50 text-gray-400'
          }`}
        >
          {item.status === 'approved' ? '✓ Approved' : '✕ Passed'}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-md">{error}</p>
      )}
    </div>
  );
}

// ── Filter tabs ───────────────────────────────────────────────────────────────

type FilterMode = 'pending' | 'all';

// ── SuggestionsTab ────────────────────────────────────────────────────────────

export default function SuggestionsTab() {
  const [items, setItems] = useState<JobQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterMode>('pending');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const all = await apiClient.getJobQueue();
      setItems(all);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load suggestions.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleAction = useCallback(
    async (id: string, action: 'approve' | 'reject') => {
      const updated = await apiClient.actionJobQueueItem(id, action);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    },
    []
  );

  const displayed = filter === 'pending'
    ? items.filter((i) => i.status === 'suggested')
    : items;

  const pendingCount = items.filter((i) => i.status === 'suggested').length;

  return (
    <div className="p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] text-gray-500 leading-snug">
            Jobs discovered by the agent. Approve to move to Queue, pass to skip.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="text-[10px] text-gray-400 hover:text-gray-600 px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 flex-shrink-0"
        >
          {loading ? '…' : '↻'}
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1">
        {(['pending', 'all'] as FilterMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setFilter(mode)}
            className={`text-[11px] px-2.5 py-1 rounded-full font-medium transition-colors ${
              filter === mode
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
          >
            {mode === 'pending' ? `Pending (${pendingCount})` : `All (${items.length})`}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-50 border border-red-100 rounded-xl p-3 text-[11px] text-red-600">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <div key={n} className="bg-white border border-gray-100 rounded-xl p-3 animate-pulse">
              <div className="h-3 bg-gray-100 rounded w-3/4 mb-2" />
              <div className="h-2 bg-gray-50 rounded w-1/2 mb-2" />
              <div className="h-2 bg-gray-50 rounded w-full" />
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && displayed.length === 0 && (
        <div className="text-center py-12">
          <p className="text-2xl mb-2">🔍</p>
          <p className="text-[12px] font-medium text-gray-600">
            {filter === 'pending' ? 'No pending suggestions' : 'No suggestions yet'}
          </p>
          <p className="text-[11px] text-gray-400 mt-1 leading-snug">
            The agent runs daily at 6am PT and surfaces matching jobs here.
          </p>
        </div>
      )}

      {/* Job cards */}
      {!loading && displayed.map((item) => (
        <JobCard key={item.id} item={item} onAction={handleAction} />
      ))}

      {/* Footer hint */}
      {!loading && items.length > 0 && (
        <p className="text-[9px] text-gray-200 text-center select-none pt-1">
          Agent runs daily · threshold ≥ 55
        </p>
      )}
    </div>
  );
}
