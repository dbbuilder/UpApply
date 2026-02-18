import { useState, useEffect } from 'react';
import { useAppStore } from '../store';
import { apiClient, AnalyticsDashboard } from '../../lib/api-client';

export default function AnalyticsPage() {
  const { setCurrentView } = useAppStore();
  const [dashboard, setDashboard] = useState<AnalyticsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getAnalyticsDashboard();
      setDashboard(data);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setError(err instanceof TypeError
        ? 'Server unavailable. Please retry.'
        : 'Failed to load analytics.');
    } finally {
      setLoading(false);
    }
  };

  const StatCard = ({
    label,
    value,
    suffix = '',
    color = 'text-gray-900',
  }: {
    label: string;
    value: number | string;
    suffix?: string;
    color?: string;
  }) => (
    <div className="card text-center">
      <div className={`text-2xl font-bold ${color}`}>
        {value}
        {suffix}
      </div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCurrentView('generator')}
          className="text-gray-600 hover:text-gray-900"
        >
          &larr; Back
        </button>
        <h1 className="font-bold text-gray-900">Analytics</h1>
        <div className="w-12" />
      </header>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {loading && (
          <div className="text-center py-8">
            <div className="animate-pulse-slow text-gray-500">Loading analytics...</div>
          </div>
        )}

        {error && !loading && (
          <div className="card bg-red-50 text-center py-4">
            <p className="text-sm text-red-700">{error}</p>
            <button type="button" onClick={loadDashboard} className="btn-outline text-sm mt-2">
              Retry
            </button>
          </div>
        )}

        {!loading && !error && !dashboard && (
          <div className="text-center py-8 text-gray-500">
            <p>Unable to load analytics.</p>
          </div>
        )}

        {dashboard && (
          <>
            {/* Overview stats */}
            <div className="grid grid-cols-2 gap-3">
              <StatCard label="Total Applications" value={dashboard.total_applications} />
              <StatCard
                label="Response Rate"
                value={dashboard.response_rate}
                suffix="%"
                color={
                  dashboard.response_rate >= 20
                    ? 'text-green-600'
                    : dashboard.response_rate >= 10
                    ? 'text-yellow-600'
                    : 'text-red-600'
                }
              />
              <StatCard
                label="Interview Rate"
                value={dashboard.interview_rate}
                suffix="%"
                color={dashboard.interview_rate >= 10 ? 'text-green-600' : 'text-yellow-600'}
              />
              <StatCard
                label="Hire Rate"
                value={dashboard.hire_rate}
                suffix="%"
                color={dashboard.hire_rate >= 5 ? 'text-green-600' : 'text-gray-600'}
              />
            </div>

            {/* Additional metrics */}
            <div className="grid grid-cols-2 gap-3">
              {dashboard.avg_match_score && (
                <StatCard
                  label="Avg Match Score"
                  value={dashboard.avg_match_score}
                  suffix="%"
                  color={
                    dashboard.avg_match_score >= 70
                      ? 'text-green-600'
                      : dashboard.avg_match_score >= 50
                      ? 'text-yellow-600'
                      : 'text-red-600'
                  }
                />
              )}
              {dashboard.avg_time_to_response_days && (
                <StatCard
                  label="Avg Response Time"
                  value={dashboard.avg_time_to_response_days}
                  suffix=" days"
                />
              )}
            </div>

            {/* Top skills */}
            {dashboard.top_skills.length > 0 && (
              <div className="card">
                <h3 className="font-medium text-gray-900 mb-3">Top Performing Skills</h3>
                <div className="space-y-2">
                  {dashboard.top_skills.map((skill) => (
                    <div key={skill.skill} className="flex items-center justify-between">
                      <span className="text-gray-700">{skill.skill}</span>
                      <div className="text-right">
                        <span className="text-green-600 font-medium">{skill.success_rate}%</span>
                        <span className="text-gray-400 text-sm ml-2">
                          ({skill.applications} apps)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Weekly trend */}
            {dashboard.weekly_applications.length > 0 && (
              <div className="card">
                <h3 className="font-medium text-gray-900 mb-3">Weekly Activity</h3>
                <div className="space-y-2">
                  {dashboard.weekly_applications.map((week) => (
                    <div key={week.week} className="flex items-center justify-between text-sm">
                      <span className="text-gray-500">{week.week}</span>
                      <div>
                        <span className="text-gray-700">{week.applications} applied</span>
                        {week.responses > 0 && (
                          <span className="text-green-600 ml-2">{week.responses} responded</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Insights */}
            {dashboard.insights.length > 0 && (
              <div className="card">
                <h3 className="font-medium text-gray-900 mb-3">Insights</h3>
                <div className="space-y-3">
                  {dashboard.insights.map((insight, i) => (
                    <div
                      key={i}
                      className={`p-3 rounded-lg text-sm ${
                        insight.type === 'positive'
                          ? 'bg-green-50 text-green-800'
                          : insight.type === 'improvement'
                          ? 'bg-yellow-50 text-yellow-800'
                          : 'bg-blue-50 text-blue-800'
                      }`}
                    >
                      {insight.message}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {dashboard.total_applications === 0 && (
              <div className="text-center py-8 text-gray-500">
                <p>No application data yet.</p>
                <p className="text-sm mt-1">
                  Start applying to jobs to see your analytics here.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
