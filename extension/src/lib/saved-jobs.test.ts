import { describe, expect, it } from 'vitest';
import { parseDaysAgo, savedImportItems } from './saved-jobs';

const card = (n: number, posted: string | null) => ({
  upworkJobId: `0${n}`, upworkUrl: `https://www.upwork.com/jobs/~0${n}`, title: `Job ${n}`, description: 'd',
  postedDateRaw: posted,
});

describe('saved jobs import items', () => {
  it('parses Upwork posted strings', () => {
    expect(parseDaysAgo('Posted 6 hours ago')).toBe(0);
    expect(parseDaysAgo('Posted yesterday')).toBe(1);
    expect(parseDaysAgo('Posted 3 days ago')).toBe(3);
    expect(parseDaysAgo('Posted 3 weeks ago')).toBe(21);
    expect(parseDaysAgo('Posted 2 months ago')).toBe(999);
    expect(parseDaysAgo(null)).toBe(0);
  });

  it('keeps every saved job; only recent ones go to the Queue', () => {
    const items = savedImportItems([card(1, 'Posted 6 hours ago'), card(2, 'Posted 14 days ago'),
      card(3, 'Posted 3 weeks ago'), card(4, 'Posted 2 months ago'), card(5, null)]);
    expect(items.map((i) => [i.title, i.signal_only])).toEqual([
      ['Job 1', false], ['Job 2', false], ['Job 3', true], ['Job 4', true], ['Job 5', false],
    ]);
  });
});
