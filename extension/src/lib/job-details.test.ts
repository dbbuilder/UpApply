import { describe, expect, it } from 'vitest';
import { cardFacts, countryMatches, payMatches, payValues, postedLabel, postedWithin } from './job-details';

const NOW = new Date('2026-11-15T12:00:00Z');

function card(html: string): Element {
  const el = document.createElement('article');
  el.innerHTML = html;
  return el;
}

describe('job card details', () => {
  it('reads pay, posted time, country, spend, rating, proposals and level from a tile', () => {
    const facts = cardFacts(card(`
      <small data-test="job-pubilshed-date"><span>Posted 3 hours ago</span></small>
      <ul><li data-test="payment-verified">Payment verified</li><li data-test="total-feedback">Rating is 4.9 out of 5.</li>
      <li data-test="total-spent">$90K+ spent</li><li data-test="location">Location United States</li></ul>
      <p>Hourly: $80.00 - $120.00 - Expert - Est. time: 1 to 3 months</p><p>Proposals: 5 to 10</p>`), NOW);
    expect(facts.budgetType).toBe('hourly');
    expect(facts.budgetAmount).toBe('$80.00-$120.00');
    expect(facts.details).toEqual({
      posted_at: '2026-11-15T09:00:00.000Z', posted_text: 'Posted 3 hours ago', client_country: 'United States',
      client_spent: '$90K+', client_rating: '4.9', payment_verified: true, proposals: '5 to 10',
      experience_level: 'Expert',
    });
  });

  it('leaves out what the card does not show', () => {
    expect(cardFacts(card('<p>Fixed-price</p>'), NOW)).toEqual({ budgetAmount: null, budgetType: 'fixed', details: {} });
  });

  it('parses pay figures', () => {
    expect(payValues('$80.00-$120.00')).toEqual([80, 120]);
    expect(payValues('$5K')).toEqual([5000]);
    expect(payValues(null)).toEqual([]);
  });
});

describe('Find filters', () => {
  const hourly = { budget_amount: '$60-$100', budget_type: 'hourly' };
  const fixed = { budget_amount: '$3,000', budget_type: 'fixed' };

  it('pay: hourly uses the top of the range, fixed the amount; unknown pay is out', () => {
    expect(payMatches(hourly, 'h80')).toBe(true);
    expect(payMatches(hourly, 'h100')).toBe(true);
    expect(payMatches({ ...hourly, budget_amount: '$40-$70' }, 'h80')).toBe(false);
    expect(payMatches(fixed, 'f1000')).toBe(true);
    expect(payMatches(fixed, 'f5000')).toBe(false);
    expect(payMatches(fixed, 'h60')).toBe(false);
    expect(payMatches({}, 'h60')).toBe(false);
    expect(payMatches({}, 'any')).toBe(true);
  });

  it('posted within; unknown dates are out while a date filter is on', () => {
    const recent = { details: { posted_at: '2026-11-15T02:00:00Z' } };
    const older = { details: { posted_at: '2026-11-10T12:00:00Z' } };
    expect(postedWithin(recent, '1', NOW)).toBe(true);
    expect(postedWithin(older, '3', NOW)).toBe(false);
    expect(postedWithin(older, '7', NOW)).toBe(true);
    expect(postedWithin({}, '14', NOW)).toBe(false);
    expect(postedWithin({}, 'any', NOW)).toBe(true);
  });

  it('country and posted label', () => {
    expect(countryMatches({ details: { client_country: 'United Kingdom' } }, 'United Kingdom')).toBe(true);
    expect(countryMatches({ details: {} }, 'United States')).toBe(false);
    expect(countryMatches({}, '')).toBe(true);
    expect(postedLabel({ posted_at: '2026-11-15T09:00:00Z' }, NOW)).toBe('Posted 3h ago');
    expect(postedLabel({ posted_at: '2026-11-12T09:00:00Z' }, NOW)).toBe('Posted 3d ago');
    expect(postedLabel({ posted_text: 'Posted yesterday' }, NOW)).toBe('Posted yesterday');
  });
});
