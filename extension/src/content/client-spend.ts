/**
 * The client's total spend from the job page: the amount right before "total spent" ("$15K").
 * Upwork shows it as "$15K total spent" in About the client. Never the first number on the page:
 * the old fallback matched the whole <html> element, so the trust card showed an unrelated
 * number (the client's 4.8 rating as "$5").
 */
const SPENT_RE = /(\$\s?\d[\d,]*(?:\.\d+)?\s*[KkMm]?\+?)\s*total\s+spent/i;

export function totalSpentFromText(text: string | null | undefined): string | null {
  const match = (text || '').match(SPENT_RE);
  return match ? match[1].replace(/\s+/g, '') : null;
}
