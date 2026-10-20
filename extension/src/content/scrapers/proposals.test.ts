import { describe, expect, it } from 'vitest';
import fixture from '../__fixtures__/proposal-details.html?raw';
import { expandJobDescription, readJobDescription, scrapeProposalDetail } from './proposals';

function loadFixture(): Document {
  return new DOMParser().parseFromString(fixture, 'text/html');
}

describe('readJobDescription', () => {
  it('reads the job description, without the title, skills, terms or cover letter', () => {
    const text = readJobDescription(loadFixture());
    expect(text).toMatch(/^I have a physical electronic technology device/);
    expect(text).toMatch(/startup support necessary\.$/);
    expect(text).not.toMatch(/Tech Startup Consultant Needed|More\/Less|Fundraising|Hourly rate|Getting a hardware product/);
  });

  it('drops the trailing "more" toggle text', () => {
    expect(readJobDescription(loadFixture())).not.toMatch(/more$/);
  });

  it('returns null when the page has no proposal details', () => {
    expect(readJobDescription(new DOMParser().parseFromString('<main><p>x</p></main>', 'text/html'))).toBeNull();
  });
});

describe('expandJobDescription', () => {
  it('clicks each "more" toggle inside the proposal details', () => {
    const doc = loadFixture();
    let clicks = 0;
    doc.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { clicks++; }));
    expect(expandJobDescription(doc)).toBe(1);
    expect(clicks).toBe(1);
  });
});

describe('scrapeProposalDetail', () => {
  it('still reads the cover letter from the cover-letter section', () => {
    // scrapeProposalDetail reads the global document
    document.body.innerHTML = fixture;
    expect(scrapeProposalDetail().coverLetter).toMatch(/^Getting a hardware product/);
  });
});
