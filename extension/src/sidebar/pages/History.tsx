import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../store';
import { apiClient, Proposal, Job, JobImportItem, SearchQuery, SearchLabResult, SuggestedQuery } from '../../lib/api-client';

type TabType = 'proposals' | 'jobs' | 'search';

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
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);

  const [insights, setInsights] = useState<{
    whats_working: string;
    whats_not_landing: string;
    recommendations: string[];
    job_types_to_target: string[];
    job_types_to_avoid: string[];
    positioning_tip: string;
  } | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsMessage, setInsightsMessage] = useState<string | null>(null);

  const loadInsights = useCallback(async () => {
    setInsightsLoading(true);
    try {
      const data = await apiClient.getProposalInsights();
      if (data.insights) {
        setInsights(data.insights);
      } else {
        setInsightsMessage(data.message || null);
      }
    } catch {
      // silently fail — insights are supplementary
    } finally {
      setInsightsLoading(false);
    }
  }, []);

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

  const loadSearchQueries = useCallback(async (autoSeed = false) => {
    setQueriesLoading(true);
    try {
      let data = await apiClient.getSearchQueries();
      if (autoSeed && data.length === 0) {
        setQueriesStatus('Seeding initial queries from your profile...');
        const seeded = await apiClient.seedSearchQueries();
        setQueriesStatus(`Seeded ${seeded.length} queries from your profile.`);
        data = await apiClient.getSearchQueries();
        setTimeout(() => setQueriesStatus(null), 4000);
      }
      setSearchQueries(data);
    } catch {
      // silently fail
    } finally {
      setQueriesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'proposals') {
      loadProposals();
      loadInsights();
    } else if (activeTab === 'jobs') {
      loadJobs();
    } else if (activeTab === 'search') {
      loadSearchQueries(true); // auto-seed on first open
    }
  }, [activeTab, loadProposals, loadJobs, loadInsights, loadSearchQueries]);

  const handleImportFromUpwork = async () => {
    setImporting(true);
    setImportStatus('Opening proposals pages...');

    // Poll progress storage so the user sees real-time feedback during the
    // multi-page deep scrape (active list → archived list → each detail page)
    chrome.storage.local.remove('proposalImportProgress');
    const progressInterval = setInterval(() => {
      chrome.storage.local.get('proposalImportProgress', (result) => {
        const p = result.proposalImportProgress as Record<string, unknown> | undefined;
        if (!p) return;
        if (p.stage === 'scraping_active') setImportStatus('Scraping active proposals...');
        else if (p.stage === 'scraping_archived') setImportStatus('Scraping archived proposals...');
        else if (p.stage === 'detail') {
          const cur = p.current as number;
          const tot = p.total as number;
          const grand = p.grandTotal as number | undefined;
          const suffix = grand && grand > tot ? ` of ${grand} total` : '';
          setImportStatus(`Fetching cover letters... (${cur}/${tot}${suffix})`);
        }
        else if (p.stage === 'done') clearInterval(progressInterval);
        else if (p.stage === 'error') clearInterval(progressInterval);
      });
    }, 800);

    try {
      const scrapeResult = await new Promise<{ success: boolean; data?: unknown[]; error?: string }>(
        (resolve) => chrome.runtime.sendMessage({ type: 'IMPORT_PROPOSALS' }, resolve)
      );
      clearInterval(progressInterval);

      if (!scrapeResult?.success || !scrapeResult.data?.length) {
        setImportStatus(`Nothing found. ${scrapeResult?.error || 'No proposals found.'}`);
        return;
      }

      setImportStatus(`Saving ${scrapeResult.data.length} proposals...`);
      const imported = await apiClient.importProposalsFromUpwork(
        scrapeResult.data as Record<string, unknown>[]
      );
      const withLetters = (scrapeResult.data as Record<string, unknown>[]).filter(p => p.coverLetter).length;
      setImportStatus(`Imported ${imported.length} new proposals (${withLetters} with cover letters).`);
      await loadProposals();
    } catch {
      clearInterval(progressInterval);
      setImportStatus('Import failed. Try again.');
    } finally {
      setImporting(false);
      setTimeout(() => setImportStatus(null), 6000);
    }
  };

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

  // Search tab — legacy one-shot search (kept for fallback)
  const [searchQuery, setSearchQuery] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<Job[]>([]);
  const [searchStatus, setSearchStatus] = useState<string | null>(null);
  const [savedImporting, setSavedImporting] = useState(false);
  const [savedImportStatus, setSavedImportStatus] = useState<string | null>(null);

  // Query Library state
  const [searchQueries, setSearchQueries] = useState<SearchQuery[]>([]);
  const [queriesLoading, setQueriesLoading] = useState(false);
  const [runningQueryId, setRunningQueryId] = useState<string | null>(null);
  const [runAllProgress, setRunAllProgress] = useState<{ current: number; total: number } | null>(null);
  const [addQueryText, setAddQueryText] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [generatingQueries, setGeneratingQueries] = useState(false);
  const [importingSavedSearches, setImportingSavedSearches] = useState(false);
  const [queriesStatus, setQueriesStatus] = useState<string | null>(null);

  // Search Lab state
  const [labResult, setLabResult] = useState<SearchLabResult | null>(null);
  const [labLoading, setLabLoading] = useState(false);
  const [addingQueryId, setAddingQueryId] = useState<string | null>(null);

  const handleImportSavedJobs = async () => {
    setSavedImporting(true);
    setSavedImportStatus('Opening saved jobs page...');
    try {
      // Open saved jobs page in background tab, scrape, close automatically
      const scrapeResult = await new Promise<{ success: boolean; data?: JobImportItem[]; error?: string }>(
        (resolve) => chrome.runtime.sendMessage({ type: 'IMPORT_SAVED_JOBS' }, resolve)
      );

      if (!scrapeResult?.success || !scrapeResult.data?.length) {
        setSavedImportStatus(`Nothing found. ${scrapeResult?.error || ''}`);
        return;
      }

      const rawCards = scrapeResult.data as unknown as Array<{
        upworkJobId: string; upworkUrl: string; title: string; description: string;
        jobType?: string; experienceLevel?: string; postedDateRaw?: string; clientInfo?: Record<string, unknown>;
      }>;

      const items: JobImportItem[] = rawCards.map((c) => ({
        upwork_job_id: c.upworkJobId,
        upwork_url: c.upworkUrl,
        title: c.title,
        description: c.description,
        job_type: c.jobType,
        experience_level: c.experienceLevel,
        posted_date_raw: c.postedDateRaw,
        client_info: c.clientInfo,
      }));

      setSavedImportStatus(`Analyzing ${items.length} jobs...`);
      const imported = await apiClient.importBulkJobs(items, 'saved');
      setSavedImportStatus(`Added ${imported.length} new jobs to queue.`);
      await loadJobs();
    } catch {
      setSavedImportStatus('Import failed. Try again.');
    } finally {
      setSavedImporting(false);
      setTimeout(() => setSavedImportStatus(null), 6000);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    setSearchStatus('Searching Upwork...');
    setSearchResults([]);
    try {
      const scrapeResult = await new Promise<{ success: boolean; data?: unknown[]; error?: string }>(
        (resolve) => chrome.runtime.sendMessage({ type: 'SEARCH_UPWORK_JOBS', query: searchQuery.trim() }, resolve)
      );

      if (!scrapeResult?.success || !scrapeResult.data?.length) {
        setSearchStatus(`No results found. ${scrapeResult?.error || ''}`);
        return;
      }

      const rawCards = scrapeResult.data as Array<{
        upworkJobId: string; upworkUrl: string; title: string; description: string;
        jobType?: string; experienceLevel?: string; postedDateRaw?: string; clientInfo?: Record<string, unknown>;
      }>;

      const items: JobImportItem[] = rawCards.map((c) => ({
        upwork_job_id: c.upworkJobId,
        upwork_url: c.upworkUrl,
        title: c.title,
        description: c.description,
        job_type: c.jobType,
        experience_level: c.experienceLevel,
        posted_date_raw: c.postedDateRaw,
        client_info: c.clientInfo,
      }));

      setSearchStatus(`Analyzing ${items.length} results...`);
      const analyzed = await apiClient.importBulkJobs(items, 'search', searchQuery.trim());
      setSearchResults(analyzed.sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0)));
      setSearchStatus(`Found ${analyzed.length} jobs — scored and sorted by match.`);
      await loadJobs();
    } catch (err) {
      setSearchStatus('Search failed. Try again.');
      console.error('Search error:', err);
    } finally {
      setSearchLoading(false);
    }
  };

  // Query Library handlers
  const handleRunQuery = async (sq: SearchQuery) => {
    setRunningQueryId(sq.id);
    try {
      const scrapeResult = await new Promise<{ success: boolean; data?: unknown[]; error?: string }>(
        (resolve) =>
          chrome.runtime.sendMessage(
            { type: 'SEARCH_UPWORK_JOBS', query: sq.query, urlParams: sq.url_params },
            resolve
          )
      );

      if (!scrapeResult?.success || !scrapeResult.data?.length) {
        // Still record a zero run so the query doesn't stay perpetually stale
        await apiClient.recordQueryRun(sq.id, { jobs_found: 0, avg_score: 0, high_score_count: 0 });
        await loadSearchQueries();
        return;
      }

      const rawCards = scrapeResult.data as Array<{
        upworkJobId: string; upworkUrl: string; title: string; description: string;
        jobType?: string; experienceLevel?: string; postedDateRaw?: string; clientInfo?: Record<string, unknown>;
      }>;
      const items: JobImportItem[] = rawCards.map((c) => ({
        upwork_job_id: c.upworkJobId,
        upwork_url: c.upworkUrl,
        title: c.title,
        description: c.description,
        job_type: c.jobType,
        experience_level: c.experienceLevel,
        posted_date_raw: c.postedDateRaw,
        client_info: c.clientInfo,
      }));

      const imported = await apiClient.importBulkJobs(items, 'search', sq.query, sq.id);
      const avgScore = imported.length > 0
        ? imported.reduce((s, j) => s + (j.match_score ?? 0), 0) / imported.length
        : 0;
      const highScore = imported.filter((j) => (j.match_score ?? 0) >= 70).length;
      await apiClient.recordQueryRun(sq.id, {
        jobs_found: imported.length,
        avg_score: avgScore,
        high_score_count: highScore,
      });
      await loadSearchQueries();
      await loadJobs();
    } catch {
      // silently fail per-query
    } finally {
      setRunningQueryId(null);
    }
  };

  const handleRunAll = async () => {
    const stale = searchQueries.filter(
      (sq) =>
        sq.active &&
        (!sq.last_run_at || new Date(sq.last_run_at) < new Date(Date.now() - 24 * 60 * 60 * 1000))
    );
    if (stale.length === 0) return;
    setRunAllProgress({ current: 0, total: stale.length });
    for (let i = 0; i < stale.length; i++) {
      setRunAllProgress({ current: i + 1, total: stale.length });
      await handleRunQuery(stale[i]);
      if (i < stale.length - 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
    setRunAllProgress(null);
  };

  const handleAddQuery = async () => {
    if (!addQueryText.trim()) return;
    try {
      await apiClient.createSearchQuery(addQueryText.trim());
      setAddQueryText('');
      setShowAddForm(false);
      await loadSearchQueries();
    } catch {
      // duplicate or error — silently ignore
    }
  };

  const handleDeleteQuery = async (id: string) => {
    try {
      await apiClient.deleteSearchQuery(id);
      setSearchQueries((prev) => prev.filter((q) => q.id !== id));
    } catch {
      // silently fail
    }
  };

  const handleGenerateQueries = async () => {
    setGeneratingQueries(true);
    setQueriesStatus('Generating AI queries...');
    try {
      const generated = await apiClient.generateSearchQueries();
      setQueriesStatus(
        generated.length > 0 ? `Generated ${generated.length} new queries.` : 'No new queries generated.'
      );
      await loadSearchQueries();
    } catch {
      setQueriesStatus('Generation failed. Try again.');
    } finally {
      setGeneratingQueries(false);
      setTimeout(() => setQueriesStatus(null), 5000);
    }
  };

  const handleImportSavedSearches = async () => {
    setImportingSavedSearches(true);
    setQueriesStatus('Opening Upwork saved searches...');
    try {
      const result = await new Promise<{ success: boolean; data?: Array<{ query: string; url_params: string; label: string }>; error?: string }>(
        (resolve) => chrome.runtime.sendMessage({ type: 'IMPORT_UPWORK_SAVED_SEARCHES' }, resolve)
      );
      if (!result?.success || !result.data?.length) {
        setQueriesStatus(result?.error ? `Import failed: ${result.error}` : 'No saved searches found on Upwork.');
        return;
      }
      const toImport = result.data.map((s) => ({ query: s.query, url_params: s.url_params || undefined, source: 'imported' as const }));
      const imported = await apiClient.bulkImportSearchQueries(toImport);
      setQueriesStatus(`Imported ${imported.length} saved searches.`);
      await loadSearchQueries();
    } catch {
      setQueriesStatus('Import failed. Try again.');
    } finally {
      setImportingSavedSearches(false);
      setTimeout(() => setQueriesStatus(null), 5000);
    }
  };

  const handleRunLab = async () => {
    setLabLoading(true);
    try {
      const result = await apiClient.evaluateSearchLab();
      setLabResult(result);
    } catch {
      setLabResult(null);
    } finally {
      setLabLoading(false);
    }
  };

  const handleAddSuggestion = async (suggestion: SuggestedQuery) => {
    const key = suggestion.query;
    setAddingQueryId(key);
    try {
      await apiClient.createSearchQuery(suggestion.query, suggestion.url_params, 'ai_generated');
      await loadSearchQueries();
    } catch {
      // duplicate — ignore
    } finally {
      setAddingQueryId(null);
    }
  };

  const isLoading = activeTab === 'proposals' ? proposalsLoading : activeTab === 'jobs' ? jobsLoading : false;

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
        {([
          ['proposals', `Proposals${proposals.length > 0 ? ` (${proposals.length})` : ''}`],
          ['jobs', `Queue${jobs.length > 0 ? ` (${jobs.length})` : ''}`],
          ['search', 'Search'],
        ] as [TabType, string][]).map(([tabId, label]) => (
          <button
            key={tabId}
            type="button"
            onClick={() => setActiveTab(tabId)}
            className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tabId
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
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
            {/* Import bar */}
            <div className="flex items-center gap-2 mb-3">
              <button
                type="button"
                onClick={handleImportFromUpwork}
                disabled={importing}
                className="btn-outline text-xs py-1 px-3 disabled:opacity-60"
              >
                {importing ? 'Syncing…' : '↻ Sync'}
              </button>
              {importStatus && (
                <p className="text-xs text-gray-500 flex-1">{importStatus}</p>
              )}
              {!importStatus && (
                <p className="text-xs text-gray-400 flex-1">
                  For first-time setup use Track → ↓ Import
                </p>
              )}
            </div>

            {proposals.length > 0 && (
              <InsightsBar proposals={proposals} jobs={jobs} />
            )}

            {/* AI Insights Panel */}
            {(insightsLoading || insights || insightsMessage) && (
              <div className="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-indigo-800">AI Pipeline Insights</h3>
                  {!insightsLoading && (
                    <button
                      onClick={loadInsights}
                      className="text-xs text-indigo-500 hover:text-indigo-700"
                    >
                      Refresh
                    </button>
                  )}
                </div>

                {insightsLoading && (
                  <p className="text-xs text-indigo-500 animate-pulse">Analyzing your proposal history…</p>
                )}

                {insightsMessage && !insightsLoading && (
                  <p className="text-xs text-gray-500">{insightsMessage}</p>
                )}

                {insights && !insightsLoading && (
                  <div className="space-y-3 text-xs">
                    <div>
                      <p className="font-semibold text-green-700 mb-1">✓ What's working</p>
                      <p className="text-gray-700">{insights.whats_working}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-orange-700 mb-1">✗ What's not landing</p>
                      <p className="text-gray-700">{insights.whats_not_landing}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-indigo-700 mb-1">→ Target these job types</p>
                      <div className="flex flex-wrap gap-1">
                        {insights.job_types_to_target.map((t, i) => (
                          <span key={i} className="bg-green-100 text-green-800 px-2 py-0.5 rounded-full">{t}</span>
                        ))}
                      </div>
                    </div>
                    {insights.job_types_to_avoid.length > 0 && (
                      <div>
                        <p className="font-semibold text-red-700 mb-1">✗ Avoid these</p>
                        <div className="flex flex-wrap gap-1">
                          {insights.job_types_to_avoid.map((t, i) => (
                            <span key={i} className="bg-red-100 text-red-800 px-2 py-0.5 rounded-full">{t}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    <div>
                      <p className="font-semibold text-purple-700 mb-1">💡 Positioning tip</p>
                      <p className="text-gray-700">{insights.positioning_tip}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-blue-700 mb-2">Action items</p>
                      <ul className="space-y-1">
                        {insights.recommendations.map((r, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="text-blue-400 shrink-0">{i + 1}.</span>
                            <span className="text-gray-700">{r}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}

            {proposals.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <p className="font-medium">No proposals yet</p>
                <p className="text-sm mt-1">
                  Click Import above — it will open your Upwork proposals page automatically.
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

        {/* Job Queue Tab */}
        {!isLoading && !error && activeTab === 'jobs' && (
          <>
            {/* Import saved jobs bar */}
            <div className="flex items-center gap-2 mb-3">
              <button
                type="button"
                onClick={handleImportSavedJobs}
                disabled={savedImporting}
                className="btn-outline text-xs py-1 px-3 disabled:opacity-60 shrink-0"
              >
                {savedImporting ? 'Syncing…' : '↻ Sync'}
              </button>
              {savedImportStatus ? (
                <p className="text-xs text-gray-500 flex-1">{savedImportStatus}</p>
              ) : (
                <p className="text-xs text-gray-400 flex-1">
                  Auto-opens Upwork saved jobs page and imports
                </p>
              )}
            </div>

            {jobs.length > 0 && proposals.length > 0 && (
              <InsightsBar proposals={proposals} jobs={jobs} />
            )}

            {jobs.length === 0 ? (
              <div className="text-center py-10 text-gray-500">
                <p className="font-medium">No jobs in queue yet</p>
                <p className="text-sm mt-1">
                  Import your Upwork saved jobs or use Search.
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

        {/* Search / Query Library Tab */}
        {activeTab === 'search' && (
          <>
            {/* Toolbar */}
            <div className="flex flex-wrap gap-2 mb-2">
              <button
                type="button"
                onClick={() => setShowAddForm((v) => !v)}
                className="btn-outline text-xs py-1 px-2"
              >
                + Add
              </button>
              <button
                type="button"
                onClick={handleImportSavedSearches}
                disabled={importingSavedSearches || !!runAllProgress}
                className="btn-outline text-xs py-1 px-2 disabled:opacity-60"
              >
                {importingSavedSearches ? '...' : '↓ Import'}
              </button>
              <button
                type="button"
                onClick={handleGenerateQueries}
                disabled={generatingQueries || !!runAllProgress}
                className="btn-outline text-xs py-1 px-2 disabled:opacity-60"
              >
                {generatingQueries ? '...' : 'AI Generate'}
              </button>
              {(() => {
                const staleCount = searchQueries.filter(
                  (sq) => sq.active && (!sq.last_run_at || new Date(sq.last_run_at) < new Date(Date.now() - 24 * 60 * 60 * 1000))
                ).length;
                return staleCount > 0 ? (
                  <button
                    type="button"
                    onClick={handleRunAll}
                    disabled={!!runAllProgress || !!runningQueryId}
                    className="btn-primary text-xs py-1 px-2 disabled:opacity-60"
                  >
                    {runAllProgress
                      ? `Running ${runAllProgress.current}/${runAllProgress.total}...`
                      : `▶ Run Stale (${staleCount})`}
                  </button>
                ) : null;
              })()}
            </div>

            {/* Add query form */}
            {showAddForm && (
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={addQueryText}
                  onChange={(e) => setAddQueryText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleAddQuery(); }}
                  placeholder="e.g. fractional CTO startup"
                  className="input flex-1 text-xs"
                  autoFocus
                />
                <button type="button" onClick={handleAddQuery} className="btn-primary text-xs px-3">
                  Add
                </button>
              </div>
            )}

            {/* Status line */}
            {queriesStatus && (
              <p className="text-xs text-gray-500 mb-2">{queriesStatus}</p>
            )}

            {/* Run-all progress bar */}
            {runAllProgress && (
              <div className="mb-3">
                <div className="w-full bg-gray-200 rounded-full h-1.5">
                  <div
                    className="bg-blue-500 h-1.5 rounded-full transition-all"
                    style={{ width: `${(runAllProgress.current / runAllProgress.total) * 100}%` }}
                  />
                </div>
              </div>
            )}

            {queriesLoading && searchQueries.length === 0 && (
              <div className="text-center py-8 text-gray-500 text-sm">Loading queries...</div>
            )}

            {!queriesLoading && searchQueries.length === 0 && !queriesStatus && (
              <div className="text-center py-10 text-gray-400">
                <p className="text-sm">No queries yet. Click AI Generate to get started.</p>
              </div>
            )}

            {/* Query list */}
            <div className="space-y-1">
              {searchQueries.map((sq) => {
                const isRunning = runningQueryId === sq.id;
                const statusIcon = sq.is_low_performer ? '⚠' : sq.run_count === 0 ? '○' : sq.is_stale ? '○' : '●';
                const scoreColor =
                  sq.performance_score >= 60
                    ? 'text-green-600'
                    : sq.performance_score >= 35
                    ? 'text-yellow-600'
                    : sq.run_count > 0
                    ? 'text-red-500'
                    : 'text-gray-400';

                let ageText = 'New';
                if (sq.last_run_at) {
                  const ageMs = Date.now() - new Date(sq.last_run_at).getTime();
                  const ageH = Math.floor(ageMs / 3_600_000);
                  ageText = ageH < 24 ? `${ageH}h` : `${Math.floor(ageH / 24)}d`;
                }

                return (
                  <div
                    key={sq.id}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded border text-xs ${
                      sq.is_low_performer
                        ? 'border-yellow-200 bg-yellow-50'
                        : 'border-gray-100 bg-white hover:bg-gray-50'
                    }`}
                  >
                    <span className={`shrink-0 ${sq.is_low_performer ? 'text-yellow-500' : sq.run_count > 0 && !sq.is_stale ? 'text-green-500' : 'text-gray-400'}`}>
                      {statusIcon}
                    </span>
                    <span className="flex-1 truncate text-gray-800" title={sq.query}>
                      {sq.query}
                    </span>
                    <span className={`shrink-0 font-mono ${scoreColor}`}>
                      {sq.run_count > 0 ? `${sq.performance_score}` : '—'}
                    </span>
                    <span className="shrink-0 text-gray-400">{sq.run_count}r</span>
                    <span className="shrink-0 text-gray-400">{ageText}</span>
                    <button
                      type="button"
                      onClick={() => !isRunning && !runAllProgress && handleRunQuery(sq)}
                      disabled={isRunning || !!runAllProgress}
                      className="shrink-0 text-blue-500 hover:text-blue-700 disabled:opacity-40 font-medium"
                      title="Run this query"
                    >
                      {isRunning ? '…' : '▶'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteQuery(sq.id)}
                      disabled={isRunning || !!runAllProgress}
                      className="shrink-0 text-gray-300 hover:text-red-400 disabled:opacity-40"
                      title="Remove query"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Search Lab — coverage analysis + gap query suggestions */}
            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Search Lab</p>
                <button
                  type="button"
                  onClick={handleRunLab}
                  disabled={labLoading || !!runAllProgress}
                  className="text-xs px-2 py-1 rounded bg-violet-100 text-violet-700 hover:bg-violet-200 disabled:opacity-60 font-medium"
                >
                  {labLoading ? 'Analyzing…' : labResult ? '↻ Re-evaluate' : '⚗ Evaluate Coverage'}
                </button>
              </div>

              {labLoading && (
                <div className="text-xs text-gray-400 animate-pulse text-center py-3">
                  Comparing searches against your winning jobs…
                </div>
              )}

              {!labLoading && labResult && (
                <div className="space-y-3">
                  {/* Overall coverage summary */}
                  <div className={`rounded-lg p-2.5 text-xs ${labResult.coverage_pct >= 80 ? 'bg-emerald-50 text-emerald-800' : labResult.coverage_pct >= 50 ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-800'}`}>
                    <span className="font-semibold">{labResult.coverage_pct}% covered</span>
                    {' '}— {labResult.covered_count}/{labResult.total_target_jobs} winning jobs matched by current searches
                  </div>

                  {/* Per-query coverage bars (only show queries with >0 coverage or top 5) */}
                  {labResult.query_coverage.filter(c => c.coverage_count > 0).length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Query Coverage</p>
                      <div className="space-y-1">
                        {labResult.query_coverage.filter(c => c.coverage_count > 0).slice(0, 6).map((cov) => (
                          <div key={cov.query_id} className="flex items-center gap-2">
                            <span className="text-[10px] text-gray-600 w-28 truncate flex-shrink-0" title={cov.query}>{cov.query}</span>
                            <div className="flex-1 h-2 bg-gray-100 rounded-sm overflow-hidden">
                              <div
                                className="h-full bg-violet-400 rounded-sm"
                                style={{ width: `${Math.min(cov.coverage_pct, 100)}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-gray-500 w-8 text-right flex-shrink-0">{cov.coverage_pct}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Gap jobs */}
                  {labResult.gap_jobs.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                        Uncovered Wins ({labResult.gap_jobs.length})
                      </p>
                      <div className="space-y-0.5">
                        {labResult.gap_jobs.slice(0, 5).map((title) => (
                          <p key={title} className="text-[10px] text-gray-500 truncate pl-1 border-l-2 border-red-200" title={title}>
                            {title}
                          </p>
                        ))}
                        {labResult.gap_jobs.length > 5 && (
                          <p className="text-[10px] text-gray-400 pl-1">+{labResult.gap_jobs.length - 5} more</p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Suggested queries */}
                  {labResult.suggestions.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Suggested Queries</p>
                      <div className="space-y-2">
                        {labResult.suggestions.map((s) => {
                          const alreadyAdded = searchQueries.some(
                            (q) => q.query.toLowerCase() === s.query.toLowerCase()
                          );
                          return (
                            <div key={s.query} className="rounded-lg border border-violet-100 bg-violet-50 p-2 space-y-1">
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <p className="text-xs font-medium text-violet-900">{s.query}</p>
                                  {s.url_params && (
                                    <p className="text-[9px] text-violet-500 font-mono truncate">{s.url_params}</p>
                                  )}
                                </div>
                                <button
                                  type="button"
                                  disabled={alreadyAdded || addingQueryId === s.query}
                                  onClick={() => handleAddSuggestion(s)}
                                  className="shrink-0 text-[10px] px-2 py-0.5 rounded-full font-medium transition-colors disabled:opacity-50 bg-violet-600 text-white hover:bg-violet-700"
                                >
                                  {alreadyAdded ? '✓' : addingQueryId === s.query ? '…' : '+ Add'}
                                </button>
                              </div>
                              <p className="text-[10px] text-violet-700 leading-snug">{s.reasoning}</p>
                              {s.gap_jobs_targeted.length > 0 && (
                                <p className="text-[9px] text-violet-500">
                                  Targets: {s.gap_jobs_targeted.slice(0, 2).join(', ')}
                                  {s.gap_jobs_targeted.length > 2 ? ` +${s.gap_jobs_targeted.length - 2} more` : ''}
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {labResult.gap_jobs.length === 0 && labResult.suggestions.length === 0 && (
                    <p className="text-xs text-emerald-600 text-center py-2">
                      ✓ All winning jobs are covered by existing searches
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* One-shot search fallback */}
            <div className="mt-4 pt-3 border-t border-gray-100">
              <p className="text-xs text-gray-400 mb-2">One-shot search</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !searchLoading && handleSearch()}
                  placeholder="e.g. React developer TypeScript"
                  className="input flex-1 text-xs"
                  disabled={searchLoading}
                />
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={searchLoading || !searchQuery.trim()}
                  className="btn-primary text-xs px-3 disabled:opacity-60 shrink-0"
                >
                  {searchLoading ? '…' : 'Go'}
                </button>
              </div>
              {searchStatus && <p className="text-xs text-gray-500 mt-1">{searchStatus}</p>}
              {!searchLoading && searchResults.length > 0 && (
                <div className="mt-3 space-y-2">
                  {searchResults.map((job) => (
                    <JobCard
                      key={job.id}
                      job={job}
                      applyStatus={applyStatuses[job.id] || null}
                      onQuickApply={() => handleQuickApply(job)}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
