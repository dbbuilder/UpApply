import { describe, expect, it } from 'vitest';
import { USER_SKIP_REASONS, filterReasonChipClass, formatFilterReason, skipReasonLabel } from './skip-reasons';

describe('skip reasons', () => {
  it('offers the API codes as quick choices', () => {
    expect(USER_SKIP_REASONS.map((r) => r.code)).toEqual([
      'budget_too_low', 'wrong_skills', 'scope_unclear', 'too_large', 'client_risk',
      'too_many_proposals', 'timing', 'not_interested', 'duplicate', 'other',
    ]);
  });

  it('labels user skips, showing free text for other', () => {
    expect(skipReasonLabel('client_risk')).toBe('Client looks risky');
    expect(skipReasonLabel('other', 'On-site only')).toBe('On-site only');
    expect(skipReasonLabel('other')).toBe('Other');
    expect(skipReasonLabel(undefined)).toBe('');
  });

  it('formats pre-filter chips from code + detail', () => {
    expect(formatFilterReason('pre_filter:blocked_country', 'India')).toBe('📍 India');
    expect(formatFilterReason('pre_filter:too_old', '9d')).toBe('🕐 9d old');
    expect(formatFilterReason('pre_filter:avoid_keyword', "'wordpress'")).toBe('🚫 "wordpress"');
    expect(formatFilterReason('pre_filter:score_cap_reached', '40')).toBe('🔢 Score cap');
    expect(formatFilterReason('other', 'new_rule (x)')).toBe('new_rule (x)');
    expect(filterReasonChipClass('pre_filter:hourly_top_too_low')).toContain('amber');
  });
});
