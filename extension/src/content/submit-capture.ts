/**
 * Pure field readers for capturing what was actually submitted on Upwork's
 * apply page (spec §3.2). No chrome.* or network access — wiring lives in index.ts.
 */
import { SELECTORS } from './upwork-selectors';

export interface SubmittedAnswer {
  question: string;
  answer: string;
}

export interface CapturedSubmission {
  coverLetter: string | null;
  answers: SubmittedAnswer[];
}

const SUBMIT_LABEL = /^(send for \d+ connects?|submit( a)? proposal)$/i;

function firstMatch(root: ParentNode, selectors: readonly string[]): Element | null {
  for (const selector of selectors) {
    if (selector.includes(':has-text')) continue;
    try {
      const el = root.querySelector(selector);
      if (el) return el;
    } catch {
      // invalid selector — try the next one
    }
  }
  return null;
}

function fieldValue(el: Element | null): string {
  if (!el) return '';
  const tag = el.tagName.toLowerCase();
  if (tag !== 'textarea' && tag !== 'input') return '';
  return (el as HTMLTextAreaElement | HTMLInputElement).value.trim();
}

function collapse(text: string | null | undefined): string {
  return (text ?? '').replace(/\s+/g, ' ').trim();
}

/** Read the cover letter and every screening answer from the apply form. */
export function readSubmission(doc: Document): CapturedSubmission {
  const coverLetter = fieldValue(firstMatch(doc, SELECTORS.coverLetterTextarea)) || null;

  const answers: SubmittedAnswer[] = [];
  // One combined selector list → each question group appears once even when it
  // carries both .fe-proposal-job-questions and .questions-area.
  doc.querySelectorAll(SELECTORS.screeningQuestions.join(', ')).forEach((group) => {
    const question = collapse(firstMatch(group, SELECTORS.screeningQuestionLabel)?.textContent);
    if (!question) return;
    answers.push({ question, answer: fieldValue(firstMatch(group, SELECTORS.screeningQuestionInput)) });
  });

  return { coverLetter, answers };
}

/** True when a click target is (inside) the proposal Submit / "Send for N Connects" button. */
export function isSubmitButton(target: Element | null): boolean {
  const button = target?.closest('button');
  if (!button) return false;
  if (button.closest('.fe-apply-footer-controls') && button.classList.contains('air3-btn-primary')) {
    return true;
  }
  return SUBMIT_LABEL.test(collapse(button.textContent));
}
