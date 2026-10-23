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
/** Chrome can end one request after ~5 min; each import run stops by this point and the sidebar starts the next chunk. */
export const RUN_BUDGET_MS = 240_000;
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
 * A detail page is throttled only when Upwork's error toast is showing, or the read could not
 * run at all (null). Missing __NUXT__ proposal data is NOT throttling: Upwork's page state
 * shape changes, and the caller falls back to reading the rendered page.
 */
export function isThrottledRead(read: DetailRead | null | undefined): boolean {
  if (!read) return true;
  return !!read.hasErrorToast;
}

/** List pages are read once per import; later chunks reuse them for this long. */
export const LIST_CACHE_TTL_MS = 60 * 60_000;

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

// ── Nuxt 3 payload (__NUXT_DATA__) ───────────────────────────────────────────
// Upwork's proposal pages moved from window.__NUXT__ (Nuxt 2) to a serialized
// <script id="__NUXT_DATA__"> payload: a flat array where object and array members
// are indices into the same array, and wrappers look like ["ShallowReactive", i].

const NUXT_WRAPPERS = new Set(['Reactive', 'ShallowReactive', 'Ref', 'ShallowRef', 'EmptyRef', 'EmptyShallowRef']);
const NUXT_SCALARS = new Set(['Date', 'RegExp', 'BigInt', 'URL']);

/** Rebuilds the value graph of a Nuxt 3 payload array (index 0 is the root). */
export function reviveNuxtPayload(arr: unknown[]): unknown {
  const memo = new Map<number, unknown>();
  const revive = (i: unknown): unknown => {
    if (typeof i !== 'number' || !Number.isInteger(i) || i < 0 || i >= arr.length) return null;
    if (memo.has(i)) return memo.get(i);
    const v = arr[i];
    if (Array.isArray(v)) {
      if (typeof v[0] === 'string' && NUXT_WRAPPERS.has(v[0])) {
        const out = v.length > 1 ? revive(v[1]) : null;
        memo.set(i, out);
        return out;
      }
      if (typeof v[0] === 'string' && NUXT_SCALARS.has(v[0])) {
        memo.set(i, v[1]);
        return v[1];
      }
      const out: unknown[] = [];
      memo.set(i, out);
      for (const x of v) out.push(revive(x));
      return out;
    }
    if (v && typeof v === 'object') {
      const out: Record<string, unknown> = {};
      memo.set(i, out);
      for (const [k, x] of Object.entries(v as Record<string, unknown>)) out[k] = revive(x);
      return out;
    }
    memo.set(i, v);
    return v;
  };
  return revive(0);
}

export interface ProposalFields {
  hasApplication: boolean;
  coverLetter: string | null;
  status: string | null;
  bidAmount: string | null;
  jobTitle: string | null;
  answers: { question: string; answer: string }[];
  jobDescription: string | null;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
/** Fields from a proposalDetailsV3Response object (same shape in Nuxt 2 and Nuxt 3 pages). */
export function proposalFieldsFromV3(v3: any): ProposalFields {
  const app = v3?.application;
  const qa: any[] = Array.isArray(app?.questionsAnswers) ? app.questionsAnswers : [];
  return {
    hasApplication: !!app,
    coverLetter: (typeof app?.coverLetter === 'string' && app.coverLetter) || null,
    status: app?.status != null ? String(app.status) : null,
    bidAmount: String(app?.terms?.chargeRate?.amount ?? '') || null,
    jobTitle: v3?.jobDetails?.opening?.job?.info?.title || null,
    answers: qa
      .map(x => ({ question: String(x?.question ?? ''), answer: String(x?.answer ?? '') }))
      .filter(x => x.answer.trim().length > 0),
    jobDescription: (typeof v3?.jobDetails?.opening?.job?.description === 'string' && v3.jobDetails.opening.job.description) || null,
  };
}

/** Proposal fields from the raw __NUXT_DATA__ text, or null when it holds no proposal. */
export function proposalFromNuxtData(raw: string | null | undefined): ProposalFields | null {
  if (!raw) return null;
  let root: any;
  try { root = reviveNuxtPayload(JSON.parse(raw)); } catch { return null; }
  const store = root?.vuex?.['proposal-details'] ?? root?.state?.['proposal-details'];
  const v3 = store?.proposalDetailsV3Response;
  return v3 ? proposalFieldsFromV3(v3) : null;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/**
 * Status to store for a scraped proposal. The list page's text is human-readable and carries
 * real outcome signals ("responded", "interviewed"); Upwork's detail-page status is an opaque
 * numeric code the API cannot map, so it is only a last resort. "submitted" is the list's
 * default, so an archived row says "archived" instead.
 */
export function pickProposalStatus(
  listStatus: string | null | undefined,
  detailStatus: string | null | undefined,
  archived: boolean,
): string {
  const list = (listStatus ?? '').trim().toLowerCase();
  if (list && list !== 'submitted') return list;
  if (archived) return 'archived';
  if (list) return list;
  return (detailStatus ?? '').trim() || 'submitted';
}
