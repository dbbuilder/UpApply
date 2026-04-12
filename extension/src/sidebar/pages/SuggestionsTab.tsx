/**
 * SuggestionsTab — shows agent-discovered jobs awaiting user review.
 *
 * Features:
 * - Score badge (green ≥75, amber ≥55, red <55)
 * - Skill chips, AI reasoning, budget/date
 * - Approve / Pass with rejection reason picker
 * - Learning summary banner (autonomy level + approval rate)
 */
import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError, JobQueueItem, JobQueueStats } from '../../lib/api-client';

// ── Constants ─────────────────────────────────────────────────────────────────

const REJECTION_REASONS = [
  'Budget too low',
  'Not my specialty',
  'Too large / long',
  'Client looks risky',
  'Already applied',
  'Other',
];

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

// ── Rejection reason picker ───────────────────────────────────────────────────

interface RejectPickerProps {
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

function RejectPicker({ onConfirm, onCancel }: RejectPickerProps) {
  const [selected, setSelected] = useState<string>('');

  return (
    <div className="mt-1 space-y-1.5 bg-red-50 border border-red-100 rounded-xl p-2.5">
      <p className="text-[10px] font-medium text-red-600">Why are you passing?</p>
      <div className="flex flex-wrap gap-1">
        {REJECTION_REASONS.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setSelected(selected === r ? '' : r)}
            className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
              selected === r
                ? 'bg-red-500 text-white border-red-500'
                : 'bg-white text-red-500 border-red-200 hover:border-red-400'
            }`}
          >
            {r}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5 pt-0.5">
        <button
          type="button"
          onClick={() => onConfirm(selected || 'Other')}
          className="flex-1 py-1 text-[10px] font-medium bg-red-500 text-white rounded-lg hover:bg-red-600 active:scale-95 transition-all"
        >
          Confirm Pass
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1 text-[10px] text-gray-500 bg-gray-100 rounded-lg hover:bg-gray-200 active:scale-95 transition-all"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Job card ──────────────────────────────────────────────────────────────────

interface JobCardProps {
  item: JobQueueItem;
  onAction: (id: string, action: 'approve' | 'reject', reason?: string) => Promise<void>;
}

function JobCard({ item, onAction }: JobCardProps) {
  const [acting, setActing] = useState<'approve' | 'reject' | null>(null);
  const [showRejectPicker, setShowRejectPicker] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isReviewed = item.status === 'approved' || item.status === 'rejected';

  const handleApprove = async () => {
    if (acting) return;
    setActing('approve');
    setError(null);
    try {
      await onAction(item.id, 'approve');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setActing(null);
    }
  };

  const handleRejectClick = () => {
    if (acting) return;
    setShowRejectPicker(true);
  };

  const handleRejectConfirm = async (reason: string) => {
    setShowRejectPicker(false);
    setActing('reject');
    setError(null);
    try {
      await onAction(item.id, 'reject', reason);
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

      {/* Action buttons */}
      {!isReviewed && !showRejectPicker && (
        <div className="flex gap-2 pt-0.5">
          <button
            type="button"
            disabled={!!acting}
            onClick={handleApprove}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg
              bg-emerald-50 text-emerald-700 hover:bg-emerald-100 active:scale-95
              text-[11px] font-medium transition-all disabled:opacity-50"
          >
            {acting === 'approve' ? '…' : '✓ Approve'}
          </button>
          <button
            type="button"
            disabled={!!acting}
            onClick={handleRejectClick}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg
              bg-red-50 text-red-600 hover:bg-red-100 active:scale-95
              text-[11px] font-medium transition-all disabled:opacity-50"
          >
            {acting === 'reject' ? '…' : '✕ Pass'}
          </button>
        </div>
      )}

      {/* Rejection reason picker */}
      {showRejectPicker && (
        <RejectPicker
          onConfirm={handleRejectConfirm}
          onCancel={() => setShowRejectPicker(false)}
        />
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
          {item.status === 'approved'
            ? '✓ Approved'
            : `✕ Passed${item.rejection_reason ? ` · ${item.rejection_reason}` : ''}`}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-md">{error}</p>
      )}
    </div>
  );
}

// ── Learning banner ───────────────────────────────────────────────────────────

interface LearningBannerProps {
  stats: JobQueueStats;
}

function LearningBanner({ stats }: LearningBannerProps) {
  const { all_time, recent_30, autonomy_label, score_threshold } = stats;
  const rate = recent_30.approval_rate;
  const rateStr = rate != null ? `${Math.round(rate * 100)}%` : '—';
  const approvedRecent = recent_30.approved;
  const totalRecent = recent_30.total;

  let message = '';
  if (totalRecent >= 5) {
    if (rate != null && rate >= 0.70) {
      message = `Great signal — approving ${rateStr} of recent suggestions. Threshold may lower.`;
    } else if (rate != null && rate < 0.35) {
      message = `Low approval rate (${rateStr}). Threshold raised to be more selective.`;
    } else {
      message = `Approved ${approvedRecent}/${totalRecent} recent suggestions (${rateStr}).`;
    }
  } else if (all_time.suggestions_shown > 0) {
    message = `${all_time.suggestions_shown} jobs seen so far — keep reviewing to calibrate.`;
  } else {
    message = 'Agent runs daily. Review suggestions to teach it your preferences.';
  }

  return (
    <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-3 py-2 space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-indigo-600">
          🤖 {autonomy_label}
        </span>
        <span className="text-[10px] text-indigo-400">
          threshold ≥ {score_threshold}
        </span>
      </div>
      <p className="text-[10px] text-indigo-500 leading-snug">{message}</p>
    </div>
  );
}

// ── Filter tabs ───────────────────────────────────────────────────────────────

type FilterMode = 'pending' | 'all';

// ── SuggestionsTab ────────────────────────────────────────────────────────────

export default function SuggestionsTab() {
  const [items, setItems] = useState<JobQueueItem[]>([]);
  const [stats, setStats] = useState<JobQueueStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterMode>('pending');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [all, queueStats] = await Promise.all([
        apiClient.getJobQueue(),
        apiClient.getJobQueueStats(),
      ]);
      setItems(all);
      setStats(queueStats);
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
    async (id: string, action: 'approve' | 'reject', reason?: string) => {
      const updated = await apiClient.actionJobQueueItem(id, action, reason);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
      // Refresh stats in background after each decision
      apiClient.getJobQueueStats().then(setStats).catch(() => {});
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
        <p className="text-[11px] text-gray-500 leading-snug">
          Jobs discovered by the agent. Approve to move to Queue, pass to skip.
        </p>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="text-[10px] text-gray-400 hover:text-gray-600 px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 flex-shrink-0"
        >
          {loading ? '…' : '↻'}
        </button>
      </div>

      {/* Learning banner */}
      {stats && !loading && <LearningBanner stats={stats} />}

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
          Agent learns from every Approve / Pass decision
        </p>
      )}
    </div>
  );
}
