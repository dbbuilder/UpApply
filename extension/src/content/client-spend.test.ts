import { describe, expect, it } from 'vitest';
import { totalSpentFromText } from './client-spend';
import { querySelector } from './upwork-selectors';

describe('client total spent', () => {
  it('reads the amount next to "total spent", not the rating', () => {
    const about = 'About the client Payment method verified 4.8 4.84 of 12 reviews USA 32 jobs posted '
      + '100% hire rate, 4 open jobs $15K total spent 43 hires, 24 active $5.99 /hr avg hourly rate paid';
    expect(totalSpentFromText(about)).toBe('$15K');
    expect(totalSpentFromText('$8.2K total spent')).toBe('$8.2K');
    expect(totalSpentFromText('$1,250 total spent')).toBe('$1,250');
    expect(totalSpentFromText('$10K+ total spent')).toBe('$10K+');
    expect(totalSpentFromText('4.8 of 12 reviews')).toBeNull();
    expect(totalSpentFromText(null)).toBeNull();
  });

  it(':has-text picks the smallest matching element, never the whole page', () => {
    document.body.innerHTML = '<section><span>4.8</span><div class="spend"><strong>$15K</strong> total spent</div></section>';
    expect(querySelector([':has-text("total spent")'])?.className).toBe('spend');
  });
});
