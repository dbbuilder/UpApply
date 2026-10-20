/**
 * Proposal scrapers — list page + detail page.
 */

import type { ScrapedProposal } from '../../types';
import { logger } from '../../lib/logger';

/**
 * Extract proposals from the My Proposals page.
 */
export function extractProposals(): ScrapedProposal[] {
  const proposals: ScrapedProposal[] = [];
  const seen = new Set<string>();

  // Strategy: anchor off proposal list row links.
  // On /nx/proposals/ the links use data-ev-label="jpn_list_details_link" and
  // href="/nx/proposals/{numericId}". Status comes from the <tr>'s data-ev-sublocation.
  // Fallback: any <a href*="/nx/proposals/"> that links to a numeric proposal ID.
  const proposalLinks = Array.from(
    document.querySelectorAll<HTMLAnchorElement>(
      'a[data-ev-label="jpn_list_details_link"], a[href*="/nx/proposals/"]:not([href$="/nx/proposals/"])'
    )
  );
  logger.log('UpApply: Found', proposalLinks.length, 'proposal links');

  for (const link of proposalLinks) {
    const href = link.getAttribute('href') || '';
    const proposalUrl = new URL(href, window.location.origin).href;
    // Extract numeric proposal ID from /nx/proposals/{numericId}
    const proposalIdMatch = proposalUrl.match(/\/nx\/proposals\/(\d+)/);
    const proposalId = proposalIdMatch?.[1] || null;
    if (!proposalId || seen.has(proposalId)) continue;
    seen.add(proposalId);

    const jobTitle = link.textContent?.trim() || link.getAttribute('aria-label')?.replace(/ Boosted$/, '').trim() || null;
    if (!jobTitle) continue;

    // The <tr> contains data-ev-sublocation indicating which section this is in
    const row = link.closest('tr');
    const sublocation = row?.getAttribute('data-ev-sublocation') || '';
    let status = 'submitted';
    if (sublocation === 'active_candidacies') status = 'responded';
    else if (sublocation === 'interviews') status = 'interviewed';

    // Date is in <td data-cy="time-slot">
    let submittedAt: string | null = null;
    const timeSlot = row?.querySelector('td[data-cy="time-slot"]');
    if (timeSlot) {
      // Text like "Initiated\nMar 3, 2026" or "Received\nFeb 28, 2026"
      const rawText = timeSlot.textContent?.trim() || '';
      const dateMatch = rawText.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+\d{4}/);
      if (dateMatch) submittedAt = dateMatch[0];
    }

    proposals.push({
      proposalId,
      jobTitle,
      jobUrl: proposalUrl, // best available — proposal detail URL
      coverLetter: null,   // not visible on list page
      bidAmount: null,     // not visible on list page
      bidType: null,
      status,
      submittedAt,
    });
  }

  logger.log('UpApply: Extracted', proposals.length, 'proposals');
  return proposals;
}

// window-level key for the shared scraping promise (shared across all
// instances of this content script injected into the same tab).
export const SCRAPE_KEY = '__upapplyScrapingPromise';

/**
 * Wait for the next-page button to become enabled (not disabled).
 * The button is briefly disabled during page transitions.
 */
export function waitForNextButton(timeoutMs = 2000): Promise<HTMLButtonElement | null> {
  // The proposals page has multiple sections, each with its own next-page button:
  //   - invitations/offers section MAY appear above proposals
  //   - proposals section (what we want to paginate)
  //   - interviews section MAY appear below proposals
  // Strategy: find the last proposal link with a NUMERIC proposal ID (excludes
  // interview/uid/ links below and offer links above), then return the first
  // next-page button that comes after it in document order — that's the proposals btn.
  const findNext = (): HTMLButtonElement | null => {
    const allNextBtns = document.querySelectorAll<HTMLButtonElement>(
      'button[data-test="next-page"], button[aria-label="Next page"]'
    );
    if (allNextBtns.length === 0) return null;
    if (allNextBtns.length === 1) return allNextBtns[0];

    // Find the last link that points to a numeric proposal ID (not interview/uid/)
    const proposalLinks = Array.from(
      document.querySelectorAll<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]')
    ).filter(a => /\/nx\/proposals\/\d+/.test(a.href));
    const lastProposalLink = proposalLinks[proposalLinks.length - 1];
    if (lastProposalLink) {
      for (const btn of allNextBtns) {
        if (lastProposalLink.compareDocumentPosition(btn) & Node.DOCUMENT_POSITION_FOLLOWING) {
          return btn;
        }
      }
    }
    return allNextBtns[0]; // fallback: first button (document order)
  };
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      const btn = findNext();
      if (!btn) { resolve(null); return; }
      if (!btn.disabled) { resolve(btn); return; }
      if (Date.now() >= deadline) { resolve(null); return; }
      setTimeout(check, 100);
    };
    setTimeout(check, 100);
  });
}

/**
 * Wait for proposal pagination to advance to targetPage.
 * Primary signal: active page button's data-ev-page_index matches targetPage (works in background tabs).
 * Fallback: first proposal link href changes.
 * Returns true if page actually changed, false if timeout (click didn't work).
 */
export function waitForProposalPageChange(previousFirstHref: string | null, targetPage: number, timeoutMs = 15000): Promise<boolean> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      // Primary: first PROPOSAL link href changed (numeric ID only — excludes interview links
      // below proposals section whose pagination we must not accidentally trigger).
      const proposalLinks = Array.from(
        document.querySelectorAll<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]')
      ).filter(a => /\/nx\/proposals\/\d+/.test(a.href));
      const firstProposalHref = proposalLinks[0]?.getAttribute('href') || null;
      if (firstProposalHref && firstProposalHref !== previousFirstHref) { resolve(true); return; }

      // Fallback: active pagination button in proposals section shows target page.
      // Use the FIRST active pagination button (proposals section comes before interviews).
      const activeBtns = document.querySelectorAll<HTMLElement>('.air3-pagination-nr-btn.is-active');
      const activeBtn = activeBtns[0];
      const activePage = parseInt(activeBtn?.getAttribute('data-ev-page_index') || '0', 10);
      if (activePage === targetPage) { resolve(true); return; }

      if (Date.now() >= deadline) { resolve(false); return; } // timed out — click didn't work
      setTimeout(check, 200);
    };
    // Initial delay after click — Vue needs time to process the click before DOM updates
    // Background tabs have rAF throttled to ~1fps, so the first meaningful update
    // may not appear for 1–2s after the click.
    setTimeout(check, 1000);
  });
}

/**
 * Extract proposals across all pagination pages by clicking "next page"
 * until the last page is reached. Uses a lock to prevent concurrent runs
 * when multiple content script instances are active.
 */
export async function extractAllProposals(): Promise<ScrapedProposal[]> {
  const win = window as unknown as Record<string, unknown>;

  // If another instance already started scraping, share its result
  if (win[SCRAPE_KEY]) {
    logger.log('UpApply: Joining existing scrape in progress');
    return win[SCRAPE_KEY] as Promise<ScrapedProposal[]>;
  }

  // Become the leader — store the promise so other instances join it
  const scrapePromise = (async (): Promise<ScrapedProposal[]> => {
    // data-ev-max_page_count may not exist on proposals pages — treat as optional hint only.
    // We paginate by clicking "next" until no next button exists (safer than trusting totalPages).
    const paginationDiv = document.querySelector('[data-ev-max_page_count]');
    const totalPages = paginationDiv
      ? parseInt(paginationDiv.getAttribute('data-ev-max_page_count') || '1', 10)
      : null;

    logger.log('UpApply: Proposals pagination — total pages:', totalPages ?? 'unknown (will paginate until no next button)');

    const all: ScrapedProposal[] = [];
    const seenIds = new Set<string>();

    const addPage = (page: ScrapedProposal[]) => {
      for (const p of page) {
        if (p.proposalId && !seenIds.has(p.proposalId)) {
          seenIds.add(p.proposalId);
          all.push(p);
        }
      }
    };

    // Cap list scraping at 150 proposals — background visits at most 150 detail pages,
    // so there is no value collecting more IDs than that. This prevents the archived
    // list (800+ proposals = 50+ pages) from running 100s+ and hitting the 120s timeout.
    const MAX_LIST_PROPOSALS = 150;

    // Wait for at least one proposal link to appear (Vue may still be rendering,
    // especially on /archived which takes longer to hydrate than the active tab).
    await new Promise<void>((resolve) => {
      const deadline = Date.now() + 8000;
      const check = () => {
        const hasLink = Array.from(
          document.querySelectorAll<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]')
        ).some(a => /\/nx\/proposals\/\d+/.test(a.href));
        if (hasLink || Date.now() >= deadline) resolve();
        else setTimeout(check, 200);
      };
      setTimeout(check, 200);
    });

    // Page 1 is now loaded
    chrome.storage.local.set({ proposalListProgress: { page: 1, totalPages } });
    addPage(extractProposals());

    // Paginate until no next button — don't rely on totalPages being accurate
    let pageNum = 2;
    while (totalPages === null || pageNum <= totalPages) {
      if (all.length >= MAX_LIST_PROPOSALS) {
        logger.log(`UpApply: Reached ${MAX_LIST_PROPOSALS}-proposal cap — stopping list pagination`);
        break;
      }
      // Capture the first PROPOSAL link href (numeric ID — excludes interview/uid/ links)
      const firstProposalLink = Array.from(
        document.querySelectorAll<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]')
      ).find(a => /\/nx\/proposals\/\d+/.test(a.href));
      const previousFirstHref = firstProposalLink?.getAttribute('href') || null;

      // Wait for next button to be enabled (it's briefly disabled during transitions)
      const nextBtn = await waitForNextButton();
      if (!nextBtn) {
        logger.log('UpApply: No enabled next button found at page', pageNum - 1, '— stopping');
        break;
      }

      logger.log('UpApply: Clicking to page', pageNum, totalPages ? `of ${totalPages}` : '(unknown total)');
      chrome.storage.local.set({ proposalListProgress: { page: pageNum, totalPages } });
      nextBtn.click();

      // Wait for page indicator to update (primary) or first link href to change (fallback).
      // Returns false if the click didn't trigger navigation (background tab click issue).
      const changed = await waitForProposalPageChange(previousFirstHref, pageNum);
      if (!changed) {
        logger.log('UpApply: Page did not advance to', pageNum, '— stopping pagination');
        break;
      }

      addPage(extractProposals());
      pageNum++;
    }

    logger.log('UpApply: Total proposals across all pages:', all.length);
    return all;
  })();

  win[SCRAPE_KEY] = scrapePromise;
  try {
    return await scrapePromise;
  } finally {
    delete win[SCRAPE_KEY];
  }
}

export interface ProposalDetail {
  coverLetter: string | null;
  answers: { question: string; answer: string }[];
}

const PROPOSAL_DETAILS = '[data-test="proposal-details"]';
const NOT_DESCRIPTION = 'h1, h2, h3, h4, [data-cy="cover-letter-section"], [data-test="terms-review"]';

/** Clicks the "more" toggles inside the proposal's job details so the full description renders. */
export function expandJobDescription(doc: Document = document): number {
  const root = doc.querySelector(PROPOSAL_DETAILS);
  if (!root) return 0;
  let clicked = 0;
  root.querySelectorAll<HTMLElement>('button, a, [role="button"]').forEach(el => {
    // Visible label only: Upwork's toggle also carries an sr-only "More/Less about …" span.
    const label = (el.querySelector('span:not(.sr-only)')?.textContent ?? el.textContent ?? '').trim().toLowerCase();
    const isToggle = el.matches('.air3-truncation-btn, [data-ev-label="truncation_toggle"]') || label === 'more';
    if (isToggle && label.startsWith('more')) { el.click(); clicked++; }
  });
  return clicked;
}

/**
 * The client's job description from a proposal details page: the longest text block inside
 * the job details that holds no heading, terms or cover letter. Upwork no longer exposes
 * window.__NUXT__ here, so the rendered page is the source.
 */
export function readJobDescription(doc: Document = document): string | null {
  const root = doc.querySelector(PROPOSAL_DETAILS);
  if (!root) return null;
  // Current markup: .fe-job-details .description > .air3-truncation (text span + "more" button
  // whose sr-only label repeats the title). Read the text without the toggle.
  const desc = root.querySelector<HTMLElement>('.description');
  if (desc) {
    const clone = desc.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('.air3-truncation-labels, button, .sr-only').forEach(el => el.remove());
    const text = (clone.textContent || '').replace(/\s*…\s*$/, '').trim();
    if (text.length >= 80) return text;
  }
  // Fallback for other markup: the longest text block that holds no heading, terms or letter.
  let best = '';
  root.querySelectorAll<HTMLElement>('p, div, span, section').forEach(el => {
    if (el.querySelector(NOT_DESCRIPTION) || el.closest('[data-cy="cover-letter-section"], [data-test="terms-review"]')) return;
    const text = (el.textContent || '').trim();
    if (text.length > best.length) best = text;
  });
  best = best.replace(/\s*(?:…|\.\.\.)?\s*(?:more|less)\s*$/i, '').trim();
  return best.length >= 80 ? best : null;
}

/**
 * Extract the submitted cover letter and screening answers from an Upwork proposal
 * detail page. DOM fallback only — the background prefers window.__NUXT__, whose
 * answers are never truncated.
 *
 * DOM structure (confirmed from proposaldetails.html):
 *   div[data-cy="cover-letter-section"]
 *     p.break.text-pre-line                       ← cover letter
 *     [data-test="questions-answers"] li
 *       strong                                    ← question
 *       span.air3-truncation span[id]             ← answer (may end in "…" + "more")
 */
export function scrapeProposalDetail(): ProposalDetail {
  let coverLetter: string | null = null;
  const answers: { question: string; answer: string }[] = [];

  const section = document.querySelector('[data-cy="cover-letter-section"]');
  if (section) {
    const parts: string[] = [];
    section.querySelectorAll('p.break.text-pre-line').forEach(p => {
      const t = p.textContent?.trim();
      if (t) parts.push(t);
    });
    const joined = parts.join('\n\n');
    if (joined.length > 50) coverLetter = joined;

    section.querySelectorAll('[data-test="questions-answers"] li').forEach(li => {
      const question = li.querySelector('strong')?.textContent?.trim() || '';
      const answer =
        li.querySelector('span.air3-truncation span[id]')?.textContent?.trim() ||
        li.querySelector('span.air3-truncation')?.textContent?.trim() ||
        '';
      if (answer) answers.push({ question, answer });
    });
  }

  if (!coverLetter) {
    // Fallback: .cover-letter-section (older Upwork markup)
    const fallback = document.querySelector('.cover-letter-section p.break, .cover-letter p');
    const t = fallback?.textContent?.trim();
    if (t && t.length > 50) coverLetter = t;
  }

  return { coverLetter, answers };
}
