/**
 * SuggestionsTab — shows agent-discovered jobs awaiting user review.
 *
 * Features:
 * - Score badge (green ≥75, amber ≥55, red <55)
 * - Skill chips, AI reasoning, budget/date
 * - Approve / Pass with rejection reason picker
 * - Learning summary banner (autonomy level + approval rate)
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient, AgentDigest, ApiError, ConfirmSubmitResult, DraftSubmitResult, JobQueueItem, JobQueueStats } from '../../lib/api-client';
import { useAppStore } from '../store';

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

/** Return Tailwind classes for a pre-filter reason chip based on its prefix. */
function filterReasonChipClass(reason: string): string {
  if (reason.startsWith('blocked_country')) return 'bg-orange-100 text-orange-700';
  if (reason.startsWith('budget_too_low') || reason.startsWith('hourly_top_too_low'))
    return 'bg-amber-100 text-amber-700';
  if (reason.startsWith('avoid_keyword')) return 'bg-red-100 text-red-600';
  // too_old, score_cap_reached
  return 'bg-gray-100 text-gray-500';
}

/** Convert a raw filter_reason code into a human-readable label. */
function formatFilterReason(reason: string): string {
  if (reason.startsWith('blocked_country')) {
    const country = reason.match(/\(([^)]+)\)/)?.[1];
    return country ? `📍 ${country}` : 'Geo blocked';
  }
  if (reason.startsWith('budget_too_low')) {
    const detail = reason.match(/\(([^)]+)\)/)?.[1];
    return detail ? `💰 Budget ${detail}` : 'Budget too low';
  }
  if (reason.startsWith('hourly_top_too_low')) {
    const detail = reason.match(/\(([^)]+)\)/)?.[1];
    return detail ? `⏱ ${detail}` : 'Hourly too low';
  }
  if (reason.startsWith('too_old')) {
    const detail = reason.match(/\(([^)]+)\)/)?.[1];
    return detail ? `🕐 ${detail} old` : 'Too old';
  }
  if (reason.startsWith('avoid_keyword')) {
    const kw = reason.match(/\(([^)]+)\)/)?.[1];
    return kw ? `🚫 "${kw.replace(/'/g, '')}"` : 'Blocked keyword';
  }
  if (reason.startsWith('score_cap_reached')) return '🔢 Score cap';
  return reason;
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

// ── Confirm send modal ────────────────────────────────────────────────────────

const COUNTDOWN_SECONDS = 60;

interface ConfirmSendModalProps {
  item: JobQueueItem;
  onConfirm: (bidAmount?: number, connectsSpent?: number) => Promise<ConfirmSubmitResult>;
  onAbort: () => void;
}

function ConfirmSendModal({ onConfirm, onAbort }: ConfirmSendModalProps) {
  const [seconds, setSeconds] = useState(COUNTDOWN_SECONDS);
  const [bidAmount, setBidAmount] = useState('');
  const [connectsSpent, setConnectsSpent] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setSeconds((s) => {
        if (s <= 1) {
          clearInterval(intervalRef.current!);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const handleConfirm = async () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    setConfirming(true);
    setError(null);
    try {
      const bid = bidAmount ? parseFloat(bidAmount) : undefined;
      const connects = connectsSpent ? parseInt(connectsSpent, 10) : undefined;
      await onConfirm(bid, connects);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setConfirming(false);
    }
  };

  const handleAbort = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    onAbort();
  };

  const pct = ((seconds / COUNTDOWN_SECONDS) * 100).toFixed(1);

  return (
    <div className="mt-2 bg-white border border-indigo-200 rounded-xl p-3 space-y-3 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold text-indigo-700">Ready to auto-fill?</p>
        <span className="text-[11px] font-mono text-indigo-400">{seconds}s</span>
      </div>

      {/* Countdown bar */}
      <div className="h-1 bg-indigo-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-400 transition-all duration-1000"
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="text-[10px] text-gray-500 leading-snug">
        The agent will open the apply page and fill your cover letter.
        Add your bid details below, then confirm — or abort to review first.
      </p>

      {/* Optional bid fields */}
      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-[9px] text-gray-400 uppercase tracking-wide">Bid ($)</label>
          <input
            type="number"
            min="0"
            step="0.01"
            value={bidAmount}
            onChange={(e) => setBidAmount(e.target.value)}
            placeholder="e.g. 85"
            className="w-full mt-0.5 px-2 py-1 text-[11px] border border-gray-200 rounded-lg
              focus:outline-none focus:border-indigo-300 bg-gray-50"
          />
        </div>
        <div className="flex-1">
          <label className="text-[9px] text-gray-400 uppercase tracking-wide">Connects</label>
          <input
            type="number"
            min="0"
            value={connectsSpent}
            onChange={(e) => setConnectsSpent(e.target.value)}
            placeholder="e.g. 6"
            className="w-full mt-0.5 px-2 py-1 text-[11px] border border-gray-200 rounded-lg
              focus:outline-none focus:border-indigo-300 bg-gray-50"
          />
        </div>
      </div>

      {error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-lg">{error}</p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={confirming || seconds === 0}
          onClick={handleConfirm}
          className="flex-1 py-1.5 text-[11px] font-medium bg-indigo-500 text-white
            rounded-lg hover:bg-indigo-600 active:scale-95 transition-all disabled:opacity-50"
        >
          {confirming ? 'Opening…' : '✓ Send Now'}
        </button>
        <button
          type="button"
          onClick={handleAbort}
          className="px-3 py-1.5 text-[11px] text-gray-500 bg-gray-100
            rounded-lg hover:bg-gray-200 active:scale-95 transition-all"
        >
          Abort
        </button>
      </div>

      {seconds === 0 && !confirming && (
        <p className="text-[10px] text-center text-gray-400">
          Countdown expired — review the draft or confirm manually.
        </p>
      )}
    </div>
  );
}

// ── Draft panel ───────────────────────────────────────────────────────────────

interface DraftPanelProps {
  item: JobQueueItem;
  onRequestDraft: (id: string) => Promise<void>;
  onSubmitEdit: (id: string, text: string) => Promise<DraftSubmitResult>;
  onConfirmSubmit: (id: string, bid?: number, connects?: number) => Promise<ConfirmSubmitResult>;
}

function DraftPanel({ item, onRequestDraft, onSubmitEdit, onConfirmSubmit }: DraftPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [editedText, setEditedText] = useState(item.draft_cover_letter || '');
  const [requesting, setRequesting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [submitResult, setSubmitResult] = useState<DraftSubmitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync textarea when draft arrives
  useEffect(() => {
    if (item.draft_cover_letter && !editedText) {
      setEditedText(item.draft_cover_letter);
    }
  }, [item.draft_cover_letter]);

  const handleRequestDraft = async () => {
    setRequesting(true);
    setError(null);
    try {
      await onRequestDraft(item.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setRequesting(false);
    }
  };

  const handleCopy = async () => {
    if (!editedText) return;
    await navigator.clipboard.writeText(editedText);
    setSubmitting(true);
    setError(null);
    try {
      const result = await onSubmitEdit(item.id, editedText);
      setSubmitResult(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmSend = async (bid?: number, connects?: number): Promise<ConfirmSubmitResult> => {
    setShowConfirmModal(false);
    return onConfirmSubmit(item.id, bid, connects);
  };

  // Not approved — don't show
  if (item.status !== 'approved') return null;

  // Generating
  if (item.draft_status === 'generating') {
    return (
      <div className="mt-1 bg-indigo-50 border border-indigo-100 rounded-xl px-3 py-2 flex items-center gap-2">
        <span className="text-[10px] text-indigo-500 animate-pulse">Generating draft…</span>
      </div>
    );
  }

  // No draft yet
  if (!item.draft_cover_letter || item.draft_status === 'none') {
    return (
      <div className="mt-1">
        <button
          type="button"
          disabled={requesting}
          onClick={handleRequestDraft}
          className="w-full py-1.5 text-[11px] font-medium bg-indigo-50 text-indigo-600
            border border-indigo-100 rounded-xl hover:bg-indigo-100 active:scale-95
            transition-all disabled:opacity-50"
        >
          {requesting ? '…' : '✏️ Generate Draft'}
        </button>
        {error && <p className="text-[10px] text-red-500 mt-1">{error}</p>}
      </div>
    );
  }

  // Draft ready or sent
  return (
    <div className="mt-1 space-y-1.5">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-1.5 bg-indigo-50
          border border-indigo-100 rounded-xl text-[11px] font-medium text-indigo-600
          hover:bg-indigo-100 transition-colors"
      >
        <span>
          {item.draft_status === 'sent' ? '✓ Draft sent' : '✏️ Draft ready'}
        </span>
        <span className="text-[10px] text-indigo-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="space-y-1.5">
          <textarea
            ref={textareaRef}
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            rows={10}
            className="w-full text-[11px] leading-relaxed font-mono p-2 border border-gray-200
              rounded-xl resize-y focus:outline-none focus:border-indigo-300 bg-gray-50"
          />
          {item.draft_status !== 'sent' && !showConfirmModal && (
            <div className="flex gap-2">
              <button
                type="button"
                disabled={submitting || !editedText}
                onClick={handleCopy}
                className="flex-1 py-1.5 text-[11px] font-medium bg-emerald-50 text-emerald-700
                  border border-emerald-200 rounded-xl hover:bg-emerald-100 active:scale-95
                  transition-all disabled:opacity-50"
              >
                {submitting ? '…' : '📋 Copy & Mark Sent'}
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setShowConfirmModal(true)}
                className="flex-1 py-1.5 text-[11px] font-medium bg-indigo-500 text-white
                  rounded-xl hover:bg-indigo-600 active:scale-95 transition-all disabled:opacity-50"
              >
                🚀 Send with Auto-fill
              </button>
            </div>
          )}

          {showConfirmModal && (
            <ConfirmSendModal
              item={item}
              onConfirm={handleConfirmSend}
              onAbort={() => setShowConfirmModal(false)}
            />
          )}
          {submitResult && (
            <p className="text-[10px] text-indigo-500 bg-indigo-50 px-2 py-1 rounded-lg leading-snug">
              {submitResult.message}
            </p>
          )}
          {error && (
            <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-lg">{error}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Job card ──────────────────────────────────────────────────────────────────

interface JobCardProps {
  item: JobQueueItem;
  onAction: (id: string, action: 'approve' | 'reject', reason?: string) => Promise<void>;
  onRequestDraft: (id: string) => Promise<void>;
  onSubmitEdit: (id: string, text: string) => Promise<DraftSubmitResult>;
  onConfirmSubmit: (id: string, bid?: number, connects?: number) => Promise<ConfirmSubmitResult>;
}

function JobCard({ item, onAction, onRequestDraft, onSubmitEdit, onConfirmSubmit }: JobCardProps) {
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

      {/* Draft panel — visible when approved */}
      {item.status === 'approved' && (
        <DraftPanel
          item={item}
          onRequestDraft={onRequestDraft}
          onSubmitEdit={onSubmitEdit}
          onConfirmSubmit={onConfirmSubmit}
        />
      )}

      {/* Error */}
      {error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-md">{error}</p>
      )}
    </div>
  );
}

// ── Filtered card ─────────────────────────────────────────────────────────────

interface FilteredCardProps {
  item: JobQueueItem;
  onScoreAnyway: (id: string) => Promise<void>;
}

function FilteredCard({ item, onScoreAnyway }: FilteredCardProps) {
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reason = item.rejection_reason ?? 'filtered';

  const handleScoreAnyway = async () => {
    setScoring(true);
    setError(null);
    try {
      await onScoreAnyway(item.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setScoring(false);
    }
  };

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-2.5 space-y-1.5">
      {/* Title */}
      <a
        href={item.upwork_url}
        target="_blank"
        rel="noreferrer"
        className="text-[11px] font-medium text-gray-700 hover:text-emerald-700 leading-snug line-clamp-2 block"
      >
        {item.title}
      </a>

      {/* Filter reason chip + budget */}
      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-none ${filterReasonChipClass(reason)}`}
        >
          {formatFilterReason(reason)}
        </span>
        {item.budget_amount && (
          <span className="text-[10px] text-gray-400">
            {item.budget_amount}{item.budget_type === 'hourly' ? '/hr' : ''}
          </span>
        )}
      </div>

      {/* Score anyway button */}
      <button
        type="button"
        disabled={scoring}
        onClick={handleScoreAnyway}
        className="w-full py-1 text-[10px] font-medium text-indigo-600 bg-indigo-50
          hover:bg-indigo-100 rounded-lg active:scale-95 transition-all disabled:opacity-50"
      >
        {scoring ? 'Scoring…' : 'Score anyway'}
      </button>

      {error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-0.5 rounded">{error}</p>
      )}
    </div>
  );
}

// ── Digest panel ──────────────────────────────────────────────────────────────

interface DigestPanelProps {
  digest: AgentDigest;
}

function DigestPanel({ digest }: DigestPanelProps) {
  const { today, pipeline, roi_30d, autonomy } = digest;
  const hasTodayActivity = Object.values(today).some((v) => v > 0);

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-3 space-y-2">
      {/* Level header */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-gray-700">
          Level {autonomy.level} · {autonomy.label}
        </span>
        <span className="text-[9px] text-gray-400">
          {autonomy.days_at_level}d at this level
        </span>
      </div>

      {/* Pipeline row */}
      <div className="flex gap-2 text-center">
        {[
          { label: 'Pending', value: pipeline.pending_review, color: 'text-amber-600' },
          { label: 'Drafts ready', value: pipeline.drafts_ready, color: 'text-indigo-600' },
          { label: 'Awaiting reply', value: pipeline.awaiting_response, color: 'text-emerald-600' },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex-1 bg-gray-50 rounded-lg py-1.5 px-1">
            <p className={`text-sm font-bold ${color}`}>{value}</p>
            <p className="text-[9px] text-gray-400 leading-tight">{label}</p>
          </div>
        ))}
      </div>

      {/* Today row */}
      {hasTodayActivity && (
        <div className="flex flex-wrap gap-1 text-[10px] text-gray-500 pt-0.5">
          <span className="font-medium text-gray-600 mr-0.5">Today:</span>
          {today.surfaced > 0 && <span>{today.surfaced} surfaced</span>}
          {today.approved > 0 && <span>· {today.approved} approved</span>}
          {today.drafted > 0 && <span>· {today.drafted} drafted</span>}
          {today.submitted > 0 && <span>· {today.submitted} sent</span>}
          {today.responses > 0 && <span>· {today.responses} responses</span>}
        </div>
      )}

      {/* Connects warning */}
      {roi_30d.connects_balance != null && roi_30d.min_reserve != null && (
        roi_30d.connects_balance - roi_30d.min_reserve < 10 && (
          <p className="text-[10px] text-amber-600 bg-amber-50 px-2 py-1 rounded-lg leading-snug">
            Low connects: {roi_30d.connects_balance} remaining (reserve {roi_30d.min_reserve})
          </p>
        )
      )}

      {/* Next level hint */}
      {autonomy.next_level_hint && (
        <p className="text-[9px] text-gray-400 leading-snug border-t border-gray-50 pt-1.5">
          {autonomy.next_level_hint}
        </p>
      )}
    </div>
  );
}

// ── Learning banner ───────────────────────────────────────────────────────────

interface LearningBannerProps {
  stats: JobQueueStats;
}

function LearningBanner({ stats }: LearningBannerProps) {
  const { all_time, recent_30, autonomy_label, score_threshold, avg_edit_distance } = stats;
  const rate = recent_30.approval_rate;
  const rateStr = rate != null ? `${Math.round(rate * 100)}%` : '—';
  const approvedRecent = recent_30.approved;
  const totalRecent = recent_30.total;

  let message = '';
  if (avg_edit_distance != null && all_time.proposals_submitted >= 3) {
    const editPct = Math.round(avg_edit_distance * 100);
    message = `Avg edit: ${editPct}% · Approval: ${rateStr} · ${all_time.proposals_submitted} drafts sent`;
  } else if (totalRecent >= 5) {
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
  const { setCurrentView } = useAppStore();
  const [items, setItems] = useState<JobQueueItem[]>([]);
  const [stats, setStats] = useState<JobQueueStats | null>(null);
  const [digest, setDigest] = useState<AgentDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterMode>('pending');
  const [showFiltered, setShowFiltered] = useState(false);

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
      // Load digest in background — non-blocking
      apiClient.getAgentDigest().then(setDigest).catch(() => {});
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
      apiClient.getJobQueueStats().then(setStats).catch(() => {});
    },
    []
  );

  const handleRequestDraft = useCallback(async (id: string) => {
    const updated = await apiClient.generateQueueItemDraft(id);
    setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    // Poll once after 8 seconds to pick up completed draft
    setTimeout(async () => {
      try {
        const all = await apiClient.getJobQueue();
        setItems(all);
      } catch { /* ignore */ }
    }, 8000);
  }, []);

  const handleSubmitEdit = useCallback(
    async (id: string, text: string) => {
      const result = await apiClient.submitQueueItemEdit(id, text);
      const [all, queueStats] = await Promise.all([
        apiClient.getJobQueue(),
        apiClient.getJobQueueStats(),
      ]);
      setItems(all);
      setStats(queueStats);
      return result;
    },
    []
  );

  const handleConfirmSubmit = useCallback(async (
    id: string, bid?: number, connects?: number
  ): Promise<ConfirmSubmitResult> => {
    const item = items.find((i) => i.id === id);
    if (!item?.draft_cover_letter || !item.upwork_url) {
      return { status: 'error', message: 'Draft or URL missing', autonomy_level: 0 };
    }

    // 1. Record confirmation on backend
    const result = await apiClient.confirmQueueItemSubmit(id, {
      bid_amount: bid,
      connects_spent: connects,
    });

    // 2. Store pendingAutoFill in chrome.storage so content script fills the textarea
    await chrome.storage.local.set({
      pendingAutoFill: {
        jobUrl: item.upwork_url,
        jobId: id,
        coverLetter: item.draft_cover_letter,
        timestamp: Date.now(),
      },
    });

    // 3. Open the apply page in a new tab
    const applyUrl = item.upwork_url.includes('/apply')
      ? item.upwork_url
      : item.upwork_url.replace(/\/?$/, '/apply');
    await chrome.tabs.create({ url: applyUrl, active: true });

    // 4. Refresh queue in background
    apiClient.getJobQueue().then(setItems).catch(() => {});

    return result;
  }, [items]);

  const handleScoreAnyway = useCallback(async (id: string) => {
    const updated = await apiClient.scoreAnyway(id);
    setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    // Poll once after 8s to pick up the scored result
    setTimeout(async () => {
      try {
        const all = await apiClient.getJobQueue();
        setItems(all);
      } catch { /* ignore */ }
    }, 8000);
  }, []);

  const nonFiltered = items.filter((i) => i.status !== 'pre_filtered');
  const filteredItems = items.filter((i) => i.status === 'pre_filtered');

  const displayed = filter === 'pending'
    ? nonFiltered.filter((i) => i.status === 'suggested')
    : nonFiltered;

  const pendingCount = nonFiltered.filter((i) => i.status === 'suggested').length;

  return (
    <div className="p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-gray-500 leading-snug flex-1 min-w-0">
          Jobs discovered by the agent. Approve to move to Queue, pass to skip.
        </p>
        <div className="flex gap-1 flex-shrink-0 ml-1">
          <button
            type="button"
            onClick={() => setCurrentView('guardrails')}
            title="Guardrail settings"
            className="text-[12px] text-gray-400 hover:text-gray-600 px-1.5 py-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            ⚙
          </button>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="text-[10px] text-gray-400 hover:text-gray-600 px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50"
          >
            {loading ? '…' : '↻'}
          </button>
        </div>
      </div>

      {/* Digest panel — richer view when digest loaded */}
      {digest && !loading && <DigestPanel digest={digest} />}

      {/* Learning banner — fallback when digest not yet loaded */}
      {stats && !loading && !digest && <LearningBanner stats={stats} />}

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
        <JobCard
          key={item.id}
          item={item}
          onAction={handleAction}
          onRequestDraft={handleRequestDraft}
          onSubmitEdit={handleSubmitEdit}
          onConfirmSubmit={handleConfirmSubmit}
        />
      ))}

      {/* Filtered section — collapsible */}
      {!loading && filteredItems.length > 0 && (
        <div className="space-y-1.5">
          <button
            type="button"
            onClick={() => setShowFiltered((v) => !v)}
            className="w-full flex items-center justify-between px-2 py-1.5
              bg-gray-50 border border-gray-100 rounded-xl text-[10px] text-gray-500
              hover:bg-gray-100 transition-colors"
          >
            <span className="font-medium">
              {showFiltered ? '▾' : '▸'} Pre-filtered ({filteredItems.length})
            </span>
            <span className="text-gray-400">blocked by geo / budget / keyword</span>
          </button>
          {showFiltered && (
            <div className="space-y-1.5 pl-1">
              {filteredItems.map((item) => (
                <FilteredCard
                  key={item.id}
                  item={item}
                  onScoreAnyway={handleScoreAnyway}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer hint */}
      {!loading && items.length > 0 && (
        <p className="text-[9px] text-gray-200 text-center select-none pt-1">
          Agent learns from every Approve / Pass decision
        </p>
      )}
    </div>
  );
}
