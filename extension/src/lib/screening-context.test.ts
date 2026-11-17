import { describe, expect, it } from 'vitest';
import { currentAnswer, otherAnswers } from './screening-context';

const qs = [{ question: 'Payments?' }, { question: 'TypeScript, React and Postgres?' }, { question: 'Above and beyond?' }];

describe('screening answer context', () => {
  it('collects the other answers, sidebar first, then what is typed on Upwork', () => {
    expect(otherAnswers(qs, 1, { q2: 'Rebuilt a billing run overnight.' }, ['Integrated FIS and Stripe.', 'x', 'ignored'])).toEqual([
      { question: 'Payments?', answer: 'Integrated FIS and Stripe.', user_written: true },  // typed on Upwork
      { question: 'Above and beyond?', answer: 'Rebuilt a billing run overnight.', user_written: false },  // AI
    ]);
    expect(otherAnswers(qs, 1, { q2: 'Edited by me.' }, [], { q2: true })[0].user_written).toBe(true);
  });

  it('skips the question being answered and empty boxes', () => {
    expect(otherAnswers(qs, 0, { q0: 'mine' }, ['', '  ', ''])).toEqual([]);
  });

  it('revises the sidebar text, else the text in Upwork\'s box', () => {
    expect(currentAnswer(1, { q1: 'sidebar' }, ['', 'page'])).toBe('sidebar');
    expect(currentAnswer(1, {}, ['', 'page'])).toBe('page');
    expect(currentAnswer(1, {}, [])).toBe('');
  });
});
