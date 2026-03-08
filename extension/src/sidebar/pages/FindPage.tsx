import { useEffect, useState } from 'react';

interface ScoredJobEntry {
  url: string;
  title: string;
  score: number;
  chips: string[];
  scored_at: string;
}

export default function FindPage() {
  const [jobs, setJobs] = useState<ScoredJobEntry[]>([]);

  useEffect(() => {
    chrome.storage.local.get('scoredJobsCache', (data) => {
      const cache: Record<string, ScoredJobEntry> = data.scoredJobsCache || {};
      const sorted = Object.values(cache).sort((a, b) => b.score - a.score);
      setJobs(sorted);
    });
  }, []);

  const scoreColor = (s: number) =>
    s >= 90 ? '#15803d' : s >= 80 ? '#16a34a' : s >= 70 ? '#ca8a04' : '#dc2626';

  const openJob = (url: string) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs[0]?.id;
      if (tabId !== undefined) {
        chrome.tabs.update(tabId, { url });
      }
    });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white border-b px-4 py-3 flex-shrink-0">
        <h1 className="font-bold text-gray-900 text-sm">Scored Jobs</h1>
        <p className="text-xs text-gray-500 mt-0.5">{jobs.length} scored this session</p>
      </div>
      <div className="flex-1 overflow-auto p-4 space-y-2">
        {jobs.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <div className="text-3xl mb-2">🔍</div>
            <p className="text-sm font-medium text-gray-500">No scored jobs yet</p>
            <p className="text-xs mt-1">Use the Score button on Upwork notifications or saved jobs</p>
          </div>
        ) : (
          jobs.map(job => (
            <div key={job.url} className="card p-3">
              <div className="flex items-start gap-2">
                <span
                  className="flex-shrink-0 text-xs font-bold rounded-full px-2 py-0.5 text-white"
                  style={{ background: scoreColor(job.score), minWidth: 36, textAlign: 'center' }}
                >
                  {job.score}
                </span>
                <div className="flex-1 min-w-0">
                  <button
                    type="button"
                    onClick={() => openJob(job.url)}
                    className="text-sm font-medium text-gray-900 hover:text-emerald-700 text-left line-clamp-2 w-full"
                  >
                    {job.title}
                  </button>
                  {job.chips.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {job.chips.map(chip => (
                        <span key={chip} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                          {chip}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
