import { beforeEach, describe, expect, it } from 'vitest';
import { locationRestriction } from './location-restriction';

describe("Upwork's location rule on a job page", () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('reads the header line, not the surrounding page', () => {
    document.body.innerHTML = `<header><span>Posted yesterday</span>
      <div class="loc"><svg></svg><span>Only freelancers located in the U.S. may apply.</span></div></header>
      <section><p>Finish our React/TypeScript CRM.</p></section>`;
    expect(locationRestriction()).toBe('Only freelancers located in the U.S. may apply.');
  });

  it('a job open worldwide has none', () => {
    document.body.innerHTML = '<span>Posted 1 hour ago</span><span>Worldwide</span>';
    expect(locationRestriction()).toBeNull();
  });
});
