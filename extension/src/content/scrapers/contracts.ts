/**
 * Contract history scraper — /nx/contracts page.
 */

export interface ScrapedContract {
  contract_id: string;
  title: string;
  contract_type: string;
  rate: string | null;
  status: string;
  client_name: string | null;
  date_range: string | null;
}

export function scrapeContracts(): ScrapedContract[] {
  const results: ScrapedContract[] = [];
  document.querySelectorAll<HTMLElement>('section[data-test^="contract-"]').forEach(section => {
    const testVal = section.getAttribute('data-test') || '';
    const idMatch = testVal.match(/^contract-(\d+)$/);
    if (!idMatch) return;
    const id = idMatch[1];

    const titleEl = section.querySelector<HTMLElement>(`[data-test="contract-${id}-title"]`);
    const title = titleEl?.getAttribute('title') || titleEl?.textContent?.trim() || '';
    if (!title) return;

    const hourlyEl = section.querySelector(`[data-test="contract-${id}-hourly-terms"]`);
    const fixedEl  = section.querySelector(`[data-test="contract-${id}-fixed-price-terms"]`);
    const contract_type = hourlyEl ? 'hourly' : fixedEl ? 'fixed' : 'unknown';
    const rate = (hourlyEl || fixedEl)?.textContent?.trim() || null;

    const status = section.querySelector(`[data-test="contract-${id}-active-info"]`) ? 'active'
      : section.querySelector(`[data-test="contract-${id}-paused-info"]`) ? 'paused'
      : 'ended';

    const clientEl = section.querySelector<HTMLElement>(`[data-test="contract-${id}-contract-party-info-section"] p`);
    const client_name = clientEl?.textContent?.replace(/^Hired by\s+/i, '').trim() || null;

    const datesEl = section.querySelector(`[data-test="contract-${id}-dates"]`);
    const date_range = datesEl?.textContent?.trim() || null;

    results.push({ contract_id: id, title, contract_type, rate, status, client_name, date_range });
  });
  return results;
}

/**
 * Click through all pagination pages and collect every contract.
 * Uses data-ev-max_page_count to know how many pages exist, then
 * clicks [data-test="next-page"] and waits for Vue to re-render each page.
 */
export async function scrapeAllContracts(): Promise<ScrapedContract[]> {
  const all: ScrapedContract[] = [];

  // Detect total pages from pagination buttons (most reliable — data-ev-max_page_count
  // is not present on the live contracts page).
  // "Current page 1 of N" sr-only text is the most explicit signal; fall back to
  // counting the numbered page buttons.
  let maxPages = 1;
  const srOnly = document.querySelector('.air3-pagination-nr-btn.is-active .sr-only');
  const srMatch = srOnly?.textContent?.match(/of\s+(\d+)/i);
  if (srMatch) {
    maxPages = parseInt(srMatch[1], 10);
  } else {
    const pageItems = document.querySelectorAll('[data-test="pagination-item"]');
    if (pageItems.length > 0) maxPages = pageItems.length;
  }

  const reportPage = (page: number) => {
    if (chrome?.storage?.local) {
      chrome.storage.local.set({ contractImportProgress: { stage: 'scraping', page, total: maxPages } });
    }
  };

  reportPage(1);
  all.push(...scrapeContracts());

  for (let page = 2; page <= maxPages; page++) {
    const nextBtn = document.querySelector<HTMLButtonElement>('[data-test="next-page"]');
    if (!nextBtn || nextBtn.disabled || nextBtn.classList.contains('is-disabled')) break;

    nextBtn.click();

    // Step 1: wait for the active page button to show the new page number
    await new Promise<void>(resolve => {
      const deadline = Date.now() + 8000;
      const check = () => {
        const active = document.querySelector('.air3-pagination-nr-btn.is-active span[aria-hidden="true"]');
        if (active?.textContent?.trim() === String(page)) resolve();
        else if (Date.now() > deadline) resolve();
        else setTimeout(check, 200);
      };
      setTimeout(check, 300);
    });

    // Step 2: wait for Upwork to remove old sections and render new ones.
    // Sections briefly drop to 0 between pages — poll until they reappear.
    await new Promise<void>(resolve => {
      const deadline = Date.now() + 6000;
      let seenEmpty = false;
      const check = () => {
        const count = document.querySelectorAll('section[data-test^="contract-"]').length;
        if (count === 0) seenEmpty = true;
        if ((seenEmpty && count > 0) || Date.now() > deadline) resolve();
        else setTimeout(check, 100);
      };
      setTimeout(check, 100);
    });

    reportPage(page);
    all.push(...scrapeContracts());
  }

  return all;
}
