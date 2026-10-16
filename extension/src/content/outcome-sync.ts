/**
 * Pure reader for outcome sync (spec §3.3): Upwork Proposals-page rows → outcome items.
 * Reads textContent / attributes only.
 */
import type { ProposalOutcomeItem } from '../lib/api-client';

const PROPOSAL_ID = /\/nx\/proposals\/(?:interview\/uid\/)?(\d+)/;
const DATE = /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+\d{4}/;

function text(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function statusFor(row: Element): string {
  const section = row.getAttribute('data-ev-sublocation') ?? '';
  if (section === 'interviews' || section === 'archived_interviews') return 'interviewed';
  if (section === 'active_candidacies') return 'responded';
  if (section === 'archived_proposals') {
    const why = text(row.querySelector('[data-qa="reason-slot"]')).toLowerCase();
    if (/\bhired\b|contract (started|offered)|offer accepted/.test(why)) return 'hired';
    if (/declin|not selected|rejected|another freelancer/.test(why)) return 'declined';
    return 'submitted'; // closed / expired / withdrawn: no signal (server applies the 14-day rule)
  }
  if (/\bviewed\b/i.test(text(row.querySelector('[data-cy="proposal-views-slot"]')))) return 'viewed';
  return 'submitted';
}

export function extractOutcomeItems(root: ParentNode = document): ProposalOutcomeItem[] {
  const items: ProposalOutcomeItem[] = [];
  const seen = new Set<string>();
  for (const link of Array.from(root.querySelectorAll<HTMLAnchorElement>('tr a[data-ev-label="jpn_list_details_link"], tr a[href*="/nx/proposals/"]'))) {
    const id = (link.getAttribute('href') ?? '').match(PROPOSAL_ID)?.[1];
    const row = link.closest('tr');
    const title = text(link) || (link.getAttribute('aria-label') ?? '').replace(/ Boosted$/, '').trim();
    if (!id || !row || !title || seen.has(id)) continue;
    seen.add(id);
    const date = text(row.querySelector('td[data-cy="time-slot"]')).match(DATE)?.[0];
    items.push({
      upwork_proposal_id: id,
      job_title: title.slice(0, 500),
      status: statusFor(row),
      ...(date ? { submitted_at: date } : {}),
    });
  }
  return items;
}
