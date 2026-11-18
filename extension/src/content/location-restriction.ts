/**
 * Upwork's own location rule on a job page, e.g. "Only freelancers located in the U.S. may apply."
 * It sits in the job header, not the description, so the must-have check would never see it.
 * Found by its wording (the smallest element that says it), not by Upwork's classes.
 */
import { SELECTORS } from './upwork-selectors';

const RULE_RE = /Only freelancers located in .{1,120}? may apply\.?/i;
const MAX_ELEMENT_CHARS = 200;

const DESCRIPTION_SELECTORS = SELECTORS.jobDescription.join(', ');

/** The smallest element outside the job description that states the rule (a description that
 *  quotes some other country's rule must not win over the header's own line). */
export function locationRestriction(doc: Document = document): string | null {
  const descriptions = Array.from(doc.querySelectorAll(DESCRIPTION_SELECTORS));
  let best: { rule: string; size: number } | null = null;
  for (const el of Array.from(doc.querySelectorAll('span, p, div, li, small, strong'))) {
    const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (text.length > MAX_ELEMENT_CHARS) continue;
    const match = text.match(RULE_RE);
    if (!match || descriptions.some((d) => d.contains(el))) continue;
    if (!best || text.length < best.size) best = { rule: match[0], size: text.length };
  }
  return best?.rule ?? null;
}
