import { useState, useEffect } from 'react';
import { useAppStore } from '../store';
import { apiClient, Application, Job } from '../../lib/api-client';

export default function HistoryPage() {
  const { setCurrentView } = useAppStore();
  const [applications, setApplications] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [appsResult, jobsResult] = await Promise.all([
        apiClient.getApplications(),
        apiClient.getJobs(),
      ]);
      setApplications(appsResult);

      const jobsMap: Record<string, Job> = {};
      jobsResult.forEach((job) => {
        jobsMap[job.id] = job;
      });
      setJobs(jobsMap);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'hired':
        return 'badge-green';
      case 'responded':
      case 'interviewed':
        return 'badge-yellow';
      case 'declined':
        return 'badge-red';
      case 'submitted':
      case 'viewed':
        return 'badge-gray';
      default:
        return 'badge-gray';
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCurrentView('generator')}
          className="text-gray-600 hover:text-gray-900"
        >
          ← Back
        </button>
        <h1 className="font-bold text-gray-900">Application History</h1>
        <div className="w-12" />
      </header>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {loading && (
          <div className="text-center py-8">
            <div className="animate-pulse-slow text-gray-500">Loading history...</div>
          </div>
        )}

        {!loading && applications.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            <p>No applications yet.</p>
            <p className="text-sm mt-1">Your submitted applications will appear here.</p>
          </div>
        )}

        <div className="space-y-3">
          {applications.map((app) => {
            const job = jobs[app.job_id];
            return (
              <div key={app.id} className="card">
                <div className="flex justify-between items-start mb-2">
                  <h4 className="font-medium text-gray-900 line-clamp-2">
                    {job?.title || 'Unknown Job'}
                  </h4>
                  <span className={`badge ${getStatusColor(app.status)}`}>{app.status}</span>
                </div>

                <div className="text-sm text-gray-500 space-y-1">
                  {app.submitted_at && <p>Submitted: {formatDate(app.submitted_at)}</p>}
                  {app.bid_amount && <p>Bid: ${app.bid_amount}</p>}
                  {job?.match_score && (
                    <p>
                      Match Score:{' '}
                      <span
                        className={
                          job.match_score >= 70
                            ? 'text-green-600'
                            : job.match_score >= 50
                            ? 'text-yellow-600'
                            : 'text-red-600'
                        }
                      >
                        {job.match_score}%
                      </span>
                    </p>
                  )}
                  {app.earnings && <p className="text-green-600">Earned: ${app.earnings}</p>}
                </div>

                {app.client_response && (
                  <div className="mt-2 p-2 bg-gray-50 rounded text-sm text-gray-600">
                    <span className="font-medium">Client:</span> {app.client_response}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
