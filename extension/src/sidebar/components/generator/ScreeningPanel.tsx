import type { ScreeningQuestion } from '../../../types';
import type { ScreeningAnswerSearchResult } from '../../../lib/api-client';

interface ScreeningPanelProps {
  questions: ScreeningQuestion[];
  questionAnswers: Record<string, string>;
  suggestedAnswers: Record<string, ScreeningAnswerSearchResult[]>;
  loadingSuggestions: Record<string, boolean>;
  generatingAnswers: Record<string, boolean>;
  onAnswerChange: (index: number, value: string) => void;
  onQuestionFocus: (question: string, index: number) => void;
  onUseSuggestedAnswer: (index: number, answer: string) => void;
  onGenerateAnswer: (question: string, index: number) => void;
  onFillQuestion: (selector: string, index: number, question: string) => void;
  onFillAll: () => void;
}

export default function ScreeningPanel({
  questions,
  questionAnswers,
  suggestedAnswers,
  loadingSuggestions,
  generatingAnswers,
  onAnswerChange,
  onQuestionFocus,
  onUseSuggestedAnswer,
  onGenerateAnswer,
  onFillQuestion,
  onFillAll,
}: ScreeningPanelProps) {
  return (
    <div className="card animate-slide-up">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-medium text-gray-900">
          Screening Questions ({questions.length})
        </h4>
        {questions.some((_, i) => questionAnswers[`q${i}`]) && (
          <button type="button" onClick={onFillAll} className="btn-primary text-xs py-1 px-3">
            Fill All ↵
          </button>
        )}
      </div>
      <div className="space-y-4">
        {questions.map((q, index) => (
          <div key={index} className="border-b border-gray-100 pb-3 last:border-0">
            <p className="text-sm text-gray-700 mb-2">{q.question}</p>
            <textarea
              className="w-full border border-gray-200 rounded-lg p-2 text-sm resize-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
              rows={3}
              placeholder="Enter your answer or click AI to generate..."
              value={questionAnswers[`q${index}`] || ''}
              onChange={e => onAnswerChange(index, e.target.value)}
              onFocus={() => onQuestionFocus(q.question, index)}
            />

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
                      onClick={() => onUseSuggestedAnswer(index, suggestion.answer.answer)}
                      className="text-blue-600 hover:text-blue-800 whitespace-nowrap"
                    >
                      Use
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-2 mt-2">
              <button
                type="button"
                onClick={() => onGenerateAnswer(q.question, index)}
                disabled={generatingAnswers[`q${index}`]}
                className="btn-outline text-xs py-1 px-3 disabled:opacity-60"
              >
                {generatingAnswers[`q${index}`] ? 'Generating...' : 'AI Answer'}
              </button>
              <button
                type="button"
                onClick={() => onFillQuestion(q.inputSelector, index, q.question)}
                className="btn-outline text-xs py-1 px-3"
                disabled={!questionAnswers[`q${index}`]}
              >
                Fill &amp; Save
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
