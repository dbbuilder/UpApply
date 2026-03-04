import { useState, useEffect } from 'react';
import { useAppStore } from '../store';
import { apiClient, ProposalStats } from '../../lib/api-client';

export default function AnalyticsPage() {
  const { setCurrentView } = useAppStore();
  const [stats, setStats] = useState<ProposalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getProposalStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats:', err);
      setError(err instanceof TypeError
        ? 'Server unavailable. Please retry.'
        : 'Failed to load stats.');
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
        <h1 className="font-bold text-gray-900">Stats</h1>
        <div className="w-12" />
      </header>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {loading && (
          <div className="text-center py-8">
            <div className="animate-pulse-slow text-gray-500">Loading stats...</div>
          </div>
        )}

        {error && !loading && (
          <div className="card bg-red-50 text-center py-4">
            <p className="text-sm text-red-700">{error}</p>
            <button type="button" onClick={loadStats} className="btn-outline text-sm mt-2">
              Retry
            </button>
          </div>
        )}

        {stats && !loading && (
          <>
            {stats.total_proposals === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <p className="text-lg mb-2">No proposals yet.</p>
                <p className="text-sm">
                  Go to{' '}
                  <button
                    type="button"
                    onClick={() => setCurrentView('history')}
                    className="text-emerald-600 underline"
                  >
                    My Pipeline
                  </button>{' '}
                  and import your Upwork proposals to see stats here.
                </p>
              </div>
            ) : (
              <>
                {/* Overview stats */}
                <div className="grid grid-cols-2 gap-3">
                  <StatCard label="Total Proposals" value={stats.total_proposals} />
                  <StatCard
                    label="Response Rate"
                    value={Math.round(stats.response_rate)}
                    suffix="%"
                    color={
                      stats.response_rate >= 20
                        ? 'text-green-600'
                        : stats.response_rate >= 10
                        ? 'text-yellow-600'
                        : 'text-red-600'
                    }
                  />
                  <StatCard
                    label="Hire Rate"
                    value={Math.round(stats.hire_rate)}
                    suffix="%"
                    color={stats.hire_rate >= 5 ? 'text-green-600' : 'text-gray-600'}
                  />
                  <StatCard label="Times Hired" value={stats.hired} color="text-green-600" />
                </div>

                {/* Breakdown */}
                <div className="card">
                  <h3 className="font-medium text-gray-900 mb-3">Proposal Breakdown</h3>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Submitted (awaiting review)</span>
                      <span className="font-medium">{stats.submitted}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Client responded</span>
                      <span className="font-medium text-blue-600">{stats.responded}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Hired</span>
                      <span className="font-medium text-green-600">{stats.hired}</span>
                    </div>
                    {stats.total_earnings > 0 && (
                      <div className="flex justify-between text-sm border-t pt-2 mt-2">
                        <span className="text-gray-600">Total Earnings</span>
                        <span className="font-medium text-green-600">
                          ${stats.total_earnings.toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <p className="text-xs text-center text-gray-400">
                  Based on {stats.total_proposals} imported Upwork proposals
                </p>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
