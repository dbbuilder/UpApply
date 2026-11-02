import { describe, expect, it } from 'vitest';
import { upworkApplyUrl } from './apply-url';

describe('upworkApplyUrl', () => {
  it('builds the proposal form URL from a job URL', () => {
    expect(upworkApplyUrl('https://www.upwork.com/jobs/~0123456789012345678'))
      .toBe('https://www.upwork.com/nx/proposals/job/~0123456789012345678/apply/');
  });

  it('handles slugged and trailing-slash job URLs', () => {
    expect(upworkApplyUrl('https://www.upwork.com/freelance-jobs/apply/React-Dev_~01abc123/'))
      .toBe('https://www.upwork.com/nx/proposals/job/~01abc123/apply/');
  });

  it('never appends /apply to the job URL', () => {
    expect(upworkApplyUrl('https://www.upwork.com/jobs/~0123/')).not.toContain('/jobs/~0123/apply');
  });

  it('keeps an apply URL as is', () => {
    const url = 'https://www.upwork.com/nx/proposals/job/~0123/apply/';
    expect(upworkApplyUrl(url)).toBe(url);
  });

  it('falls back to the given URL without a job id', () => {
    expect(upworkApplyUrl('https://www.upwork.com/nx/find-work/')).toBe('https://www.upwork.com/nx/find-work/');
  });
});
