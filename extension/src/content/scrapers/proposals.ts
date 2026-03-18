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

/**
 * Extract cover letter text from an Upwork proposal detail page.
 *
 * DOM structure (confirmed from proposaldetails.html):
 *   div[data-cy="cover-letter-section"]        ← container card
 *     section.air3-card-section
 *       p.break.text-pre-line                  ← the proposal text
 *       [data-test="questions-answers"]         ← Q&A responses (append if present)
 */
export function scrapeProposalPageText(): string | null {
  // Primary: confirmed selector from DOM analysis
  const section = document.querySelector('[data-cy="cover-letter-section"]');
  if (section) {
    // Collect the cover letter paragraph(s)
    const parts: string[] = [];
    section.querySelectorAll('p.break.text-pre-line').forEach(p => {
      const t = p.textContent?.trim();
      if (t) parts.push(t);
    });
    // Also grab Q&A answers if present — they add context for scoring calibration
    section.querySelectorAll('[data-test="questions-answers"] span.air3-truncation').forEach(span => {
      const t = span.textContent?.trim();
      if (t) parts.push(t);
    });
    if (parts.length && parts.join('').length > 50) return parts.join('\n\n');
  }

  // Fallback: .cover-letter-section (older Upwork markup)
  const fallback = document.querySelector('.cover-letter-section p.break, .cover-letter p');
  if (fallback) {
    const t = fallback.textContent?.trim();
    if (t && t.length > 50) return t;
  }

  return null;
}
