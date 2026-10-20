// Pure helpers for the Proposals detail-page scraper (background IMPORT_PROPOSALS).
// No chrome.* calls here so they can be unit-tested.

/** Randomized pause between detail pages — Upwork throttles back-to-back loads (~18 pages at 1.5 s). */
export const DETAIL_DELAY_MIN_MS = 6_000;
export const DETAIL_DELAY_MAX_MS = 10_000;
/** Backoff before each retry of a throttled proposal; its length is the retry count. */
export const THROTTLE_BACKOFF_MS = [30_000, 60_000, 120_000];
/** ± fraction of jitter applied to each backoff wait. */
export const THROTTLE_JITTER = 0.2;
/** Stop the run after this many proposals in a row stay throttled after all retries. */
export const MAX_CONSECUTIVE_THROTTLED = 3;
/** Scraped proposals are saved to the API every this many results. */
export const SAVE_BATCH_SIZE = 10;
/** A stored proposal is complete (skipped on re-runs) at or above both lengths. */
export const COMPLETE_LETTER_MIN_CHARS = 300;
export const COMPLETE_JOB_TEXT_MIN_CHARS = 200;
/** Text Upwork shows (stacked toasts) when it is rate-limiting detail pages. */
export const THROTTLE_PAGE_TEXT = 'There was an error loading this page';

export function randomDetailDelayMs(rand: () => number = Math.random): number {
  return Math.round(DETAIL_DELAY_MIN_MS + rand() * (DETAIL_DELAY_MAX_MS - DETAIL_DELAY_MIN_MS));
}

/** Wait before retry number `retry` (0-based), with jitter; null when retries are exhausted. */
export function throttleBackoffMs(retry: number, rand: () => number = Math.random): number | null {
  const base = THROTTLE_BACKOFF_MS[retry];
  if (base === undefined) return null;
  return Math.round(base * (1 + (rand() * 2 - 1) * THROTTLE_JITTER));
}

export interface DetailRead {
  /** proposalDetailsV3Response.application was present in __NUXT__. */
  hasApplication: boolean;
  /** Page text contains THROTTLE_PAGE_TEXT (checked in the page's main world). */
  hasErrorToast?: boolean;
}

/**
 * A detail page is throttled when Upwork's error toast is showing or the NUXT state has no
 * application. An application with an empty cover letter is a real (letter-less) proposal.
 * A null read (executeScript failed) counts as throttled.
 */
export function isThrottledRead(read: DetailRead | null | undefined): boolean {
  if (!read) return true;
  if (read.hasErrorToast) return true;
  return !read.hasApplication;
}

export interface StoredProposalLike {
  upwork_proposal_id?: string | null;
  cover_letter_text?: string | null;
  job_text?: string | null;
}

export function isProposalComplete(p: StoredProposalLike): boolean {
  return (p.cover_letter_text ?? '').trim().length >= COMPLETE_LETTER_MIN_CHARS
    && (p.job_text ?? '').trim().length >= COMPLETE_JOB_TEXT_MIN_CHARS;
}

/** Upwork proposal ids already stored with a full letter and job text. */
export function completeProposalIds(stored: StoredProposalLike[]): Set<string> {
  const ids = new Set<string>();
  for (const p of stored) {
    if (p.upwork_proposal_id && isProposalComplete(p)) ids.add(p.upwork_proposal_id);
  }
  return ids;
}

/**
 * Removes and returns the next batch from `pending` once it holds `size` items
 * (or anything at all when `force`), else null.
 */
export function takeBatch<T>(pending: T[], size: number, force = false): T[] | null {
  if (pending.length === 0) return null;
  if (!force && pending.length < size) return null;
  return pending.splice(0, force ? pending.length : size);
}
