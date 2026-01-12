import { useEffect, useState } from 'react';
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
    fillScreeningQuestion,
    logout,
  } = useAppStore();

  // State for screening question answers
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});

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

  const handleOpenEditor = () => {
    if (!coverLetter) return;

    // Create a popup window with the cover letter for editing
    const width = 600;
    const height = 500;
    const left = (screen.width - width) / 2;
    const top = (screen.height - height) / 2;

    const popup = window.open('', 'CoverLetterEditor',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`);

    if (popup) {
      popup.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>Edit Cover Letter - UpApply</title>
          <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 16px; background: #f9fafb; }
            h2 { margin-bottom: 12px; color: #111827; font-size: 18px; }
            textarea { width: 100%; height: calc(100vh - 120px); padding: 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; line-height: 1.6; resize: none; }
            textarea:focus { outline: none; border-color: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1); }
            .buttons { margin-top: 12px; display: flex; gap: 8px; }
            button { padding: 8px 16px; border-radius: 6px; font-size: 14px; cursor: pointer; border: none; }
            .primary { background: #10b981; color: white; }
            .primary:hover { background: #059669; }
            .secondary { background: #e5e7eb; color: #374151; }
            .secondary:hover { background: #d1d5db; }
            .word-count { font-size: 12px; color: #6b7280; margin-top: 8px; }
          </style>
        </head>
        <body>
          <h2>Edit Cover Letter</h2>
          <textarea id="editor">${coverLetter.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
          <div class="word-count" id="wordCount">Words: ${coverLetter.split(/\s+/).filter(w => w).length}</div>
          <div class="buttons">
            <button class="primary" onclick="copyAndClose()">Copy & Close</button>
            <button class="secondary" onclick="window.close()">Cancel</button>
          </div>
          <script>
            const editor = document.getElementById('editor');
            const wordCount = document.getElementById('wordCount');
            editor.addEventListener('input', () => {
              const words = editor.value.split(/\\s+/).filter(w => w).length;
              wordCount.textContent = 'Words: ' + words;
            });
            function copyAndClose() {
              navigator.clipboard.writeText(editor.value);
              window.opener.postMessage({ type: 'COVER_LETTER_UPDATED', content: editor.value }, '*');
              window.close();
            }
          </script>
        </body>
        </html>
      `);
      popup.document.close();
    }
  };

  // Listen for updates from the popup editor
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'COVER_LETTER_UPDATED') {
        useAppStore.getState().setCoverLetter(event.data.content);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const handleFillQuestion = async (selector: string, index: number) => {
    const answer = questionAnswers[`q${index}`];
    if (!answer) {
      alert('Please enter an answer first');
      return;
    }
    const success = await fillScreeningQuestion(selector, answer);
    if (!success) {
      alert('Failed to fill answer. Make sure you are on the Upwork proposal page.');
    }
  };

  const handleAnswerChange = (index: number, value: string) => {
    setQuestionAnswers(prev => ({ ...prev, [`q${index}`]: value }));
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
                      onClick={handleOpenEditor}
                      className="text-gray-500 hover:text-gray-700 text-sm"
                      title="Open in larger editor"
                    >
                      Edit
                    </button>
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

            {/* Screening Questions */}
            {currentJob?.screeningQuestions && currentJob.screeningQuestions.length > 0 && coverLetter && (
              <div className="card animate-slide-up">
                <h4 className="font-medium text-gray-900 mb-3">
                  Screening Questions ({currentJob.screeningQuestions.length})
                </h4>
                <div className="space-y-4">
                  {currentJob.screeningQuestions.map((q, index) => (
                    <div key={index} className="border-b border-gray-100 pb-3 last:border-0">
                      <p className="text-sm text-gray-700 mb-2">{q.question}</p>
                      <textarea
                        className="w-full border border-gray-200 rounded-lg p-2 text-sm resize-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                        rows={3}
                        placeholder="Enter your answer..."
                        value={questionAnswers[`q${index}`] || ''}
                        onChange={(e) => handleAnswerChange(index, e.target.value)}
                      />
                      <button
                        type="button"
                        onClick={() => handleFillQuestion(q.inputSelector, index)}
                        className="btn-outline text-sm mt-2"
                        disabled={!questionAnswers[`q${index}`]}
                      >
                        Fill Answer
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
