import { useState } from 'react';
import { useAppStore } from '../store';
import { apiClient, BetaFeedbackCreate } from '../../lib/api-client';

type FeedbackType = 'bug' | 'feature_request' | 'usability' | 'general';

const FEEDBACK_TYPES: { value: FeedbackType; label: string; emoji: string }[] = [
  { value: 'bug', label: 'Bug Report', emoji: '🐛' },
  { value: 'feature_request', label: 'Feature Request', emoji: '💡' },
  { value: 'usability', label: 'Usability Issue', emoji: '🎯' },
  { value: 'general', label: 'General Feedback', emoji: '💬' },
];

export default function BetaFeedbackPage() {
  const { setCurrentView } = useAppStore();
  const [feedbackType, setFeedbackType] = useState<FeedbackType>('general');
  const [description, setDescription] = useState('');
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) {
      setError('Please describe your feedback');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const data: BetaFeedbackCreate = {
        feedback_type: feedbackType,
        description: description.trim(),
        email: email.trim() || undefined,
        extension_version: '1.0.0',
        browser_info: navigator.userAgent.substring(0, 200),
      };

      // Try to get the current page URL from the active tab
      try {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tabs[0]?.url) {
          data.page_url = tabs[0].url;
        }
      } catch {
        // Ignore if we can't get the URL
      }

      await apiClient.submitBetaFeedback(data);
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit feedback');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen flex flex-col">
        <header className="bg-white border-b px-4 py-3">
          <h1 className="font-bold text-gray-900">Beta Feedback</h1>
        </header>
        <div className="flex-1 flex items-center justify-center p-4">
          <div className="text-center">
            <div className="text-5xl mb-4">🎉</div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Thank You!</h2>
            <p className="text-gray-600 mb-6">
              Your feedback helps us improve UpApply.
            </p>
            <button
              type="button"
              onClick={() => setCurrentView('generator')}
              className="btn-primary"
            >
              Back to Generator
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCurrentView('generator')}
          className="text-gray-600 hover:text-gray-900"
        >
          &larr; Back
        </button>
        <h1 className="font-bold text-gray-900">Beta Feedback</h1>
        <div className="w-12" />
      </header>

      <div className="flex-1 overflow-auto p-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Feedback Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              What type of feedback?
            </label>
            <div className="grid grid-cols-2 gap-2">
              {FEEDBACK_TYPES.map(({ value, label, emoji }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFeedbackType(value)}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    feedbackType === value
                      ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-500'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <span className="text-lg mr-2">{emoji}</span>
                  <span className="text-sm font-medium">{label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Description */}
          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Describe your feedback
              <span className="text-red-500 ml-1">*</span>
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={
                feedbackType === 'bug'
                  ? 'What happened? What did you expect to happen?'
                  : feedbackType === 'feature_request'
                  ? 'What feature would you like to see?'
                  : feedbackType === 'usability'
                  ? 'What was confusing or difficult to use?'
                  : 'Tell us what you think...'
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
              rows={5}
            />
          </div>

          {/* Email (optional) */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Email <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            />
            <p className="text-xs text-gray-500 mt-1">
              So we can follow up if needed
            </p>
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !description.trim()}
            className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting...' : 'Submit Feedback'}
          </button>

          <p className="text-xs text-center text-gray-500">
            Thank you for helping us improve UpApply!
          </p>
        </form>
      </div>
    </div>
  );
}
