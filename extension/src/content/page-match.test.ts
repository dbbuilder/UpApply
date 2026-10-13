import { describe, expect, it } from 'vitest';
import { isApplyPage, isProposalsListPage } from './page-match';

const path = (url: string) => new URL(url).pathname;

describe('isApplyPage', () => {
  it.each([
    'https://www.upwork.com/nx/proposals/job/~022029995898151908292/apply/',
    'https://www.upwork.com/nx/proposals/job/~022029995898151908292/apply',
    'https://www.upwork.com/nx/proposals/job/~01abc/apply/?referrer=x#top',
  ])('matches the real apply page %s', url => {
    expect(isApplyPage(path(url))).toBe(true);
  });

  it.each([
    'https://www.upwork.com/messages?next=/apply',
    'https://www.upwork.com/messages#/nx/proposals/job/~01abc/apply/',
    'https://www.upwork.com/nx/find-work/?q=/apply',
    'https://www.upwork.com/jobs/~01abc',
    'https://www.upwork.com/nx/proposals/job/~01abc/apply/extra',
    'https://www.upwork.com/evil/nx/proposals/job/~01abc/apply/',
    'https://www.upwork.com/nx/proposals/job/~01abc/applyx',
    'https://www.upwork.com/nx/proposals/job/01abc/apply/',
    'https://www.upwork.com/applying',
  ])('rejects %s', url => {
    expect(isApplyPage(path(url))).toBe(false);
  });
});

describe('isProposalsListPage', () => {
  it.each([
    'https://www.upwork.com/nx/proposals/',
    'https://www.upwork.com/nx/proposals',
    'https://www.upwork.com/nx/proposals/archived',
    'https://www.upwork.com/nx/proposals/archived/?page=2',
  ])('matches the Proposals list %s', url => {
    expect(isProposalsListPage(path(url))).toBe(true);
  });

  it.each([
    'https://www.upwork.com/messages?next=/nx/proposals/',
    'https://www.upwork.com/messages#/nx/proposals/',
    'https://www.upwork.com/nx/proposals/2010632891814129665',
    'https://www.upwork.com/nx/proposals/job/~01abc/apply/',
    'https://www.upwork.com/x/nx/proposals/',
    'https://www.upwork.com/nx/proposalsx',
  ])('rejects %s', url => {
    expect(isProposalsListPage(path(url))).toBe(false);
  });
});
