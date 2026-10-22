import { describe, expect, it } from 'vitest';
import {
  COMPLETE_JOB_TEXT_MIN_CHARS, COMPLETE_LETTER_MIN_CHARS, DETAIL_DELAY_MAX_MS, DETAIL_DELAY_MIN_MS,
  THROTTLE_BACKOFF_MS, completeProposalIds, isProposalComplete, isThrottledRead,
  pickProposalStatus, randomDetailDelayMs, takeBatch, throttleBackoffMs,
} from './proposal-scrape';

describe('randomDetailDelayMs', () => {
  it('stays within the 6–10 s window', () => {
    expect(randomDetailDelayMs(() => 0)).toBe(DETAIL_DELAY_MIN_MS);
    expect(randomDetailDelayMs(() => 1)).toBe(DETAIL_DELAY_MAX_MS);
    expect(randomDetailDelayMs(() => 0.5)).toBe(8_000);
  });
});

describe('throttleBackoffMs', () => {
  it('follows the 30/60/120 s schedule without jitter at rand=0.5', () => {
    expect(THROTTLE_BACKOFF_MS.map((_, i) => throttleBackoffMs(i, () => 0.5))).toEqual([30_000, 60_000, 120_000]);
  });

  it('applies ±20% jitter', () => {
    expect(throttleBackoffMs(0, () => 0)).toBe(24_000);
    expect(throttleBackoffMs(0, () => 1)).toBe(36_000);
  });

  it('returns null once retries are exhausted', () => {
    expect(throttleBackoffMs(3)).toBeNull();
  });
});

describe('isThrottledRead', () => {
  it('treats a missing read or missing application as throttled', () => {
    expect(isThrottledRead(null)).toBe(true);
    expect(isThrottledRead(undefined)).toBe(true);
    expect(isThrottledRead({ hasApplication: false })).toBe(false); // missing NUXT data → DOM fallback, not throttled
  });

  it('treats the error toast as throttled even with an application', () => {
    expect(isThrottledRead({ hasApplication: true, hasErrorToast: true })).toBe(true);
  });

  it('an application without a cover letter is a real proposal, not throttled', () => {
    expect(isThrottledRead({ hasApplication: true, hasErrorToast: false })).toBe(false);
  });
});

describe('isProposalComplete / completeProposalIds', () => {
  const letter = 'x'.repeat(COMPLETE_LETTER_MIN_CHARS);
  const job = 'y'.repeat(COMPLETE_JOB_TEXT_MIN_CHARS);

  it('needs both a full letter and job text', () => {
    expect(isProposalComplete({ cover_letter_text: letter, job_text: job })).toBe(true);
    expect(isProposalComplete({ cover_letter_text: letter.slice(1), job_text: job })).toBe(false);
    expect(isProposalComplete({ cover_letter_text: letter, job_text: job.slice(1) })).toBe(false);
    expect(isProposalComplete({ cover_letter_text: letter, job_text: null })).toBe(false);
    expect(isProposalComplete({ cover_letter_text: ' '.repeat(400), job_text: job })).toBe(false);
  });

  it('collects ids of complete proposals only', () => {
    const ids = completeProposalIds([
      { upwork_proposal_id: 'a', cover_letter_text: letter, job_text: job },
      { upwork_proposal_id: 'b', cover_letter_text: '', job_text: job },
      { upwork_proposal_id: null, cover_letter_text: letter, job_text: job },
    ]);
    expect([...ids]).toEqual(['a']);
  });
});

describe('takeBatch', () => {
  it('waits for a full batch, then removes it', () => {
    const pending = [1, 2, 3];
    expect(takeBatch(pending, 4)).toBeNull();
    pending.push(4, 5);
    expect(takeBatch(pending, 4)).toEqual([1, 2, 3, 4]);
    expect(pending).toEqual([5]);
  });

  it('force drains whatever is left', () => {
    const pending = [5];
    expect(takeBatch(pending, 4, true)).toEqual([5]);
    expect(pending).toEqual([]);
    expect(takeBatch(pending, 4, true)).toBeNull();
  });
});

describe('pickProposalStatus', () => {
  it('keeps the list page outcome text over Upwork\'s numeric code', () => {
    expect(pickProposalStatus('interviewed', '8', false)).toBe('interviewed');
    expect(pickProposalStatus('Responded', '2', true)).toBe('responded');
  });

  it('marks archived rows archived when the list only says submitted', () => {
    expect(pickProposalStatus('submitted', '8', true)).toBe('archived');
  });

  it('keeps submitted for active rows instead of the numeric code', () => {
    expect(pickProposalStatus('submitted', '7', false)).toBe('submitted');
  });

  it('falls back to the numeric code only without list text', () => {
    expect(pickProposalStatus(null, '7', false)).toBe('7');
    expect(pickProposalStatus('', null, false)).toBe('submitted');
    expect(pickProposalStatus(undefined, '8', true)).toBe('archived');
  });
});
