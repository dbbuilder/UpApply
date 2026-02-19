/**
 * Draft Saver: Auto-saves proposal form data so refreshing the page
 * (e.g. to see updated connects) doesn't lose cover letter, screening
 * answers, or bid amount.
 *
 * Uses sessionStorage keyed by job URL. Data is saved on every input
 * event and restored when the form renders after a page load.
 */

import { querySelector, SELECTORS } from './upwork-selectors';

interface DraftData {
  coverLetter: string;
  bidAmount: string;
  screeningAnswers: Record<string, string>; // label -> answer
  savedAt: number;
}

const STORAGE_PREFIX = 'upapply_draft_';

/**
 * Get a stable storage key for the current proposal page.
 * Uses the job ID from the URL (e.g. ~021234567890).
 */
function getStorageKey(): string | null {
  const url = window.location.href;
  // Match job ID from /apply/~XXXX or /jobs/~XXXX
  const match = url.match(/~(\w+)/);
  if (!match) return null;
  return STORAGE_PREFIX + match[1];
}

/**
 * Check if we're on a proposal/apply page.
 */
function isApplyPage(): boolean {
  return window.location.href.includes('/proposals/') &&
         window.location.href.includes('/apply');
}

/**
 * Collect all current form values.
 */
function collectFormData(): DraftData | null {
  const coverLetterEl = querySelector(SELECTORS.coverLetterTextarea) as HTMLTextAreaElement | null;
  const bidEl = querySelector(SELECTORS.bidAmountInput) as HTMLInputElement | null;

  // Don't save if the form hasn't rendered yet
  if (!coverLetterEl) return null;

  const screeningAnswers: Record<string, string> = {};
  const questionContainers = document.querySelectorAll(
    '.fe-proposal-job-questions .form-group, .questions-area .form-group, [data-test="screening-question"]'
  );
  questionContainers.forEach((container) => {
    const label = container.querySelector('label, .label');
    const input = container.querySelector('textarea, input[type="text"]') as HTMLTextAreaElement | HTMLInputElement | null;
    if (label && input && input.value) {
      const key = label.textContent?.trim() || '';
      if (key) {
        screeningAnswers[key] = input.value;
      }
    }
  });

  return {
    coverLetter: coverLetterEl.value || '',
    bidAmount: bidEl?.value || '',
    screeningAnswers,
    savedAt: Date.now(),
  };
}

/**
 * Save draft to sessionStorage.
 */
function saveDraft(): void {
  const key = getStorageKey();
  if (!key) return;

  const data = collectFormData();
  if (!data) return;

  // Only save if there's actual content
  if (!data.coverLetter && !data.bidAmount && Object.keys(data.screeningAnswers).length === 0) {
    return;
  }

  try {
    sessionStorage.setItem(key, JSON.stringify(data));
    updateIndicator('saved');
    console.log('UpApply: Draft saved');
  } catch {
    // sessionStorage full or unavailable
  }
}

/**
 * Load saved draft from sessionStorage.
 */
function loadDraft(): DraftData | null {
  const key = getStorageKey();
  if (!key) return null;

  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;

    const data: DraftData = JSON.parse(raw);

    // Expire drafts older than 4 hours
    if (Date.now() - data.savedAt > 4 * 60 * 60 * 1000) {
      sessionStorage.removeItem(key);
      return null;
    }

    return data;
  } catch {
    return null;
  }
}

/**
 * Clear saved draft.
 */
function clearDraft(): void {
  const key = getStorageKey();
  if (key) {
    sessionStorage.removeItem(key);
    updateIndicator('cleared');
    console.log('UpApply: Draft cleared');
  }
}

/**
 * Set a native input value and trigger Vue/React change detection.
 */
function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  // Use the native setter to bypass framework wrappers
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
    'value'
  )?.set;

  if (nativeInputValueSetter) {
    nativeInputValueSetter.call(el, value);
  } else {
    el.value = value;
  }

  // Fire events that Vue/Nuxt listens to
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

/**
 * Restore draft values into the form.
 * Returns true if any values were restored.
 */
function restoreDraft(draft: DraftData): boolean {
  let restored = false;

  // Restore cover letter
  if (draft.coverLetter) {
    const coverLetterEl = querySelector(SELECTORS.coverLetterTextarea) as HTMLTextAreaElement | null;
    if (coverLetterEl && !coverLetterEl.value) {
      setNativeValue(coverLetterEl, draft.coverLetter);
      restored = true;
      console.log('UpApply: Restored cover letter draft');
    }
  }

  // Restore bid amount
  if (draft.bidAmount) {
    const bidEl = querySelector(SELECTORS.bidAmountInput) as HTMLInputElement | null;
    if (bidEl && !bidEl.value) {
      setNativeValue(bidEl, draft.bidAmount);
      restored = true;
      console.log('UpApply: Restored bid amount draft');
    }
  }

  // Restore screening answers
  if (Object.keys(draft.screeningAnswers).length > 0) {
    const questionContainers = document.querySelectorAll(
      '.fe-proposal-job-questions .form-group, .questions-area .form-group, [data-test="screening-question"]'
    );
    questionContainers.forEach((container) => {
      const label = container.querySelector('label, .label');
      const input = container.querySelector('textarea, input[type="text"]') as HTMLTextAreaElement | HTMLInputElement | null;
      if (label && input) {
        const key = label.textContent?.trim() || '';
        const savedAnswer = draft.screeningAnswers[key];
        if (savedAnswer && !input.value) {
          setNativeValue(input, savedAnswer);
          restored = true;
          console.log('UpApply: Restored screening answer for:', key.substring(0, 50));
        }
      }
    });
  }

  return restored;
}

/**
 * Attach input listeners to auto-save on typing.
 */
function attachSaveListeners(): void {
  let saveTimer: ReturnType<typeof setTimeout> | null = null;

  const debouncedSave = () => {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 500);
  };

  // Cover letter
  const coverLetterEl = querySelector(SELECTORS.coverLetterTextarea) as HTMLTextAreaElement | null;
  if (coverLetterEl) {
    coverLetterEl.addEventListener('input', debouncedSave);
  }

  // Bid amount
  const bidEl = querySelector(SELECTORS.bidAmountInput) as HTMLInputElement | null;
  if (bidEl) {
    bidEl.addEventListener('input', debouncedSave);
  }

  // Screening questions
  const questionInputs = document.querySelectorAll(
    '.fe-proposal-job-questions textarea, .fe-proposal-job-questions input[type="text"], ' +
    '.questions-area textarea, .questions-area input[type="text"], ' +
    '[data-test="screening-question"] textarea, [data-test="screening-question"] input[type="text"]'
  );
  questionInputs.forEach((input) => {
    input.addEventListener('input', debouncedSave);
  });

  console.log('UpApply: Draft save listeners attached', {
    coverLetter: !!coverLetterEl,
    bid: !!bidEl,
    questions: questionInputs.length,
  });
}

/**
 * Inject the floating draft indicator/button into the page.
 */
function injectIndicator(): void {
  if (document.getElementById('upapply-draft-indicator')) return;

  const container = document.createElement('div');
  container.id = 'upapply-draft-indicator';
  container.innerHTML = `
    <style>
      #upapply-draft-indicator {
        position: fixed;
        bottom: 20px;
        left: 20px;
        z-index: 10000;
        display: flex;
        align-items: center;
        gap: 8px;
        background: #1a1a2e;
        color: #e0e0e0;
        padding: 8px 14px;
        border-radius: 8px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 13px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.3);
        transition: opacity 0.3s, transform 0.3s;
        opacity: 0;
        transform: translateY(10px);
      }
      #upapply-draft-indicator.visible {
        opacity: 1;
        transform: translateY(0);
      }
      #upapply-draft-indicator .upapply-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #4ade80;
        flex-shrink: 0;
      }
      #upapply-draft-indicator .upapply-dot.restoring {
        background: #60a5fa;
      }
      #upapply-draft-indicator .upapply-clear-btn {
        background: none;
        border: 1px solid #555;
        color: #aaa;
        cursor: pointer;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        margin-left: 4px;
      }
      #upapply-draft-indicator .upapply-clear-btn:hover {
        background: #333;
        color: #fff;
        border-color: #777;
      }
    </style>
    <span class="upapply-dot"></span>
    <span class="upapply-text">Draft auto-save active</span>
    <button class="upapply-clear-btn" title="Clear saved draft">Clear</button>
  `;

  document.body.appendChild(container);

  // Clear button handler
  container.querySelector('.upapply-clear-btn')?.addEventListener('click', () => {
    clearDraft();
  });

  // Show with animation
  requestAnimationFrame(() => {
    container.classList.add('visible');
  });
}

/**
 * Update the indicator text/state.
 */
function updateIndicator(state: 'saved' | 'restored' | 'cleared' | 'active'): void {
  const el = document.getElementById('upapply-draft-indicator');
  if (!el) return;

  const textEl = el.querySelector('.upapply-text') as HTMLSpanElement;
  const dotEl = el.querySelector('.upapply-dot') as HTMLSpanElement;
  if (!textEl || !dotEl) return;

  dotEl.classList.remove('restoring');

  switch (state) {
    case 'saved':
      textEl.textContent = 'Draft saved';
      // Fade back to normal after 2s
      setTimeout(() => {
        if (textEl.textContent === 'Draft saved') {
          textEl.textContent = 'Draft auto-save active';
        }
      }, 2000);
      break;
    case 'restored':
      dotEl.classList.add('restoring');
      textEl.textContent = 'Draft restored!';
      setTimeout(() => {
        dotEl.classList.remove('restoring');
        textEl.textContent = 'Draft auto-save active';
      }, 3000);
      break;
    case 'cleared':
      textEl.textContent = 'Draft cleared';
      setTimeout(() => {
        textEl.textContent = 'Draft auto-save active';
      }, 2000);
      break;
    case 'active':
      textEl.textContent = 'Draft auto-save active';
      break;
  }
}

/**
 * Wait for the proposal form to render, then set up draft saving.
 * Uses MutationObserver since the form is rendered by Vue/Nuxt after hydration.
 */
export function initDraftSaver(): void {
  if (!isApplyPage()) return;

  console.log('UpApply: Draft saver initializing on apply page');

  const draft = loadDraft();
  let hasRestored = false;
  let hasAttached = false;

  const trySetup = () => {
    const coverLetterEl = querySelector(SELECTORS.coverLetterTextarea);
    if (!coverLetterEl) return false; // Form not rendered yet

    if (!hasAttached) {
      hasAttached = true;
      injectIndicator();
      attachSaveListeners();
    }

    // Restore draft if we have one and haven't already
    if (draft && !hasRestored) {
      hasRestored = true;
      const didRestore = restoreDraft(draft);
      if (didRestore) {
        updateIndicator('restored');
      }
    }

    return true;
  };

  // Try immediately
  if (trySetup()) return;

  // Otherwise watch for form to appear
  const observer = new MutationObserver(() => {
    if (trySetup()) {
      observer.disconnect();
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Safety timeout — stop watching after 30s
  setTimeout(() => {
    observer.disconnect();
    if (!hasAttached) {
      console.log('UpApply: Draft saver timed out waiting for form');
    }
  }, 30000);
}
