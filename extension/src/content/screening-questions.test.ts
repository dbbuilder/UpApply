import { beforeEach, describe, expect, it, vi } from 'vitest';
import { findScreeningQuestions, watchScreeningQuestions } from './screening-questions';

// Trimmed from a saved Upwork apply page (working/SubmitProposal.html, 2026-03)
const APPLY_PAGE = `
  <textarea rows="10" aria-labelledby="cover_letter_label" class="air3-textarea inner-textarea"></textarea>
  <div class="fe-proposal-job-questions questions-area">
    <div class="form-group mb-8x"><label id="" class="label">
      Have you created or edited UI animations or micro-interactions before? If yes, please share examples.
    </label><div class="air3-textarea textarea-wrapper p-0"><textarea rows="10" aria-labelledby="" class="air3-textarea inner-textarea"></textarea></div></div>
    <div class="form-group mb-8x"><label id="" class="label">
      When designing a responsive SaaS UI, how do you ensure the design works well across devices?
    </label><div class="air3-textarea textarea-wrapper p-0"><textarea rows="10" aria-labelledby="" class="air3-textarea inner-textarea"></textarea></div></div>
  </div>
  <div class="attachments-area mt-6x"><div class="form-group mb-8x"><label class="label">Attachments</label></div></div>`;

describe('screening questions on the apply page', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('reads Upwork question groups and tags each answer box', () => {
    document.body.innerHTML = APPLY_PAGE;
    const qs = findScreeningQuestions();
    expect(qs.map((q) => q.question)).toEqual([
      'Have you created or edited UI animations or micro-interactions before? If yes, please share examples.',
      'When designing a responsive SaaS UI, how do you ensure the design works well across devices?',
    ]);
    expect(qs.map((q) => q.inputSelector)).toEqual(['[data-upapply-q="0"]', '[data-upapply-q="1"]']);
    (document.querySelector(qs[1].inputSelector) as HTMLTextAreaElement).value = 'typed on Upwork';
    expect((document.querySelectorAll('textarea')[2] as HTMLTextAreaElement).value).toBe('typed on Upwork');
  });

  it('falls back to any non-cover-letter answer box when the classes change', () => {
    document.body.innerHTML = `
      <textarea aria-labelledby="cover_letter_label"></textarea>
      <fieldset><legend>What's your experience with TypeScript, React and Postgres?</legend><textarea></textarea></fieldset>
      <div class="milestones"><textarea></textarea></div>
      <textarea aria-label="Tell us about a time you went above and beyond."></textarea>`;
    expect(findScreeningQuestions().map((q) => q.question)).toEqual([
      "What's your experience with TypeScript, React and Postgres?",
      'Tell us about a time you went above and beyond.',
    ]);
  });

  it('a page with no questions has none', () => {
    document.body.innerHTML = '<textarea aria-labelledby="cover_letter_label"></textarea>';
    expect(findScreeningQuestions()).toEqual([]);
  });

  it('waits for the list to settle, so questions drawn in two steps are reported together', async () => {
    vi.useFakeTimers();
    const group = (q: string) => `<div class="form-group"><label>${q}</label><textarea></textarea></div>`;
    document.body.innerHTML = `<div class="fe-proposal-job-questions">${group('First?')}</div>`;
    const seen: string[][] = [];
    watchScreeningQuestions((qs) => seen.push(qs.map((q) => q.question)), 15_000, 800);
    document.querySelector('.fe-proposal-job-questions')!.insertAdjacentHTML('beforeend', group('Second?'));
    await vi.advanceTimersByTimeAsync(900);
    expect(seen).toEqual([['First?', 'Second?']]);
    vi.useRealTimers();
  });
});
