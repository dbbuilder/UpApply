import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../store';
import { apiClient, Proposal, Job } from '../../lib/api-client';

type TabType = 'proposals' | 'jobs';

function InsightsBar({ proposals, jobs }: { proposals: Proposal[]; jobs: Job[] }) {
  // Compute skill frequency weighted by outcome (proposals count 2x, hired 3x)
  const skillCounts: Record<string, number> = {};
  proposals.forEach((p) => {
    const weight = p.was_hired ? 3 : p.client_responded ? 2 : 1;
    (p.job_skills || []).forEach((skill) => {
      skillCounts[skill] = (skillCounts[skill] || 0) + weight;
    });
  });
  // Jobs count 1x (less weight than submitted proposals)
  jobs.forEach((j) => {
    (j.analysis?.skill_matches || []).forEach((sm) => {
      skillCounts[sm.skill] = (skillCounts[sm.skill] || 0) + 1;
    });
  });
  const topSkills = Object.entries(skillCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([skill]) => skill);

  const hired = proposals.filter((p) => p.was_hired).length;
  const responded = proposals.filter((p) => p.client_responded).length;
  const total = proposals.length;
  const hireRate = total > 0 ? Math.round((hired / total) * 100) : 0;
  const responseRate = total > 0 ? Math.round(((responded + hired) / total) * 100) : 0;

  const bids = proposals.filter((p) => p.bid_amount).map((p) => p.bid_amount!);
  const avgBid = bids.length > 0 ? Math.round(bids.reduce((a, b) => a + b, 0) / bids.length) : null;

  if (proposals.length === 0 && jobs.length === 0) return null;

  return (
    <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 mb-3 space-y-2">
      <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">What You're Targeting</p>

      {topSkills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {topSkills.map((skill) => (
            <span key={skill} className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
              {skill}
            </span>
          ))}
        </div>
      )}

      {total > 0 && (
        <div className="flex gap-4 text-xs text-blue-800">
          <span>{total} submitted</span>
          {responseRate > 0 && <span>{responseRate}% response</span>}
          {hireRate > 0 && <span className="font-semibold text-green-700">{hireRate}% hired</span>}
          {avgBid && <span>avg ${avgBid}{proposals[0]?.bid_type === 'hourly' ? '/hr' : ''}</span>}
        </div>
      )}
    </div>
  );
}

function ProposalCard({
  proposal,
  expanded,
  onToggleExpand,
  onOutcomeChange,
}: {
  proposal: Proposal;
  expanded: boolean;
  onToggleExpand: () => void;
  onOutcomeChange: (status: string, wasHired: boolean) => void;
}) {
  const statusColor = proposal.was_hired
    ? 'badge-green'
    : proposal.client_responded
    ? 'badge-yellow'
    : proposal.status === 'declined'
    ? 'badge-red'
    : 'badge-gray';

  const statusLabel = proposal.was_hired
    ? 'Hired'
    : proposal.client_responded
    ? 'Responded'
    : proposal.status || 'Submitted';

  const formatDate = (d?: string) => {
    if (!d) return null;
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className={`card ${proposal.was_hired ? 'border-green-200 bg-green-50' : ''}`}>
      <div className="flex justify-between items-start mb-1">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-gray-900 text-sm line-clamp-2">
            {proposal.job_title || 'Untitled Job'}
          </h4>
        </div>
        <span className={`badge ${statusColor} ml-2 shrink-0`}>{statusLabel}</span>
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-gray-500 mb-2">
        {proposal.submitted_at && <span>{formatDate(proposal.submitted_at)}</span>}
        {proposal.bid_amount && (
          <span className="font-medium text-gray-700">
            ${proposal.bid_amount}{proposal.bid_type === 'hourly' ? '/hr' : ''}
          </span>
        )}
        {proposal.job_budget && <span>{proposal.job_budget}</span>}
      </div>

      {proposal.job_skills && proposal.job_skills.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {proposal.job_skills.slice(0, 4).map((skill) => (
            <span key={skill} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
              {skill}
            </span>
          ))}
          {proposal.job_skills.length > 4 && (
            <span className="text-xs text-gray-400">+{proposal.job_skills.length - 4}</span>
          )}
        </div>
      )}

      {proposal.cover_letter_text && (
        <div className="mt-1">
          <button
            type="button"
            onClick={onToggleExpand}
            className="text-xs text-blue-600 hover:underline"
          >
            {expanded ? 'Hide cover letter' : 'Show cover letter'}
          </button>
          {expanded && (
            <div className="mt-2 p-2 bg-white border border-gray-100 rounded text-xs text-gray-700 whitespace-pre-wrap max-h-40 overflow-y-auto">
              {proposal.cover_letter_text}
            </div>
          )}
        </div>
      )}

      <div className="mt-2 pt-2 border-t border-gray-100 flex gap-2 items-center">
        <label className="text-xs text-gray-400 shrink-0">Outcome:</label>
        <select
          value={proposal.was_hired ? 'hired' : proposal.client_responded ? 'responded' : proposal.status || 'submitted'}
          onChange={(e) => {
            const val = e.target.value;
            onOutcomeChange(val, val === 'hired');
          }}
          className="input text-xs py-0.5 flex-1"
        >
          <option value="submitted">Submitted</option>
          <option value="viewed">Viewed</option>
          <option value="responded">Responded</option>
          <option value="interviewed">Interviewed</option>
          <option value="hired">Hired ✓</option>
          <option value="declined">Declined</option>
          <option value="no_response">No Response</option>
        </select>
      </div>
    </div>
  );
}

function JobCard({
  job,
  applyStatus,
  onQuickApply,
}: {
  job: Job;
  applyStatus: string | null;
  onQuickApply: () => void;
}) {
  const score = job.match_score ?? 0;
  const scoreColor = score >= 80 ? 'text-green-600' : score >= 65 ? 'text-yellow-600' : score >= 50 ? 'text-orange-500' : 'text-red-500';

  const skills = job.analysis?.skill_matches?.slice(0, 4).map((sm) => sm.skill) || [];
  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

  return (
    <div className="card">
      <div className="flex justify-between items-start mb-1">
        <h4 className="font-medium text-gray-900 text-sm line-clamp-2 flex-1 min-w-0 pr-2">
          {job.title}
        </h4>
        {job.match_score !== undefined && (
          <span className={`text-sm font-bold shrink-0 ${scoreColor}`}>{score}%</span>
        )}
      </div>

      <p className="text-xs text-gray-400 mb-2">{formatDate(job.created_at)}</p>

      {skills.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {skills.map((skill) => (
            <span key={skill} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
              {skill}
            </span>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={onQuickApply}
        disabled={!!applyStatus}
        className="btn-primary w-full text-sm py-1.5 disabled:opacity-60"
      >
        {applyStatus || 'Quick Apply →'}
      </button>
    </div>
  );
}

export default function HistoryPage() {
  const { setCurrentView } = useAppStore();
  const [activeTab, setActiveTab] = useState<TabType>('proposals');

  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [proposalsLoading, setProposalsLoading] = useState(false);
  const [expandedProposal, setExpandedProposal] = useState<string | null>(null);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [applyStatuses, setApplyStatuses] = useState<Record<string, string>>({});

  const [error, setError] = useState<string | null>(null);

  const loadProposals = useCallback(async () => {
    setProposalsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getProposals({ limit: 100 });
      // Sort: hired first, then responded, then rest newest-first
      const sorted = [...data].sort((a, b) => {
        const scoreA = a.was_hired ? 3 : a.client_responded ? 2 : 1;
        const scoreB = b.was_hired ? 3 : b.client_responded ? 2 : 1;
        if (scoreB !== scoreA) return scoreB - scoreA;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
      setProposals(sorted);
    } catch {
      setError('Failed to load proposals.');
    } finally {
      setProposalsLoading(false);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getJobs();
      const sorted = [...data].sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));
      setJobs(sorted);
    } catch {
      setError('Failed to load saved jobs.');
    } finally {
      setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'proposals') {
      loadProposals();
    } else {
      loadJobs();
    }
  }, [activeTab, loadProposals, loadJobs]);

  const handleOutcomeChange = async (proposalId: string, status: string, wasHired: boolean) => {
    try {
      const clientResponded = status === 'responded' || status === 'interviewed' || wasHired;
      await apiClient.updateProposal(proposalId, { status, was_hired: wasHired, client_responded: clientResponded });
      setProposals((prev) =>
        prev.map((p) =>
          p.id === proposalId
            ? { ...p, status, was_hired: wasHired, client_responded: clientResponded }
            : p
        )
      );
    } catch {
      // silent fail — outcome update is non-critical
    }
  };

  const handleQuickApply = async (job: Job) => {
    setApplyStatuses((prev) => ({ ...prev, [job.id]: 'Preparing...' }));
    try {
      // Derive apply URL: /jobs/~XXXX → /nx/proposals/job/~XXXX/apply/
      const jobSlug = job.upwork_url?.match(/(~[a-zA-Z0-9]+)/)?.[1];
      const applyUrl = jobSlug
        ? `https://www.upwork.com/nx/proposals/job/${jobSlug}/apply/`
        : job.upwork_url;

      // Look for an existing cover letter for this job
      let coverLetterText: string | null = null;
      try {
        const letters = await apiClient.getCoverLetters(job.id);
        if (letters.length > 0) {
          // Use the most recently generated letter
          coverLetterText = letters[letters.length - 1].content;
        }
      } catch {
        // No cover letters yet — will open without pre-fill
      }

      if (coverLetterText) {
        // Store for content script to pick up and auto-fill on the apply page
        await chrome.storage.local.set({
          pendingAutoFill: {
            jobUrl: job.upwork_url,
            jobId: job.id,
            coverLetter: coverLetterText,
            timestamp: Date.now(),
          },
        });
        setApplyStatuses((prev) => ({ ...prev, [job.id]: 'Opening with cover letter...' }));
      } else {
        setApplyStatuses((prev) => ({ ...prev, [job.id]: 'Opening...' }));
      }

      // Open the apply page in the same window (sidebar stays open)
      await chrome.tabs.create({ url: applyUrl || job.upwork_url, active: true });

      setTimeout(() => {
        setApplyStatuses((prev) => {
          const next = { ...prev };
          delete next[job.id];
          return next;
        });
      }, 4000);
    } catch {
      setApplyStatuses((prev) => ({ ...prev, [job.id]: 'Error — try again' }));
      setTimeout(() => {
        setApplyStatuses((prev) => {
          const next = { ...prev };
          delete next[job.id];
          return next;
        });
      }, 3000);
    }
  };

  const isLoading = activeTab === 'proposals' ? proposalsLoading : jobsLoading;

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
        <h1 className="font-bold text-gray-900">My Pipeline</h1>
        <div className="w-12" />
      </header>

      {/* Tabs */}
      <div className="bg-white border-b flex">
        <button
          type="button"
          onClick={() => setActiveTab('proposals')}
          className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'proposals'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Proposals {proposals.length > 0 && `(${proposals.length})`}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('jobs')}
          className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'jobs'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Saved Jobs {jobs.length > 0 && `(${jobs.length})`}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {isLoading && (
          <div className="text-center py-8 text-gray-500 text-sm">Loading...</div>
        )}

        {error && !isLoading && (
          <div className="card bg-red-50 text-center py-4">
            <p className="text-sm text-red-700">{error}</p>
            <button
              type="button"
              onClick={activeTab === 'proposals' ? loadProposals : loadJobs}
              className="btn-outline text-sm mt-2"
            >
              Retry
            </button>
          </div>
        )}

        {/* Proposals Tab */}
        {!isLoading && !error && activeTab === 'proposals' && (
          <>
            {proposals.length > 0 && (
              <InsightsBar proposals={proposals} jobs={jobs} />
            )}

            {proposals.length === 0 ? (
              <div className="text-center py-10 text-gray-500">
                <p className="font-medium">No proposals yet</p>
                <p className="text-sm mt-1">
                  Import from the My Proposals page or submit applications via the Generator.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {proposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    expanded={expandedProposal === proposal.id}
                    onToggleExpand={() =>
                      setExpandedProposal(expandedProposal === proposal.id ? null : proposal.id)
                    }
                    onOutcomeChange={(status, wasHired) =>
                      handleOutcomeChange(proposal.id, status, wasHired)
                    }
                  />
                ))}
              </div>
            )}
          </>
        )}

        {/* Saved Jobs Tab */}
        {!isLoading && !error && activeTab === 'jobs' && (
          <>
            {jobs.length > 0 && proposals.length > 0 && (
              <InsightsBar proposals={proposals} jobs={jobs} />
            )}

            {jobs.length === 0 ? (
              <div className="text-center py-10 text-gray-500">
                <p className="font-medium">No saved jobs yet</p>
                <p className="text-sm mt-1">
                  Analyze jobs on Upwork and they'll appear here.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {jobs.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    applyStatus={applyStatuses[job.id] || null}
                    onQuickApply={() => handleQuickApply(job)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
