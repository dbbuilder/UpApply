import { parsePostedAt, parseTileText } from './job-gather';

/** What a job card showed when it was scored, kept for the Find tab (display and filters). */
export interface JobDetails {
  posted_at?: string;
  posted_text?: string;
  client_country?: string;
  client_spent?: string;
  client_rating?: string;
  payment_verified?: boolean;
  proposals?: string;
  experience_level?: string;
}

export interface CardFacts {
  budgetAmount: string | null;
  budgetType: 'hourly' | 'fixed' | null;
  details: JobDetails;
}

const text = (el: Element | null | undefined) => (el?.textContent || '').replace(/\s+/g, ' ').trim();

/** Read a job card (search, saved or best-matches tile). Anything not on the card is left out. */
export function cardFacts(row: Element, now: Date = new Date()): CardFacts {
  const raw = (row as HTMLElement).innerText || row.textContent || '';
  const tile = parseTileText(raw);
  const postedText = text(row.querySelector('[data-test="job-pubilshed-date"]')) || tile.postedText || '';
  const posted = parsePostedAt(postedText, now);
  const country = text(row.querySelector('[data-test="location"], [data-test="client-country"]'))
    .replace(/^location\s*/i, '');
  const spent = text(row.querySelector('[data-test="total-spent"]')).match(/\$[\d.,]+\s*[KkMm]?\+?/);
  const rating = text(row.querySelector('[data-test="total-feedback"]')).match(/\d(?:\.\d+)?/);
  const level = text(row.querySelector('[data-test="experience-level"]'))
    || (raw.match(/\b(Entry level|Intermediate|Expert)\b/i)?.[1] ?? '');
  const details: JobDetails = {};
  if (posted) details.posted_at = posted.toISOString();
  if (postedText) details.posted_text = postedText.slice(0, 60);
  if (country) details.client_country = country.slice(0, 80);
  if (spent) details.client_spent = spent[0].replace(/\s+/g, '');
  if (rating) details.client_rating = rating[0];
  if (/payment (method )?verified/i.test(raw)) details.payment_verified = !/payment (method )?unverified/i.test(raw);
  if (tile.proposalsText) details.proposals = tile.proposalsText.slice(0, 40);
  if (level) details.experience_level = level.slice(0, 40);
  return { budgetAmount: tile.budgetAmount, budgetType: tile.budgetType, details };
}

/** Dollar figures in a budget ("$80.00-$120.00" -> [80, 120]). */
export function payValues(amount: string | null | undefined): number[] {
  return [...(amount || '').matchAll(/\$\s*(\d[\d,]*(?:\.\d+)?)\s*([KkMm])?/g)].map(([, n, s]) =>
    parseFloat(n.replace(/,/g, '')) * (s ? ({ k: 1e3, m: 1e6 } as Record<string, number>)[s.toLowerCase()] : 1));
}

// ── Find tab filters ───────────────────────────────────────────────────────

export type PostedFilter = 'any' | '1' | '3' | '7' | '14';
export type PayFilter = 'any' | 'h60' | 'h80' | 'h100' | 'f1000' | 'f5000' | 'f10000';

export const PAY_LABELS: Record<PayFilter, string> = {
  any: 'Any pay', h60: 'Hourly ≥ $60', h80: 'Hourly ≥ $80', h100: 'Hourly ≥ $100',
  f1000: 'Fixed ≥ $1K', f5000: 'Fixed ≥ $5K', f10000: 'Fixed ≥ $10K',
};
export const POSTED_LABELS: Record<PostedFilter, string> = {
  any: 'Any date', '1': 'Last 24 hours', '3': 'Last 3 days', '7': 'Last 7 days', '14': 'Last 14 days',
};

export interface FilterableJob {
  budget_amount?: string | null;
  budget_type?: string | null;
  details?: JobDetails | null;
}

/** Posted within N days. A job with no posted time is left out while a date filter is on. */
export function postedWithin(job: FilterableJob, filter: PostedFilter, now: Date = new Date()): boolean {
  if (filter === 'any') return true;
  const at = job.details?.posted_at ? Date.parse(job.details.posted_at) : NaN;
  return Number.isFinite(at) && now.getTime() - at <= Number(filter) * 86_400_000;
}

/** Hourly: the top of the range meets the floor. Fixed: the amount does. Unknown pay is left out. */
export function payMatches(job: FilterableJob, filter: PayFilter): boolean {
  if (filter === 'any') return true;
  const values = payValues(job.budget_amount);
  if (!values.length) return false;
  const floor = Number(filter.slice(1));
  return filter.startsWith('h')
    ? job.budget_type === 'hourly' && Math.max(...values) >= floor
    : job.budget_type === 'fixed' && Math.max(...values) >= floor;
}

export function countryMatches(job: FilterableJob, country: string): boolean {
  return !country || job.details?.client_country === country;
}

/** "Posted 3 hours ago" style label from the stored time, else the card's own text. */
export function postedLabel(details: JobDetails | null | undefined, now: Date = new Date()): string | null {
  const at = details?.posted_at ? Date.parse(details.posted_at) : NaN;
  if (!Number.isFinite(at)) return details?.posted_text ?? null;
  const hours = Math.max(0, (now.getTime() - at) / 3_600_000);
  if (hours < 1) return 'Posted < 1h ago';
  if (hours < 24) return `Posted ${Math.floor(hours)}h ago`;
  return `Posted ${Math.floor(hours / 24)}d ago`;
}
