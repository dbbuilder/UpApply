/**
 * Canonical skip reasons, mirroring api/app/services/skip_reasons.py.
 * The Pass picker sends the code; the API returns skip_reason / skip_reason_detail on each item.
 */

export const USER_SKIP_REASONS = [
  { code: 'budget_too_low', label: 'Budget too low' },
  { code: 'wrong_skills', label: 'Not my skills' },
  { code: 'scope_unclear', label: 'Scope unclear' },
  { code: 'too_large', label: 'Too large / long' },
  { code: 'client_risk', label: 'Client looks risky' },
  { code: 'too_many_proposals', label: 'Too many proposals' },
  { code: 'timing', label: 'Bad timing' },
  { code: 'not_interested', label: 'Not interested' },
  { code: 'duplicate', label: 'Already applied' },
  { code: 'other', label: 'Other' },
] as const;

export type UserSkipReason = (typeof USER_SKIP_REASONS)[number]['code'];

/** Label for a user skip code, falling back to the free text (or the raw code). */
export function skipReasonLabel(code?: string | null, detail?: string | null): string {
  const known = USER_SKIP_REASONS.find((r) => r.code === code);
  if (!known) return detail || code || '';
  return code === 'other' && detail ? detail : known.label;
}

/** Human-readable chip for a pre-filter block ("pre_filter:blocked_country" + "India"). */
export function formatFilterReason(code?: string | null, detail?: string | null): string {
  const rule = (code ?? '').replace(/^pre_filter:/, '');
  switch (rule) {
    case 'blocked_country':
      return detail ? `📍 ${detail}` : 'Geo blocked';
    case 'budget_too_low':
      return detail ? `💰 Budget ${detail}` : 'Budget too low';
    case 'hourly_top_too_low':
      return detail ? `⏱ ${detail}` : 'Hourly too low';
    case 'too_old':
      return detail ? `🕐 ${detail} old` : 'Too old';
    case 'avoid_keyword':
      return detail ? `🚫 "${detail.replace(/'/g, '')}"` : 'Blocked keyword';
    case 'score_cap_reached':
      return '🔢 Score cap';
    default:
      return detail || rule || 'filtered';
  }
}

/** Tailwind classes for a pre-filter chip. */
export function filterReasonChipClass(code?: string | null): string {
  const rule = (code ?? '').replace(/^pre_filter:/, '');
  if (rule === 'blocked_country') return 'bg-orange-100 text-orange-700';
  if (rule === 'budget_too_low' || rule === 'hourly_top_too_low') return 'bg-amber-100 text-amber-700';
  if (rule === 'avoid_keyword') return 'bg-red-100 text-red-600';
  // too_old, score_cap_reached
  return 'bg-gray-100 text-gray-500';
}
