/**
 * The client's total spend from the job page: the amount right before "total spent" ("$15K") in
 * the About the client section. Only that section is read: the job description is written by the
 * client, so a poster could put "$500K total spent" there to dress up their own trust card. No
 * section found means no data. (The old fallback matched the whole <html> element, so the card
 * showed an unrelated number, e.g. the 4.8 rating as "$5".)
 */
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

/** The About the client section: a tagged container, else the nearest ancestor of the
 *  "About the client" heading that holds a "total spent" line. Null when there is none. */
export function clientSection(doc: Document = document): Element | null {
  for (const selector of CLIENT_SECTION_SELECTORS) {
    const el = doc.querySelector(selector);
    if (el) return el;
  }
  const heading = Array.from(doc.querySelectorAll('h1, h2, h3, h4, h5, h6'))
    .find((h) => /^\s*about the client\s*$/i.test(h.textContent || ''));
  for (let node = heading?.parentElement ?? null; node && node !== doc.body; node = node.parentElement) {
    if (/total\s+spent/i.test(node.textContent || '')) return node;
  }
  return null;
}

export function clientTotalSpent(doc: Document = document): string | null {
  const section = clientSection(doc);
  return section ? totalSpentFromText((section as HTMLElement).innerText ?? section.textContent) : null;
}
