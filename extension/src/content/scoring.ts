/**
 * Badge scoring pipeline — notification rows, job tiles, action panels, button injection.
 * Self-contained: sets up its own MutationObserver on import.
 */

import { logger } from '../lib/logger';
import { detectNotifChips } from '../lib/notif-chips';
import { scrapeProposalPageText } from './scrapers/proposals';

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

// ---------------------------------------------------------------------------
// Star rating — combines score + budget into 1–5 ★ for quick visual triage
// ---------------------------------------------------------------------------

function _parseBudgetFromChips(chips: string[]): { amount: number; type: 'hourly' | 'fixed' } | null {
  const chip = chips.find(c => c.startsWith('$'));
  if (!chip) return null;
  // Use top-of-range if it's a range like "$50-$100/hr"
  const top = chip.replace(/^\$[\d,]+(?:\.\d+)?\s*[-–]\s*/, ''); // strip lower bound
  const isHourly = /\/h(r|our)?/.test(chip);
  const num = parseFloat(top.replace(/[^0-9.]/g, ''));
  if (!num || isNaN(num)) return null;
  return { amount: num, type: isHourly ? 'hourly' : 'fixed' };
}

function _computeStars(score: number, chips: string[]): number {
  // Base stars from AI score
  let stars: number;
  if (score >= 85) stars = 5;
  else if (score >= 70) stars = 4;
  else if (score >= 52) stars = 3;
  else if (score >= 35) stars = 2;
  else stars = 1;

  // Budget modifier: ±1 based on rate/amount
  const budget = _parseBudgetFromChips(chips);
  if (budget) {
    const { amount, type } = budget;
    const isHigh = type === 'hourly' ? amount >= 100 : amount >= 8000;
    const isLow  = type === 'hourly' ? amount < 25   : amount < 400;
    if (isHigh) stars = Math.min(5, stars + 1);
    else if (isLow) stars = Math.max(1, stars - 1);
  }

  return stars;
}

function _starsDisplay(stars: number): string {
  return '★'.repeat(stars) + '☆'.repeat(5 - stars);
}

function _starsColors(stars: number): { bg: string; color: string } {
  if (stars >= 5) return { bg: '#b45309', color: '#fff' }; // amber/gold
  if (stars >= 4) return { bg: '#15803d', color: '#fff' }; // green
  if (stars >= 3) return { bg: '#ca8a04', color: '#fff' }; // yellow
  if (stars >= 2) return { bg: '#9a3412', color: '#fff' }; // orange
  return { bg: '#6b7280', color: '#fff' };                  // gray
}

// Job data stored at score time so action panel can save/generate without re-fetching
interface _JobRecord {
  title: string;
  description: string;
  skills: string[];
  savedJobId?: string;  // set after first successful POST /api/v1/jobs
}
const _jobDataStore = new Map<string, _JobRecord>();

/** Trim the chip list based on star tier — fewer stars = less visual noise. */
function _filterChipsByStars(chips: string[], stars: number): string[] {
  const budgetChip = chips.find(c => c.startsWith('$'));
  const keywords   = chips.filter(c => !c.startsWith('$'));

  if (stars >= 4) return chips;                                      // all chips
  if (stars === 3) return [...keywords.slice(0, 3), ...(budgetChip ? [budgetChip] : [])]; // 3 keywords + budget
  if (stars === 2) return budgetChip ? [budgetChip] : [];            // budget only
  return [];                                                          // 1★: none
}

function _injectNotifBadge(row: Element, jobUrl: string): HTMLElement {
  const badge = document.createElement('span');
  badge.dataset.upapplyJob = _normalizeJobUrl(jobUrl);
  badge.style.cssText =
    'display:inline-flex;align-items:center;justify-content:center;' +
    'min-width:62px;height:22px;border-radius:11px;' +
    'font-size:13px;font-weight:700;color:#9ca3af;' +
    'background:#f3f4f6;border:1px solid #e5e7eb;' +
    'padding:0 6px;margin-left:8px;vertical-align:middle;' +
    'cursor:default;font-family:-apple-system,sans-serif;white-space:nowrap;letter-spacing:1px;';
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
let _contractImportBtnInjected = false;
let _workroomProposalBtnInjected = false;
let _tileObserver: IntersectionObserver | null = null;

/** Reset all scoring state — called on SPA navigation so stale flags never block a fresh run. */
function _resetNotifState(): void {
  _notifQueue.length = 0;
  _notifProcessing = false;
  _notifTotal = 0;
  _notifDone = 0;
  _scoredNotifUrls.clear();
  _scoreButtonInjected = false;
  _contractImportBtnInjected = false;
  _workroomProposalBtnInjected = false;
  if (_tileObserver) { _tileObserver.disconnect(); _tileObserver = null; }
  _clearAuthTokenCache();
  _closeActivePanel();
  _jobDataStore.clear();
  _hudVisibleRows.clear();
  if (_hud) _hud.style.display = 'none';
  document.getElementById('ua-score-btn')?.remove();
  document.getElementById('ua-contract-import-btn')?.remove();
  document.getElementById('ua-workroom-proposal-btn')?.remove();
  document.getElementById('ua-notif-progress')?.remove();
  document.getElementById('ua-low-connects')?.remove();
  document.getElementById('ua-login-prompt')?.remove();
  _cachedConnectsBalance = undefined;
  _lowConnectsAlertShown = false;
  _saveIconInjected.clear();
}

// Chip colour map — specific keywords get accent colours, budget is neutral
const _CHIP_COLORS: Record<string, { bg: string; color: string }> = {
  'MVP':       { bg: '#7c3aed', color: '#fff' },  // purple
  'SaaS':      { bg: '#0891b2', color: '#fff' },  // teal
  'Azure':     { bg: '#0078d4', color: '#fff' },  // Microsoft blue
  'SQL':       { bg: '#b45309', color: '#fff' },  // amber
  'Role':      { bg: '#374151', color: '#fff' },  // dark gray
  'AI':        { bg: '#4f46e5', color: '#fff' },  // indigo
  'Python':    { bg: '#2563eb', color: '#fff' },  // blue
  'React':     { bg: '#0e7490', color: '#fff' },  // cyan-700
  'API':       { bg: '#475569', color: '#fff' },  // slate
  'CTO':       { bg: '#6d28d9', color: '#fff' },  // violet (high-value)
  'Cloud':     { bg: '#0284c7', color: '#fff' },  // sky
  'Auto':      { bg: '#c2410c', color: '#fff' },  // orange (automation)
  'Urgent':    { bg: '#dc2626', color: '#fff' },  // red
  'Long-term': { bg: '#059669', color: '#fff' },  // emerald
};

const _CHIP_BASE_CSS =
  'display:inline-flex;align-items:center;justify-content:center;' +
  'height:20px;border-radius:10px;' +
  'font-size:11px;font-weight:600;' +
  'vertical-align:middle;' +
  'font-family:-apple-system,sans-serif;white-space:nowrap;letter-spacing:0.01em;';

function _makeChipEl(label: string): HTMLElement {
  const chip = document.createElement('span');
  const colors = _CHIP_COLORS[label] ?? { bg: '#166534', color: '#fff' };
  chip.style.cssText =
    _CHIP_BASE_CSS +
    `background:${colors.bg};color:${colors.color};padding:0 7px;margin-left:5px;`;
  chip.textContent = label;
  chip.dataset.upapplyChip = label;
  return chip;
}

function _injectChips(row: Element, chips: string[]): void {
  chips.forEach((label) => {
    const chip = _makeChipEl(label);
    const all = [...row.querySelectorAll<HTMLElement>('[data-upapply-job],[data-upapply-chip]')];
    const last = all[all.length - 1];
    if (last) last.after(chip);
  });
}

// ---------------------------------------------------------------------------
// Action panel — score details + Apply Queue + Cover Letter
// ---------------------------------------------------------------------------

let _activePanel: { el: HTMLElement; timer: ReturnType<typeof setTimeout> | null } | null = null;

function _closeActivePanel(): void {
  if (_activePanel) {
    _activePanel.el.remove();
    if (_activePanel.timer) clearTimeout(_activePanel.timer);
    _activePanel = null;
  }
}
function _cancelClosePanel(): void {
  if (_activePanel?.timer) { clearTimeout(_activePanel.timer); _activePanel.timer = null; }
}
function _scheduleClosePanel(): void {
  if (!_activePanel) return;
  _activePanel.timer = setTimeout(_closeActivePanel, 350);
}

/** Save the job to the API (idempotent — caches savedJobId). */
async function _ensureJobSaved(jobUrl: string, token: string, apiBase: string, fallbackTitle = ''): Promise<string | null> {
  const rec = _jobDataStore.get(jobUrl);
  if (rec?.savedJobId) return rec.savedJobId;

  // Lazy-fetch description if not already cached from scoring
  let title = rec?.title || fallbackTitle || 'Job';
  let description = rec?.description || '';
  let skills = rec?.skills || [];
  if (!description) {
    const d = await _fetchJobData(jobUrl);
    description = d.description || title;
    skills = d.skills || [];
  }

  const resp = await fetch(`${apiBase}/api/v1/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({
      upwork_url: jobUrl,
      title,
      description,
      skills_required: skills.length ? skills : undefined,
    }),
    signal: AbortSignal.timeout(25_000),
  });
  if (!resp.ok) return null;
  const job = await resp.json() as { id: string };
  if (rec) rec.savedJobId = job.id;
  else _jobDataStore.set(jobUrl, { title, description, skills, savedJobId: job.id });
  return job.id;
}

/** Inject a "+" toggle button after the job link that expands an inline description preview. */
function _injectPreviewToggle(row: Element, jobUrl: string): void {
  if (row.querySelector('[data-upapply-toggle]')) return;
  const link = row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
  if (!link) return;

  // Toggle button — inline, immediately after the job link
  const toggle = document.createElement('span');
  toggle.dataset.upapplyToggle = '1';
  toggle.textContent = '+';
  toggle.title = 'Preview job posting';
  toggle.style.cssText =
    'display:inline-flex;align-items:center;justify-content:center;' +
    'width:15px;height:15px;border-radius:50%;border:1.5px solid #9ca3af;' +
    'font-size:11px;font-weight:700;color:#6b7280;cursor:pointer;' +
    'margin-left:5px;vertical-align:middle;flex-shrink:0;' +
    'transition:background 0.15s,color 0.15s,border-color 0.15s;';

  // Outer: animates max-height. Inner: carries padding (avoids animation glitch).
  const preview = document.createElement('div');
  preview.dataset.upapplyPreview = '1';
  preview.style.cssText = 'max-height:0;overflow:hidden;transition:max-height 0.28s ease;';

  const previewInner = document.createElement('div');
  previewInner.style.cssText =
    'padding:8px 10px;font-size:12px;line-height:1.6;color:#374151;' +
    'background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;' +
    'white-space:pre-wrap;word-break:break-word;margin-top:5px;';
  preview.appendChild(previewInner);

  let open = false;
  let loaded = false;

  toggle.addEventListener('click', async (e) => {
    e.stopPropagation();
    e.preventDefault(); // prevent <a> navigation when toggle is inside the link
    open = !open;

    if (open) {
      toggle.textContent = '−';
      toggle.style.background = '#1d4ed8';
      toggle.style.color = '#fff';
      toggle.style.borderColor = '#1d4ed8';

      if (!loaded) {
        previewInner.textContent = 'Loading…';
        preview.style.maxHeight = '120px';
        preview.style.overflowY = 'auto';

        let description = _jobDataStore.get(jobUrl)?.description || '';
        if (!description) {
          const d = await _fetchJobData(jobUrl);
          description = d.description || '(No description available)';
          const rec = _jobDataStore.get(jobUrl);
          if (rec) rec.description = description;
          else _jobDataStore.set(jobUrl, { title: link.textContent?.trim() || '', description, skills: d.skills });
        }
        previewInner.textContent = description;
        loaded = true;
      } else {
        preview.style.maxHeight = '120px';
        preview.style.overflowY = 'auto';
      }
    } else {
      toggle.textContent = '+';
      toggle.style.background = '';
      toggle.style.color = '#6b7280';
      toggle.style.borderColor = '#9ca3af';
      preview.style.maxHeight = '0';
      preview.style.overflowY = 'hidden';
    }
  });

  // Append toggle INSIDE the <a> so it stays on the same line as the link text
  link.appendChild(toggle);
  // Insert preview block right after the <a> element (collapses to 0 height until opened)
  link.after(preview);
}

/** Small always-visible inline checkbox injected directly into the notification row. */
function _makeInlineAction(
  text: string,
  accentColor: string,
  onClick: (cb: HTMLElement, lbl: HTMLElement) => Promise<void>,
): HTMLElement {
  const wrap = document.createElement('span');
  wrap.style.cssText =
    'display:inline-flex;align-items:center;gap:3px;cursor:pointer;' +
    'margin-left:7px;vertical-align:middle;user-select:none;';

  const cb = document.createElement('span');
  cb.style.cssText =
    `display:inline-flex;align-items:center;justify-content:center;` +
    `width:13px;height:13px;border-radius:3px;border:1.5px solid ${accentColor};` +
    `font-size:9px;flex-shrink:0;transition:background 0.15s,border-color 0.15s;`;

  const lbl = document.createElement('span');
  lbl.textContent = text;
  lbl.style.cssText = `font-size:10px;color:${accentColor};font-weight:600;white-space:nowrap;`;

  wrap.appendChild(cb);
  wrap.appendChild(lbl);

  let running = false;
  wrap.addEventListener('click', (e) => {
    e.stopPropagation();
    if (running || cb.dataset.done === '1') return;
    running = true;
    lbl.style.opacity = '0.6';
    onClick(cb, lbl).finally(() => { running = false; lbl.style.opacity = '1'; });
  });
  return wrap;
}


async function _queueJobAction(jobUrl: string, title: string, cb: HTMLElement, lbl: HTMLElement): Promise<void> {
  const token = await _getAuthToken();
  if (!token) { lbl.textContent = '× Not logged in'; lbl.style.color = '#ef4444'; return; }
  const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
  try {
    lbl.textContent = '⟳ Saving job…';
    const jobId = await _ensureJobSaved(jobUrl, token, apiBase, title);
    if (!jobId) throw new Error('save failed');
    lbl.textContent = '⟳ Queuing…';
    const r = await fetch(`${apiBase}/api/v1/applications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ job_id: jobId }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) throw new Error(`${r.status}`);
    cb.textContent = '✓'; cb.dataset.done = '1';
    cb.style.cssText += 'background:#16a34a;border-color:#16a34a;color:#fff;';
    lbl.textContent = 'Apply Queue'; lbl.style.color = '#16a34a';
  } catch {
    lbl.textContent = '× Failed'; lbl.style.color = '#ef4444';
  }
}

async function _coverLetterAction(jobUrl: string, title: string, cb: HTMLElement, lbl: HTMLElement): Promise<void> {
  const token = await _getAuthToken();
  if (!token) { lbl.textContent = '× Not logged in'; lbl.style.color = '#ef4444'; return; }
  const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
  try {
    lbl.textContent = '⟳ Saving job…';
    const jobId = await _ensureJobSaved(jobUrl, token, apiBase, title);
    lbl.textContent = '⟳ Generating…';
    const body = jobId
      ? { job_id: jobId, include_call_offer: true }
      : { job_data: { upwork_url: jobUrl, title, description: _jobDataStore.get(jobUrl)?.description || title }, include_call_offer: true };
    const r = await fetch(`${apiBase}/api/v1/jobs/cover-letters/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60_000),
    });
    if (!r.ok) throw new Error(`${r.status}`);
    cb.textContent = '✓'; cb.dataset.done = '1';
    cb.style.cssText += 'background:#1d4ed8;border-color:#1d4ed8;color:#fff;';
    lbl.textContent = '+ Cover Letter'; lbl.style.color = '#1d4ed8';
  } catch {
    lbl.textContent = '× Failed'; lbl.style.color = '#ef4444';
  }
}

function _showActionPanel(badge: HTMLElement, jobUrl: string, title: string, stars: number, score: number, chips: string[], reason: string): void {
  _closeActivePanel();

  const rect = badge.getBoundingClientRect();
  // Guard: badge not yet rendered (zero-size rect from race with Upwork's layout) — retry after paint
  if (rect.width === 0 || rect.bottom === 0) {
    requestAnimationFrame(() => _showActionPanel(badge, jobUrl, title, stars, score, chips, reason));
    return;
  }
  const NAV_H = 72; // Upwork nav bar height — panel must never overlap it
  const panelLeft = Math.max(8, Math.min(rect.left, window.innerWidth - 330 - 8));
  const rawTop = rect.bottom + 6;
  const openAbove = (window.innerHeight - rect.bottom) < 160;

  const panel = document.createElement('div');
  panel.style.cssText = [
    'position:fixed',
    openAbove ? `bottom:${window.innerHeight - rect.top + 6}px` : `top:${Math.max(NAV_H, rawTop)}px`,
    `left:${panelLeft}px`,
    'z-index:2147483647',
    'background:#fff',
    'border:1px solid #e5e7eb',
    'border-radius:10px',
    'box-shadow:0 4px 18px rgba(0,0,0,0.16)',
    'padding:10px 12px',
    'min-width:240px',
    'max-width:320px',
    'font-family:system-ui,-apple-system,sans-serif',
  ].join(';');

  // Row 1: stars pill + score + budget
  const { bg, color } = _starsColors(stars);
  const budgetChip = chips.find(c => c.startsWith('$'));
  const topRow = document.createElement('div');
  topRow.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px;';

  const starPill = document.createElement('span');
  starPill.textContent = _starsDisplay(stars);
  starPill.style.cssText = `background:${bg};color:${color};font-size:12px;font-weight:700;border-radius:6px;padding:2px 8px;letter-spacing:1px;flex-shrink:0;`;
  topRow.appendChild(starPill);

  const scoreEl = document.createElement('span');
  scoreEl.textContent = `${score}/100`;
  scoreEl.style.cssText = 'font-size:12px;font-weight:700;color:#374151;';
  topRow.appendChild(scoreEl);

  if (budgetChip) {
    const budgetEl = document.createElement('span');
    budgetEl.textContent = budgetChip;
    budgetEl.style.cssText = 'font-size:11px;font-weight:600;color:#059669;background:#d1fae5;padding:1px 6px;border-radius:4px;margin-left:auto;white-space:nowrap;';
    topRow.appendChild(budgetEl);
  }
  panel.appendChild(topRow);

  // Bonus chips (those hidden by star tier)
  const visibleSet = new Set(_filterChipsByStars(chips, stars));
  const bonusChips = chips.filter(c => !visibleSet.has(c) && !c.startsWith('$'));
  if (bonusChips.length) {
    const chipRow = document.createElement('div');
    chipRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px;';
    bonusChips.forEach(label => {
      const c = _makeChipEl(label);
      c.style.marginLeft = '0';
      chipRow.appendChild(c);
    });
    panel.appendChild(chipRow);
  }

  // Reason text
  if (reason) {
    const reasonEl = document.createElement('div');
    reasonEl.textContent = reason.length > 110 ? reason.slice(0, 110) + '…' : reason;
    reasonEl.style.cssText = 'font-size:11px;color:#6b7280;line-height:1.4;margin-bottom:8px;';
    panel.appendChild(reasonEl);
  }

  document.body.appendChild(panel);
  _activePanel = { el: panel, timer: null };

  panel.addEventListener('mouseenter', _cancelClosePanel);
  panel.addEventListener('mouseleave', _scheduleClosePanel);

  // Close on outside click
  const closeOnClick = (e: MouseEvent) => {
    if (!panel.contains(e.target as Node) && e.target !== badge) {
      _closeActivePanel();
      document.removeEventListener('click', closeOnClick, true);
    }
  };
  setTimeout(() => document.addEventListener('click', closeOnClick, true), 0);
}

function _attachBadgePanel(badge: HTMLElement, jobUrl: string, title: string, stars: number, score: number, chips: string[], reason: string): void {
  badge.style.cursor = 'pointer';
  badge.addEventListener('mouseenter', () => {
    _cancelClosePanel();
    _showActionPanel(badge, jobUrl, title, stars, score, chips, reason);
  });
  badge.addEventListener('mouseleave', _scheduleClosePanel);
  badge.addEventListener('click', (e) => {
    e.stopPropagation();
    if (_activePanel) { _closeActivePanel(); }
    else { _showActionPanel(badge, jobUrl, title, stars, score, chips, reason); }
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
    'position:fixed;bottom:80px;right:16px;z-index:2147483647;' +
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
// Fetch job data via Upwork's internal GraphQL API
// Content script runs on upwork.com so cookies are sent automatically.
// This avoids opening background tabs and bypasses bot-detection entirely.
// ---------------------------------------------------------------------------

function _getUpworkCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|;\\s*)${encodeURIComponent(name)}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

interface JobFetchResult {
  description: string;
  pageText: string;
  budgetAmount: string | null;
  budgetType: 'hourly' | 'fixed' | null;
  skills: string[];
  clientCountry: string | null;
  connectsRequired: number | null;
}

/**
 * Primary path: call Upwork's internal GraphQL API with the job UID.
 * Uses the session cookies already present in the browser.
 */
async function _fetchJobViaGraphQL(jobUid: string): Promise<JobFetchResult | null> {
  // Upwork stores the OAuth bearer token in a JS-readable cookie
  const authToken = _getUpworkCookie('oauth2_global_js_token');
  // CSRF double-submit cookie (Angular/Vue SPA pattern)
  const xsrfToken = _getUpworkCookie('XSRF-TOKEN') || _getUpworkCookie('x-odesk-csrf-token');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  if (xsrfToken) headers['X-XSRF-TOKEN'] = xsrfToken;

  // Minimal query — only the fields we need
  // Note: Upwork changed the argument from jobUid → jobPostingId (same ~UID value)
  const query = `query jobPosting($jobPostingId:String!){
    jobPosting(jobPostingId:$jobPostingId){
      id title description contractorTier jobType
      hourlyBudgetMin hourlyBudgetMax
      amount{ amount currencyCode }
      skills{ prettyName }
      client{ location{ country } }
      connectsRequired
    }
  }`;

  const resp = await fetch('/api/graphql/v1', {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify({ operationName: 'jobPosting', query, variables: { jobPostingId: jobUid } }),
    signal: AbortSignal.timeout(8000),
  });

  logger.log('[UpApply] GraphQL status:', resp.status, 'for', jobUid);
  if (!resp.ok) return null;

  const json = await resp.json() as { data?: { jobPosting?: Record<string, unknown> }; errors?: unknown[] };
  logger.log('[UpApply] GraphQL response:', JSON.stringify(json).slice(0, 400));

  const job = json?.data?.jobPosting;
  if (!job) return null;

  // Budget
  let budgetAmount: string | null = null;
  let budgetType: 'hourly' | 'fixed' | null = null;
  const hMin = job.hourlyBudgetMin as number | null;
  const hMax = job.hourlyBudgetMax as number | null;
  const fixedAmt = (job.amount as Record<string, unknown> | null)?.amount as number | null;

  if (hMin != null || hMax != null) {
    budgetType = 'hourly';
    const min = hMin != null ? `$${Math.round(hMin)}` : null;
    const max = hMax != null ? `$${Math.round(hMax)}` : null;
    budgetAmount = [min, max].filter(Boolean).join('-');
  } else if (fixedAmt != null) {
    budgetType = 'fixed';
    budgetAmount = `$${Math.round(fixedAmt).toLocaleString()}`;
  }

  const description = (job.description as string) || '';
  const skillsRaw = (job.skills as Array<{ prettyName?: string }> | null) || [];
  const skills = skillsRaw.map(s => s.prettyName || '').filter(Boolean);
  const clientData = job.client as { location?: { country?: string } } | null;
  const clientCountry = clientData?.location?.country || null;
  const connectsRequired = typeof job.connectsRequired === 'number' ? job.connectsRequired : null;
  return { description, pageText: description, budgetAmount, budgetType, skills, clientCountry, connectsRequired };
}

// _fetchJobViaHTML removed: Upwork is CSR so the HTML shell is nearly empty,
// and DOMParser.parseFromString on a ~1MB page runs synchronously on the
// main thread. With 3 concurrent workers this caused "Page Unresponsive".
// GraphQL is the only fetch path; title is used as fallback if it returns empty.

/** Fetch job data via GraphQL only. HTML fallback removed — Upwork is CSR so
 *  the HTML shell is nearly empty and DOMParser on a ~1MB page runs synchronously
 *  on the main thread, causing "Page Unresponsive" when multiple workers hit it. */
async function _fetchJobData(jobUrl: string): Promise<JobFetchResult> {
  const uidMatch = jobUrl.match(/(~[0-9a-f]+)/i);
  if (uidMatch) {
    const result = await _fetchJobViaGraphQL(uidMatch[1]).catch(() => null);
    if (result && result.description.length > 0) {
      logger.log('[UpApply] GraphQL success:', { descLen: result.description.length, budget: result.budgetAmount });
      return result;
    }
  }
  return { description: '', pageText: '', budgetAmount: null, budgetType: null, skills: [], clientCountry: null, connectsRequired: null };
}

// ---------------------------------------------------------------------------
// Auth token — read once from chrome.storage.local, cached in memory.
// Content script calls the API directly; no service worker round trip needed.
// ---------------------------------------------------------------------------

let _contentAuthToken: string | null | undefined = undefined;

async function _getAuthToken(): Promise<string | null> {
  if (_contentAuthToken !== undefined) return _contentAuthToken;
  if (chrome?.storage?.local) {
    const stored = await chrome.storage.local.get('authToken');
    _contentAuthToken = (stored['authToken'] as string) || null;
  } else {
    // chrome.storage unavailable in this module context — ask background SW
    try {
      const resp = await chrome.runtime.sendMessage({ type: 'GET_AUTH_TOKEN' }) as { token: string | null };
      _contentAuthToken = resp?.token || null;
    } catch {
      _contentAuthToken = null;
    }
  }
  return _contentAuthToken;
}

/** Called on SPA navigation to force re-read of token on next scoring run. */
function _clearAuthTokenCache(): void {
  _contentAuthToken = undefined;
}

// ---------------------------------------------------------------------------
// Connects balance — fetched once per scoring session from Upwork's GraphQL
// ---------------------------------------------------------------------------

let _cachedConnectsBalance: number | null | undefined = undefined;
let _lowConnectsAlertShown = false;

async function _fetchUserConnects(): Promise<number | null> {
  if (_cachedConnectsBalance !== undefined) return _cachedConnectsBalance;

  const authToken = _getUpworkCookie('oauth2_global_js_token');
  const xsrfToken = _getUpworkCookie('XSRF-TOKEN') || _getUpworkCookie('x-odesk-csrf-token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  if (xsrfToken) headers['X-XSRF-TOKEN'] = xsrfToken;

  const query = `query userConnects {
    currentUserConnectsBalance { connectsBalance }
  }`;
  try {
    const resp = await fetch('/api/graphql/v1', {
      method: 'POST', headers, credentials: 'include',
      body: JSON.stringify({ operationName: 'userConnects', query }),
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) { _cachedConnectsBalance = null; return null; }
    const json = await resp.json() as {
      data?: { currentUserConnectsBalance?: { connectsBalance?: number } };
    };
    const balance = json?.data?.currentUserConnectsBalance?.connectsBalance ?? null;
    _cachedConnectsBalance = balance;
    logger.log('[UpApply] connects balance:', balance);
    return balance;
  } catch {
    _cachedConnectsBalance = null;
    return null;
  }
}

/** Show a one-time login prompt overlay when the user clicks Score without being
 *  logged in to UpApply. Dismissible; auto-removes after 12s. */
function _showLoginPrompt(): void {
  if (document.getElementById('ua-login-prompt')) return;

  const el = document.createElement('div');
  el.id = 'ua-login-prompt';
  el.style.cssText =
    'position:fixed;top:64px;left:50%;transform:translateX(-50%);z-index:2147483647;' +
    'background:#1e3a5f;color:#fff;' +
    'font-size:13px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'padding:10px 18px;border-radius:22px;' +
    'box-shadow:0 3px 14px rgba(0,0,0,0.4);white-space:nowrap;' +
    'display:flex;align-items:center;gap:10px;';

  const msg = document.createElement('span');
  msg.textContent = '🔒 Open the UpApply extension and log in to score jobs';

  const dismiss = document.createElement('span');
  dismiss.textContent = '×';
  dismiss.style.cssText =
    'cursor:pointer;opacity:0.6;font-size:16px;line-height:1;flex-shrink:0;';
  dismiss.addEventListener('click', () => el.remove());

  el.appendChild(msg);
  el.appendChild(dismiss);
  document.body.appendChild(el);

  // Auto-remove after 12s
  setTimeout(() => el.remove(), 12_000);
}

// ---------------------------------------------------------------------------
// 💾 Save icon — injected after every a[href*="/jobs/~"] on any Upwork page
// ---------------------------------------------------------------------------

const _saveIconInjected = new Set<string>(); // tracks normalized URLs already injected

async function _handleSaveJob(jobUrl: string, title: string, icon: HTMLElement): Promise<void> {
  const token = await _getAuthToken();
  if (!token) { _showLoginPrompt(); return; }

  const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL']
    || 'https://upapply-api.onrender.com';

  icon.textContent = '⟳';
  icon.title = 'Saving…';
  icon.style.cursor = 'default';
  icon.style.opacity = '1';

  try {
    // Fetch full job data via GraphQL so we store description + skills
    const jobData = await _fetchJobData(jobUrl);
    const description = jobData.description || title;

    // Save (idempotent — returns existing job if already saved)
    const saveResp = await fetch(`${apiBase}/api/v1/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        upwork_url: jobUrl,
        title: title || 'Job',
        description,
        skills_required: jobData.skills.length ? jobData.skills : undefined,
        client_info: jobData.clientCountry ? { location: jobData.clientCountry } : undefined,
      }),
      signal: AbortSignal.timeout(25_000),
    });
    if (!saveResp.ok) throw new Error(`save ${saveResp.status}`);
    const job = await saveResp.json() as { id: string };

    // Check if we already have a past proposal for this job URL
    const propResp = await fetch(
      `${apiBase}/api/v1/proposals?job_url=${encodeURIComponent(jobUrl)}&limit=1`,
      { headers: { 'Authorization': `Bearer ${token}` }, signal: AbortSignal.timeout(5_000) },
    ).catch(() => null);
    const proposals = (propResp?.ok ? await propResp.json() : []) as unknown[];
    const hasPastProposal = Array.isArray(proposals) && proposals.length > 0;

    if (hasPastProposal) {
      // Already in our corpus — surface as past reference, no re-queue
      icon.textContent = '📁';
      icon.style.cssText += 'background:#7c3aed;color:#fff;border-radius:4px;padding:0 3px;font-size:10px;';
      icon.title = 'UpApply: saved — past proposal exists';
    } else {
      // New job — add to apply queue
      await fetch(`${apiBase}/api/v1/applications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ job_id: job.id }),
        signal: AbortSignal.timeout(10_000),
      }).catch(() => {});
      icon.textContent = '✓';
      icon.style.cssText += 'background:#16a34a;color:#fff;border-radius:4px;padding:0 3px;font-size:10px;';
      icon.title = 'UpApply: saved & queued for apply';
    }
    icon.dataset.done = '1';

    // Also stash job data so preview/action panel work without re-fetching
    if (!_jobDataStore.has(jobUrl)) {
      _jobDataStore.set(jobUrl, { title: title || 'Job', description, skills: jobData.skills });
    }
  } catch {
    icon.textContent = '!';
    icon.style.cssText += 'background:#dc2626;color:#fff;border-radius:4px;padding:0 3px;font-size:10px;';
    icon.title = 'UpApply: save failed — click to retry';
    icon.style.cursor = 'pointer';
    icon.dataset.done = '';  // allow retry
  }
}

function _injectSaveIcon(link: HTMLAnchorElement): void {
  // Never inject inside UpApply's own elements
  if (link.closest('[data-upapply-job],[data-upapply-chip],[data-upapply-actions],[data-upapply-toggle]')) return;
  // Already injected next to this exact link element
  if (link.nextElementSibling?.getAttribute?.('data-upapply-save') === '1') return;

  const jobUrl = _normalizeJobUrl(link.href);
  const dedupeKey = jobUrl;
  if (_saveIconInjected.has(dedupeKey)) return;
  _saveIconInjected.add(dedupeKey);

  const title = link.textContent?.trim() || '';

  const icon = document.createElement('span');
  icon.setAttribute('data-upapply-save', '1');
  icon.textContent = '💾';
  icon.title = 'UpApply: save this job';
  icon.style.cssText =
    'display:inline-flex;align-items:center;justify-content:center;' +
    'min-width:16px;height:16px;font-size:11px;line-height:1;cursor:pointer;' +
    'margin-left:4px;vertical-align:middle;flex-shrink:0;' +
    'opacity:0.45;transition:opacity 0.15s;';

  icon.addEventListener('mouseenter', () => { if (!icon.dataset.done) icon.style.opacity = '1'; });
  icon.addEventListener('mouseleave', () => { if (icon.dataset.done !== '1') icon.style.opacity = '0.45'; });

  let running = false;
  icon.addEventListener('click', async (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (running || icon.dataset.done === '1') return;
    running = true;
    await _handleSaveJob(jobUrl, title, icon);
    running = false;
  });

  link.after(icon);
}

/** Attach save icons to all job links on the current page (safe to call repeatedly). */
function _attachSaveIcons(): void {
  document.querySelectorAll<HTMLAnchorElement>('a[href*="/jobs/~"]').forEach(_injectSaveIcon);
}

/** Show a sticky banner when available connects < connectsRequired + HIGHEST_BID.
 *  HIGHEST_BID = 6 represents the maximum extra connects a boosted proposal costs
 *  on top of the base job requirement — so this fires before the user genuinely
 *  can't submit at max bid on the next job. */
function _checkLowConnects(available: number, connectsRequired: number): void {
  const HIGHEST_BID = 6;
  if (available >= connectsRequired + HIGHEST_BID) return; // enough — no alert
  if (_lowConnectsAlertShown) return;
  if (document.getElementById('ua-low-connects')) return;
  _lowConnectsAlertShown = true;

  const el = document.createElement('div');
  el.id = 'ua-low-connects';
  el.style.cssText =
    'position:fixed;top:64px;left:50%;transform:translateX(-50%);z-index:2147483647;' +
    'background:#7c2d12;color:#fff;' +
    'font-size:12px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'padding:6px 16px;border-radius:20px;' +
    'box-shadow:0 2px 10px rgba(0,0,0,0.35);white-space:nowrap;' +
    'display:flex;align-items:center;gap:10px;';

  const msg = document.createElement('span');
  msg.textContent =
    `⚠ Low connects: ${available} available — job needs ${connectsRequired}, max bid needs ${connectsRequired + HIGHEST_BID}`;

  const buyLink = document.createElement('a');
  buyLink.textContent = 'Buy more';
  buyLink.style.cssText =
    'color:#fde68a;text-decoration:underline;cursor:pointer;font-size:11px;flex-shrink:0;';
  buyLink.addEventListener('click', (e) => {
    e.preventDefault();
    window.open('https://www.upwork.com/nx/account-settings/connects', '_blank');
  });

  const dismiss = document.createElement('span');
  dismiss.textContent = '×';
  dismiss.style.cssText =
    'cursor:pointer;opacity:0.7;font-size:15px;line-height:1;flex-shrink:0;';
  dismiss.addEventListener('click', () => el.remove());

  el.appendChild(msg);
  el.appendChild(buyLink);
  el.appendChild(dismiss);
  document.body.appendChild(el);
}

/** Score a single item and update its badge. Never throws. */
async function _scoreOneNotif(item: _NotifQueueItem): Promise<void> {
  const uid = item.jobUrl.match(/(~[0-9a-f]+)/i)?.[1] ?? item.jobUrl.slice(-12);
  logger.log(`[UpApply] score START  ${uid} "${item.title.slice(0, 40)}"`);
  try {
    // 1. Persistent cache check
    // sc_v9: added description/title/skills so preview toggle never needs to re-fetch
    const CACHE_KEY = `sc_v9_${item.jobUrl}`;
    const CACHE_TTL = 24 * 60 * 60 * 1000;
    type CacheEntry = { score: number; chips: string[]; reason?: string; title?: string; description?: string; skills?: string[]; ts: number };
    const storageAvailable = !!(chrome?.storage?.local);
    if (storageAvailable) {
      const cacheStore = await chrome.storage.local.get(CACHE_KEY);
      const cached = cacheStore[CACHE_KEY] as CacheEntry | undefined;
      if (cached && Date.now() - cached.ts < CACHE_TTL) {
        logger.log(`[UpApply] score CACHED ${uid} score=${cached.score}`);
        // Restore job data so preview toggle and action panel don't need to re-fetch
        if (!_jobDataStore.has(item.jobUrl)) {
          _jobDataStore.set(item.jobUrl, {
            title: cached.title || item.title,
            description: cached.description || '',
            skills: cached.skills || [],
          });
        }
        _applyBadgeResult(item, cached.score, cached.chips, true, cached.reason);
        return;
      }
    } else {
      // Fallback: ask background for cached value
      try {
        const resp = await chrome.runtime.sendMessage({ type: 'GET_NOTIF_CACHE', key: CACHE_KEY }) as { value: CacheEntry | null };
        const cached = resp?.value;
        if (cached && Date.now() - cached.ts < CACHE_TTL) {
          logger.log(`[UpApply] score CACHED(SW) ${uid} score=${cached.score}`);
          if (!_jobDataStore.has(item.jobUrl)) {
            _jobDataStore.set(item.jobUrl, {
              title: cached.title || item.title,
              description: cached.description || '',
              skills: cached.skills || [],
            });
          }
          _applyBadgeResult(item, cached.score, cached.chips, true, cached.reason);
          return;
        }
      } catch { /* skip cache on error */ }
    }

    // 2. Auth token (read once per scoring session, cached in memory)
    const token = await _getAuthToken();
    if (!token) {
      item.badge.textContent = '?';
      item.badge.style.background = '#6b7280';
      item.badge.title = 'UpApply: not logged in';
      return;
    }

    // 3. Fetch job description via Upwork GraphQL (content script context, 8s timeout)
    logger.log(`[UpApply] score FETCH  ${uid}`);
    const jobData = await _fetchJobData(item.jobUrl);
    const description = jobData.description || ''; // real description; don't fall back to title
    const scoreText = description || item.title;   // scoring API needs something to analyze
    logger.log(`[UpApply] score FETCH  ${uid} done — descLen=${description.length} budget=${jobData.budgetAmount} connects=${jobData.connectsRequired} source=${jobData.description ? 'graphql' : 'title-fallback'}`);

    // Fire-and-forget connects check — never blocks scoring
    if (jobData.connectsRequired != null) {
      _fetchUserConnects().then(balance => {
        if (balance != null) _checkLowConnects(balance, jobData.connectsRequired!);
      }).catch(() => {});
    }

    // 4. Score via API directly (no SW message channel — eliminates zombie channel accumulation)
    logger.log(`[UpApply] score SCORE  ${uid}`);
    const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL']
      || 'https://upapply-api.onrender.com';
    const apiResp = await fetch(`${apiBase}/api/v1/jobs/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        title: item.title || 'Job',
        description: scoreText,
        skills_required: jobData.skills.length > 0 ? jobData.skills : undefined,
        client_info: jobData.clientCountry ? { location: jobData.clientCountry } : undefined,
      }),
      signal: AbortSignal.timeout(25_000),
    });

    if (!apiResp.ok) throw new Error(`API ${apiResp.status}`);
    const data = await apiResp.json() as { match_score: number; reason?: string };
    logger.log(`[UpApply] score SCORE  ${uid} done — score=${data.match_score}`);

    // 5. Compute chips and cache result
    const chips = detectNotifChips(item.title, scoreText, jobData.budgetAmount, jobData.budgetType);
    const cacheValue = {
      score: data.match_score, chips, reason: data.reason,
      title: item.title, description, skills: jobData.skills,
      ts: Date.now(),
    };
    if (storageAvailable) {
      await chrome.storage.local.set({ [CACHE_KEY]: cacheValue });
    } else {
      chrome.runtime.sendMessage({ type: 'SET_NOTIF_CACHE', key: CACHE_KEY, value: cacheValue }).catch(() => {});
    }

    // Store full job data so the action panel can save/generate without re-fetching
    _jobDataStore.set(item.jobUrl, {
      title: item.title,
      description,
      skills: jobData.skills,
    });

    _applyBadgeResult(item, data.match_score, chips, false, data.reason);
    logger.log(`[UpApply] score DONE   ${uid}`);
  } catch (err) {
    console.error(`[UpApply] score ERROR  ${uid}`, err);
    item.badge.textContent = '?';
    item.badge.style.background = '#6b7280';
    item.badge.title = 'UpApply: scoring error';
  }
}

function _applyBadgeResult(item: _NotifQueueItem, score: number, chips: string[], fromCache: boolean, reason?: string): void {
  const rounded = Math.round(score);
  const stars = _computeStars(rounded, chips);
  const { bg, color } = _starsColors(stars);
  item.badge.style.background = bg;
  item.badge.style.color = color;
  item.badge.style.border = 'none';
  item.badge.textContent = _starsDisplay(stars);
  item.badge.title = `UpApply: ${stars}★  (score ${rounded}/100)${fromCache ? ' · cached' : ''} — click for details`;
  const visibleChips = _filterChipsByStars(chips, stars);
  if (visibleChips.length) _injectChips(item.row, visibleChips);
  _attachBadgePanel(item.badge, item.jobUrl, item.title, stars, rounded, chips, reason ?? '');

  // Inline action checkboxes — always visible on the row, no hover required
  if (!item.row.querySelector('[data-upapply-actions]')) {
    const actionsWrap = document.createElement('span');
    actionsWrap.dataset.upapplyActions = '1';
    actionsWrap.style.cssText = 'display:inline-flex;align-items:center;';
    actionsWrap.appendChild(
      _makeInlineAction('Queue', '#16a34a', (c, l) => _queueJobAction(item.jobUrl, item.title, c, l)),
    );
    actionsWrap.appendChild(
      _makeInlineAction('Letter', '#1d4ed8', (c, l) => _coverLetterAction(item.jobUrl, item.title, c, l)),
    );
    // Insert after the last badge/chip in the row
    const allInRow = [...item.row.querySelectorAll<HTMLElement>('[data-upapply-job],[data-upapply-chip]')];
    const lastEl = allInRow[allInRow.length - 1] ?? item.badge;
    lastEl.after(actionsWrap);
  }

  // Preview toggle "+" after the job link
  _injectPreviewToggle(item.row, item.jobUrl);

  // Inject scoring reason as a blue line below the job title link
  if (reason) {
    const existingReason = item.row.querySelector('[data-upapply-reason]');
    if (!existingReason) {
      const link = item.row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
      if (link) {
        const reasonEl = document.createElement('span');
        reasonEl.setAttribute('data-upapply-reason', '1');
        reasonEl.textContent = reason;
        reasonEl.style.cssText = 'display:block;color:#3b82f6;font-size:11px;line-height:1.4;margin-top:3px;font-weight:normal;';
        link.insertAdjacentElement('afterend', reasonEl);
      }
    }
  }

  // Persist to scoredJobsCache for the sidebar's Find view
  if (chrome?.storage?.local) {
    chrome.storage.local.get('scoredJobsCache', (data) => {
      const cache: Record<string, { url: string; title: string; score: number; chips: string[]; scored_at: string }> =
        data.scoredJobsCache || {};
      cache[item.jobUrl] = {
        url: item.jobUrl,
        title: item.title || '',
        score: rounded,
        chips,
        scored_at: new Date().toISOString(),
      };
      // Cap at 500 entries — evict oldest by scored_at
      const entries = Object.values(cache).sort((a, b) => b.scored_at.localeCompare(a.scored_at));
      const capped: typeof cache = {};
      entries.slice(0, 500).forEach(e => { capped[e.url] = e; });
      chrome.storage.local.set({ scoredJobsCache: capped });
    });
  }

  // Fire-and-forget write to API job-reviews for persistence across sessions
  _getAuthToken().then(token => {
    if (!token) return;
    const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
    // Parse budget from chips
    const budgetChip = chips.find(c => c.startsWith('$'));
    const budgetType = budgetChip?.includes('/hr') ? 'hourly' : budgetChip ? 'fixed' : undefined;
    fetch(`${apiBase}/api/v1/job-reviews`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        upwork_job_url: item.jobUrl,
        job_title: item.title || '',
        ai_score: score,
        chips,
        budget_amount: budgetChip || null,
        budget_type: budgetType || null,
        scored_at: new Date().toISOString(),
      }),
      signal: AbortSignal.timeout(10_000),
    }).catch(() => {}); // silent — never block badge display
  }).catch(() => {});

  // Register this row with the scroll HUD so its score shows while it's visible
  _observeRowForHud(item.row);
}

// ---------------------------------------------------------------------------
// Floating scroll HUD — shows score of the topmost visible scored job
// ---------------------------------------------------------------------------
let _hud: HTMLElement | null = null;
const _hudVisibleRows = new Set<Element>();
let _hudObserver: IntersectionObserver | null = null;

function _refreshHud(): void { /* HUD removed — inline star badges are sufficient */ }

function _observeRowForHud(row: Element): void {
  if (!_hudObserver) {
    _hudObserver = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) _hudVisibleRows.add(e.target);
        else _hudVisibleRows.delete(e.target);
      }
      _refreshHud();
    }, { threshold: 0.15 });
  }
  _hudObserver.observe(row);
}

/** Ping /health until the server responds (handles Render free-tier cold-starts).
 *  Shows a "Waking up…" indicator; resolves true when alive, false on timeout. */
async function _warmupServer(): Promise<boolean> {
  const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL']
    || 'https://upapply-api.onrender.com';

  // Quick probe first — if already awake this resolves in < 200ms
  try {
    const probe = await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(3000) });
    if (probe.ok) return true;
  } catch { /* sleeping — fall through to slow warmup */ }

  // Server is asleep: show indicator and wait up to 60s for cold-start
  const bar = _getOrCreateProgressBar();
  const label = bar.querySelector<HTMLElement>('#ua-notif-label')!;
  label.textContent = 'UpApply: waking up server…';
  bar.style.opacity = '1';

  try {
    const resp = await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(60_000) });
    return resp.ok;
  } catch {
    label.textContent = 'UpApply: server unreachable';
    return false;
  }
}

async function _processNotifQueue(): Promise<void> {
  if (_notifProcessing) {
    logger.warn('[UpApply] _processNotifQueue called while already processing — skipped');
    return;
  }
  _notifProcessing = true;
  _notifDone = 0;
  _updateProgressBar(0, _notifTotal);

  const items = _notifQueue.splice(0);
  logger.log(`[UpApply] queue START total=${items.length}`);

  // Check auth before doing any work — show a login prompt and bail if missing
  const token = await _getAuthToken();
  if (!token) {
    logger.warn('[UpApply] not logged in — aborting queue');
    items.forEach(item => {
      item.badge.textContent = '–';
      item.badge.style.background = '#6b7280';
      item.badge.title = 'UpApply: not logged in';
    });
    _showLoginPrompt();
    _notifProcessing = false;
    _hideProgressBar();
    return;
  }

  // Warm up the Render server before scoring — free tier spins down after
  // inactivity and cold-starts take 30–60s, longer than the 25s API timeout.
  const alive = await _warmupServer();
  if (!alive) {
    logger.warn('[UpApply] server unreachable — aborting queue');
    items.forEach(item => {
      item.badge.textContent = '✕';
      item.badge.style.background = '#6b7280';
      item.badge.title = 'UpApply: server unreachable';
    });
    _notifProcessing = false;
    _hideProgressBar();
    return;
  }

  try {
    for (const item of items) {
      // Yield to the browser event loop before each item.
      // One item at a time prevents concurrent DOM updates from stacking
      // Vue re-renders, which is what causes "Page Unresponsive".
      await new Promise<void>(resolve => setTimeout(resolve, 50));
      // Hard 35s ceiling per item (8s GraphQL + 25s API + 2s buffer).
      // MUST clearTimeout when scoring wins — otherwise the stale callback
      // fires later and overwrites a successfully-set score badge with '?'.
      let hardTimeoutId: ReturnType<typeof setTimeout>;
      await Promise.race([
        _scoreOneNotif(item).finally(() => clearTimeout(hardTimeoutId)),
        new Promise<void>(resolve => {
          hardTimeoutId = setTimeout(() => {
            logger.warn(`[UpApply] item hard timeout: ${item.jobUrl}`);
            item.badge.textContent = '?';
            item.badge.style.background = '#6b7280';
            item.badge.title = 'UpApply: timed out';
            resolve();
          }, 35_000);
        }),
      ]);
      _notifDone++;
      _updateProgressBar(_notifDone, _notifTotal);
      logger.log(`[UpApply] progress ${_notifDone}/${_notifTotal}`);
    }
  } finally {
    logger.log(`[UpApply] queue FINISHED done=${_notifDone}/${_notifTotal}`);
    _notifProcessing = false;
    _hideProgressBar();
    // Re-trigger: items pushed by IntersectionObserver while this run was active
    // sit in _notifQueue. The guard at the top prevents double-entry.
    if (_notifQueue.length > 0) {
      _processNotifQueue();
    }
  }
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

/** Scores a job tile the moment it scrolls into view. One observation per tile. */
function _observeJobTile(article: HTMLElement): void {
  if (!_tileObserver) {
    _tileObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        _tileObserver!.unobserve(entry.target);

        if (entry.target.querySelector('[data-upapply-job]')) continue;
        const link = entry.target.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
        if (!link) continue;
        const jobUrl = _normalizeJobUrl(link.href);
        if (_scoredNotifUrls.has(jobUrl)) continue;

        _scoredNotifUrls.add(jobUrl);
        const title = link.textContent?.trim() || '';
        const badge = _injectNotifBadge(entry.target, jobUrl);
        _notifQueue.push({ badge, row: entry.target, jobUrl, title });
        _notifTotal++;
        _processNotifQueue(); // safe — _notifProcessing guard skips if running; re-trigger picks up remainder
      }
    }, { threshold: 0.1 });
  }
  _tileObserver.observe(article);
}

/** Called by MutationObserver — registers any new, unobserved job tiles with the viewport observer. */
function _attachTileObservers(): void {
  document.querySelectorAll<HTMLElement>('article[data-test="JobTile"]').forEach((article) => {
    if (article.dataset.upapplyObserved === '1') return;
    if (article.querySelector('[data-upapply-job]')) return;
    article.dataset.upapplyObserved = '1';
    _observeJobTile(article);
  });
}

// ---------------------------------------------------------------------------
// Score buttons — fixed overlays injected into document.body, never into
// Vue-managed component trees (which breaks Upwork's event handlers).
// ---------------------------------------------------------------------------

let _scoreButtonInjected = false;


function _injectScoreButton(): void {
  if (_scoreButtonInjected) return;
  _scoreButtonInjected = true;
  document.getElementById('ua-score-btn')?.remove();

  const btn = document.createElement('button');
  btn.id = 'ua-score-btn';
  btn.type = 'button';
  // Always fixed to the viewport — never inserted into Upwork's nav DOM,
  // which can be inside a scrollable container on the notifications page.
  btn.style.cssText =
    'position:fixed;top:64px;right:16px;z-index:2147483647;' +
    'background:#1d4ed8;color:#fff;border:none;cursor:pointer;' +
    'padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;' +
    'font-family:-apple-system,sans-serif;white-space:nowrap;' +
    'display:flex;align-items:center;gap:4px;' +
    'box-shadow:0 1px 4px rgba(0,0,0,0.2);transition:background 0.15s;';
  btn.textContent = '⚡ Score';
  btn.title = 'Score all notifications';
  btn.addEventListener('mouseenter', () => { btn.style.background = '#1e40af'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#1d4ed8'; });
  btn.addEventListener('click', () => {
    document.getElementById('ua-score-btn')?.remove();
    _scoreButtonInjected = false;
    _processNotificationRows();
  });
  document.body.appendChild(btn);
}

// ---------------------------------------------------------------------------
// Contract import button — injected on /nx/contracts page
// ---------------------------------------------------------------------------

function _injectContractImportButton(): void {
  if (_contractImportBtnInjected) return;
  _contractImportBtnInjected = true;
  document.getElementById('ua-contract-import-btn')?.remove();

  const btn = document.createElement('div');
  btn.id = 'ua-contract-import-btn';
  btn.style.cssText =
    'position:fixed;bottom:140px;right:16px;z-index:2147483647;' +
    'display:flex;align-items:center;gap:6px;' +
    'padding:6px 14px;border-radius:20px;cursor:pointer;' +
    'background:#1d4ed8;color:#fff;' +
    'font-size:12px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'box-shadow:0 2px 8px rgba(0,0,0,0.25);white-space:nowrap;' +
    'user-select:none;transition:background 0.15s;';
  btn.textContent = '📥 Import wins';
  btn.title = 'Import contract history as won jobs';
  btn.addEventListener('mouseenter', () => { btn.style.background = '#1e40af'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#1d4ed8'; });
  btn.addEventListener('click', () => {
    _contractImportBtnInjected = false;
    btn.textContent = 'Importing…';
    btn.style.cursor = 'default';
    chrome.runtime.sendMessage({ type: 'IMPORT_CONTRACTS' }, (resp: { success: boolean; imported?: number; updated?: number; error?: string } | undefined) => {
      if (resp?.success) {
        btn.textContent = `✓ ${(resp.imported ?? 0) + (resp.updated ?? 0)} wins imported`;
      } else {
        btn.textContent = `✗ ${resp?.error || 'Import failed'}`;
      }
      setTimeout(() => { btn.remove(); }, 3000);
    });
  });
  document.body.appendChild(btn);
}

// ---------------------------------------------------------------------------
// Proposal save button — injected on /nx/proposals/{id} detail pages
// ---------------------------------------------------------------------------

function _injectProposalSaveButton(proposalText: string): void {
  if (_workroomProposalBtnInjected) return;
  _workroomProposalBtnInjected = true;
  document.getElementById('ua-workroom-proposal-btn')?.remove();

  const btn = document.createElement('div');
  btn.id = 'ua-workroom-proposal-btn';
  btn.style.cssText =
    'position:fixed;bottom:140px;right:16px;z-index:2147483647;' +
    'display:flex;align-items:center;gap:6px;' +
    'padding:6px 14px;border-radius:20px;cursor:pointer;' +
    'background:#16a34a;color:#fff;' +
    'font-size:12px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'box-shadow:0 2px 8px rgba(0,0,0,0.25);white-space:nowrap;' +
    'user-select:none;transition:background 0.15s;';
  btn.textContent = '💾 Save as winning proposal';
  btn.title = 'Mark this as a hired proposal to improve future cover letters';
  btn.addEventListener('mouseenter', () => { btn.style.background = '#15803d'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#16a34a'; });
  btn.addEventListener('click', async () => {
    btn.textContent = 'Saving…';
    btn.style.cursor = 'default';
    try {
      const token = await _getAuthToken();
      if (!token) { btn.textContent = '✗ Not logged in'; setTimeout(() => btn.remove(), 3000); return; }
      const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
      // Job title: prefer the proposal job title heading, fall back to page title
      const titleEl = document.querySelector<HTMLElement>(
        '.qa-contract-title, h1.contract-title, [data-test="job-title"], h1'
      );
      const jobTitle = titleEl?.textContent?.trim() || document.title;
      const resp = await fetch(`${apiBase}/api/v1/proposals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          cover_letter_text: proposalText,
          upwork_job_url: window.location.href,
          job_title: jobTitle,
          was_hired: true,
          status: 'hired',
          source: 'contract_import',
        }),
        signal: AbortSignal.timeout(20_000),
      });
      if (resp.ok) {
        btn.style.background = '#15803d';
        btn.textContent = '✓ Proposal saved';
      } else {
        btn.textContent = `✗ Error ${resp.status}`;
      }
    } catch (err) {
      btn.textContent = `✗ ${String(err).substring(0, 30)}`;
    }
    setTimeout(() => { btn.remove(); _workroomProposalBtnInjected = false; }, 4000);
  });
  document.body.appendChild(btn);
}

// ---------------------------------------------------------------------------
// MutationObserver — SPA navigation detection + scoring triggers
// ---------------------------------------------------------------------------

// MutationObserver covers three cases:
//   1. Bell dropdown: inject score button (user-triggered scoring)
//   2. Full notifications page (/ab/notifications/): auto-score rows
//   3. Any page with article[data-test="JobTile"]: auto-score tiles via IntersectionObserver
let _lastObservedPath = window.location.pathname;
let _observerDebounce: ReturnType<typeof setTimeout> | undefined;

function _handleMutations(): void {
  // Upwork is a SPA — detect pushState navigation and reset stale scoring state
  // so _notifProcessing=true from a previous page never blocks a fresh run.
  const currentPath = window.location.pathname;
  if (currentPath !== _lastObservedPath) {
    _lastObservedPath = currentPath;
    _resetNotifState();
  }

  const isNotifPage = currentPath.includes('/notifications');
  const hasRows     = !!document.querySelector('.notification-row a[href*="/jobs/~"]');
  const hasTiles    = !!document.querySelector('article[data-test="JobTile"]');

  // Notification button: only show on the dedicated notifications page, never on
  // other pages just because the bell dropdown happens to be open.
  if (isNotifPage && hasRows && !_notifProcessing) {
    _injectScoreButton();
  } else if (_scoreButtonInjected && !_notifProcessing) {
    document.getElementById('ua-score-btn')?.remove();
    _scoreButtonInjected = false;
  }

  // Job tile pages (search, best-matches, most-recent, saved, find-work):
  // auto-score each tile as it enters the viewport — no button needed.
  if (hasTiles) {
    _attachTileObservers();
  }

  // Contract import button: show on /nx/wm/freelancer/contracts (actual Upwork URL)
  // Also accepts the legacy /nx/contracts path in case Upwork changes it back.
  const isContractsPage = currentPath.includes('/wm/freelancer/contracts')
    || currentPath === '/nx/contracts';
  const hasContracts = !!document.querySelector('section[data-test^="contract-"]');
  if (isContractsPage && hasContracts && !_contractImportBtnInjected) {
    _injectContractImportButton();
  } else if (_contractImportBtnInjected && (!isContractsPage || !hasContracts)) {
    document.getElementById('ua-contract-import-btn')?.remove();
    _contractImportBtnInjected = false;
  }

  // Proposal save button: show on /nx/proposals/{id} pages when cover letter text is found.
  // User navigates to a hired proposal and clicks to save it as a winning example.
  const isProposalDetailPage = /\/nx\/proposals\/\d+/.test(currentPath)
    || /\/ab\/proposals\/\d+/.test(currentPath);
  if (isProposalDetailPage && !_workroomProposalBtnInjected) {
    const proposalText = scrapeProposalPageText();
    if (proposalText) {
      _injectProposalSaveButton(proposalText);
    }
  } else if (_workroomProposalBtnInjected && !isProposalDetailPage) {
    document.getElementById('ua-workroom-proposal-btn')?.remove();
    _workroomProposalBtnInjected = false;
  }

  // 💾 Save icons — attach to every job link on every page (tiles, rows, detail, search)
  _attachSaveIcons();
}

// Guard: only the NEWEST content script instance may score notifications.
// When the extension is reloaded while a tab is open Chrome injects the new
// script alongside the still-running old one. A monotonic generation counter
// lets the newest script win: each instance increments the counter and checks
// it on every mutation — if a newer instance has loaded, the old one yields.
const _W = window as Window & { __upapply_gen?: number };
const _MY_GEN = (_W.__upapply_gen ?? 0) + 1;
_W.__upapply_gen = _MY_GEN;
logger.log(`[UpApply] scoring gen=${_MY_GEN}`);

new MutationObserver(() => {
  // Yield immediately if a newer instance has taken over
  if (_W.__upapply_gen !== _MY_GEN) return;
  // Debounce: Upwork's SPA triggers bursts of mutations during navigation.
  // Running 5 querySelector calls on every mutation causes main-thread jank
  // that blocks header clicks. 200ms keeps responsiveness while still
  // catching dropdown open/close reliably.
  clearTimeout(_observerDebounce);
  _observerDebounce = setTimeout(_handleMutations, 200);
}).observe(document.body, { childList: true, subtree: true });

// No auto-scoring on any page — all scoring is user-initiated via buttons
