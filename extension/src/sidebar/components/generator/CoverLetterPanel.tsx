interface CoverLetterPanelProps {
  coverLetter: string;
  jobAnalysis: unknown; // just for the inclusions form visibility — non-null means show
  inclusions: string;
  setInclusions: (v: string) => void;
  prototypeUrl: string;
  setPrototypeUrl: (v: string) => void;
  includeCallOffer: boolean;
  setIncludeCallOffer: (v: boolean) => void;
  coverLetterError: string | null;
  coverLetterLoading: boolean;
  showFeedbackInput: boolean;
  feedbackText: string;
  setFeedbackText: (v: string) => void;
  improvementNotes: string[] | null;
  showImprovementNotes: boolean;
  setShowImprovementNotes: (v: boolean | ((prev: boolean) => boolean)) => void;
  improving: boolean;
  submitting: boolean;
  submitted: boolean;
  showAppliedPrompt: boolean;
  markingApplied: boolean;
  applicationId: string | null;
  onGenerate: () => void;
  onGenerateAll: () => void;
  onRetryGenerate: () => void;
  onFill: () => void;
  onCopy: () => void;
  onRegenerate: () => void;
  onRegenerateFresh: () => void;
  onOpenEditor: () => void;
  onImprove: () => void;
  onMarkSubmitted: () => void;
  onMarkAsApplied: () => void;
  onDismissAppliedPrompt: () => void;
}

export default function CoverLetterPanel({
  coverLetter,
  jobAnalysis,
  inclusions,
  setInclusions,
  prototypeUrl,
  setPrototypeUrl,
  includeCallOffer,
  setIncludeCallOffer,
  coverLetterError,
  coverLetterLoading,
  showFeedbackInput,
  feedbackText,
  setFeedbackText,
  improvementNotes,
  showImprovementNotes,
  setShowImprovementNotes,
  improving,
  submitting,
  submitted,
  showAppliedPrompt,
  markingApplied,
  applicationId,
  onGenerate,
  onGenerateAll,
  onRetryGenerate,
  onFill,
  onCopy,
  onRegenerate,
  onRegenerateFresh,
  onOpenEditor,
  onImprove,
  onMarkSubmitted,
  onMarkAsApplied,
  onDismissAppliedPrompt,
}: CoverLetterPanelProps) {
  return (
    <>
      {/* Cover Letter Error */}
      {coverLetterError && (
        <div className="card bg-red-50 border-red-200">
          <h4 className="font-medium text-red-800 mb-1">Generation Failed</h4>
          <p className="text-sm text-red-700">{coverLetterError}</p>
          <button type="button" onClick={onRetryGenerate} className="btn-outline text-sm mt-2">
            Retry
          </button>
        </div>
      )}

      {/* Inclusions + Generate button */}
      {jobAnalysis && !coverLetter && !coverLetterLoading && !coverLetterError && (
        <div className="space-y-2">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">
              Include in cover letter <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={inclusions}
              onChange={e => setInclusions(e.target.value)}
              rows={3}
              className="input text-sm w-full"
              placeholder={'Concepts to weave in, or "exact phrases" in quotes\ne.g. I built a similar SaaS dashboard\n"10+ years of React experience"'}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">
              Prototype URL <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="url"
              value={prototypeUrl}
              onChange={e => setPrototypeUrl(e.target.value)}
              className="input text-sm w-full"
              placeholder="https://your-prototype.vercel.app"
            />
            {prototypeUrl.trim() && (
              <p className="text-xs text-gray-400 mt-1 italic">
                Will add: "...I created a prototype of this project at {prototypeUrl.trim()}..."
              </p>
            )}
          </div>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeCallOffer}
              onChange={e => setIncludeCallOffer(e.target.checked)}
              className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            <span className="text-xs text-gray-600">
              Include no-cost call offer
              <span className="text-gray-400 ml-1">(recommended)</span>
            </span>
          </label>
          <div className="flex gap-2">
            <button type="button" onClick={onGenerate} className="btn-outline flex-1">
              Cover Letter Only
            </button>
            <button type="button" onClick={onGenerateAll} className="btn-primary flex-1">
              Generate All
            </button>
          </div>
        </div>
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
              <button type="button" onClick={onOpenEditor} className="text-gray-500 hover:text-gray-700 text-sm" title="Open in larger editor">
                Edit
              </button>
              <button type="button" onClick={onCopy} className="text-gray-500 hover:text-gray-700 text-sm">
                Copy
              </button>
              <button type="button" onClick={onRegenerate} className="text-gray-500 hover:text-gray-700 text-sm">
                {showFeedbackInput ? 'Submit' : 'Regenerate'}
              </button>
              {showFeedbackInput && (
                <button type="button" onClick={onRegenerateFresh} className="text-gray-400 hover:text-gray-600 text-sm">
                  Fresh
                </button>
              )}
            </div>
          </div>

          {showFeedbackInput && (
            <div className="mb-3">
              <input
                type="text"
                value={feedbackText}
                onChange={e => setFeedbackText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && feedbackText.trim() && onRegenerate()}
                placeholder="What should be different? (e.g., more technical, shorter...)"
                className="input text-sm"
                autoFocus
              />
              <button
                type="button"
                onClick={() => { setFeedbackText(''); onRegenerateFresh(); }}
                className="text-xs text-gray-400 mt-1"
              >
                Cancel
              </button>
            </div>
          )}

          <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700 whitespace-pre-wrap max-h-[300px] overflow-auto">
            {coverLetter}
          </div>

          <button type="button" onClick={onFill} className="btn-primary w-full mt-3">
            Fill in Upwork Form
          </button>

          {improvementNotes && improvementNotes.length > 0 && (
            <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 text-xs">
              <button
                type="button"
                onClick={() => setShowImprovementNotes(v => !v)}
                className="w-full flex items-center justify-between px-3 py-2 text-amber-800 font-medium"
              >
                <span>✨ {improvementNotes.length} improvement{improvementNotes.length !== 1 ? 's' : ''} applied</span>
                <span>{showImprovementNotes ? '▲' : '▼'}</span>
              </button>
              {showImprovementNotes && (
                <ul className="px-3 pb-2 space-y-1 text-amber-700">
                  {improvementNotes.map((note, i) => (
                    <li key={i} className="leading-snug">• {note}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={onImprove}
              disabled={improving}
              title="Compare against your won proposals and improve this letter"
              className="flex-1 btn-outline text-xs py-1.5 disabled:opacity-50"
            >
              {improving ? '✨ Comparing…' : '✨ Improve'}
            </button>
            <button
              type="button"
              onClick={onMarkSubmitted}
              disabled={submitting || submitted}
              title="Save this letter to your corpus as submitted"
              className={`flex-1 text-xs py-1.5 rounded border font-medium transition-colors ${
                submitted
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700 cursor-default'
                  : 'btn-outline'
              }`}
            >
              {submitted ? '✓ Submitted' : submitting ? 'Saving…' : 'Mark Submitted'}
            </button>
          </div>

          {showAppliedPrompt && !applicationId && (
            <div className="mt-3 p-3 bg-blue-50 rounded-lg">
              <p className="text-sm text-blue-800 mb-2">Form filled! Did you submit the proposal?</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={onMarkAsApplied}
                  disabled={markingApplied}
                  className="btn-primary text-sm flex-1"
                >
                  {markingApplied ? 'Saving...' : 'Yes, Mark as Applied'}
                </button>
                <button type="button" onClick={onDismissAppliedPrompt} className="btn-outline text-sm flex-1">
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
    </>
  );
}
