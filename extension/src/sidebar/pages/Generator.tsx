import { useEffect, useState } from 'react';
import { useAppStore } from '../store';
import { apiClient, ScreeningAnswerSearchResult, AttachmentData } from '../../lib/api-client';

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
    analysisError,
    coverLetter,
    coverLetterLoading,
    coverLetterError,
    savedJobId,
    applicationId,
    setCurrentView,
    analyzeCurrentJob,
    generateCoverLetter,
    regenerateCoverLetter,
    fillCoverLetter,
    fillScreeningQuestion,
    saveCurrentJob,
    createApplication,
    logout,
    addSkillToProfile,
  } = useAppStore();

  // State for screening question answers
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});
  const [suggestedAnswers, setSuggestedAnswers] = useState<Record<string, ScreeningAnswerSearchResult[]>>({});
  const [loadingSuggestions, setLoadingSuggestions] = useState<Record<string, boolean>>({});

  // State for fetching full job with attachments
  const [fetchingFullJob, setFetchingFullJob] = useState(false);
  const [fullJobFetched, setFullJobFetched] = useState(false);
  const [attachmentCount, setAttachmentCount] = useState(0);
  const [attachmentStatuses, setAttachmentStatuses] = useState<string[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // State for regeneration feedback
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');

  // State for application tracking
  const [showAppliedPrompt, setShowAppliedPrompt] = useState(false);
  const [markingApplied, setMarkingApplied] = useState(false);

  // State for adding skills from missing list
  const [addingSkill, setAddingSkill] = useState<string | null>(null);
  const [addedSkills, setAddedSkills] = useState<Set<string>>(new Set());

  useEffect(() => {
    // Request current job data from stored cache first
    chrome.runtime.sendMessage({ type: 'GET_CURRENT_JOB' }, (response) => {
      console.log('UpApply Sidebar: GET_CURRENT_JOB response:', response);
      if (response?.data) {
        useAppStore.getState().setCurrentJob(response.data);
      }
    });

    // Also actively request extraction via background (handles script injection)
    chrome.runtime.sendMessage({ type: 'REQUEST_JOB_EXTRACTION' }, (response) => {
      if (chrome.runtime.lastError) return; // No listener or not on Upwork
      if (response?.success && response.data) {
        useAppStore.getState().setCurrentJob(response.data);
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

  const handleRegenerate = () => {
    if (showFeedbackInput && feedbackText.trim()) {
      regenerateCoverLetter(feedbackText.trim());
      setFeedbackText('');
      setShowFeedbackInput(false);
    } else {
      setShowFeedbackInput(true);
    }
  };

  const handleRegenerateFresh = () => {
    setShowFeedbackInput(false);
    setFeedbackText('');
    generateCoverLetter();
  };

  const handleFill = async () => {
    const success = await fillCoverLetter();
    if (success) {
      setShowAppliedPrompt(true);
    }
  };

  const handleMarkAsApplied = async () => {
    setMarkingApplied(true);
    const success = await createApplication();
    setMarkingApplied(false);
    if (success) {
      setShowAppliedPrompt(false);
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

  const handleFillQuestion = async (selector: string, index: number, question: string) => {
    const answer = questionAnswers[`q${index}`];
    if (!answer) {
      alert('Please enter an answer first');
      return;
    }
    const success = await fillScreeningQuestion(selector, answer);
    if (!success) {
      alert('Failed to fill answer. Make sure you are on the Upwork proposal page.');
      return;
    }

    // Save the Q&A for future reference
    try {
      await apiClient.createScreeningAnswer({
        question,
        answer,
        job_title: currentJob?.title || undefined,
        job_skills: currentJob?.skills,
      });
      console.log('Screening answer saved for future use');
    } catch (err) {
      console.error('Failed to save screening answer:', err);
    }
  };

  // Search for similar past answers when a question is focused
  const handleQuestionFocus = async (question: string, index: number) => {
    const key = `q${index}`;
    if (suggestedAnswers[key] || loadingSuggestions[key]) return;

    setLoadingSuggestions(prev => ({ ...prev, [key]: true }));
    try {
      const results = await apiClient.searchScreeningAnswers(question, 3);
      setSuggestedAnswers(prev => ({ ...prev, [key]: results }));
    } catch (err) {
      console.error('Failed to search past answers:', err);
    } finally {
      setLoadingSuggestions(prev => ({ ...prev, [key]: false }));
    }
  };

  const handleUseSuggestedAnswer = (index: number, answer: string) => {
    setQuestionAnswers(prev => ({ ...prev, [`q${index}`]: answer }));
  };

  const handleAddMissingSkill = async (skillName: string) => {
    setAddingSkill(skillName);
    const success = await addSkillToProfile(skillName, 'beginner');
    setAddingSkill(null);
    if (success) {
      setAddedSkills(prev => new Set(prev).add(skillName));
    }
  };

  const handleAnswerChange = (index: number, value: string) => {
    setQuestionAnswers(prev => ({ ...prev, [`q${index}`]: value }));
  };

  // Fetch the full job posting via background tab
  const handleFetchFullJob = async () => {
    setFetchingFullJob(true);
    setFetchError(null);
    setAttachmentStatuses([]);

    try {
      // First, get the "View job posting" link from the current page
      const linkResponse = await new Promise<{ success: boolean; url?: string; error?: string }>((resolve) => {
        chrome.runtime.sendMessage({ type: 'GET_VIEW_POSTING_LINK' }, resolve);
      });

      if (!linkResponse.success || !linkResponse.url) {
        setFetchError('Could not find "View job posting" link on this page');
        return;
      }

      console.log('UpApply: Fetching full job from:', linkResponse.url);

      // Open background tab and extract data
      const extractResponse = await new Promise<{
        success: boolean;
        data?: { fullDescription: string | null; attachments: Array<{ url: string; filename: string; contentType: string }> };
        error?: string;
      }>((resolve) => {
        chrome.runtime.sendMessage({ type: 'EXTRACT_FULL_JOB', jobPostingUrl: linkResponse.url }, resolve);
      });

      if (!extractResponse.success || !extractResponse.data) {
        setFetchError(extractResponse.error || 'Failed to extract job posting data');
        return;
      }

      const { fullDescription, attachments } = extractResponse.data;
      console.log('UpApply: Extracted', attachments.length, 'attachments');

      // Save the job to get a job_id for attachment extraction
      let jobId = savedJobId;
      if (!jobId) {
        jobId = await saveCurrentJob();
      }

      // If there are attachments and we have a job_id, download and send to backend
      if (attachments.length > 0 && jobId) {
        const attachmentData: AttachmentData[] = [];
        const statuses: string[] = [];

        for (const att of attachments) {
          try {
            statuses.push(`Downloading ${att.filename}...`);
            setAttachmentStatuses([...statuses]);

            const downloadResponse = await new Promise<{
              success: boolean;
              data?: string;
              contentType?: string;
              error?: string;
            }>((resolve) => {
              chrome.runtime.sendMessage({ type: 'DOWNLOAD_ATTACHMENT', url: att.url }, resolve);
            });

            if (downloadResponse.success && downloadResponse.data) {
              attachmentData.push({
                data: downloadResponse.data,
                filename: att.filename,
                content_type: downloadResponse.contentType || att.contentType,
              });
              statuses[statuses.length - 1] = `Downloaded ${att.filename}`;
            } else {
              statuses[statuses.length - 1] = `Failed: ${att.filename}`;
            }
            setAttachmentStatuses([...statuses]);
          } catch (err) {
            console.error('Failed to download attachment:', att.filename, err);
            statuses[statuses.length - 1] = `Error: ${att.filename}`;
            setAttachmentStatuses([...statuses]);
          }
        }

        // Send to backend for text extraction
        if (attachmentData.length > 0) {
          try {
            const extractResult = await apiClient.extractJobAttachments(
              jobId,
              attachmentData,
              fullDescription || undefined,
            );
            console.log('UpApply: Extracted text from', extractResult.attachment_count, 'attachments');
          } catch (err) {
            console.error('Failed to extract attachment text:', err);
          }
        }
      }

      // Update current job with full description
      if (fullDescription) {
        const updatedJob = { ...currentJob, fullDescription };
        useAppStore.getState().setCurrentJob(updatedJob as typeof currentJob);
      }

      setFullJobFetched(true);
      setAttachmentCount(attachments.length);
    } catch (err) {
      console.error('UpApply: Fetch full job error:', err);
      setFetchError(String(err));
    } finally {
      setFetchingFullJob(false);
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
            onClick={() => setCurrentView('skills')}
            className="text-gray-600 hover:text-gray-900 text-sm"
          >
            Skills
          </button>
          <button
            type="button"
            onClick={() => setCurrentView('memories')}
            className="text-gray-600 hover:text-gray-900 text-sm"
          >
            Memories
          </button>
          <button
            type="button"
            onClick={() => setCurrentView('history')}
            className="text-gray-600 hover:text-gray-900 text-sm"
          >
            History
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
            onClick={() => setCurrentView('feedback')}
            className="text-amber-600 hover:text-amber-700 text-sm"
            title="Send feedback"
          >
            Feedback
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
            <div className="text-gray-400 text-4xl mb-3">&#128188;</div>
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

              {/* Fetch Full Job */}
              <div className="mt-3 pt-3 border-t border-gray-100">
                {!fullJobFetched ? (
                  <button
                    type="button"
                    onClick={handleFetchFullJob}
                    disabled={fetchingFullJob}
                    className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
                  >
                    {fetchingFullJob ? (
                      <>
                        <span className="animate-spin">&#9203;</span>
                        Fetching full job details...
                      </>
                    ) : (
                      <>
                        &#128196; Fetch full job posting & attachments
                      </>
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

            {/* Analysis Error */}
            {analysisError && (
              <div className="card bg-red-50 border-red-200">
                <h4 className="font-medium text-red-800 mb-1">Analysis Failed</h4>
                <p className="text-sm text-red-700">{analysisError}</p>
                <button
                  type="button"
                  onClick={handleAnalyze}
                  className="btn-outline text-sm mt-2"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Analysis */}
            {!jobAnalysis && !analysisLoading && !analysisError && (
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
                        <li key={i}>&#8226; {warning}</li>
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
                          &#10003; {strength}
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
                        <span key={skill} className="badge badge-red inline-flex items-center gap-1">
                          {skill}
                          {addedSkills.has(skill) ? (
                            <span className="text-green-600 text-xs" title="Added to profile">&#10003;</span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleAddMissingSkill(skill)}
                              disabled={addingSkill === skill}
                              className="text-red-400 hover:text-green-600 text-xs font-bold ml-0.5"
                              title="Add to profile"
                            >
                              {addingSkill === skill ? '...' : '+'}
                            </button>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Cover Letter Error */}
            {coverLetterError && (
              <div className="card bg-red-50 border-red-200">
                <h4 className="font-medium text-red-800 mb-1">Generation Failed</h4>
                <p className="text-sm text-red-700">{coverLetterError}</p>
                <button
                  type="button"
                  onClick={handleGenerate}
                  className="btn-outline text-sm mt-2"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Generate button */}
            {jobAnalysis && !coverLetter && !coverLetterLoading && !coverLetterError && (
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
                      onClick={handleRegenerate}
                      className="text-gray-500 hover:text-gray-700 text-sm"
                    >
                      {showFeedbackInput ? 'Submit' : 'Regenerate'}
                    </button>
                    {showFeedbackInput && (
                      <button
                        type="button"
                        onClick={handleRegenerateFresh}
                        className="text-gray-400 hover:text-gray-600 text-sm"
                      >
                        Fresh
                      </button>
                    )}
                  </div>
                </div>

                {/* Feedback input for regeneration */}
                {showFeedbackInput && (
                  <div className="mb-3">
                    <input
                      type="text"
                      value={feedbackText}
                      onChange={(e) => setFeedbackText(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && feedbackText.trim() && handleRegenerate()}
                      placeholder="What should be different? (e.g., more technical, shorter...)"
                      className="input text-sm"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => { setShowFeedbackInput(false); setFeedbackText(''); }}
                      className="text-xs text-gray-400 mt-1"
                    >
                      Cancel
                    </button>
                  </div>
                )}

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

                {/* Mark as Applied prompt */}
                {showAppliedPrompt && !applicationId && (
                  <div className="mt-3 p-3 bg-blue-50 rounded-lg">
                    <p className="text-sm text-blue-800 mb-2">Form filled! Did you submit the proposal?</p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={handleMarkAsApplied}
                        disabled={markingApplied}
                        className="btn-primary text-sm flex-1"
                      >
                        {markingApplied ? 'Saving...' : 'Yes, Mark as Applied'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowAppliedPrompt(false)}
                        className="btn-outline text-sm flex-1"
                      >
                        Not Yet
                      </button>
                    </div>
                  </div>
                )}

                {applicationId && (
                  <div className="mt-3 p-2 bg-green-50 rounded-lg text-sm text-green-700 text-center">
                    &#10003; Application tracked
                  </div>
                )}
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
                        onFocus={() => handleQuestionFocus(q.question, index)}
                      />

                      {/* Past Answer Suggestions */}
                      {loadingSuggestions[`q${index}`] && (
                        <p className="text-xs text-gray-400 mt-1">Searching past answers...</p>
                      )}
                      {suggestedAnswers[`q${index}`]?.length > 0 && (
                        <div className="mt-2 bg-blue-50 rounded p-2">
                          <p className="text-xs font-medium text-blue-700 mb-1">Past answers for similar questions:</p>
                          {suggestedAnswers[`q${index}`].map((suggestion, sIdx) => (
                            <div key={sIdx} className="text-xs text-gray-600 mb-1 flex justify-between items-start gap-2">
                              <span className="flex-1 line-clamp-2">{suggestion.answer.answer}</span>
                              <button
                                type="button"
                                onClick={() => handleUseSuggestedAnswer(index, suggestion.answer.answer)}
                                className="text-blue-600 hover:text-blue-800 whitespace-nowrap"
                              >
                                Use
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      <button
                        type="button"
                        onClick={() => handleFillQuestion(q.inputSelector, index, q.question)}
                        className="btn-outline text-sm mt-2"
                        disabled={!questionAnswers[`q${index}`]}
                      >
                        Fill & Save Answer
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
