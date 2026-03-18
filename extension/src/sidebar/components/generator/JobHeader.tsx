import type { JobAnalysisResponse } from '../../../lib/api-client';
import type { JobData } from '../../../types';

interface JobHeaderProps {
  currentJob: JobData;
  jobAnalysis: JobAnalysisResponse | null;
  onRefresh: () => void;
  fetchingFullJob: boolean;
  fullJobFetched: boolean;
  attachmentCount: number;
  attachmentStatuses: string[];
  fetchError: string | null;
  onFetchFullJob: () => void;
}

export default function JobHeader({
  currentJob,
  jobAnalysis,
  onRefresh,
  fetchingFullJob,
  fullJobFetched,
  attachmentCount,
  attachmentStatuses,
  fetchError,
  onFetchFullJob,
}: JobHeaderProps) {
  return (
    <div className="card">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium text-gray-900 line-clamp-2 flex-1">{currentJob.title}</h3>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {jobAnalysis && (
            <span
              className="text-xs font-bold px-2 py-0.5 rounded-full text-white"
              style={{
                background:
                  jobAnalysis.match_score >= 70
                    ? '#16a34a'
                    : jobAnalysis.match_score >= 50
                    ? '#ca8a04'
                    : '#dc2626',
              }}
            >
              {Math.round(jobAnalysis.match_score)}%
            </span>
          )}
          <button
            type="button"
            onClick={onRefresh}
            className="text-gray-400 hover:text-gray-700 text-sm"
            title="Sync job from current page"
          >
            ⟳
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mt-2">
        {currentJob.budgetAmount && (
          <span className="badge badge-green">{currentJob.budgetAmount}</span>
        )}
        {currentJob.skills.slice(0, 4).map((skill) => (
          <span key={skill} className="badge badge-gray">{skill}</span>
        ))}
        {currentJob.skills.length > 4 && (
          <span className="badge badge-gray">+{currentJob.skills.length - 4}</span>
        )}
      </div>

      {/* Fetch Full Job */}
      <div className="mt-3 pt-3 border-t border-gray-100">
        {!fullJobFetched ? (
          <button
            type="button"
            onClick={onFetchFullJob}
            disabled={fetchingFullJob}
            className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
          >
            {fetchingFullJob ? (
              <>
                <span className="animate-spin">&#9203;</span>
                Fetching full job details...
              </>
            ) : (
              <>&#128196; Fetch full job posting &amp; attachments</>
            )}
          </button>
        ) : (
          <div className="text-sm text-gray-500 flex items-center gap-1">
            &#10003; Full job loaded
            {attachmentCount > 0 && (
              <span className="text-emerald-600">
                ({attachmentCount} attachment{attachmentCount !== 1 ? 's' : ''})
              </span>
            )}
          </div>
        )}
        {fetchingFullJob && attachmentStatuses.length > 0 && (
          <div className="mt-2 text-xs text-gray-500 space-y-1">
            {attachmentStatuses.map((status, i) => (
              <p key={i}>{status}</p>
            ))}
          </div>
        )}
        {fetchError && (
          <p className="text-sm text-red-500 mt-1">{fetchError}</p>
        )}
      </div>
    </div>
  );
}
