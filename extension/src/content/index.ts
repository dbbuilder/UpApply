/**
 * Content script for extracting job data from Upwork pages.
 */

import {
  SELECTORS,
  extractText,
  extractTexts,
  querySelector,
  querySelectorAll,
} from './upwork-selectors';
import type { ScreeningQuestion, JobData, ScrapedProposal, AttachmentInfo, JobPostingData } from '../types';
import { initDraftSaver } from './draft-saver';

/**
 * Extract screening questions from the page.
 */
function extractScreeningQuestions(): ScreeningQuestion[] {
  const questions: ScreeningQuestion[] = [];

  // Find all question containers
  const questionContainers = document.querySelectorAll(
    '.fe-proposal-job-questions .form-group, .questions-area .form-group'
  );

  questionContainers.forEach((container, index) => {
    const label = container.querySelector('label, .label');
    const input = container.querySelector('textarea, input[type="text"]');

    if (label && input) {
      const questionText = label.textContent?.trim() || '';
      if (questionText) {
        // Create a unique selector for this input
        questions.push({
          question: questionText,
          inputSelector: input.id ? `#${input.id}` : `.fe-proposal-job-questions .form-group:nth-child(${index + 1}) textarea, .fe-proposal-job-questions .form-group:nth-child(${index + 1}) input`,
        });
      }
    }
  });

  return questions;
}

/**
 * Extract job data from the current page.
 */
function extractJobData(): JobData {
  const url = window.location.href;

  // Extract basic job info
  const title = extractText(SELECTORS.jobTitle);
  const description = extractText(SELECTORS.jobDescription);
  const skills = extractTexts(SELECTORS.skills);
  const experienceLevel = extractText(SELECTORS.experienceLevel);
  const projectLength = extractText(SELECTORS.projectLength);

  // Debug: if extraction failed, dump what we can find
  if (!title) {
    const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5')).slice(0, 10);
    console.log('UpApply: Title not found. Page headings:', headings.map(h => ({
      tag: h.tagName,
      class: h.className.substring(0, 60),
      text: h.textContent?.trim().substring(0, 80),
      parent: h.parentElement?.className.substring(0, 60),
    })));
  }

  console.log('UpApply: Extraction results:', {
    title: title?.substring(0, 60),
    descriptionLength: description?.length,
    skillCount: skills.length,
  });

  // Extract budget info
  const budgetAmount = extractText(SELECTORS.budgetAmount);
  let budgetType: string | null = null;

  // Determine budget type from content or selectors
  const hourlyElement = querySelector(SELECTORS.budgetType);
  if (hourlyElement?.textContent?.toLowerCase().includes('hourly')) {
    budgetType = 'hourly';
  } else if (budgetAmount?.toLowerCase().includes('/hr')) {
    budgetType = 'hourly';
  } else if (budgetAmount) {
    budgetType = 'fixed';
  }

  // Extract client info
  const clientRating = extractText(SELECTORS.clientRating);
  const clientLocation = extractText(SELECTORS.clientLocation);
  const clientSpent = extractText(SELECTORS.clientSpent);
  const clientHireRate = extractText(SELECTORS.clientHireRate);

  // Extract screening questions
  const screeningQuestions = extractScreeningQuestions();

  return {
    url,
    title,
    description,
    budgetType,
    budgetAmount,
    skills,
    experienceLevel,
    projectLength,
    screeningQuestions,
    clientInfo: {
      rating: clientRating,
      location: clientLocation,
      totalSpent: clientSpent,
      hireRate: clientHireRate,
    },
  };
}

/**
 * Check if we're on a job details page.
 */
function isJobPage(): boolean {
  return window.location.href.includes('/jobs/');
}

/**
 * Check if we're on the My Proposals page.
 */
function isMyProposalsPage(): boolean {
  const url = window.location.href;
  return url.includes('/freelancers/proposals') ||
         url.includes('/nx/find-work/proposals') ||
         url.includes('/nx/proposals') ||
         url.includes('/ab/proposals');
}

/**
 * Check if the current page has job card listings (saved jobs or search results).
 */
function isJobCardPage(): boolean {
  const url = window.location.href;
  return url.includes('/nx/search/jobs') || url.includes('/nx/find-work/');
}

interface ScrapedJobCard {
  upworkJobId: string;
  upworkUrl: string;
  title: string;
  description: string;
  jobType: string | null;
  experienceLevel: string | null;
  postedDateRaw: string | null;
  clientInfo: {
    paymentVerified: boolean;
    rating: string | null;
    totalSpent: string | null;
  };
}

/**
 * Extract job cards from a saved-jobs or search-results page.
 * Structure: article[data-test="JobTile"] with data-test-key=jobId
 */
function extractJobCards(): ScrapedJobCard[] {
  const cards: ScrapedJobCard[] = [];
  const articles = document.querySelectorAll('article[data-test="JobTile"]');

  articles.forEach((article) => {
    const titleLink = article.querySelector<HTMLAnchorElement>('a[data-test="job-tile-title-link"]');
    if (!titleLink) return;

    const title = titleLink.textContent?.trim() || '';
    const href = titleLink.getAttribute('href') || '';
    const fullUrl = href.startsWith('http') ? href : `https://www.upwork.com${href}`;

    // Extract job ID from URL: ~0(\d+) pattern
    const idMatch = fullUrl.match(/~0?(\d{15,})/);
    if (!idMatch) return;
    const upworkJobId = idMatch[1];

    const description = article.querySelector('[data-test="UpCLineClamp JobDescription"]')
      ?.textContent?.trim() || '';

    const jobTypeEl = article.querySelector('[data-test="job-type-label"]');
    const jobType = jobTypeEl?.textContent?.trim().toLowerCase().includes('fixed')
      ? 'fixed'
      : jobTypeEl?.textContent?.trim().toLowerCase().includes('hourly')
      ? 'hourly'
      : null;

    const expEl = article.querySelector('[data-test="experience-level"]');
    const experienceLevel = expEl?.textContent?.trim() || null;

    const dateEl = article.querySelector('[data-test="job-pubilshed-date"]');
    const postedDateRaw = dateEl?.textContent?.trim() || null;

    const paymentVerified = !!article.querySelector('[data-test="payment-verified"]');
    const ratingEl = article.querySelector('[data-test="total-feedback"]');
    const rating = ratingEl?.textContent?.trim() || null;
    const spentEl = article.querySelector('[data-test="total-spent"]');
    const totalSpent = spentEl?.textContent?.trim() || null;

    cards.push({
      upworkJobId,
      upworkUrl: fullUrl.split('?')[0], // strip query params
      title,
      description,
      jobType,
      experienceLevel,
      postedDateRaw,
      clientInfo: { paymentVerified, rating, totalSpent },
    });
  });

  return cards;
}

/**
 * Extract job cards across all pagination pages.
 */
async function extractAllJobCards(): Promise<ScrapedJobCard[]> {
  // Use same cross-instance lock as proposals
  const lockKey = '__upapplyJobCardScrapingPromise';
  const win = window as unknown as Record<string, unknown>;

  if (win[lockKey]) {
    console.log('UpApply: Joining existing job card scrape');
    return win[lockKey] as Promise<ScrapedJobCard[]>;
  }

  const promise = (async () => {
    const all: ScrapedJobCard[] = [];

    // Read total pages from pagination attribute
    const paginationEl = document.querySelector('[data-ev-max_page_count]');
    const totalPages = paginationEl
      ? parseInt(paginationEl.getAttribute('data-ev-max_page_count') || '1', 10)
      : 1;
    const pagesToScrape = Math.min(totalPages, 50); // cap at 50 pages

    console.log('UpApply: Job card scrape — total pages:', totalPages, 'scraping up to:', pagesToScrape);

    all.push(...extractJobCards());
    console.log('UpApply: Page 1 —', all.length, 'job cards');

    for (let page = 2; page <= pagesToScrape; page++) {
      const nextBtn = document.querySelector<HTMLButtonElement>('button[data-test="next-page"]');
      if (!nextBtn || nextBtn.disabled) break;

      const firstCardId = document.querySelector('article[data-test="JobTile"]')?.getAttribute('data-test-key');
      nextBtn.click();

      // Wait for page to change
      await new Promise<void>((resolve) => {
        const start = Date.now();
        const poll = setInterval(() => {
          const newId = document.querySelector('article[data-test="JobTile"]')?.getAttribute('data-test-key');
          if (newId !== firstCardId || Date.now() - start > 3000) {
            clearInterval(poll);
            resolve();
          }
        }, 100);
      });

      // Wait for next button to re-enable
      await new Promise<void>((resolve) => {
        const start = Date.now();
        const poll = setInterval(() => {
          const btn = document.querySelector<HTMLButtonElement>('button[data-test="next-page"]');
          if (!btn?.disabled || Date.now() - start > 2000) {
            clearInterval(poll);
            resolve();
          }
        }, 100);
      });

      const pageCards = extractJobCards();
      all.push(...pageCards);
      console.log('UpApply: Page', page, '—', pageCards.length, 'job cards (total:', all.length, ')');
    }

    return all;
  })();

  win[lockKey] = promise;
  try {
    return await promise;
  } finally {
    delete win[lockKey];
  }
}

/**
 * Extract proposals from the My Proposals page.
 */
function extractProposals(): ScrapedProposal[] {
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
  console.log('UpApply: Found', proposalLinks.length, 'proposal links');

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

  console.log('UpApply: Extracted', proposals.length, 'proposals');
  return proposals;
}

// window-level key for the shared scraping promise (shared across all
// instances of this content script injected into the same tab).
const SCRAPE_KEY = '__upapplyScrapingPromise';

/**
 * Wait for the next-page button to become enabled (not disabled).
 * The button is briefly disabled during page transitions.
 */
function waitForNextButton(timeoutMs = 2000): Promise<HTMLButtonElement | null> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      const btn = document.querySelector<HTMLButtonElement>('button[data-test="next-page"]');
      if (!btn) { resolve(null); return; }
      if (!btn.disabled) { resolve(btn); return; }
      if (Date.now() >= deadline) { resolve(null); return; }
      setTimeout(check, 100);
    };
    setTimeout(check, 100);
  });
}

/**
 * Wait for new proposal links to appear after a page navigation click.
 * Resolves when the first proposal link's href changes or a timeout occurs.
 */
function waitForProposalPageChange(previousFirstId: string | null, timeoutMs = 2500): Promise<void> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      const first = document.querySelector<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]');
      const firstId = first?.getAttribute('href') || null;
      if (firstId && firstId !== previousFirstId) {
        resolve();
      } else if (Date.now() >= deadline) {
        resolve(); // timeout — extract whatever's there
      } else {
        setTimeout(check, 150);
      }
    };
    setTimeout(check, 150);
  });
}

/**
 * Extract proposals across all pagination pages by clicking "next page"
 * until the last page is reached. Uses a lock to prevent concurrent runs
 * when multiple content script instances are active.
 */
async function extractAllProposals(): Promise<ScrapedProposal[]> {
  const win = window as unknown as Record<string, unknown>;

  // If another instance already started scraping, share its result
  if (win[SCRAPE_KEY]) {
    console.log('UpApply: Joining existing scrape in progress');
    return win[SCRAPE_KEY] as Promise<ScrapedProposal[]>;
  }

  // Become the leader — store the promise so other instances join it
  const scrapePromise = (async (): Promise<ScrapedProposal[]> => {
    const paginationDiv = document.querySelector('[data-ev-max_page_count]');
    const totalPages = paginationDiv
      ? parseInt(paginationDiv.getAttribute('data-ev-max_page_count') || '1', 10)
      : 1;

    console.log('UpApply: Proposals pagination — total pages:', totalPages);

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

    // Page 1 is already loaded
    addPage(extractProposals());

    for (let page = 2; page <= totalPages; page++) {
      const firstLink = document.querySelector<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]');
      const previousFirstHref = firstLink?.getAttribute('href') || null;

      // Wait for next button to be enabled (it's briefly disabled during transitions)
      const nextBtn = await waitForNextButton();
      if (!nextBtn) {
        console.log('UpApply: No enabled next button found at page', page - 1, '— stopping');
        break;
      }

      console.log('UpApply: Clicking to page', page, 'of', totalPages);
      nextBtn.click();
      await waitForProposalPageChange(previousFirstHref);

      addPage(extractProposals());
    }

    console.log('UpApply: Total proposals across all pages:', all.length);
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
 * Infer content type from URL or filename.
 */
function inferContentType(url: string, filename: string): string {
  const ext = (url.match(/\.(\w+)(?:\?|$)/) || filename.match(/\.(\w+)$/) || [])[1]?.toLowerCase();
  const typeMap: Record<string, string> = {
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    txt: 'text/plain',
  };
  return typeMap[ext] || 'application/octet-stream';
}

/**
 * Get the "View job posting" link URL from the current page.
 */
function getViewJobPostingLink(): string | null {
  const linkElement = querySelector(SELECTORS.viewJobPostingLink) as HTMLAnchorElement | null;
  if (linkElement?.href) {
    return linkElement.href;
  }
  return null;
}

/**
 * Extract job posting data from a job details page.
 * This is used when viewing the full job posting (not the /apply page).
 */
function extractJobPostingData(): JobPostingData {
  // Get full description
  const fullDescription = extractText(SELECTORS.jobPostingFullDescription);

  // Get attachments
  const attachmentElements = querySelectorAll(SELECTORS.jobPostingAttachments);
  const attachments: AttachmentInfo[] = [];
  const seenUrls = new Set<string>();

  for (const el of attachmentElements) {
    const link = el as HTMLAnchorElement;
    if (!link.href || seenUrls.has(link.href)) continue;

    // Skip non-attachment links
    if (!link.href.includes('attachment') &&
        !link.href.includes('/ab/') &&
        !link.href.match(/\.(pdf|docx?|png|jpe?g|gif|txt)(\?|$)/i)) {
      continue;
    }

    seenUrls.add(link.href);
    const filename = link.textContent?.trim() ||
                     link.getAttribute('download') ||
                     link.href.split('/').pop()?.split('?')[0] ||
                     'attachment';

    attachments.push({
      url: link.href,
      filename,
      contentType: inferContentType(link.href, filename),
    });
  }

  console.log('UpApply: Extracted job posting data:', {
    descriptionLength: fullDescription?.length,
    attachmentCount: attachments.length,
  });

  return {
    fullDescription,
    attachments,
  };
}

/**
 * Fill the cover letter textarea with generated content.
 */
function fillCoverLetter(content: string): boolean {
  const textarea = querySelector(SELECTORS.coverLetterTextarea) as HTMLTextAreaElement | null;

  if (!textarea) {
    console.warn('UpApply: Cover letter textarea not found');
    return false;
  }

  // Set value and trigger input event for React/Vue compatibility
  textarea.value = content;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));

  // Focus the textarea
  textarea.focus();

  return true;
}

/**
 * Set the bid amount in the proposal form.
 */
function setBidAmount(amount: number): boolean {
  const input = querySelector(SELECTORS.bidAmountInput) as HTMLInputElement | null;

  if (!input) {
    console.warn('UpApply: Bid amount input not found');
    return false;
  }

  input.value = amount.toString();
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));

  return true;
}

/**
 * Fill a screening question answer.
 */
function fillScreeningQuestion(selector: string, answer: string): boolean {
  try {
    const input = document.querySelector(selector) as HTMLTextAreaElement | HTMLInputElement | null;
    if (!input) {
      console.warn('UpApply: Screening question input not found:', selector);
      return false;
    }

    input.value = answer;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  } catch (error) {
    console.error('UpApply: Error filling screening question:', error);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Notification page job scorer
// ---------------------------------------------------------------------------

const _scoredNotifUrls = new Set<string>();

/** Strip query params and trailing slashes so the same job with different
 *  tracking params (?source=notification, ?source=job-alert, etc.) counts
 *  as the same URL. */
function _normalizeJobUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.origin + u.pathname.replace(/\/+$/, '');
  } catch {
    return url;
  }
}

function _scoreToNotifColors(score: number): { bg: string; color: string } {
  if (score >= 90) return { bg: '#15803d', color: '#ffffff' }; // deep green
  if (score >= 80) return { bg: '#22c55e', color: '#14532d' }; // lighter green
  if (score >= 70) return { bg: '#ca8a04', color: '#ffffff' }; // yellow
  return { bg: '#dc2626', color: '#ffffff' };                  // red
}

function _injectNotifBadge(row: Element, jobUrl: string): HTMLElement {
  const badge = document.createElement('span');
  badge.dataset.upapplyJob = _normalizeJobUrl(jobUrl);
  badge.style.cssText =
    'display:inline-flex;align-items:center;justify-content:center;' +
    'min-width:38px;height:24px;border-radius:12px;' +
    'font-size:13px;font-weight:700;color:#9ca3af;' +
    'background:#f3f4f6;border:1px solid #e5e7eb;' +
    'padding:0 8px;margin-left:8px;vertical-align:middle;' +
    'cursor:default;font-family:-apple-system,sans-serif;white-space:nowrap;';
  badge.textContent = '…';
  badge.title = 'UpApply: scoring…';
  const link = row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
  if (link) link.after(badge);
  return badge;
}

interface _NotifQueueItem {
  badge: HTMLElement;
  row: Element;
  jobUrl: string;
  title: string;
}
const _notifQueue: _NotifQueueItem[] = [];
let _notifProcessing = false;
let _notifTotal = 0;   // total jobs queued in this scoring run
let _notifDone  = 0;   // jobs completed (success or failure)

// Chip colour map — specific keywords get accent colours, budget is neutral
const _CHIP_COLORS: Record<string, { bg: string; color: string }> = {
  'MVP':   { bg: '#7c3aed', color: '#fff' },
  'SaaS':  { bg: '#0891b2', color: '#fff' },
  'Azure': { bg: '#0078d4', color: '#fff' },
  'SQL':   { bg: '#b45309', color: '#fff' },
  'Role':  { bg: '#374151', color: '#fff' },
};

function _injectChips(row: Element, chips: string[]): void {
  chips.forEach((label) => {
    const chip = document.createElement('span');
    const colors = _CHIP_COLORS[label] ?? { bg: '#166534', color: '#fff' }; // budget → green
    chip.style.cssText =
      'display:inline-flex;align-items:center;justify-content:center;' +
      `background:${colors.bg};color:${colors.color};` +
      'height:20px;border-radius:10px;' +
      'font-size:11px;font-weight:600;' +
      'padding:0 7px;margin-left:5px;vertical-align:middle;' +
      'font-family:-apple-system,sans-serif;white-space:nowrap;letter-spacing:0.01em;';
    chip.textContent = label;
    // Insert after the last upapply element in this row
    const all = [...row.querySelectorAll<HTMLElement>('[data-upapply-job],[data-upapply-chip]')];
    const lastBadge = all[all.length - 1];
    if (lastBadge) lastBadge.after(chip);
    chip.dataset.upapplyChip = label;
  });
}

// ---------------------------------------------------------------------------
// Progress bar injected near the notification bell
// ---------------------------------------------------------------------------

function _getOrCreateProgressBar(): HTMLElement {
  let bar = document.getElementById('ua-notif-progress');
  if (bar) return bar;

  bar = document.createElement('div');
  bar.id = 'ua-notif-progress';
  bar.style.cssText =
    'position:fixed;top:60px;right:16px;z-index:2147483647;' +
    'background:#1d4ed8;color:#fff;' +
    'font-size:11px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'padding:5px 10px;border-radius:20px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,0.25);' +
    'display:flex;align-items:center;gap:6px;white-space:nowrap;' +
    'transition:opacity 0.3s;';

  const spinner = document.createElement('span');
  spinner.id = 'ua-notif-spinner';
  spinner.style.cssText =
    'width:10px;height:10px;border-radius:50%;border:2px solid rgba(255,255,255,0.4);' +
    'border-top-color:#fff;animation:ua-spin 0.7s linear infinite;';
  bar.appendChild(spinner);

  const label = document.createElement('span');
  label.id = 'ua-notif-label';
  bar.appendChild(label);

  // Keyframes (inject once)
  if (!document.getElementById('ua-notif-styles')) {
    const style = document.createElement('style');
    style.id = 'ua-notif-styles';
    style.textContent = '@keyframes ua-spin{to{transform:rotate(360deg)}}';
    document.head.appendChild(style);
  }

  document.body.appendChild(bar);
  return bar;
}

function _updateProgressBar(done: number, total: number): void {
  const bar = _getOrCreateProgressBar();
  const label = bar.querySelector<HTMLElement>('#ua-notif-label')!;
  label.textContent = `UpApply scoring ${done}/${total}…`;
  bar.style.opacity = '1';
}

function _hideProgressBar(): void {
  const bar = document.getElementById('ua-notif-progress');
  if (!bar) return;
  bar.style.opacity = '0';
  setTimeout(() => bar.remove(), 400);
}

// ---------------------------------------------------------------------------

async function _processNotifQueue(): Promise<void> {
  if (_notifProcessing) return;
  _notifProcessing = true;
  _notifDone = 0;
  _updateProgressBar(0, _notifTotal);

  while (_notifQueue.length > 0) {
    const item = _notifQueue.shift()!;
    await new Promise<void>((resolve) => {
      chrome.runtime.sendMessage(
        { type: 'SCORE_NOTIFICATION_JOB', jobUrl: item.jobUrl, title: item.title },
        (resp: { success: boolean; score?: number; chips?: string[]; cached?: boolean } | undefined) => {
          if (resp?.success && resp.score != null) {
            const score = Math.round(resp.score);
            const { bg, color } = _scoreToNotifColors(score);
            item.badge.style.background = bg;
            item.badge.style.color = color;
            item.badge.style.border = 'none';
            item.badge.textContent = String(score);
            item.badge.title = `UpApply match: ${score}/100${resp.cached ? ' (cached)' : ''}`;
            if (resp.chips?.length) _injectChips(item.row, resp.chips);
          } else {
            item.badge.textContent = '?';
            item.badge.title = 'UpApply: could not score';
          }
          _notifDone++;
          _updateProgressBar(_notifDone, _notifTotal);
          resolve();
        }
      );
    });
    // Cached hits don't need the rate-limit delay
    if (_notifQueue.length > 0) {
      await new Promise(r => setTimeout(r, 800));
    }
  }

  _notifProcessing = false;
  _hideProgressBar();
}

function _processNotificationRows(): void {
  // Works for both the bell dropdown AND the full /ab/notifications/ page.
  // Both use .notification-row elements containing a[href*="/jobs/~"] links.
  document.querySelectorAll<Element>('.notification-row').forEach((row) => {
    // Skip rows that already have a badge (prevents double-injection when
    // MutationObserver fires on our own DOM changes)
    if (row.querySelector('[data-upapply-job]')) return;
    const link = row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
    if (!link) return;
    const jobUrl = _normalizeJobUrl(link.href);
    if (_scoredNotifUrls.has(jobUrl)) return;
    _scoredNotifUrls.add(jobUrl);
    const title = link.textContent?.trim() || '';
    const badge = _injectNotifBadge(row, jobUrl);
    _notifQueue.push({ badge, row, jobUrl, title });
    _notifTotal++;
  });
  _processNotifQueue();
}

// MutationObserver covers two cases:
//   1. Bell dropdown: Upwork injects ul[data-cy="notifications-list"] into DOM when opened
//   2. Full notifications page (/ab/notifications/): rows are already in the DOM and the
//      observer fires as Upwork's Vue renders them in
let _notifObserverFired = false;
new MutationObserver(() => {
  const isNotifPage = window.location.pathname.includes('/notifications');
  const hasDropdown = !!document.querySelector('ul[data-cy="notifications-list"]');
  const hasRows     = !!document.querySelector('.notification-row a[href*="/jobs/~"]');

  if (hasDropdown || (isNotifPage && hasRows)) {
    _processNotificationRows();
    // On the full page, stop watching once we've done a first pass —
    // subsequent calls come from new rows added by infinite scroll
    if (isNotifPage && hasRows && !_notifObserverFired) {
      _notifObserverFired = true;
    }
  }
}).observe(document.body, { childList: true, subtree: true });

// Also try immediately on the full notifications page (rows may already be in DOM)
if (window.location.pathname.includes('/notifications')) {
  setTimeout(_processNotificationRows, 1500);
}

// ---------------------------------------------------------------------------

interface ScrapedSavedSearch {
  query: string;
  url_params: string;
  label: string;
}

/**
 * Extract saved searches from Upwork's find-work or search pages.
 * Looks for links to /nx/search/jobs that contain a q= parameter.
 */
function extractSavedSearches(): ScrapedSavedSearch[] {
  const results: ScrapedSavedSearch[] = [];
  const seen = new Set<string>();

  const links = document.querySelectorAll<HTMLAnchorElement>('a[href*="/nx/search/jobs"]');
  links.forEach((link) => {
    try {
      const url = new URL(link.href);
      const q = url.searchParams.get('q');
      if (!q || !q.trim()) return;

      const normalized = q.trim().toLowerCase();
      if (seen.has(normalized)) return;
      seen.add(normalized);

      // Build url_params from remaining params (exclude q and nbs)
      const extra = new URLSearchParams(url.search);
      extra.delete('q');
      extra.delete('nbs');
      const urlParams = extra.toString();

      const label = link.textContent?.trim() || q.trim();
      results.push({ query: q.trim(), url_params: urlParams, label });
    } catch {
      // Ignore malformed URLs
    }
  });

  return results;
}

/**
 * Handle messages from background script or sidebar.
 */
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  console.log('UpApply: Received message', message.type, message);

  switch (message.type) {
    case 'EXTRACT_JOB_DATA':
      console.log('UpApply: EXTRACT_JOB_DATA received, isJobPage:', isJobPage(), 'URL:', window.location.href);
      if (!isJobPage()) {
        console.log('UpApply: Not a job page, returning error');
        sendResponse({ success: false, error: 'Not on a job page' });
        return true;
      }
      try {
        const jobData = extractJobData();
        console.log('UpApply: Extraction complete, title:', jobData.title);
        if (!jobData.title) {
          // Send debug info back so it's visible in the background/sidebar console
          const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5')).slice(0, 8);
          const debug = headings.map(h => `<${h.tagName} class="${h.className.substring(0, 40)}"> ${h.textContent?.trim().substring(0, 60)}`);
          console.log('UpApply: DEBUG headings:', debug);
          sendResponse({ success: true, data: jobData, debug });
        } else {
          sendResponse({ success: true, data: jobData });
        }
      } catch (err) {
        console.error('UpApply: Extraction error:', err);
        sendResponse({ success: false, error: String(err) });
      }
      return true;

    case 'FILL_COVER_LETTER':
      const filled = fillCoverLetter(message.content);
      sendResponse({ success: filled });
      break;

    case 'SET_BID_AMOUNT':
      const bidSet = setBidAmount(message.amount);
      sendResponse({ success: bidSet });
      break;

    case 'GET_PAGE_STATUS':
      sendResponse({
        isJobPage: isJobPage(),
        url: window.location.href,
      });
      break;

    case 'FILL_SCREENING_QUESTION':
      const questionFilled = fillScreeningQuestion(message.selector, message.answer);
      sendResponse({ success: questionFilled });
      break;

    case 'SCRAPE_PROPOSALS': {
      if (!isMyProposalsPage()) {
        sendResponse({ success: false, error: 'Not on My Proposals page', url: window.location.href });
      } else {
        // Collect debug selector hits to send back to background console
        const debugHits: string[] = [];
        const debugSelectors = [
          '[data-test="proposal-list-item"]',
          '[data-test="proposals-list"] > *',
          '[data-test="proposal-row"]',
          '.proposals-list-item',
          '.up-card-section.up-card-list-section',
          '[class*="proposal" i]',
          '[class*="job-tile" i]',
          '[data-ev-label*="proposal" i]',
          'article',
          'li',
          'section',
        ];
        for (const sel of debugSelectors) {
          const count = document.querySelectorAll(sel).length;
          if (count > 0 && count < 200) debugHits.push(`"${sel}" × ${count}`);
        }
        (async () => {
          try {
            const proposals = await extractAllProposals();
            sendResponse({ success: true, data: proposals, url: window.location.href, debug: debugHits });
          } catch (err) {
            sendResponse({ success: false, error: String(err), debug: debugHits });
          }
        })();
        return true; // keep message channel open for async sendResponse
      }
      break;
    }

    case 'SCRAPE_JOB_CARDS': {
      if (!isJobCardPage()) {
        sendResponse({ success: false, error: 'Not on a job listings page', url: window.location.href });
      } else {
        (async () => {
          try {
            const cards = await extractAllJobCards();
            sendResponse({ success: true, data: cards, url: window.location.href });
          } catch (err) {
            sendResponse({ success: false, error: String(err) });
          }
        })();
        return true;
      }
      break;
    }

    case 'SCRAPE_SAVED_SEARCHES': {
      try {
        const results = extractSavedSearches();
        sendResponse({ success: true, data: results, url: window.location.href });
      } catch (err) {
        sendResponse({ success: false, error: String(err) });
      }
      break;
    }

    case 'GET_PAGE_TYPE':
      sendResponse({
        isJobPage: isJobPage(),
        isMyProposalsPage: isMyProposalsPage(),
        isJobCardPage: isJobCardPage(),
        url: window.location.href,
      });
      break;

    case 'GET_VIEW_POSTING_LINK':
      const viewLink = getViewJobPostingLink();
      sendResponse({ success: !!viewLink, url: viewLink });
      break;

    case 'EXTRACT_JOB_POSTING_DATA':
      try {
        const postingData = extractJobPostingData();
        sendResponse({ success: true, data: postingData });
      } catch (err) {
        console.error('UpApply: Job posting extraction error:', err);
        sendResponse({ success: false, error: String(err) });
      }
      break;

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
  }

  return true; // Keep message channel open for async response
});

/**
 * Guard against re-injection. The background script may re-inject
 * the content script, but we only want to initialize once per page.
 */
const INIT_FLAG = '__upapply_initialized__';

/**
 * Auto-fill cover letter from a pending Quick Apply initiated by the sidebar.
 * Checks chrome.storage for a pendingAutoFill entry matching this apply page.
 */
async function checkPendingAutoFill(): Promise<void> {
  if (!window.location.href.includes('/apply')) return;

  const result = await chrome.storage.local.get('pendingAutoFill');
  const pending = result.pendingAutoFill as {
    jobUrl: string;
    jobId: string;
    coverLetter: string;
    timestamp: number;
  } | undefined;

  if (!pending) return;

  // Expire after 5 minutes
  if (Date.now() - pending.timestamp > 5 * 60 * 1000) {
    await chrome.storage.local.remove('pendingAutoFill');
    return;
  }

  // Match by job slug (~XXXX) so URL format differences don't matter
  const urlSlug = window.location.href.match(/(~[a-zA-Z0-9]+)/)?.[1];
  const pendingSlug = pending.jobUrl?.match(/(~[a-zA-Z0-9]+)/)?.[1];
  if (!urlSlug || urlSlug !== pendingSlug) return;

  // Consume the pending fill immediately so it doesn't apply twice
  await chrome.storage.local.remove('pendingAutoFill');
  console.log('UpApply: Pending auto-fill found for job slug', urlSlug);

  const tryFill = (): boolean => fillCoverLetter(pending.coverLetter);

  // Try immediately; if form not rendered yet, wait via MutationObserver
  if (!tryFill()) {
    const observer = new MutationObserver(() => {
      if (tryFill()) {
        observer.disconnect();
        console.log('UpApply: Pending auto-fill applied via observer');
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // Give up after 15 seconds
    setTimeout(() => observer.disconnect(), 15000);
  } else {
    console.log('UpApply: Pending auto-fill applied immediately');
  }
}

/**
 * Initialize content script.
 */
function init() {
  // Prevent duplicate init from re-injection
  if ((window as unknown as Record<string, unknown>)[INIT_FLAG]) {
    console.log('UpApply: Already initialized, skipping');
    return;
  }
  (window as unknown as Record<string, unknown>)[INIT_FLAG] = true;

  console.log('UpApply: Content script loaded on', window.location.href);

  // Notify background script that we're ready
  chrome.runtime.sendMessage({
    type: 'CONTENT_SCRIPT_READY',
    url: window.location.href,
    isJobPage: isJobPage(),
  }).catch(() => { /* sidebar/background may not be listening */ });

  // Check for Quick Apply pending fill (fires when sidebar opens an apply page)
  checkPendingAutoFill().catch(() => {});

  // Initialize draft saver on proposal/apply pages
  initDraftSaver();

  // Watch for SPA navigation
  let lastUrl = window.location.href;
  const observer = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      console.log('UpApply: URL changed to', lastUrl);

      // Re-extract job data on navigation
      if (isJobPage()) {
        setTimeout(() => {
          const jobData = extractJobData();
          chrome.runtime.sendMessage({
            type: 'JOB_DATA_EXTRACTED',
            data: jobData,
          }).catch(() => { /* no listener */ });
        }, 2000);
      }

      // Re-initialize draft saver if navigated to apply page
      initDraftSaver();

      // Check for pending Quick Apply fill after SPA navigation
      checkPendingAutoFill().catch(() => {});
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
