import { describe, expect, it } from 'vitest';
import fixture from './__fixtures__/submit-proposal.html?raw';
import { isSubmitButton, readSubmission } from './submit-capture';

function loadFixture(): Document {
  return new DOMParser().parseFromString(fixture, 'text/html');
}

function setValue(doc: Document, selector: string, index: number, value: string): void {
  const el = doc.querySelectorAll<HTMLTextAreaElement>(selector)[index];
  el.value = value;
}

describe('readSubmission', () => {
  it('reads the cover letter and every screening answer at submit time', () => {
    const doc = loadFixture();
    setValue(doc, 'textarea[aria-labelledby="cover_letter_label"]', 0, '  Zero downtime is the whole job here.\n\nWarm regards,\nChris  ');
    setValue(doc, '.questions-area textarea', 0, 'Yes — Framer Motion work for a fintech dashboard.');
    setValue(doc, '.questions-area textarea', 1, 'Mobile-first breakpoints, tested on real devices.');

    const result = readSubmission(doc);

    expect(result.coverLetter).toBe('Zero downtime is the whole job here.\n\nWarm regards,\nChris');
    expect(result.answers).toEqual([
      {
        question: 'Have you created or edited UI animations or micro-interactions before? If yes, please share examples or links to your work.',
        answer: 'Yes — Framer Motion work for a fintech dashboard.',
      },
      {
        question: 'When designing a responsive SaaS UI, how do you ensure the design works well across desktop, tablet, and mobile screens?',
        answer: 'Mobile-first breakpoints, tested on real devices.',
      },
    ]);
  });

  it('does not double-count question groups matched by more than one selector', () => {
    const doc = loadFixture();
    expect(readSubmission(doc).answers).toHaveLength(2);
  });

  it('returns null cover letter when the textarea is empty or missing', () => {
    const doc = loadFixture();
    expect(readSubmission(doc).coverLetter).toBeNull();
    doc.querySelector('.cover-letter-area')?.remove();
    expect(readSubmission(doc).coverLetter).toBeNull();
  });

  it('returns no answers on a job without screening questions', () => {
    const doc = loadFixture();
    doc.querySelector('.questions-area')?.remove();
    expect(readSubmission(doc).answers).toEqual([]);
  });
});

describe('isSubmitButton', () => {
  it('accepts the apply footer primary button and clicks on its children', () => {
    const doc = loadFixture();
    const send = doc.querySelector('.fe-apply-footer-controls .air3-btn-primary');
    expect(isSubmitButton(send)).toBe(true);
    const inner = doc.createElement('span');
    send?.appendChild(inner);
    expect(isSubmitButton(inner)).toBe(true);
  });

  it('accepts a legacy "Submit Proposal" button by its label', () => {
    const doc = loadFixture();
    expect(isSubmitButton(doc.querySelector('.legacy-submit span'))).toBe(true);
  });

  it('rejects Cancel, the nav search submit, non-buttons and null', () => {
    const doc = loadFixture();
    expect(isSubmitButton(doc.querySelector('.fe-apply-footer-controls .air3-btn-link'))).toBe(false);
    expect(isSubmitButton(doc.querySelector('nav button'))).toBe(false);
    expect(isSubmitButton(doc.querySelector('textarea'))).toBe(false);
    expect(isSubmitButton(null)).toBe(false);
  });
});
