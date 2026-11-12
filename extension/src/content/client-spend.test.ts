import { beforeEach, describe, expect, it } from 'vitest';
import { clientTotalSpent, totalSpentFromText } from './client-spend';
import { querySelector } from './upwork-selectors';

const PAGE = (client: string, description = 'Build our CRM.') => `
  <main>
    <section class="description"><h2>Summary</h2><p>${description}</p></section>
    <aside><div class="client">
      <h4>About the client</h4>
      <p>Payment method verified</p><p>4.8 of 12 reviews</p>
      ${client}
    </div></aside>
  </main>`;

describe('client total spent', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('reads the amount next to "total spent", not the rating', () => {
    expect(totalSpentFromText('4.8 of 12 reviews 32 jobs posted $15K total spent 43 hires')).toBe('$15K');
    expect(totalSpentFromText('$8.2K total spent')).toBe('$8.2K');
    expect(totalSpentFromText('$1,250 total spent')).toBe('$1,250');
    expect(totalSpentFromText('$10K+ total spent')).toBe('$10K+');
    expect(totalSpentFromText('4.8 of 12 reviews')).toBeNull();
    expect(totalSpentFromText(null)).toBeNull();
  });

  it('reads only the About the client section, never the job description', () => {
    document.body.innerHTML = PAGE('<p><strong>$15K</strong> total spent</p>',
      'Trusted client: $900K total spent on Upwork!');
    expect(clientTotalSpent()).toBe('$15K');
  });

  it('a description claim with no client section is no data', () => {
    document.body.innerHTML = '<section><p>Trusted client: $900K total spent on Upwork!</p></section>';
    expect(clientTotalSpent()).toBeNull();
  });

  it('a tagged client container wins', () => {
    document.body.innerHTML = '<div data-test="about-client-container"><span>$2.5K total spent</span></div>'
      + '<p>$900K total spent</p>';
    expect(clientTotalSpent()).toBe('$2.5K');
  });

  it(':has-text picks the smallest matching element, never the whole page', () => {
    document.body.innerHTML = '<section><span>4.8</span><div class="spend"><strong>$15K</strong> total spent</div></section>';
    expect(querySelector([':has-text("total spent")'])?.className).toBe('spend');
  });
});
