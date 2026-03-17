import { useState, useEffect } from 'react';
import { apiClient, ProposalStats, AnalyticsDashboard } from '../../lib/api-client';
import HistoryPage from './History';
import WorkTab from './WorkTab';

type TrackTab = 'pipeline' | 'work' | 'history' | 'trends';

// ── Pipeline tab ─────────────────────────────────────────────────────────────

interface FunnelStage {
  label: string;
  count: number;
  color: string;
}

function PipelineTab() {
  const [stats, setStats] = useState<ProposalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getProposalStats()
      .then(setStats)
      .catch(() => setError('Failed to load pipeline data.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-4 text-sm text-gray-500 text-center pt-8">Loading pipeline…</div>;
  if (error) return <div className="p-4 text-sm text-red-600 text-center">{error}</div>;
  if (!stats) return null;

  const stages: FunnelStage[] = [
    { label: 'Scored', count: stats.scored_count, color: 'bg-gray-400' },
    { label: 'Applied', count: stats.total_proposals, color: 'bg-blue-500' },
    { label: 'Viewed', count: stats.viewed, color: 'bg-blue-400' },
    { label: 'Responded', count: stats.responded, color: 'bg-amber-500' },
    { label: 'Interviewed', count: stats.interviewed, color: 'bg-orange-500' },
    { label: 'Hired', count: stats.hired, color: 'bg-emerald-600' },
  ];

  const maxCount = Math.max(...stages.map((s) => s.count), 1);

  const applyToHireRate = stats.total_proposals > 0
    ? ((stats.hired / stats.total_proposals) * 100).toFixed(1)
    : '0';
  const scoreToApplyRate = stats.scored_count > 0
    ? ((stats.total_proposals / stats.scored_count) * 100).toFixed(1)
    : '0';

  return (
    <div className="p-4 space-y-4">
      {stats.total_proposals === 0 && stats.scored_count === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <p className="text-sm">Score jobs or import proposals to see your pipeline.</p>
        </div>
      ) : (
        <>
          {/* Funnel */}
          <div className="space-y-2">
            {stages.map((stage) => {
              const pct = Math.max((stage.count / maxCount) * 100, stage.count > 0 ? 4 : 0);
              return (
                <div key={stage.label} className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 w-20 text-right flex-shrink-0">{stage.label}</span>
                  <div className="flex-1 h-5 bg-gray-100 rounded-sm overflow-hidden">
                    <div
                      className={`h-full ${stage.color} rounded-sm transition-all`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold text-gray-700 w-8 flex-shrink-0">{stage.count}</span>
                </div>
              );
            })}
          </div>

          {/* Conversion summary */}
          <div className="bg-gray-50 rounded-lg p-3 space-y-1">
            <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Conversion</p>
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">Scored → Applied</span>
              <span className="font-medium">{scoreToApplyRate}%</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">Applied → Responded</span>
              <span className="font-medium">{stats.response_rate.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">Applied → Hired</span>
              <span className="font-medium text-emerald-600">{applyToHireRate}%</span>
            </div>
            {stats.avg_days_to_response != null && (
              <div className="flex justify-between text-xs border-t pt-1 mt-1">
                <span className="text-gray-500">Avg days to response</span>
                <span className="font-medium">{stats.avg_days_to_response}d</span>
              </div>
            )}
          </div>

          {/* Earnings */}
          {stats.total_earnings > 0 && (
            <div className="bg-emerald-50 rounded-lg p-3 text-center">
              <p className="text-xs text-emerald-600 font-medium">Total Earnings</p>
              <p className="text-lg font-bold text-emerald-700">
                ${stats.total_earnings.toLocaleString()}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Trends tab ────────────────────────────────────────────────────────────────

function TrendsTab() {
  const [data, setData] = useState<AnalyticsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getAnalyticsDashboard()
      .then(setData)
      .catch(() => setError('Failed to load trends.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-4 text-sm text-gray-500 text-center pt-8">Loading trends…</div>;
  if (error) return <div className="p-4 text-sm text-red-600 text-center">{error}</div>;
  if (!data) return null;

  const hasWeekly = data.weekly_applications.some((w) => w.applications > 0);
  const maxWeekly = Math.max(...data.weekly_applications.map((w) => w.applications), 1);

  return (
    <div className="p-4 space-y-5">
      {/* Weekly bar chart */}
      {hasWeekly ? (
        <div>
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Weekly Applications</p>
          <div className="flex items-end gap-1 h-16">
            {data.weekly_applications.map((week) => {
              const totalPct = (week.applications / maxWeekly) * 100;
              const responsePct = week.applications > 0 ? (week.responses / week.applications) * 100 : 0;
              const label = week.week.slice(5); // MM-DD
              return (
                <div key={week.week} className="flex-1 flex flex-col items-center gap-0.5">
                  <div className="w-full relative" style={{ height: `${Math.max(totalPct * 0.56, week.applications > 0 ? 4 : 0)}px` }}>
                    <div className="absolute inset-0 bg-blue-200 rounded-t-sm" />
                    <div
                      className="absolute bottom-0 left-0 right-0 bg-emerald-400 rounded-t-sm"
                      style={{ height: `${responsePct}%` }}
                    />
                  </div>
                  <span className="text-[9px] text-gray-400 rotate-0">{label}</span>
                </div>
              );
            })}
          </div>
          <div className="flex gap-3 mt-1">
            <span className="text-[10px] text-gray-400 flex items-center gap-1">
              <span className="w-2 h-2 bg-blue-200 rounded-sm inline-block" /> Applied
            </span>
            <span className="text-[10px] text-gray-400 flex items-center gap-1">
              <span className="w-2 h-2 bg-emerald-400 rounded-sm inline-block" /> Responded
            </span>
          </div>
        </div>
      ) : (
        <div className="text-center py-4 text-gray-400 text-xs">
          No weekly data yet — import proposals to see trends.
        </div>
      )}

      {/* Skill win rates */}
      {data.top_skills.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Skill Success Rates</p>
          <div className="space-y-1.5">
            {data.top_skills.slice(0, 8).map((skill) => (
              <div key={skill.skill} className="flex items-center gap-2">
                <span className="text-xs text-gray-600 w-24 truncate flex-shrink-0">{skill.skill}</span>
                <div className="flex-1 h-3 bg-gray-100 rounded-sm overflow-hidden">
                  <div
                    className="h-full bg-blue-400 rounded-sm"
                    style={{ width: `${Math.min(skill.success_rate, 100)}%` }}
                  />
                </div>
                <span className="text-[10px] text-gray-500 w-10 text-right flex-shrink-0">
                  {skill.success_rate.toFixed(0)}%
                </span>
                <span className="text-[10px] text-gray-400 flex-shrink-0">
                  ({skill.applications})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Insights */}
      {data.insights.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Insights</p>
          <div className="space-y-2">
            {data.insights.map((insight, i) => (
              <div
                key={i}
                className={`text-xs p-2 rounded-lg ${
                  insight.type === 'positive'
                    ? 'bg-emerald-50 text-emerald-800'
                    : 'bg-amber-50 text-amber-800'
                }`}
              >
                {insight.message}
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasWeekly && data.top_skills.length === 0 && data.insights.length === 0 && (
        <div className="text-center py-8 text-gray-400 text-sm">
          Import proposals and track applications to see trends here.
        </div>
      )}
    </div>
  );
}

// ── Main TrackPage ────────────────────────────────────────────────────────────

export default function TrackPage() {
  const [activeTab, setActiveTab] = useState<TrackTab>('pipeline');

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white border-b px-4 pt-3 flex-shrink-0">
        <h1 className="font-bold text-gray-900 text-sm mb-2">Track</h1>
        <div className="flex gap-1 pb-2">
          {([
            { id: 'pipeline' as const, label: 'Pipeline' },
            { id: 'work' as const, label: 'Work' },
            { id: 'history' as const, label: 'History' },
            { id: 'trends' as const, label: 'Trends' },
          ]).map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {activeTab === 'pipeline' && <PipelineTab />}
        {activeTab === 'work' && <WorkTab />}
        {activeTab === 'history' && (
          <div className="[&>div>header]:hidden h-full">
            <HistoryPage />
          </div>
        )}
        {activeTab === 'trends' && <TrendsTab />}
      </div>
    </div>
  );
}
