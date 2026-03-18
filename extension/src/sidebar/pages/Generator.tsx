import { useEffect, useState } from 'react';
import { useAppStore } from '../store';
import { apiClient, ScreeningAnswerSearchResult, AttachmentData, MilestoneSuggestion } from '../../lib/api-client';
import JobHeader from '../components/generator/JobHeader';
import AnalysisPanel from '../components/generator/AnalysisPanel';
import CoverLetterPanel from '../components/generator/CoverLetterPanel';
import ScreeningPanel from '../components/generator/ScreeningPanel';
import MilestonesPanel from '../components/generator/MilestonesPanel';

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
    analyzeCurrentJob,
    generateCoverLetter,
    regenerateCoverLetter,
    fillCoverLetter,
    fillScreeningQuestion,
    saveCurrentJob,
    createApplication,
    addSkillToProfile,
  } = useAppStore();

  // Screening question state
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});
  const [suggestedAnswers, setSuggestedAnswers] = useState<Record<string, ScreeningAnswerSearchResult[]>>({});
  const [loadingSuggestions, setLoadingSuggestions] = useState<Record<string, boolean>>({});
  const [generatingAnswers, setGeneratingAnswers] = useState<Record<string, boolean>>({});

  // Fetch full job state
  const [fetchingFullJob, setFetchingFullJob] = useState(false);
  const [fullJobFetched, setFullJobFetched] = useState(false);
  const [attachmentCount, setAttachmentCount] = useState(0);
  const [attachmentStatuses, setAttachmentStatuses] = useState<string[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Regeneration feedback state
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');

  // Application tracking state
  const [showAppliedPrompt, setShowAppliedPrompt] = useState(false);
  const [markingApplied, setMarkingApplied] = useState(false);

  // Submit + improve feedback loop state
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [improving, setImproving] = useState(false);
  const [improvementNotes, setImprovementNotes] = useState<string[] | null>(null);
  const [showImprovementNotes, setShowImprovementNotes] = useState(false);

  // Missing skill add state
  const [addingSkill, setAddingSkill] = useState<string | null>(null);
  const [addedSkills, setAddedSkills] = useState<Set<string>>(new Set());

  // Cover letter options state
  const [inclusions, setInclusions] = useState('');
  const [prototypeUrl, setPrototypeUrl] = useState('');
  const [includeCallOffer, setIncludeCallOffer] = useState(true);

  // Milestones state
  const [milestones, setMilestones] = useState<MilestoneSuggestion[]>([]);
  const [generatingMilestones, setGeneratingMilestones] = useState(false);
  const [fillingMilestones, setFillingMilestones] = useState(false);
  const [milestonesBudget, setMilestonesBudget] = useState('');

  // Parse the max dollar value from a budget string like "$1,000–$5,000" or "$6,500"
  const parseBudgetMax = (str: string | null | undefined): string => {
    if (!str) return '';
    const cleaned = str.replace(/[$,]/g, '').replace(/\/hr.*/i, '').trim();
    const range = cleaned.match(/[\d.]+[-–]+([\d.]+)/);
    if (range) return String(Math.round(parseFloat(range[1])));
    const single = cleaned.match(/^[\d.]+/);
    return single ? String(Math.round(parseFloat(single[0]))) : '';
  };

  useEffect(() => {
    if (currentJob?.budgetAmount) {
      const parsed = parseBudgetMax(currentJob.budgetAmount);
      if (parsed) setMilestonesBudget(parsed);
    }
  }, [currentJob?.budgetAmount]);

  useEffect(() => {
    chrome.runtime.sendMessage({ type: 'GET_CURRENT_JOB' }, (response) => {
      if (response?.data) useAppStore.getState().setCurrentJob(response.data);
    });
    chrome.runtime.sendMessage({ type: 'REQUEST_JOB_EXTRACTION' }, (response) => {
      if (chrome.runtime.lastError) return;
      if (response?.success && response.data) useAppStore.getState().setCurrentJob(response.data);
    });
  }, []);

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

  const handleRefreshJob = () => {
    chrome.runtime.sendMessage({ type: 'REQUEST_JOB_EXTRACTION' }, (response) => {
      if (response?.success && response.data) {
        useAppStore.getState().setCurrentJob(response.data);
      } else {
        alert('Could not extract job data. Make sure you are on an Upwork job/proposal page. Error: ' + (response?.error || 'No response'));
      }
    });
  };

  const _resetFeedbackLoopState = () => {
    setSubmitted(false);
    setImprovementNotes(null);
    setShowImprovementNotes(false);
  };

  const handleGenerate = () => {
    _resetFeedbackLoopState();
    generateCoverLetter(inclusions.trim() || undefined, prototypeUrl.trim() || undefined, includeCallOffer);
  };

  const handleRegenerate = () => {
    if (showFeedbackInput && feedbackText.trim()) {
      _resetFeedbackLoopState();
      regenerateCoverLetter(feedbackText.trim(), includeCallOffer);
      setFeedbackText('');
      setShowFeedbackInput(false);
    } else {
      setShowFeedbackInput(true);
    }
  };

  const handleRegenerateFresh = () => {
    _resetFeedbackLoopState();
    setShowFeedbackInput(false);
    setFeedbackText('');
    generateCoverLetter(inclusions.trim() || undefined, prototypeUrl.trim() || undefined, includeCallOffer);
  };

  const handleFill = async () => {
    const success = await fillCoverLetter();
    if (success) setShowAppliedPrompt(true);
  };

  const handleMarkAsApplied = async () => {
    setMarkingApplied(true);
    const success = await createApplication();
    setMarkingApplied(false);
    if (success) setShowAppliedPrompt(false);
  };

  const handleCopy = () => {
    if (coverLetter) navigator.clipboard.writeText(coverLetter);
  };

  const handleMarkSubmitted = async () => {
    const { coverLetterId } = useAppStore.getState();
    if (!coverLetterId || !coverLetter) return;
    setSubmitting(true);
    try {
      await apiClient.submitCoverLetter(coverLetterId, coverLetter);
      setSubmitted(true);
    } catch {
      // silent — non-critical action
    } finally {
      setSubmitting(false);
    }
  };

  const handleImprove = async () => {
    const { coverLetterId } = useAppStore.getState();
    if (!coverLetterId) return;
    setImproving(true);
    setImprovementNotes(null);
    try {
      const result = await apiClient.improveCoverLetter(coverLetterId);
      useAppStore.getState().setCoverLetter(result.improved_content);
      useAppStore.getState().setCoverLetterId(result.cover_letter_id);
      setImprovementNotes(result.improvement_notes);
      setShowImprovementNotes(true);
      setSubmitted(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('422') || msg.includes('Need at least')) {
        alert('Need at least 1 won proposal in your corpus. Apply to jobs and mark outcomes to build your winning letter library.');
      }
    } finally {
      setImproving(false);
    }
  };

  const handleOpenEditor = () => {
    if (!coverLetter) return;
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

  const handleFillQuestion = async (selector: string, index: number, question: string) => {
    const answer = questionAnswers[`q${index}`];
    if (!answer) { alert('Please enter an answer first'); return; }
    const success = await fillScreeningQuestion(selector, answer);
    if (!success) { alert('Failed to fill answer. Make sure you are on the Upwork proposal page.'); return; }
    try {
      await apiClient.createScreeningAnswer({
        question,
        answer,
        job_title: currentJob?.title || undefined,
        job_skills: currentJob?.skills,
      });
    } catch {
      // non-critical
    }
  };

  const handleQuestionFocus = async (question: string, index: number) => {
    const key = `q${index}`;
    if (suggestedAnswers[key] || loadingSuggestions[key]) return;
    setLoadingSuggestions(prev => ({ ...prev, [key]: true }));
    try {
      const results = await apiClient.searchScreeningAnswers(question, 3);
      setSuggestedAnswers(prev => ({ ...prev, [key]: results }));
    } catch {
      // non-critical
    } finally {
      setLoadingSuggestions(prev => ({ ...prev, [key]: false }));
    }
  };

  const handleUseSuggestedAnswer = (index: number, answer: string) => {
    setQuestionAnswers(prev => ({ ...prev, [`q${index}`]: answer }));
  };

  const handleGenerateAnswer = async (question: string, index: number) => {
    const key = `q${index}`;
    setGeneratingAnswers(prev => ({ ...prev, [key]: true }));
    try {
      const result = await apiClient.generateScreeningAnswer(
        question,
        currentJob?.title ?? undefined,
        currentJob?.description ?? undefined,
        currentJob?.skills ?? undefined,
      );
      setQuestionAnswers(prev => ({ ...prev, [key]: result.answer }));
    } catch {
      // silent
    } finally {
      setGeneratingAnswers(prev => ({ ...prev, [key]: false }));
    }
  };

  const handleFillAll = async () => {
    if (!currentJob?.screeningQuestions) return;
    const answers = currentJob.screeningQuestions
      .map((_, i) => ({ index: i, answer: questionAnswers[`q${i}`] }))
      .filter(a => !!a.answer);
    if (!answers.length) return;
    await new Promise<void>((resolve) => {
      chrome.runtime.sendMessage({ type: 'FILL_ALL_QUESTIONS', answers }, () => resolve());
    });
  };

  const handleGenerateAll = async () => {
    await generateCoverLetter(inclusions.trim() || undefined, prototypeUrl.trim() || undefined, includeCallOffer);
    if (currentJob?.screeningQuestions && currentJob.screeningQuestions.length > 0) {
      const results = await Promise.allSettled(
        currentJob.screeningQuestions.map((q, i) =>
          apiClient.generateScreeningAnswer(
            q.question,
            currentJob.title ?? undefined,
            currentJob.description ?? undefined,
            currentJob.skills ?? undefined,
          ).then(r => ({ index: i, answer: r.answer }))
        )
      );
      const newAnswers: Record<string, string> = {};
      results.forEach(r => {
        if (r.status === 'fulfilled') newAnswers[`q${r.value.index}`] = r.value.answer;
      });
      setQuestionAnswers(prev => ({ ...prev, ...newAnswers }));
    }
  };

  const handleGenerateMilestones = async () => {
    if (!currentJob) return;
    setGeneratingMilestones(true);
    try {
      const budgetStr = milestonesBudget ? `$${milestonesBudget}` : (currentJob.budgetAmount ?? undefined);
      const result = await apiClient.suggestMilestones(
        currentJob.title || '',
        currentJob.description || '',
        budgetStr,
        3,
      );
      setMilestones(result.milestones);
    } catch {
      // non-critical
    } finally {
      setGeneratingMilestones(false);
    }
  };

  const handleFillMilestones = async () => {
    if (!milestones.length) return;
    setFillingMilestones(true);
    await new Promise<void>((resolve) => {
      chrome.runtime.sendMessage({ type: 'FILL_MILESTONES', milestones }, () => resolve());
    });
    setFillingMilestones(false);
  };

  const handleAddMissingSkill = async (skillName: string) => {
    setAddingSkill(skillName);
    const success = await addSkillToProfile(skillName, 'beginner');
    setAddingSkill(null);
    if (success) setAddedSkills(prev => new Set(prev).add(skillName));
  };

  const handleAnswerChange = (index: number, value: string) => {
    setQuestionAnswers(prev => ({ ...prev, [`q${index}`]: value }));
  };

  const handleFetchFullJob = async () => {
    setFetchingFullJob(true);
    setFetchError(null);
    setAttachmentStatuses([]);
    try {
      const linkResponse = await new Promise<{ success: boolean; url?: string; error?: string }>((resolve) => {
        chrome.runtime.sendMessage({ type: 'GET_VIEW_POSTING_LINK' }, resolve);
      });
      if (!linkResponse.success || !linkResponse.url) {
        setFetchError('Could not find "View job posting" link on this page');
        return;
      }
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
      let jobId = savedJobId;
      if (!jobId) jobId = await saveCurrentJob();
      if (attachments.length > 0 && jobId) {
        const attachmentData: AttachmentData[] = [];
        const statuses: string[] = [];
        for (const att of attachments) {
          try {
            statuses.push(`Downloading ${att.filename}...`);
            setAttachmentStatuses([...statuses]);
            const downloadResponse = await new Promise<{
              success: boolean; data?: string; contentType?: string; error?: string;
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
          } catch {
            statuses[statuses.length - 1] = `Error: ${att.filename}`;
            setAttachmentStatuses([...statuses]);
          }
        }
        if (attachmentData.length > 0) {
          try {
            await apiClient.extractJobAttachments(jobId, attachmentData, fullDescription || undefined);
          } catch {
            // non-critical
          }
        }
      }
      if (fullDescription) {
        const updatedJob = { ...currentJob, fullDescription };
        useAppStore.getState().setCurrentJob(updatedJob as typeof currentJob);
      }
      setFullJobFetched(true);
      setAttachmentCount(attachments.length);
    } catch (err) {
      setFetchError(String(err));
    } finally {
      setFetchingFullJob(false);
    }
  };

  return (
    <div className="flex flex-col">
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {!currentJob || !currentJob.title ? (
          <div className="card text-center py-8">
            <div className="text-gray-400 text-4xl mb-3">&#128188;</div>
            <h3 className="font-medium text-gray-900">No Job Detected</h3>
            <p className="text-sm text-gray-500 mt-1">
              Navigate to an Upwork job page to get started
            </p>
            <button type="button" onClick={handleRefreshJob} className="btn-outline mt-4">
              Refresh Detection
            </button>
          </div>
        ) : (
          <>
            <JobHeader
              currentJob={currentJob}
              jobAnalysis={jobAnalysis}
              onRefresh={handleRefreshJob}
              fetchingFullJob={fetchingFullJob}
              fullJobFetched={fullJobFetched}
              attachmentCount={attachmentCount}
              attachmentStatuses={attachmentStatuses}
              fetchError={fetchError}
              onFetchFullJob={handleFetchFullJob}
            />

            <AnalysisPanel
              jobAnalysis={jobAnalysis}
              analysisLoading={analysisLoading}
              analysisError={analysisError}
              onAnalyze={() => analyzeCurrentJob()}
              addedSkills={addedSkills}
              addingSkill={addingSkill}
              onAddMissingSkill={handleAddMissingSkill}
            />

            <CoverLetterPanel
              coverLetter={coverLetter || ''}
              jobAnalysis={jobAnalysis}
              inclusions={inclusions}
              setInclusions={setInclusions}
              prototypeUrl={prototypeUrl}
              setPrototypeUrl={setPrototypeUrl}
              includeCallOffer={includeCallOffer}
              setIncludeCallOffer={setIncludeCallOffer}
              coverLetterError={coverLetterError}
              coverLetterLoading={coverLetterLoading}
              showFeedbackInput={showFeedbackInput}
              feedbackText={feedbackText}
              setFeedbackText={setFeedbackText}
              improvementNotes={improvementNotes}
              showImprovementNotes={showImprovementNotes}
              setShowImprovementNotes={setShowImprovementNotes}
              improving={improving}
              submitting={submitting}
              submitted={submitted}
              showAppliedPrompt={showAppliedPrompt}
              markingApplied={markingApplied}
              applicationId={applicationId}
              onGenerate={handleGenerate}
              onGenerateAll={handleGenerateAll}
              onRetryGenerate={handleGenerate}
              onFill={handleFill}
              onCopy={handleCopy}
              onRegenerate={handleRegenerate}
              onRegenerateFresh={handleRegenerateFresh}
              onOpenEditor={handleOpenEditor}
              onImprove={handleImprove}
              onMarkSubmitted={handleMarkSubmitted}
              onMarkAsApplied={handleMarkAsApplied}
              onDismissAppliedPrompt={() => setShowAppliedPrompt(false)}
            />

            {currentJob?.screeningQuestions && currentJob.screeningQuestions.length > 0 && (
              <ScreeningPanel
                questions={currentJob.screeningQuestions}
                questionAnswers={questionAnswers}
                suggestedAnswers={suggestedAnswers}
                loadingSuggestions={loadingSuggestions}
                generatingAnswers={generatingAnswers}
                onAnswerChange={handleAnswerChange}
                onQuestionFocus={handleQuestionFocus}
                onUseSuggestedAnswer={handleUseSuggestedAnswer}
                onGenerateAnswer={handleGenerateAnswer}
                onFillQuestion={handleFillQuestion}
                onFillAll={handleFillAll}
              />
            )}

            {coverLetter && (
              <MilestonesPanel
                milestones={milestones}
                generatingMilestones={generatingMilestones}
                fillingMilestones={fillingMilestones}
                milestonesBudget={milestonesBudget}
                budgetPlaceholder={currentJob?.budgetAmount}
                setMilestonesBudget={setMilestonesBudget}
                onGenerate={handleGenerateMilestones}
                onFill={handleFillMilestones}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
