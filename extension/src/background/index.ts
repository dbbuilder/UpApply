/**
 * Background service worker for UpApply extension.
 * Handles communication between content scripts and sidebar.
 */
import type { JobData } from '../types';
import { extractBudgetFromPageText, detectNotifChips, topOfRange as _topOfRange } from '../lib/notif-chips';
import { logger } from '../lib/logger';

// Store current job data for sidebar access
let currentJobData: JobData | null = null;

// ---------------------------------------------------------------------------
// SW keepalive — MV3 service workers are terminated after ~30s of inactivity.
// During active scoring we touch chrome.storage every 20s to reset the timer.
// ---------------------------------------------------------------------------
let _keepAliveTimer: ReturnType<typeof setInterval> | undefined;
let _activeScoringCount = 0;

function _startKeepAlive(): void {
  if (_keepAliveTimer) return;
  _keepAliveTimer = setInterval(() => {
    chrome.storage.local.get('__ping', () => void chrome.runtime.lastError);
  }, 20_000);
}

function _stopKeepAlive(): void {
  if (_keepAliveTimer) { clearInterval(_keepAliveTimer); _keepAliveTimer = undefined; }
}

// Listen for messages from content script and sidebar
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  logger.log('UpApply Background: Received message', message.type);

  switch (message.type) {
    case 'PING':
      sendResponse({ pong: true });
      return false;

    case 'CONTENT_SCRIPT_READY':
      logger.log('Content script ready on', message.url);
      break;

    case 'JOB_DATA_EXTRACTED':
      currentJobData = message.data;
      logger.log('Job data extracted:', currentJobData?.title);

      // Store in local storage for sidebar access
      chrome.storage.local.set({ currentJob: currentJobData });

      // Notify sidebar if it's open
      chrome.runtime.sendMessage({
        type: 'JOB_DATA_UPDATED',
        data: currentJobData,
      }).catch(() => {
        // Sidebar might not be open
      });
      break;

    case 'GET_CURRENT_JOB':
      sendResponse({ data: currentJobData });
      break;

    case 'GET_AUTH_TOKEN': {
      // Content script may not have chrome.storage access — delegate to SW
      chrome.storage.local.get('authToken').then((stored) => {
        try { sendResponse({ token: (stored['authToken'] as string) || null }); } catch { /* channel closed */ }
      }).catch(() => { try { sendResponse({ token: null }); } catch { /* channel closed */ } });
      return true;
    }

    case 'SET_NOTIF_CACHE': {
      // Content script delegates cache writes when chrome.storage unavailable
      const { key, value } = message as { key: string; value: unknown };
      chrome.storage.local.set({ [key]: value }).catch(() => {});
      break;
    }

    case 'GET_NOTIF_CACHE': {
      const { key: cacheKey } = message as { key: string };
      chrome.storage.local.get(cacheKey).then((stored) => {
        try { sendResponse({ value: stored[cacheKey] ?? null }); } catch { /* channel closed */ }
      }).catch(() => { try { sendResponse({ value: null }); } catch { /* channel closed */ } });
      return true;
    }

    case 'REQUEST_JOB_EXTRACTION':
      // Forward extraction request to content script in active tab
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        logger.log('UpApply Background: Requesting extraction from tab', tab?.id, tab?.url);

        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if not already loaded
        try {
          // Get content script path from manifest
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
            logger.log('UpApply Background: Content script injected:', contentScriptPath);
          }
        } catch (e) {
          logger.log('UpApply Background: Script injection note:', e);
        }

        // Small delay to let script initialize
        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, { type: 'EXTRACT_JOB_DATA' }, (response) => {
            logger.log('UpApply Background: Extraction response:', response);
            if (response?.debug) {
              logger.log('UpApply Background: DEBUG - page headings:', response.debug);
            }
            if (chrome.runtime.lastError) {
              console.error('UpApply Background: Error:', chrome.runtime.lastError.message);
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the Upwork page and try again.' });
            } else if (response?.success) {
              currentJobData = response.data;
              chrome.storage.local.set({ currentJob: currentJobData });
              sendResponse(response);
            } else {
              sendResponse(response || { success: false, error: 'No response from content script' });
            }
          });
        }, 200);
      });
      return true; // Keep channel open for async response

    case 'FILL_COVER_LETTER':
      // Forward to content script in active tab (with injection if needed)
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if not already loaded
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
            logger.log('UpApply Background: Content script injected for fill');
          }
        } catch (e) {
          logger.log('UpApply Background: Script injection note:', e);
        }

        // Small delay to let script initialize
        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'FILL_COVER_LETTER',
            content: message.content,
          }, (response) => {
            if (chrome.runtime.lastError) {
              console.error('UpApply Background: Fill error:', chrome.runtime.lastError);
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
      return true; // Keep channel open for async response

    case 'SET_BID_AMOUNT':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if needed
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'SET_BID_AMOUNT',
            amount: message.amount,
          }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false });
            }
          });
        }, 200);
      });
      return true;

    case 'FILL_SCREENING_QUESTION':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if needed
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'FILL_SCREENING_QUESTION',
            selector: message.selector,
            answer: message.answer,
          }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false });
            }
          });
        }, 200);
      });
      return true;

    case 'FILL_ALL_QUESTIONS':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'FILL_ALL_QUESTIONS',
            answers: message.answers,
          }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false });
            }
          });
        }, 200);
      });
      return true;

    case 'FILL_MILESTONES':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'FILL_MILESTONES',
            milestones: message.milestones,
          }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false });
            }
          });
        }, 200);
      });
      return true;

    case 'OPEN_SIDEBAR':
      if (sender.tab?.windowId) {
        chrome.sidePanel.open({ windowId: sender.tab.windowId });
      }
      break;

    case 'SCRAPE_PROPOSALS':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if needed
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, { type: 'SCRAPE_PROPOSALS' }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              if (response?.debug?.length) {
                logger.log('UpApply Proposals debug — selectors that matched: ' + response.debug.join(' | '));
              }
              logger.log('UpApply Proposals scrape result:', response?.success, '— found', response?.data?.length ?? 0, 'proposals', 'url:', response?.url);
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
      return true;

    case 'REPORT_PROPOSAL_RESPONSE': {
      // Called by content script when it detects a proposal status change on upwork.com/nx/proposals
      // message.data: { queueItemId, responseType, upworkProposalId? }
      const { queueItemId, responseType, upworkProposalId } = message.data ?? {};
      if (!queueItemId || !responseType) {
        sendResponse({ success: false, error: 'Missing queueItemId or responseType' });
        break;
      }
      chrome.storage.local.get('authToken').then(async (stored) => {
        const token = stored.authToken as string | undefined;
        if (!token) { sendResponse({ success: false, error: 'Not authenticated' }); return; }
        const apiBase = import.meta.env.VITE_API_URL ?? 'https://upapply-api.onrender.com';
        try {
          const res = await fetch(`${apiBase}/api/v1/job-queue/${queueItemId}/proposal-response`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({ response_type: responseType, upwork_proposal_id: upworkProposalId }),
          });
          sendResponse({ success: res.ok });
        } catch (e) {
          sendResponse({ success: false, error: String(e) });
        }
      });
      return true; // async
    }

    case 'SCRAPE_JOB_CARDS':
      // Forward to active tab's content script (user should be on saved jobs or search page)
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [contentScriptPath] });
          }
        } catch (e) { /* already loaded */ }
        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, { type: 'SCRAPE_JOB_CARDS' }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh.' });
            } else {
              logger.log('UpApply Job cards scrape:', response?.success, '—', response?.data?.length ?? 0, 'cards');
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
      return true;

    case 'IMPORT_SAVED_JOBS':
      // Navigate to saved jobs page in background tab, scrape, close, return cards
      (async () => {
        const savedUrl = 'https://www.upwork.com/nx/search/jobs/saved/';
        logger.log('UpApply Background: Opening saved jobs tab:', savedUrl);
        const savedTab = await chrome.tabs.create({ url: savedUrl, active: false });
        if (!savedTab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(savedTab.id);
          await new Promise(resolve => setTimeout(resolve, 2000));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: savedTab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
            chrome.tabs.sendMessage(savedTab.id!, { type: 'SCRAPE_JOB_CARDS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(savedTab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'IMPORT_PROPOSALS':
      // Deep scrape: active list + archived list + detail pages for cover letters.
      // Manifest auto-injects the content script on all upwork.com pages — we never
      // re-inject manually (that creates duplicate instances causing "message channel
      // closed" errors). We use a ping-wait instead to confirm the CS is ready.
      (async () => {
        const setProgress = (p: Record<string, unknown>) =>
          chrome.storage.local.set({ proposalImportProgress: p });

        _startKeepAlive();
        _activeScoringCount++;

        // Wait for the manifest-injected content script to respond to a PING.
        const waitForContentScript = (tabId: number, maxMs = 12_000): Promise<boolean> =>
          new Promise((resolve) => {
            const deadline = Date.now() + maxMs;
            const tryPing = () => {
              chrome.tabs.sendMessage(tabId, { type: 'PING' }, (resp) => {
                if (!chrome.runtime.lastError && resp?.pong) { resolve(true); return; }
                if (Date.now() < deadline) setTimeout(tryPing, 400);
                else resolve(false);
              });
            };
            tryPing();
          });

        // Navigate and wait — listener registered BEFORE update to avoid race condition
        // where the page completes before the listener is added.
        const navigateAndWait = async (tabId: number, url: string, timeoutMs = 20_000): Promise<void> => {
          await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => {
              chrome.tabs.onUpdated.removeListener(listener);
              reject(new Error('Tab load timeout'));
            }, timeoutMs);
            const listener = (id: number, changeInfo: chrome.tabs.TabChangeInfo) => {
              if (id === tabId && changeInfo.status === 'complete') {
                chrome.tabs.onUpdated.removeListener(listener);
                clearTimeout(timeout);
                resolve();
              }
            };
            // Register listener synchronously BEFORE the awaited update call
            chrome.tabs.onUpdated.addListener(listener);
            chrome.tabs.update(tabId, { url }).catch((e) => {
              chrome.tabs.onUpdated.removeListener(listener);
              clearTimeout(timeout);
              reject(e);
            });
          });
        };

        const scrapeListPage = (tabId: number): Promise<import('../types').ScrapedProposal[]> =>
          new Promise((resolve) => {
            // 120s timeout — extractAllProposals paginates up to many pages (each page ~8s)
            const timeout = setTimeout(() => resolve([]), 120_000);
            chrome.tabs.sendMessage(tabId, { type: 'SCRAPE_PROPOSALS' }, (resp) => {
              clearTimeout(timeout);
              if (chrome.runtime.lastError || !resp?.success) resolve([]);
              else resolve((resp.data as import('../types').ScrapedProposal[]) || []);
            });
          });

        // Save the currently active tab so we can restore focus after scraping.
        // Making the proposals tab active gives Vue full rAF speed — without this,
        // background-tab rAF throttling (~1fps) makes each page navigation take 10–15s
        // instead of ~1s, causing the 120s scrapeListPage timeout to fire after 2 pages.
        const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const restoreTab = async () => {
          if (currentTab?.id) {
            try { await chrome.tabs.update(currentTab.id, { active: true }); } catch { /* ignore */ }
          }
        };

        try {
          await setProgress({ stage: 'opening' });
          const propTab = await chrome.tabs.create({ url: 'https://www.upwork.com/nx/proposals/', active: true });
          if (!propTab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }

          try {
            // 1. Scrape active proposals list
            await setProgress({ stage: 'scraping_active' });
            await waitForTabLoad(propTab.id);
            await new Promise(r => setTimeout(r, 2000));
            await waitForContentScript(propTab.id);
            const activeProposals = await scrapeListPage(propTab.id);
            logger.log('UpApply: Active proposals found:', activeProposals.length);

            // 2. Scrape archived proposals list
            await setProgress({ stage: 'scraping_archived' });
            await navigateAndWait(propTab.id, 'https://www.upwork.com/nx/proposals/archived');
            await new Promise(r => setTimeout(r, 2000));
            await waitForContentScript(propTab.id);
            const archivedProposals = await scrapeListPage(propTab.id);
            logger.log('UpApply: Archived proposals found:', archivedProposals.length);

            // Merge — active first, archived fills in gaps; track which list each came from
            type ProposalWithSource = import('../types').ScrapedProposal & { _isArchived: boolean };
            const proposalMap = new Map<string, ProposalWithSource>();
            for (const p of activeProposals) {
              if (p.proposalId) proposalMap.set(p.proposalId, { ...p, _isArchived: false });
            }
            for (const p of archivedProposals) {
              if (p.proposalId && !proposalMap.has(p.proposalId)) {
                proposalMap.set(p.proposalId, { ...p, _isArchived: true });
              }
            }
            const allProposals = Array.from(proposalMap.values());
            logger.log('UpApply: Total unique proposals:', allProposals.length);

            if (allProposals.length === 0) {
              sendResponse({ success: false, error: 'No proposals found on active or archived pages.' });
              return;
            }

            // 3. Visit detail pages to extract cover letters.
            // Cap at 150 most recent — the list is newest-first so we take the head.
            // Visiting 900+ detail pages would take ~45 min; 150 takes ~8 min and
            // covers all the corpus-relevant recent work.
            const MAX_DETAIL_PAGES = 150;
            const detailCandidates = allProposals.slice(0, MAX_DETAIL_PAGES);
            const results: import('../types').ScrapedProposal[] = [];
            const total = detailCandidates.length;
            logger.log(`UpApply: Visiting ${total} detail pages (${allProposals.length} total proposals — capped at ${MAX_DETAIL_PAGES})`);

            for (let i = 0; i < detailCandidates.length; i++) {
              const proposal = detailCandidates[i];
              await setProgress({ stage: 'detail', current: i + 1, total, grandTotal: allProposals.length });

              if (!proposal.proposalId) {
                results.push(proposal);
                continue;
              }

              const detailUrl = `https://www.upwork.com/nx/proposals/${proposal.proposalId}`;
              try {
                await navigateAndWait(propTab.id, detailUrl, 15_000);
              } catch {
                logger.log('UpApply: Timeout loading detail for proposal', proposal.proposalId);
                results.push({ ...proposal, coverLetter: null });
                continue;
              }
              await new Promise(r => setTimeout(r, 1500));

              // Read window.__NUXT__ from the page's main world
              let nuxtCoverLetter: string | null = null;
              let nuxtStatus: string | null = null;
              let nuxtBidAmount: string | null = null;
              let nuxtJobTitle: string | null = null;
              try {
                const [nuxtResult] = await chrome.scripting.executeScript({
                  target: { tabId: propTab.id },
                  world: 'MAIN',
                  func: () => {
                    try {
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const n = (window as any).__NUXT__;
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const state = n?.state as Record<string, any> | undefined;
                      // Correct path: __NUXT__.state['proposal-details'].proposalDetailsV3Response.application
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const v3 = state?.['proposal-details']?.proposalDetailsV3Response as Record<string, any> | undefined;
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const app = v3?.application as Record<string, any> | undefined;
                      // status may be a number (Upwork internal enum) — convert to string
                      const rawStatus = app?.status;
                      const statusStr = rawStatus != null ? String(rawStatus) : null;
                      return {
                        coverLetter: (app?.coverLetter as string) || null,
                        status: statusStr,
                        bidAmount: String(app?.terms?.chargeRate?.amount || '') || null,
                        jobTitle: (v3?.jobDetails?.opening?.job?.info?.title as string) || null,
                      };
                    } catch { return { coverLetter: null, status: null, bidAmount: null, jobTitle: null }; }
                  },
                });
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const r = nuxtResult?.result as Record<string, any> | null;
                nuxtCoverLetter = r?.coverLetter || null;
                nuxtStatus = r?.status || null;
                nuxtBidAmount = r?.bidAmount || null;
                nuxtJobTitle = r?.jobTitle || null;
              } catch (e) {
                logger.log('UpApply: NUXT read failed for proposal', proposal.proposalId, String(e));
              }

              // DOM fallback via content script (already injected by manifest — no re-inject)
              let domCoverLetter: string | null = null;
              if (!nuxtCoverLetter) {
                await waitForContentScript(propTab.id, 5_000);
                const domResult = await new Promise<{ coverLetter?: string | null }>((resolve) => {
                  chrome.tabs.sendMessage(propTab.id!, { type: 'SCRAPE_PROPOSAL_DETAIL' }, (resp) => {
                    if (chrome.runtime.lastError || !resp?.success) resolve({});
                    else resolve(resp);
                  });
                });
                domCoverLetter = domResult.coverLetter || null;
              }

              const coverLetter = nuxtCoverLetter || domCoverLetter || null;
              // domJobTitle is unreliable (generic h3 may say "Hiring activity"); prefer list-page title
              const jobTitle = nuxtJobTitle || proposal.jobTitle;

              // Determine was_hired from multiple signals:
              // 1. List-page status text (most reliable for won state)
              // 2. Nuxt detail-page status (may be numeric enum or string)
              let wasHired: boolean | null = null;
              const listStatus = (proposal.status || '').toLowerCase();
              const detailStatus = (nuxtStatus || '').toLowerCase();
              const hiredKeywords = ['hired', 'contract', 'working', 'active contract'];
              const isHiredByList = hiredKeywords.some(k => listStatus.includes(k));
              const isHiredByDetail = hiredKeywords.some(k => detailStatus.includes(k));
              if (isHiredByList || isHiredByDetail) {
                wasHired = true;
              } else if (proposal._isArchived) {
                wasHired = false;
              }

              results.push({
                proposalId: proposal.proposalId,
                jobTitle,
                jobUrl: detailUrl,
                coverLetter,
                bidAmount: nuxtBidAmount ? parseFloat(nuxtBidAmount) : null,
                bidType: null,
                status: nuxtStatus || (proposal._isArchived ? 'archived' : (proposal.status || 'submitted')),
                submittedAt: proposal.submittedAt,
                wasHired,
              });
            }

            await setProgress({ stage: 'done', current: total, total });
            logger.log('UpApply: Proposal deep-scrape complete —', results.length, 'proposals,', results.filter(r => r.coverLetter).length, 'with cover letters');
            sendResponse({ success: true, data: results });
          } finally {
            try { await chrome.tabs.remove(propTab.id); } catch (e) { /* ignore */ }
            await restoreTab();
          }
        } catch (err) {
          await setProgress({ stage: 'error', error: String(err) });
          sendResponse({ success: false, error: String(err) });
        } finally {
          _activeScoringCount = Math.max(0, _activeScoringCount - 1);
          if (_activeScoringCount === 0) _stopKeepAlive();
        }
      })();
      return true;

    case 'IMPORT_UPWORK_SAVED_SEARCHES':
      // Navigate to Upwork find-work page in background tab, scrape saved searches, close tab
      (async () => {
        const findWorkUrl = 'https://www.upwork.com/nx/find-work/';
        logger.log('UpApply Background: Opening find-work tab for saved searches:', findWorkUrl);
        const findWorkTab = await chrome.tabs.create({ url: findWorkUrl, active: false });
        if (!findWorkTab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(findWorkTab.id);
          await new Promise(resolve => setTimeout(resolve, 2500));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: findWorkTab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
            chrome.tabs.sendMessage(findWorkTab.id!, { type: 'SCRAPE_SAVED_SEARCHES' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(findWorkTab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'SEARCH_UPWORK_JOBS':
      // Open a background tab, scrape search results, close tab, return cards
      (async () => {
        const query = encodeURIComponent(message.query || '');
        const extraParams = message.urlParams ? `&${message.urlParams}` : '';
        const searchUrl = `https://www.upwork.com/nx/search/jobs/?q=${query}&sort=recency${extraParams}`;
        logger.log('UpApply Background: Opening search tab for:', searchUrl);
        const tab = await chrome.tabs.create({ url: searchUrl, active: false });
        if (!tab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(tab.id);
          await new Promise(resolve => setTimeout(resolve, 2000));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
            chrome.tabs.sendMessage(tab.id!, { type: 'SCRAPE_JOB_CARDS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(tab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'GET_VIEW_POSTING_LINK':
      // Forward to content script in active tab
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id) {
          sendResponse({ success: false, error: 'No active tab' });
          return;
        }

        chrome.tabs.sendMessage(tab.id, { type: 'GET_VIEW_POSTING_LINK' }, (response) => {
          if (chrome.runtime.lastError) {
            sendResponse({ success: false, error: 'Content script not loaded' });
          } else {
            sendResponse(response || { success: false });
          }
        });
      });
      return true;

    case 'EXTRACT_FULL_JOB':
      // Open the job posting in a background tab and extract data
      (async () => {
        try {
          const data = await extractFullJobInBackground(message.jobPostingUrl);
          sendResponse({ success: true, data });
        } catch (err) {
          console.error('UpApply Background: Full job extraction failed:', err);
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;

    case 'DOWNLOAD_ATTACHMENT':
      // Download an attachment and return as base64
      (async () => {
        try {
          const result = await downloadAttachment(message.url);
          sendResponse({ success: true, ...result });
        } catch (err) {
          console.error('UpApply Background: Attachment download failed:', err);
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;

    // ------------------------------------------------------------------
    // CHECK_NOTIF_CACHE — fast cache-only lookup, no scoring
    // ------------------------------------------------------------------
    case 'CHECK_NOTIF_CACHE':
      (async () => {
        const { jobUrl } = message as { jobUrl: string };
        const CACHE_VERSION = 'v5';
        const cacheKey = `sc_${CACHE_VERSION}_${jobUrl}`;
        const CACHE_TTL = 24 * 60 * 60 * 1000;
        const cacheStore = await chrome.storage.local.get(cacheKey);
        const cached = cacheStore[cacheKey] as { score: number; chips: string[]; ts: number } | undefined;
        if (cached && Date.now() - cached.ts < CACHE_TTL) {
          sendResponse({ success: true, score: cached.score, chips: cached.chips, cached: true });
        } else {
          sendResponse({ success: false, cached: false });
        }
      })();
      return true;

    // ------------------------------------------------------------------
    // SCORE_JOB_WITH_DATA — content script already fetched page data;
    // background just scores via API + caches. No tab opening needed.
    // ------------------------------------------------------------------
    case 'SCORE_JOB_WITH_DATA':
      (async () => {
        _activeScoringCount++;
        if (_activeScoringCount === 1) _startKeepAlive();
        try {
          const { jobUrl, title, description, pageText, budgetAmount: preBudgetAmount, budgetType: preBudgetType } = message as {
            jobUrl: string; title: string; description: string; pageText: string;
            budgetAmount?: string | null; budgetType?: string | null;
          };

          // Cache check
          const CACHE_VERSION = 'v5';
          const cacheKey = `sc_${CACHE_VERSION}_${jobUrl}`;
          const CACHE_TTL = 24 * 60 * 60 * 1000;
          const cacheStore = await chrome.storage.local.get(cacheKey);
          const cached = cacheStore[cacheKey] as { score: number; chips: string[]; ts: number } | undefined;
          if (cached && Date.now() - cached.ts < CACHE_TTL) {
            sendResponse({ success: true, score: cached.score, chips: cached.chips, cached: true });
            return;
          }

          const stored = await chrome.storage.local.get('authToken');
          const token = stored.authToken as string | undefined;
          if (!token) { sendResponse({ success: false, error: 'Not logged in' }); return; }

          // Use budget from GraphQL if available, otherwise extract from page text
          let budgetAmount = preBudgetAmount ?? null;
          let budgetType   = preBudgetType   ?? null;
          if (!budgetAmount) {
            const extracted = extractBudgetFromPageText(pageText || description);
            logger.log('[UpApply] SCORE_JOB_WITH_DATA budget fallback:', extracted, 'pageTextLen:', (pageText || '').length);
            budgetAmount = extracted?.amount ?? null;
            budgetType   = extracted?.type   ?? null;
          }
          logger.log('[UpApply] SCORE_JOB_WITH_DATA final budget:', { budgetAmount, budgetType, source: preBudgetAmount ? 'graphql' : 'regex' });

          // Score via API — 25s timeout prevents SW termination from a slow/cold-start Render instance
          const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
          const analyzeResp = await fetch(`${apiBase}/api/v1/jobs/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ title: title || 'Job', description: description || title }),
            signal: AbortSignal.timeout(25_000),
          });
          if (!analyzeResp.ok) { sendResponse({ success: false, error: `API ${analyzeResp.status}` }); return; }
          const data = await analyzeResp.json() as { match_score: number };

          const chips = detectNotifChips(title, description, budgetAmount, budgetType);

          await chrome.storage.local.set({ [cacheKey]: { score: data.match_score, chips, ts: Date.now() } });
          sendResponse({ success: true, score: data.match_score, chips });
        } catch (err) {
          console.error('[UpApply] SCORE_JOB_WITH_DATA error:', err);
          sendResponse({ success: false, error: String(err) });
        } finally {
          _activeScoringCount--;
          if (_activeScoringCount === 0) _stopKeepAlive();
        }
      })();
      return true;

    // Kept for backward compatibility — no longer opens background tabs
    case 'SCORE_NOTIFICATION_JOB':
      sendResponse({ success: false, error: 'Use SCORE_JOB_WITH_DATA instead' });
      return false;

    case 'IMPORT_CONTRACTS':
      (async () => {
        try {
          const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
          const tabId = tabs[0]?.id;
          if (!tabId) { sendResponse({ success: false, error: 'No active tab' }); return; }

          // Ask content script to scrape the contracts page
          const scrapeResult = await new Promise<{ success: boolean; data?: unknown; error?: string }>(resolve => {
            chrome.tabs.sendMessage(tabId, { type: 'SCRAPE_CONTRACTS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });

          if (!scrapeResult?.success || !Array.isArray(scrapeResult.data)) {
            sendResponse({ success: false, error: scrapeResult?.error || 'Scrape failed' });
            return;
          }

          const stored = await chrome.storage.local.get('authToken');
          const token = stored.authToken as string | undefined;
          if (!token) { sendResponse({ success: false, error: 'Not logged in' }); return; }

          const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
          const resp = await fetch(`${apiBase}/api/v1/jobs/import-contracts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ contracts: scrapeResult.data }),
            signal: AbortSignal.timeout(30_000),
          });

          if (!resp.ok) { sendResponse({ success: false, error: `API ${resp.status}` }); return; }
          const data = await resp.json();
          sendResponse({ success: true, ...data });
        } catch (err) {
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;

    // Navigate the active tab to the contracts page, wait for load, then import.
    // This lets the sidebar trigger a full import without the user visiting the page first.
    case 'NAVIGATE_AND_IMPORT_CONTRACTS':
      (async () => {
        const setProgress = (p: Record<string, unknown>) =>
          chrome.storage.local.set({ contractImportProgress: p });

        try {
          const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
          const tabId = tabs[0]?.id;
          if (!tabId) { sendResponse({ success: false, error: 'No active tab' }); return; }

          await setProgress({ stage: 'navigating' });
          await chrome.tabs.update(tabId, { url: 'https://www.upwork.com/nx/wm/freelancer/contracts' });
          await waitForTabLoad(tabId, 20_000);
          // Give Vue time to render the contract sections before scraping starts
          await new Promise(r => setTimeout(r, 3000));

          await setProgress({ stage: 'scraping', page: 1 });
          const scrapeResult = await new Promise<{ success: boolean; data?: unknown; error?: string; pages?: number }>(resolve => {
            chrome.tabs.sendMessage(tabId, { type: 'SCRAPE_CONTRACTS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });

          if (!scrapeResult?.success || !Array.isArray(scrapeResult.data)) {
            await setProgress({ stage: 'error', error: scrapeResult?.error || 'No contracts found' });
            sendResponse({ success: false, error: scrapeResult?.error || 'No contracts found on page' });
            return;
          }

          const total = (scrapeResult.data as unknown[]).length;
          await setProgress({ stage: 'saving', count: total });

          const stored = await chrome.storage.local.get('authToken');
          const token = stored.authToken as string | undefined;
          if (!token) {
            await setProgress({ stage: 'error', error: 'Not logged in' });
            sendResponse({ success: false, error: 'Not logged in' });
            return;
          }

          const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
          const resp = await fetch(`${apiBase}/api/v1/jobs/import-contracts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ contracts: scrapeResult.data }),
            signal: AbortSignal.timeout(90_000),
          });

          if (!resp.ok) {
            const errText = await resp.text().catch(() => '');
            await setProgress({ stage: 'error', error: `API ${resp.status}` });
            sendResponse({ success: false, error: `API ${resp.status}: ${errText.slice(0, 200)}` });
            return;
          }
          const data = await resp.json();
          await setProgress({ stage: 'done', ...data });
          sendResponse({ success: true, ...data });
        } catch (err) {
          await setProgress({ stage: 'error', error: String(err) });
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;
  }

  return false;
});

/**
 * Wait for a tab to complete loading.
 */
function waitForTabLoad(tabId: number, timeoutMs = 30000): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Tab load timeout'));
    }, timeoutMs);

    const listener = (id: number, changeInfo: chrome.tabs.TabChangeInfo) => {
      if (id === tabId && changeInfo.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timeout);
        resolve();
      }
    };

    chrome.tabs.onUpdated.addListener(listener);
  });
}

/**
 * Extract full job data by opening the job posting in a background tab.
 */
async function extractFullJobInBackground(jobPostingUrl: string): Promise<{
  fullDescription: string | null;
  attachments: Array<{ url: string; filename: string; contentType: string }>;
}> {
  logger.log('UpApply Background: Opening background tab for:', jobPostingUrl);

  // Create background tab (not active)
  const tab = await chrome.tabs.create({
    url: jobPostingUrl,
    active: false,
  });

  if (!tab.id) {
    throw new Error('Failed to create tab');
  }

  try {
    // Wait for tab to load
    await waitForTabLoad(tab.id);

    // Additional delay for dynamic content
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Inject content script if needed
    const manifest = chrome.runtime.getManifest();
    const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
    if (contentScriptPath) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: [contentScriptPath],
        });
        logger.log('UpApply Background: Content script injected into background tab');
      } catch (e) {
        logger.log('UpApply Background: Script injection note:', e);
      }
    }

    // Small delay after injection
    await new Promise(resolve => setTimeout(resolve, 500));

    // Extract data from the tab
    const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
      chrome.tabs.sendMessage(tab.id!, { type: 'EXTRACT_JOB_POSTING_DATA' }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || { success: false, error: 'No response' });
        }
      });
    });

    if (!response.success) {
      throw new Error(response.error || 'Extraction failed');
    }

    logger.log('UpApply Background: Full job extracted successfully');
    return response.data as {
      fullDescription: string | null;
      attachments: Array<{ url: string; filename: string; contentType: string }>;
    };
  } finally {
    // Always close the background tab
    try {
      await chrome.tabs.remove(tab.id);
      logger.log('UpApply Background: Background tab closed');
    } catch (e) {
      console.error('UpApply Background: Failed to close tab:', e);
    }
  }
}

/**
 * Download an attachment and return as base64.
 * This runs in the background context which may have different CORS restrictions.
 */
async function downloadAttachment(url: string): Promise<{ data: string; contentType: string; size: number }> {
  logger.log('UpApply Background: Downloading attachment:', url);

  const response = await fetch(url, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  const contentType = response.headers.get('content-type') || 'application/octet-stream';

  // Convert to base64
  const arrayBuffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64 = btoa(binary);

  return {
    data: base64,
    contentType,
    size: blob.size,
  };
}

// Handle extension icon click - open sidebar
chrome.action.onClicked.addListener((tab) => {
  if (tab.windowId !== undefined) {
    chrome.sidePanel.open({ windowId: tab.windowId });
  }
});

// Set up side panel behavior
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

// Debounce extraction per tab to avoid duplicate EXTRACT_JOB_DATA messages
const pendingExtractions = new Map<number, ReturnType<typeof setTimeout>>();

// Listen for tab updates to extract job data on Upwork job pages
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  const url = tab.url ?? '';
  const isJobUrl = url.includes('upwork.com') && url.includes('/jobs/');
  if (changeInfo.status === 'complete' && isJobUrl) {
    // Cancel any pending extraction for this tab
    const existing = pendingExtractions.get(tabId);
    if (existing) clearTimeout(existing);

    // Delay extraction to let SPA content render (avoids null title)
    const timer = setTimeout(() => {
      pendingExtractions.delete(tabId);

      const pushUpdate = (data: JobData) => {
        currentJobData = data;
        chrome.storage.local.set({ currentJob: data });
        chrome.runtime.sendMessage({ type: 'JOB_DATA_UPDATED', data }).catch(() => {});
      };

      chrome.tabs.sendMessage(tabId, { type: 'EXTRACT_JOB_DATA' }, (response) => {
        if (chrome.runtime.lastError) return;
        if (response?.success && response.data) {
          const job = response.data as JobData;
          if (job.title) {
            pushUpdate(job);
          } else {
            // Title empty — React may still be hydrating; retry after 2s
            setTimeout(() => {
              chrome.tabs.sendMessage(tabId, { type: 'EXTRACT_JOB_DATA' }, (r2) => {
                if (!chrome.runtime.lastError && r2?.success && r2.data) pushUpdate(r2.data);
              });
            }, 2000);
          }
        }
      });
    }, 3500);
    pendingExtractions.set(tabId, timer);
  }
});

logger.log('UpApply Background: Service worker started');

// ---------------------------------------------------------------------------
// extractBudgetFromPageText, detectNotifChips, topOfRange imported from ../lib/notif-chips
