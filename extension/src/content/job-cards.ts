/**
 * Reading Upwork job tiles (article[data-test="JobTile"]) on saved-jobs and search pages.
 * The search page's title link has no data-test="job-tile-title-link" (seen 2026-11-02:
 * 10 tiles, 0 such links), so a tile's link is found by what it is: an /jobs/ link to ~0<id>.
 */

const JOB_ID = /~0?(\d{15,})/;

/** The tile's job title link, or null when the tile has no link to a job. */
export function findTitleLink(tile: Element): HTMLAnchorElement | null {
  const tagged = tile.querySelector<HTMLAnchorElement>('a[data-test="job-tile-title-link"]');
  if (tagged) return tagged;
  const jobLinks = Array.from(tile.querySelectorAll<HTMLAnchorElement>('a[href*="/jobs/"]'))
    .filter((a) => JOB_ID.test(a.getAttribute('href') || ''));
  // Prefer the link inside a heading (the title), else the first job link with text.
  return jobLinks.find((a) => a.closest('h1, h2, h3, h4')) ?? jobLinks.find((a) => a.textContent?.trim()) ?? null;
}

/** The Upwork job id (digits after "~0") in a job URL, or null. */
export function jobIdFromUrl(url: string): string | null {
  return url.match(JOB_ID)?.[1] ?? null;
}

/** The tile's description text ('' when none). */
export function readTileDescription(tile: Element): string {
  const el = tile.querySelector('[data-test="UpCLineClamp JobDescription"]')
    ?? tile.querySelector('[data-test*="JobDescription"]')
    ?? tile.querySelector('[data-test*="job-description"]');
  return el?.textContent?.trim() || '';
}
