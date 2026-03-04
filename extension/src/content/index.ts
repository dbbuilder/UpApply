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
  return window.location.href.includes('/jobs/') ||
         window.location.href.includes('/nx/proposals/');
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
 * Extract proposals from the My Proposals page.
 */
function extractProposals(): ScrapedProposal[] {
  const proposals: ScrapedProposal[] = [];

  // Debug: dump candidate containers to help identify the real selectors
  const debugSelectors = [
    '[data-test="proposal-list-item"]',
    '[data-test="proposals-list"] > *',
    '[data-test="proposal-row"]',
    '.proposals-list-item',
    '.up-card-section.up-card-list-section',
    'section[data-test]',
    'article',
    '[class*="proposal"]',
    '[class*="Proposal"]',
    '[class*="job-tile"]',
    '[class*="JobTile"]',
    'li[class*="proposal"]',
    '[data-ev-label*="proposal"]',
  ];
  for (const sel of debugSelectors) {
    const count = document.querySelectorAll(sel).length;
    if (count > 0) console.log(`UpApply: selector "${sel}" matches ${count} elements`);
  }

  // Find all proposal items — try multiple selector patterns
  const proposalItems = querySelectorAll(SELECTORS.proposalListItem);
  console.log('UpApply: Found', proposalItems.length, 'proposal items via SELECTORS.proposalListItem');

  for (const item of proposalItems) {
    try {
      // Extract job title and URL
      const titleElement = item.querySelector('h4 a, .job-title-link, [data-test="proposal-job-title"]');
      const jobTitle = titleElement?.textContent?.trim() || null;
      const jobUrl = titleElement?.getAttribute('href') || null;

      // Try to get proposal ID from data attributes or URL
      const proposalId = item.getAttribute('data-proposal-id') ||
                         jobUrl?.match(/~([a-zA-Z0-9]+)/)?.[1] ||
                         null;

      // Extract cover letter - this might require expanding the proposal
      const coverLetterElement = item.querySelector('.cover-letter-text, [data-test="proposal-cover-letter"], .proposal-description');
      const coverLetter = coverLetterElement?.textContent?.trim() || null;

      // Extract bid amount
      const bidText = item.querySelector('.proposal-bid-amount, [data-test="proposal-bid"]')?.textContent?.trim();
      let bidAmount: number | null = null;
      let bidType: string | null = null;
      if (bidText) {
        const match = bidText.match(/\$?([\d,]+\.?\d*)/);
        if (match) {
          bidAmount = parseFloat(match[1].replace(',', ''));
        }
        bidType = bidText.toLowerCase().includes('/hr') || bidText.toLowerCase().includes('hourly')
          ? 'hourly' : 'fixed';
      }

      // Extract status
      const statusElement = item.querySelector('.status-badge, [data-test="proposal-status"], .proposal-status');
      const status = statusElement?.textContent?.trim()?.toLowerCase() || 'submitted';

      // Extract submitted date
      const dateElement = item.querySelector('time, [data-test="proposal-date"], .proposal-submitted-date');
      const submittedAt = dateElement?.getAttribute('datetime') ||
                          dateElement?.textContent?.trim() ||
                          null;

      if (jobTitle || coverLetter) {
        proposals.push({
          proposalId,
          jobTitle,
          jobUrl: jobUrl ? new URL(jobUrl, window.location.origin).href : null,
          coverLetter,
          bidAmount,
          bidType,
          status,
          submittedAt,
        });
      }
    } catch (err) {
      console.error('UpApply: Error extracting proposal:', err);
    }
  }

  return proposals;
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

    case 'SCRAPE_PROPOSALS':
      if (!isMyProposalsPage()) {
        sendResponse({ success: false, error: 'Not on My Proposals page' });
      } else {
        try {
          const proposals = extractProposals();
          sendResponse({ success: true, data: proposals, url: window.location.href });
        } catch (err) {
          sendResponse({ success: false, error: String(err) });
        }
      }
      break;

    case 'GET_PAGE_TYPE':
      sendResponse({
        isJobPage: isJobPage(),
        isMyProposalsPage: isMyProposalsPage(),
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
