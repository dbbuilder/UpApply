import { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../../lib/api-client';

interface ScoredJobEntry {
  id?: string;
  url: string;
  title: string;
  score: number;
  chips: string[];
  scored_at: string;
  user_rating?: number;
  user_comment?: string;
}

const SCORE_COLOR = (s: number) =>
  s >= 90 ? '#15803d' : s >= 80 ? '#16a34a' : s >= 70 ? '#ca8a04' : '#dc2626';

const SCORE_BG = (s: number) =>
  s >= 90 ? '#f0fdf4' : s >= 80 ? '#f0fdf4' : s >= 70 ? '#fffbeb' : '#fef2f2';

function StarRating({ rating, onRate }: { rating?: number; onRate: (r: number) => void }) {
  const [hovered, setHovered] = useState(0);
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map(star => (
        <button
          key={star}
          type="button"
          onClick={() => onRate(star)}
          onMouseEnter={() => setHovered(star)}
          onMouseLeave={() => setHovered(0)}
          className="text-base leading-none"
          title={`Rate ${star} star${star > 1 ? 's' : ''}`}
        >
          <span style={{ color: star <= (hovered || rating || 0) ? '#f59e0b' : '#d1d5db' }}>★</span>
        </button>
      ))}
    </div>
  );
}

type SortKey = 'score' | 'recent' | 'rating';
type ScoreFilter = 'all' | 90 | 70 | 50;

export default function FindPage() {
  const [jobs, setJobs] = useState<ScoredJobEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedUrl, setExpandedUrl] = useState<string | null>(null);
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const [savingComment, setSavingComment] = useState<string | null>(null);

  // Filters
  const [scoreFilter, setScoreFilter] = useState<ScoreFilter>('all');
  const [chipFilter, setChipFilter] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<SortKey>('score');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Merge local cache + API reviews
      const [localData, apiReviews] = await Promise.allSettled([
        new Promise<Record<string, ScoredJobEntry>>((resolve) => {
          chrome.storage.local.get('scoredJobsCache', (d) => resolve(d.scoredJobsCache || {}));
        }),
        apiClient.listJobReviews({ sort, limit: 200 }),
      ]);

      const merged: Record<string, ScoredJobEntry> = {};

      // Start with local cache
      if (localData.status === 'fulfilled') {
        Object.entries(localData.value).forEach(([url, entry]) => {
          merged[url] = { ...entry };
        });
      }

      // Overlay API reviews (they have ratings and are persisted across sessions)
      if (apiReviews.status === 'fulfilled') {
        apiReviews.value.reviews.forEach(r => {
          merged[r.upwork_job_url] = {
            id: r.id,
            url: r.upwork_job_url,
            title: r.job_title,
            score: r.ai_score ?? 0,
            chips: r.chips ?? [],
            scored_at: r.scored_at ?? r.created_at,
            user_rating: r.user_rating ?? undefined,
            user_comment: r.user_comment ?? undefined,
          };
        });
      }

      setJobs(Object.values(merged));
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  const allChips = Array.from(new Set(jobs.flatMap(j => j.chips))).sort();

  const filtered = jobs
    .filter(j => scoreFilter === 'all' || j.score >= scoreFilter)
    .filter(j => chipFilter.size === 0 || j.chips.some(c => chipFilter.has(c)))
    .sort((a, b) => {
      if (sort === 'recent') return b.scored_at.localeCompare(a.scored_at);
      if (sort === 'rating') return (b.user_rating ?? 0) - (a.user_rating ?? 0) || b.score - a.score;
      return b.score - a.score;
    });

  const handleNavigate = (url: string) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) chrome.tabs.update(tabs[0].id, { url });
    });
  };

  const handleRate = async (job: ScoredJobEntry, rating: number) => {
    // Optimistic update
    setJobs(prev => prev.map(j => j.url === job.url ? { ...j, user_rating: rating } : j));
    if (job.id) {
      try {
        await apiClient.rateJobReview(job.id, { user_rating: rating, user_comment: job.user_comment });
      } catch { /* silent */ }
    }
  };

  const handleSaveComment = async (job: ScoredJobEntry) => {
    const comment = commentDrafts[job.url] ?? job.user_comment ?? '';
    setSavingComment(job.url);
    setJobs(prev => prev.map(j => j.url === job.url ? { ...j, user_comment: comment } : j));
    if (job.id) {
      try {
        await apiClient.rateJobReview(job.id, { user_rating: job.user_rating ?? 3, user_comment: comment });
      } catch { /* silent */ }
    }
    setSavingComment(null);
    setExpandedUrl(null);
  };

  const toggleChipFilter = (chip: string) => {
    setChipFilter(prev => {
      const next = new Set(prev);
      if (next.has(chip)) next.delete(chip); else next.add(chip);
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Filters */}
      <div className="bg-white border-b px-4 pt-3 pb-2 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">{filtered.length} jobs</span>
        </div>

        {/* Score filter */}
        <div className="flex gap-1">
          {([['all', 'All'], [90, '≥90'], [70, '≥70'], [50, '≥50']] as [ScoreFilter, string][]).map(([val, label]) => (
            <button
              key={String(val)}
              type="button"
              onClick={() => setScoreFilter(val)}
              className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                scoreFilter === val ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
          <div className="flex-1" />
          <select
            value={sort}
            onChange={e => setSort(e.target.value as SortKey)}
            className="text-xs border border-gray-200 rounded px-1 py-0.5 text-gray-600 bg-white"
          >
            <option value="score">Score</option>
            <option value="recent">Recent</option>
            <option value="rating">My Rating</option>
          </select>
        </div>

        {/* Chip filters */}
        {allChips.length > 0 && (
          <div className="flex flex-wrap gap-1 pb-1">
            {allChips.slice(0, 12).map(chip => (
              <button
                key={chip}
                type="button"
                onClick={() => toggleChipFilter(chip)}
                className={`px-2 py-0.5 rounded-full text-xs font-medium transition-colors ${
                  chipFilter.has(chip)
                    ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
              >
                {chip}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {loading && (
          <div className="text-center py-8 text-gray-400 text-sm">Loading…</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            <div className="text-3xl mb-2">🔍</div>
            <p className="text-sm font-medium text-gray-500">No scored jobs yet</p>
            <p className="text-xs mt-1">Use the Score button on Upwork notifications or saved jobs</p>
          </div>
        )}
        {filtered.map(job => (
          <div
            key={job.url}
            className="bg-white rounded-lg border border-gray-100 shadow-sm overflow-hidden"
            style={{ background: SCORE_BG(job.score) }}
          >
            <div className="flex items-start gap-2 p-3">
              {/* Score badge */}
              <span
                className="flex-shrink-0 text-xs font-bold rounded-full px-2 py-1 text-white"
                style={{ background: SCORE_COLOR(job.score), minWidth: 36, textAlign: 'center' }}
              >
                {Math.round(job.score)}
              </span>

              {/* Main content */}
              <div className="flex-1 min-w-0">
                <button
                  type="button"
                  onClick={() => handleNavigate(job.url)}
                  className="text-sm font-medium text-gray-900 hover:text-emerald-700 text-left line-clamp-2 w-full leading-snug"
                >
                  {job.title}
                </button>

                {job.chips.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {job.chips.map(chip => (
                      <span
                        key={chip}
                        onClick={() => toggleChipFilter(chip)}
                        className={`text-xs px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
                          chipFilter.has(chip) ? 'bg-indigo-100 text-indigo-700' : 'bg-white text-gray-500 border border-gray-200'
                        }`}
                      >
                        {chip}
                      </span>
                    ))}
                  </div>
                )}

                {/* Rating + comment toggle */}
                <div className="flex items-center gap-2 mt-2">
                  <StarRating
                    rating={job.user_rating}
                    onRate={(r) => handleRate(job, r)}
                  />
                  <button
                    type="button"
                    onClick={() => setExpandedUrl(expandedUrl === job.url ? null : job.url)}
                    className="text-xs text-gray-400 hover:text-gray-600 ml-1"
                  >
                    {job.user_comment ? '📝' : '+ note'}
                  </button>
                </div>

                {/* Comment editor */}
                {expandedUrl === job.url && (
                  <div className="mt-2">
                    <textarea
                      rows={2}
                      placeholder="Why is this a good or bad match?"
                      className="w-full text-xs border border-gray-200 rounded p-1.5 resize-none focus:ring-1 focus:ring-emerald-500 focus:border-transparent"
                      value={commentDrafts[job.url] ?? job.user_comment ?? ''}
                      onChange={e => setCommentDrafts(prev => ({ ...prev, [job.url]: e.target.value }))}
                    />
                    <button
                      type="button"
                      onClick={() => handleSaveComment(job)}
                      disabled={savingComment === job.url}
                      className="text-xs text-emerald-600 hover:text-emerald-800 font-medium mt-1 disabled:opacity-50"
                    >
                      {savingComment === job.url ? 'Saving…' : 'Save note'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
