import { useState } from 'react';
import { apiClient, ProfileOptimizeResponse, ProfileDimension, ProfileRecommendation, May2026Item } from '../../lib/api-client';

function scoreColor(score: number): string {
  if (score >= 75) return 'text-emerald-600';
  if (score >= 55) return 'text-amber-500';
  return 'text-red-500';
}

function scoreBg(score: number): string {
  if (score >= 75) return 'bg-emerald-100 border-emerald-200';
  if (score >= 55) return 'bg-amber-50 border-amber-200';
  return 'bg-red-50 border-red-200';
}

function statusDot(status: 'good' | 'warning' | 'critical'): string {
  if (status === 'good') return 'bg-emerald-500';
  if (status === 'warning') return 'bg-amber-400';
  return 'bg-red-500';
}

function priorityBadge(priority: string): string {
  if (priority === 'critical') return 'bg-red-100 text-red-700';
  if (priority === 'high') return 'bg-orange-100 text-orange-700';
  if (priority === 'medium') return 'bg-amber-100 text-amber-600';
  return 'bg-gray-100 text-gray-600';
}

function priorityLabel(priority: string): string {
  if (priority === 'critical') return 'Critical';
  if (priority === 'high') return 'High';
  if (priority === 'medium') return 'Medium';
  return 'Low';
}

function DimensionCard({ dim }: { dim: ProfileDimension }) {
  return (
    <div className={`card p-2.5 border rounded-lg space-y-1 ${scoreBg(dim.score)}`}>
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot(dim.status)}`} />
          <span className="text-[11px] font-semibold text-gray-800 truncate">{dim.name}</span>
        </div>
        <span className={`text-sm font-bold flex-shrink-0 ${scoreColor(dim.score)}`}>{dim.score}</span>
      </div>
      <p className="text-[10px] text-gray-600 leading-snug">{dim.summary}</p>
    </div>
  );
}

function RecommendationCard({ rec }: { rec: ProfileRecommendation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="card p-3 space-y-1.5 border border-gray-200">
      <div className="flex items-start gap-2">
        <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full flex-shrink-0 mt-0.5 ${priorityBadge(rec.priority)}`}>
          {priorityLabel(rec.priority)}
        </span>
        <div className="min-w-0">
          <p className="text-[10px] text-gray-400 uppercase tracking-wide">{rec.dimension}</p>
          <p className="text-xs font-semibold text-gray-800 leading-snug">{rec.title}</p>
        </div>
      </div>
      {expanded && (
        <div className="space-y-1 pt-0.5">
          <p className="text-[11px] text-gray-600 leading-snug"><span className="font-medium text-gray-700">Problem:</span> {rec.problem}</p>
          <p className="text-[11px] text-emerald-700 leading-snug"><span className="font-medium">Action:</span> {rec.action}</p>
        </div>
      )}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="text-[10px] text-gray-400 hover:text-gray-600"
      >
        {expanded ? '▲ Less' : '▼ Details'}
      </button>
    </div>
  );
}

function ChecklistItem({ item }: { item: May2026Item }) {
  return (
    <div className="flex items-start gap-2">
      <span className={`flex-shrink-0 text-sm mt-0.5 ${item.done ? 'text-emerald-500' : 'text-red-400'}`}>
        {item.done ? '✓' : '✗'}
      </span>
      <div className="min-w-0">
        <p className={`text-[11px] leading-snug ${item.done ? 'text-gray-600' : 'text-gray-800 font-medium'}`}>{item.item}</p>
        {item.note && <p className="text-[10px] text-gray-400 leading-snug">{item.note}</p>}
      </div>
    </div>
  );
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // fallback — not critical
  }
}

export default function OptimizePage() {
  const [data, setData] = useState<ProfileOptimizeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const analyze = async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.getProfileOptimization(forceRefresh);
      setData(result);
    } catch (err) {
      setError('Analysis failed. Check your connection and try again.');
      console.error('[UpApply] Profile optimization failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async (field: string, text: string) => {
    await copyToClipboard(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1500);
  };

  const overallColor = data
    ? data.overall_score >= 75
      ? 'text-emerald-600'
      : data.overall_score >= 55
        ? 'text-amber-500'
        : 'text-red-500'
    : 'text-gray-400';

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-4 space-y-4">

        {/* Initial state */}
        {!data && !loading && (
          <div className="text-center py-10 space-y-3">
            <p className="text-sm text-gray-500 leading-snug">
              AI analysis of your Upwork profile — scores, gaps, rewrites, and a May 2026 readiness check.
            </p>
            <button
              type="button"
              onClick={() => analyze(false)}
              className="btn-primary px-6 py-2 text-sm"
            >
              Analyze My Profile
            </button>
            {error && <p className="text-xs text-red-500">{error}</p>}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="text-center py-10 text-gray-400 text-sm animate-pulse">
            Analyzing your profile…
          </div>
        )}

        {/* Results */}
        {data && !loading && (
          <>
            {/* Overall score hero */}
            <div className="card p-4 text-center border-gray-200">
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-1">Profile Score</p>
              <p className={`text-5xl font-bold ${overallColor}`}>{data.overall_score}</p>
              <p className="text-[10px] text-gray-400 mt-1">out of 100</p>
            </div>

            {/* Dimension grid */}
            <div>
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">Dimensions</p>
              <div className="grid grid-cols-2 gap-2">
                {data.dimensions.map((dim, i) => (
                  <DimensionCard key={i} dim={dim} />
                ))}
              </div>
            </div>

            {/* Recommendations */}
            {data.recommendations.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Recommendations ({data.recommendations.length})
                </p>
                <div className="space-y-2">
                  {data.recommendations.map((rec, i) => (
                    <RecommendationCard key={i} rec={rec} />
                  ))}
                </div>
              </div>
            )}

            {/* AI Rewrites */}
            {(data.suggested_title || data.suggested_overview_hook || (data.suggested_skills && data.suggested_skills.length > 0)) && (
              <div>
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">AI Rewrites</p>
                <div className="space-y-3">

                  {data.suggested_title && (
                    <div className="card p-3 space-y-1.5 border-blue-100 bg-blue-50">
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] font-semibold text-blue-700 uppercase tracking-wide">Suggested Title</p>
                        <div className="flex items-center gap-1">
                          <span className={`text-[10px] ${data.suggested_title.length > 50 ? 'text-red-500 font-bold' : 'text-gray-400'}`}>
                            {data.suggested_title.length}/50
                          </span>
                          <button
                            type="button"
                            onClick={() => handleCopy('title', data.suggested_title!)}
                            className="text-[10px] text-blue-500 hover:text-blue-700 ml-1"
                          >
                            {copiedField === 'title' ? 'Copied!' : 'Copy'}
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-gray-800 font-medium">{data.suggested_title}</p>
                    </div>
                  )}

                  {data.suggested_overview_hook && (
                    <div className="card p-3 space-y-1.5 border-purple-100 bg-purple-50">
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] font-semibold text-purple-700 uppercase tracking-wide">Overview Hook (first ~250 chars)</p>
                        <button
                          type="button"
                          onClick={() => handleCopy('hook', data.suggested_overview_hook!)}
                          className="text-[10px] text-purple-500 hover:text-purple-700"
                        >
                          {copiedField === 'hook' ? 'Copied!' : 'Copy'}
                        </button>
                      </div>
                      <p className="text-xs text-gray-700 leading-snug">{data.suggested_overview_hook}</p>
                    </div>
                  )}

                  {data.suggested_skills && data.suggested_skills.length > 0 && (
                    <div className="card p-3 space-y-1.5 border-gray-200">
                      <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wide">Suggested Skills</p>
                      <div className="flex flex-wrap gap-1">
                        {data.suggested_skills.map((skill, i) => (
                          <span key={i} className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
                            {skill}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* May 2026 Readiness */}
            {data.may_2026_checklist.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  May 2026 Readiness
                  <span className="ml-1 text-amber-500 font-normal">(Specialized Profiles end May 28)</span>
                </p>
                <div className="card p-3 space-y-2.5 border-amber-100 bg-amber-50">
                  {data.may_2026_checklist.map((item, i) => (
                    <ChecklistItem key={i} item={item} />
                  ))}
                </div>
              </div>
            )}

            {/* Footer — cache timestamp + refresh */}
            <div className="text-center space-y-1 pt-1 pb-2">
              {data.cached_at && (
                <p className="text-[10px] text-gray-400">
                  {data.cached ? 'Cached result · ' : 'Fresh · '}
                  {new Date(data.cached_at).toLocaleString()}
                </p>
              )}
              <button
                type="button"
                onClick={() => analyze(true)}
                disabled={loading}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                ↻ Refresh Analysis
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
