import { useState } from 'react';
import { apiClient } from '../../lib/api-client';

interface Insights {
  whats_working: string;
  whats_not_landing: string;
  recommendations: string[];
  job_types_to_target: string[];
  job_types_to_avoid: string[];
  positioning_tip: string;
}

interface InsightsResult {
  insights: Insights | null;
  proposal_count?: number;
  response_rate?: number;
  message?: string;
}

export default function InsightsPage() {
  const [data, setData] = useState<InsightsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.getProposalInsights();
      setData(result);
    } catch (err) {
      setError('Failed to generate insights. Try again.');
      console.error('[UpApply] Insights failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white border-b px-4 py-3 flex-shrink-0 flex items-center justify-between">
        <h1 className="font-bold text-gray-900 text-sm">AI Insights</h1>
        {data?.proposal_count != null && (
          <span className="text-[10px] text-gray-400">
            {data.proposal_count} proposals · {data.response_rate?.toFixed(0)}% response
          </span>
        )}
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-3">
        {!data && !loading && (
          <div className="text-center py-10 space-y-3">
            <p className="text-sm text-gray-500 leading-snug">
              AI analysis of your proposal history — what's landing, what's not, and where to focus.
            </p>
            <button
              type="button"
              onClick={generate}
              className="btn-primary px-6 py-2 text-sm"
            >
              Generate Insights
            </button>
            {error && <p className="text-xs text-red-500">{error}</p>}
          </div>
        )}

        {loading && (
          <div className="text-center py-10 text-gray-400 text-sm animate-pulse">
            Analyzing your proposal history…
          </div>
        )}

        {data && !loading && (
          <>
            {data.message && !data.insights && (
              <div className="card bg-amber-50 text-amber-700 text-sm p-3 text-center">
                {data.message}
              </div>
            )}

            {data.insights && (
              <>
                {/* What's working */}
                <div className="card p-3 space-y-1 border-emerald-200 bg-emerald-50">
                  <p className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wide">What's landing</p>
                  <p className="text-xs text-gray-700 leading-snug">{data.insights.whats_working}</p>
                </div>

                {/* What's not landing */}
                <div className="card p-3 space-y-1 border-amber-200 bg-amber-50">
                  <p className="text-[10px] font-semibold text-amber-700 uppercase tracking-wide">What's not landing</p>
                  <p className="text-xs text-gray-700 leading-snug">{data.insights.whats_not_landing}</p>
                </div>

                {/* Positioning tip */}
                <div className="card p-3 space-y-1 border-blue-200 bg-blue-50">
                  <p className="text-[10px] font-semibold text-blue-700 uppercase tracking-wide">Positioning tip</p>
                  <p className="text-xs text-gray-700 leading-snug">{data.insights.positioning_tip}</p>
                </div>

                {/* Recommendations */}
                {data.insights.recommendations.length > 0 && (
                  <div className="card p-3 space-y-2">
                    <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wide">Recommendations</p>
                    <ul className="space-y-1.5">
                      {data.insights.recommendations.map((rec, i) => (
                        <li key={i} className="flex gap-2 text-xs text-gray-700">
                          <span className="text-emerald-500 mt-0.5 flex-shrink-0">→</span>
                          <span className="leading-snug">{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Job types */}
                <div className="card p-3 space-y-2">
                  <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wide">Job targeting</p>
                  {data.insights.job_types_to_target.length > 0 && (
                    <div>
                      <p className="text-[10px] text-emerald-600 font-medium mb-1">Target these</p>
                      <div className="flex flex-wrap gap-1">
                        {data.insights.job_types_to_target.map((t, i) => (
                          <span key={i} className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {data.insights.job_types_to_avoid.length > 0 && (
                    <div>
                      <p className="text-[10px] text-red-500 font-medium mb-1">Lower priority</p>
                      <div className="flex flex-wrap gap-1">
                        {data.insights.job_types_to_avoid.map((t, i) => (
                          <span key={i} className="text-[10px] bg-red-50 text-red-500 px-2 py-0.5 rounded-full">{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  onClick={generate}
                  disabled={loading}
                  className="w-full text-xs text-gray-400 hover:text-gray-600 py-1"
                >
                  ↻ Refresh
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
