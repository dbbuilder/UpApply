import { describe, expect, it } from 'vitest';
import { extractOutcomeItems } from './outcome-sync';

// Row shapes copied from saved Upwork Proposals / Archived pages (working/*.html).
function row(sublocation: string, href: string, title: string, date: string, extra = ''): string {
  return `<tr class="details-row" data-ev-sublocation="${sublocation}">
    <td data-cy="time-slot"><div> Initiated <span class="nowrap"> ${date} </span></div></td>
    <td data-cy="job-info"><a href="${href}" data-ev-label="jpn_list_details_link"> ${title} </a></td>
    ${extra}
  </tr>`;
}

function reason(text: string): string {
  return `<td data-qa="reason-slot" class="reason-slot"><div> ${text} </div></td>`;
}

function load(rows: string[]): Document {
  return new DOMParser().parseFromString(`<table><tbody>${rows.join('')}</tbody></table>`, 'text/html');
}

const P = 'https://www.upwork.com/nx/proposals/';

describe('extractOutcomeItems', () => {
  it('maps every Proposals-page section to an outcome status', () => {
    const doc = load([
      row('submitted_proposals', `${P}1001`, 'Submitted job', 'Mar 3, 2026'),
      row('submitted_proposals', `${P}1002`, 'Viewed job', 'Mar 2, 2026',
        '<td data-cy="proposal-views-slot"><div> Viewed by client </div></td>'),
      row('active_candidacies', `${P}1003`, 'Active job', 'Feb 28, 2026'),
      row('interviews', `${P}interview/uid/2001`, 'Interview job', 'Feb 6, 2026'),
      row('archived_interviews', `${P}interview/uid/2002`, 'Old interview', 'Aug 26, 2025', reason('Expired')),
      row('archived_proposals', `${P}1004`, 'Hired job', 'Jan 5, 2026', reason('Hired')),
      row('archived_proposals', `${P}1005`, 'Declined job', 'Jan 4, 2026', reason('Declined by client')),
      row('archived_proposals', `${P}1006`, 'Closed job', 'Jan 3, 2026', reason('Job is closed')),
    ]);

    expect(extractOutcomeItems(doc)).toEqual([
      { upwork_proposal_id: '1001', job_title: 'Submitted job', status: 'submitted', submitted_at: 'Mar 3, 2026' },
      { upwork_proposal_id: '1002', job_title: 'Viewed job', status: 'viewed', submitted_at: 'Mar 2, 2026' },
      { upwork_proposal_id: '1003', job_title: 'Active job', status: 'responded', submitted_at: 'Feb 28, 2026' },
      { upwork_proposal_id: '2001', job_title: 'Interview job', status: 'interviewed', submitted_at: 'Feb 6, 2026' },
      { upwork_proposal_id: '2002', job_title: 'Old interview', status: 'interviewed', submitted_at: 'Aug 26, 2025' },
      { upwork_proposal_id: '1004', job_title: 'Hired job', status: 'hired', submitted_at: 'Jan 5, 2026' },
      { upwork_proposal_id: '1005', job_title: 'Declined job', status: 'declined', submitted_at: 'Jan 4, 2026' },
      { upwork_proposal_id: '1006', job_title: 'Closed job', status: 'submitted', submitted_at: 'Jan 3, 2026' },
    ]);
  });

  it('skips rows without a proposal id and duplicate links', () => {
    const doc = load([
      row('active_candidacies', 'https://support.upwork.com/hc/en-us/articles/1-Boosted', 'Help link', 'Feb 26, 2026'),
      row('active_candidacies', `${P}1003`, 'Active job', 'Feb 28, 2026'),
      row('active_candidacies', `${P}1003`, 'Active job', 'Feb 28, 2026'),
    ]);
    expect(extractOutcomeItems(doc).map(i => i.upwork_proposal_id)).toEqual(['1003']);
  });
});
