import type { ScreeningQuestion } from '../types';

/**
 * Screening questions on Upwork's apply page (/nx/proposals/job/~<id>/apply/). They exist only
 * there, never on the job page, so the apply page has to be read for them. Each answer box is
 * tagged data-upapply-q="<n>" and addressed by that tag, so filling and reading stay stable even
 * when Upwork's classes change.
 */
const GROUPS = '.fe-proposal-job-questions .form-group, .questions-area .form-group';
const COVER_LETTER = 'textarea[aria-labelledby="cover_letter_label"], #cover_letter';
const clean = (s: string | null | undefined) => (s || '').replace(/\s+/g, ' ').trim();

function questionFor(input: Element): string {
  const group = input.closest('.form-group, fieldset, [class*="question"]');
  const label = group?.querySelector('label, legend');
  if (label && clean(label.textContent)) return clean(label.textContent);
  const labelledBy = input.getAttribute('aria-labelledby');
  const byId = labelledBy ? input.ownerDocument.getElementById(labelledBy) : null;
  return clean(byId?.textContent) || clean(input.getAttribute('aria-label'));
}

export function findScreeningQuestions(doc: Document = document): ScreeningQuestion[] {
  // Upwork's question groups (seen 2026-03), else any answer box that is not the cover letter
  let inputs: Element[] = Array.from(doc.querySelectorAll(GROUPS))
    .map((g) => g.querySelector('textarea, input[type="text"]'))
    .filter((el): el is Element => !!el);
  if (!inputs.length) {
    const cover = new Set(Array.from(doc.querySelectorAll(COVER_LETTER)));
    inputs = Array.from(doc.querySelectorAll('textarea')).filter(
      (t) => !cover.has(t) && !t.closest('.attachments-area, [class*="milestone"]'),
    );
  }
  const questions: ScreeningQuestion[] = [];
  inputs.forEach((input) => {
    const question = questionFor(input);
    if (!question || /^cover letter$/i.test(question)) return;
    const n = String(questions.length);
    input.setAttribute('data-upapply-q', n);
    questions.push({ question, inputSelector: `[data-upapply-q="${n}"]` });
  });
  return questions;
}

/** On the apply page, report the questions once they render (Upwork draws them late), for up to
 *  `timeoutMs`. Calls `report` with the questions found, or [] when there are none. */
export function watchScreeningQuestions(report: (q: ScreeningQuestion[]) => void, timeoutMs = 15_000): () => void {
  let done = false;
  const finish = (q: ScreeningQuestion[]) => {
    if (done) return;
    done = true;
    observer.disconnect();
    clearTimeout(timer);
    report(q);
  };
  const observer = new MutationObserver(() => {
    const q = findScreeningQuestions();
    if (q.length) finish(q);
  });
  const timer = setTimeout(() => finish(findScreeningQuestions()), timeoutMs);
  const now = findScreeningQuestions();
  if (now.length) {
    finish(now);
  } else {
    observer.observe(document.body, { childList: true, subtree: true });
  }
  return () => finish([]);
}
