import { describe, expect, it } from 'vitest';
import { findTitleLink, jobIdFromUrl, readTileDescription } from './job-cards';

function tile(html: string): Element {
  const wrap = document.createElement('div');
  wrap.innerHTML = `<article data-test="JobTile">${html}</article>`;
  return wrap.firstElementChild!;
}

describe('findTitleLink', () => {
  it('uses the saved-jobs title link when it is tagged', () => {
    const t = tile('<a href="/jobs/~021111111111111111111">Client</a><a data-test="job-tile-title-link" href="/jobs/Title_~022222222222222222222/">Title</a>');
    expect(findTitleLink(t)?.textContent).toBe('Title');
  });

  it('finds the untagged search-page title link inside the heading', () => {
    const t = tile(
      '<a href="/jobs/search/?q=sql">Search</a>' +
      '<h2 class="job-tile-title"><a data-test="UpLink" href="/jobs/SQL-Server-DBA_~021985123456789012345/?referrer_url_path=/nx/search/jobs/">SQL Server DBA</a></h2>' +
      '<a href="/jobs/SQL-Server-DBA_~021985123456789012345/">Apply</a>');
    expect(findTitleLink(t)?.textContent).toBe('SQL Server DBA');
  });

  it('falls back to the first job link with text when there is no heading', () => {
    const t = tile('<a href="/jobs/x_~021985123456789012345/"></a><a href="/jobs/x_~021985123456789012345/">Fractional CTO</a>');
    expect(findTitleLink(t)?.textContent).toBe('Fractional CTO');
  });

  it('returns null for a tile with no link to a job', () => {
    expect(findTitleLink(tile('<a href="/jobs/search/?q=sql">Search</a><h2>No link</h2>'))).toBeNull();
  });
});

describe('jobIdFromUrl / readTileDescription', () => {
  it('reads the job id', () => {
    expect(jobIdFromUrl('https://www.upwork.com/jobs/SQL_~021985123456789012345/')).toBe('21985123456789012345');
    expect(jobIdFromUrl('https://www.upwork.com/jobs/search/')).toBeNull();
  });

  it('reads the description from either data-test spelling', () => {
    expect(readTileDescription(tile('<p data-test="UpCLineClamp JobDescription"> Tune queries </p>'))).toBe('Tune queries');
    expect(readTileDescription(tile('<div data-test="JobDescription"><p>Migrate to Azure</p></div>'))).toBe('Migrate to Azure');
    expect(readTileDescription(tile('<p>none</p>'))).toBe('');
  });
});
