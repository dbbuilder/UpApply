/**
 * Upwork's own location rule on a job page, e.g. "Only freelancers located in the U.S. may apply."
 * It sits in the job header, not the description, so the must-have check would never see it.
 * Found by its wording (the smallest element that says it), not by Upwork's classes.
 */
const RULE_RE = /Only freelancers located in .{1,120}? may apply\.?/i;
const MAX_ELEMENT_CHARS = 200;

export function locationRestriction(doc: Document = document): string | null {
  let best: string | null = null;
  for (const el of Array.from(doc.querySelectorAll('span, p, div, li, small, strong'))) {
    const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (text.length > MAX_ELEMENT_CHARS) continue;
    const match = text.match(RULE_RE);
    if (match && (!best || match[0].length <= best.length)) best = match[0];
  }
  return best;
}
