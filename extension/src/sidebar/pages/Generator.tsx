import { useEffect } from 'react';
import { useAppStore } from '../store';

function MatchScoreBadge({ score }: { score: number }) {
  let colorClass = 'score-low';
  let label = 'Low Match';

  if (score >= 80) {
    colorClass = 'score-excellent';
    label = 'Excellent';
  } else if (score >= 65) {
    colorClass = 'score-good';
    label = 'Good';
  } else if (score >= 50) {
    colorClass = 'score-moderate';
    label = 'Moderate';
  }

  return (
    <div className="text-center">
      <div className={`text-3xl font-bold ${colorClass}`}>{score}%</div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}

export default function GeneratorPage() {
  const {
    currentJob,
    jobAnalysis,
    analysisLoading,
    coverLetter,
    coverLetterLoading,
    setCurrentView,
    analyzeCurrentJob,
    generateCoverLetter,
    fillCoverLetter,
    logout,
  } = useAppStore();

  useEffect(() => {
    // Request current job data from stored cache first
    chrome.runtime.sendMessage({ type: 'GET_CURRENT_JOB' }, (response) => {
      console.log('UpApply Sidebar: GET_CURRENT_JOB response:', response);
      if (response?.data) {
        useAppStore.getState().setCurrentJob(response.data);
      }
    });

    // Also actively request extraction from content script
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) {
        chrome.tabs.sendMessage(tabs[0].id, { type: 'EXTRACT_JOB_DATA' }, (response) => {
          console.log('UpApply Sidebar: EXTRACT_JOB_DATA response:', response);
          if (response?.success && response.data) {
            useAppStore.getState().setCurrentJob(response.data);
          }
        });
      }
    });
  }, []);

  const handleRefreshJob = () => {
    // Route through background script which has tabs permission
    chrome.runtime.sendMessage({ type: 'REQUEST_JOB_EXTRACTION' }, (response) => {
      console.log('UpApply Sidebar: Manual extract response:', response);
      if (response?.success && response.data) {
        useAppStore.getState().setCurrentJob(response.data);
      } else {
        alert('Could not extract job data. Make sure you are on an Upwork job/proposal page. Error: ' + (response?.error || 'No response'));
      }
    });
  };

  const handleAnalyze = () => {
    analyzeCurrentJob();
  };

  const handleGenerate = () => {
    generateCoverLetter();
  };

  const handleFill = async () => {
    const success = await fillCoverLetter();
    if (success) {
      // Show success feedback
    }
  };

  const handleCopy = () => {
    if (coverLetter) {
      navigator.clipboard.writeText(coverLetter);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <h1 className="font-bold text-gray-900">UpApply</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setCurrentView('memories')}
            className="text-gray-600 hover:text-gray-900 text-sm"
          >
            Memories
          </button>
          <button
            type="button"
            onClick={() => setCurrentView('analytics')}
            className="text-gray-600 hover:text-gray-900 text-sm"
          >
            Stats
          </button>
          <button
            type="button"
            onClick={logout}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {!currentJob || !currentJob.title ? (
          <div className="card text-center py-8">
            <div className="text-gray-400 text-4xl mb-3">💼</div>
            <h3 className="font-medium text-gray-900">No Job Detected</h3>
            <p className="text-sm text-gray-500 mt-1">
              Navigate to an Upwork job page to get started
            </p>
            <button
              type="button"
              onClick={handleRefreshJob}
              className="btn-outline mt-4"
            >
              Refresh Detection
            </button>
          </div>
        ) : (
          <>
            {/* Job Info */}
            <div className="card">
              <h3 className="font-medium text-gray-900 line-clamp-2">{currentJob.title}</h3>
              <div className="flex flex-wrap gap-2 mt-2">
                {currentJob.budgetAmount && (
                  <span className="badge badge-green">{currentJob.budgetAmount}</span>
                )}
                {currentJob.skills.slice(0, 4).map((skill) => (
                  <span key={skill} className="badge badge-gray">
                    {skill}
                  </span>
                ))}
                {currentJob.skills.length > 4 && (
                  <span className="badge badge-gray">+{currentJob.skills.length - 4}</span>
                )}
              </div>
            </div>

            {/* Analysis */}
            {!jobAnalysis && !analysisLoading && (
              <button
                type="button"
                onClick={handleAnalyze}
                className="btn-outline w-full"
              >
                Analyze Job Match
              </button>
            )}

            {analysisLoading && (
              <div className="card text-center py-6">
                <div className="animate-pulse-slow text-gray-500">Analyzing job...</div>
              </div>
            )}

            {jobAnalysis && (
              <div className="card animate-slide-up">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="font-medium text-gray-900">Match Analysis</h4>
                  <MatchScoreBadge score={jobAnalysis.match_score} />
                </div>

                <p className="text-sm text-gray-600 mb-3">{jobAnalysis.recommendation}</p>

                {/* Deal breakers */}
                {jobAnalysis.deal_breaker_warnings.length > 0 && (
                  <div className="bg-red-50 rounded-lg p-3 mb-3">
                    <h5 className="text-sm font-medium text-red-800 mb-1">Warnings</h5>
                    <ul className="text-sm text-red-700 space-y-1">
                      {jobAnalysis.deal_breaker_warnings.map((warning, i) => (
                        <li key={i}>• {warning}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Strengths */}
                {jobAnalysis.strengths.length > 0 && (
                  <div className="mb-3">
                    <h5 className="text-sm font-medium text-gray-700 mb-1">Strengths</h5>
                    <ul className="text-sm text-gray-600 space-y-1">
                      {jobAnalysis.strengths.map((strength, i) => (
                        <li key={i} className="text-green-600">
                          ✓ {strength}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Concerns */}
                {jobAnalysis.concerns.length > 0 && (
                  <div className="mb-3">
                    <h5 className="text-sm font-medium text-gray-700 mb-1">Concerns</h5>
                    <ul className="text-sm text-gray-600 space-y-1">
                      {jobAnalysis.concerns.map((concern, i) => (
                        <li key={i} className="text-yellow-600">
                          ! {concern}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Skill matches */}
                {jobAnalysis.skill_matches.length > 0 && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-1">Matching Skills</h5>
                    <div className="flex flex-wrap gap-1">
                      {jobAnalysis.skill_matches.map((match) => (
                        <span
                          key={match.skill}
                          className={`badge ${
                            match.match_type === 'exact' ? 'badge-green' : 'badge-yellow'
                          }`}
                        >
                          {match.skill}
                          {match.user_level && ` (${match.user_level})`}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {jobAnalysis.missing_skills.length > 0 && (
                  <div className="mt-2">
                    <h5 className="text-sm font-medium text-gray-700 mb-1">Missing Skills</h5>
                    <div className="flex flex-wrap gap-1">
                      {jobAnalysis.missing_skills.map((skill) => (
                        <span key={skill} className="badge badge-red">
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Generate button */}
            {jobAnalysis && !coverLetter && !coverLetterLoading && (
              <button
                type="button"
                onClick={handleGenerate}
                className="btn-primary w-full"
              >
                Generate Cover Letter
              </button>
            )}

            {coverLetterLoading && (
              <div className="card text-center py-6">
                <div className="animate-pulse-slow text-gray-500">
                  Generating personalized cover letter...
                </div>
              </div>
            )}

            {/* Cover Letter */}
            {coverLetter && (
              <div className="card animate-slide-up">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-medium text-gray-900">Cover Letter</h4>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleCopy}
                      className="text-gray-500 hover:text-gray-700 text-sm"
                    >
                      Copy
                    </button>
                    <button
                      type="button"
                      onClick={handleGenerate}
                      className="text-gray-500 hover:text-gray-700 text-sm"
                    >
                      Regenerate
                    </button>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700 whitespace-pre-wrap max-h-[300px] overflow-auto">
                  {coverLetter}
                </div>

                <button
                  type="button"
                  onClick={handleFill}
                  className="btn-primary w-full mt-3"
                >
                  Fill in Upwork Form
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
