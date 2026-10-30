import type { ClientReview } from '../../../lib/api-client';

const SHORTLIST_LABEL: Record<ClientReview['shortlist'], string> = {
  yes: 'Shortlisted',
  maybe: 'Maybe',
  no: 'Not shortlisted',
};

interface CoverLetterPanelProps {
  coverLetter: string;
  jobAnalysis: unknown; // just for the inclusions form visibility — non-null means show
  inclusions: string;
  setInclusions: (v: string) => void;
  prototypeUrl: string;
  setPrototypeUrl: (v: string) => void;
  includeCallOffer: boolean;
  setIncludeCallOffer: (v: boolean) => void;
  clientReview: boolean;
  setClientReview: (v: boolean) => void;
  clientReviewResult: ClientReview | null;
  coverLetterError: string | null;
  coverLetterLoading: boolean;
  submitting: boolean;
  submitted: boolean;
  showAppliedPrompt: boolean;
  markingApplied: boolean;
  applicationId: string | null;
  verifyWarnings: string[];
  factsUsed: { id: string; statement: string }[];
  claimsVerified: boolean;
  onGenerate: () => void;
  onGenerateAll: () => void;
  onRetryGenerate: () => void;
  onFill: () => void;
  onCopy: () => void;
  onRegenerateFresh: () => void;
  onOpenEditor: () => void;
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
  clientReview,
  setClientReview,
  clientReviewResult,
  coverLetterError,
  coverLetterLoading,
  submitting,
  submitted,
  showAppliedPrompt,
  markingApplied,
  applicationId,
  verifyWarnings,
  factsUsed,
  claimsVerified,
  onGenerate,
  onGenerateAll,
  onRetryGenerate,
  onFill,
  onCopy,
  onRegenerateFresh,
  onOpenEditor,
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
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={clientReview}
              onChange={e => setClientReview(e.target.checked)}
              className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            <span className="text-xs text-gray-600">Client's-eye review (slower)</span>
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
              <button type="button" onClick={onRegenerateFresh} className="text-gray-500 hover:text-gray-700 text-sm" title="Generate a brand-new draft">
                New draft
              </button>
            </div>
          </div>

          {!claimsVerified && (
            <div role="alert" className="mb-2 rounded-lg border border-red-300 bg-red-50 p-2 text-xs font-medium text-red-800">
              Claims not verified — review specifics before sending
            </div>
          )}

          <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700 whitespace-pre-wrap max-h-[300px] overflow-auto">
            {coverLetter}
          </div>

          {verifyWarnings.length > 0 && (
            <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              <p className="font-medium mb-1">Check before sending</p>
              <ul className="list-disc pl-4 space-y-0.5">
                {verifyWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {clientReviewResult && (
            <div className="mt-2 rounded-lg border border-sky-200 bg-sky-50 p-2 text-xs text-sky-900">
              <p className="font-medium">
                Client's-eye review: {SHORTLIST_LABEL[clientReviewResult.shortlist] ?? clientReviewResult.shortlist}
              </p>
              {clientReviewResult.why && <p className="mt-0.5">{clientReviewResult.why}</p>}
              <details className="mt-1">
                <summary className="cursor-pointer select-none">
                  First-draft verdicts (cut and rewrite ones were sent back to the writer)
                </summary>
                <ul className="list-disc pl-4 mt-1 space-y-0.5">
                  {clientReviewResult.paragraphs.map(p => (
                    <li key={p.paragraph}>
                      Paragraph {p.paragraph}: <span className="font-medium">{p.verdict}</span>
                      {p.reason ? ` - ${p.reason}` : ''}
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}

          {factsUsed.length > 0 && (
            <details className="mt-2 text-xs text-gray-600">
              <summary className="cursor-pointer select-none">Facts used ({factsUsed.length})</summary>
              <ul className="list-disc pl-4 mt-1 space-y-0.5">
                {factsUsed.map((f) => (
                  <li key={f.id}>{f.statement}</li>
                ))}
              </ul>
            </details>
          )}

          <button type="button" onClick={onFill} className="btn-primary w-full mt-3">
            Fill in Upwork Form
          </button>

          <div className="mt-2 flex gap-2">
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
