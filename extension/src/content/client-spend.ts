/**
 * The client's total spend from the job page: the amount right before "total spent" ("$15K") in
 * the About the client section. Only that section is read: the job description is written by the
 * client, so a poster could put "$500K total spent" there to dress up their own trust card. No
 * section found means no data. (The old fallback matched the whole <html> element, so the card
 * showed an unrelated number, e.g. the 4.8 rating as "$5".)
 */
import { SELECTORS } from './upwork-selectors';

const SPENT_RE = /(\$\s?\d[\d,]*(?:\.\d+)?\s*[KkMm]?\+?)\s*total\s+spent/gi;

/** The last "$N total spent" amount in `text` (the client section lists its own spend once). */
export function totalSpentFromText(text: string | null | undefined): string | null {
  const matches = [...(text || '').matchAll(SPENT_RE)];
  const last = matches[matches.length - 1];
  return last ? last[1].replace(/\s+/g, '') : null;
}

const CLIENT_SECTION_SELECTORS = [
  '[data-test="about-client-container"]',
  '[data-test="AboutClientUser"]',
  '[data-test="client-info"]',
];

const DESCRIPTION_SELECTORS = SELECTORS.jobDescription.join(', ');
const MAX_SECTION_CHARS = 4000;  // the client panel is short; a page-sized block is not it

/** The About the client section: a tagged container, else the widest ancestor of the
 *  "About the client" heading that still excludes the job description (its boundary is found
 *  without looking for spend text, so an empty client panel never reaches the description).
 *  Null when there is no heading. */
export function clientSection(doc: Document = document): Element | null {
  for (const selector of CLIENT_SECTION_SELECTORS) {
    const el = doc.querySelector(selector);
    if (el) return el;
  }
  const heading = Array.from(doc.querySelectorAll('h1, h2, h3, h4, h5, h6'))
    .find((h) => /^\s*about the client\s*$/i.test(h.textContent || ''));
  if (!heading?.parentElement) return null;
  const descriptions = Array.from(doc.querySelectorAll(DESCRIPTION_SELECTORS));
  let node: Element = heading.parentElement;
  for (let up = node.parentElement; up && up !== doc.body && up !== doc.documentElement; up = up.parentElement) {
    if (descriptions.some((d) => up!.contains(d)) || (up.textContent || '').length > MAX_SECTION_CHARS) break;
    node = up;
  }
  return node;
}

export function clientTotalSpent(doc: Document = document): string | null {
  const section = clientSection(doc);
  return section ? totalSpentFromText((section as HTMLElement).innerText ?? section.textContent) : null;
}
