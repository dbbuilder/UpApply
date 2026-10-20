import { describe, expect, it } from 'vitest';
import { proposalFromNuxtData, reviveNuxtPayload } from './proposal-scrape';

// Same encoding as Upwork's __NUXT_DATA__: members are indices into the array.
const LETTER = 'Getting a hardware product from prototype to shelf is mostly about the right introductions.';
const DESCRIPTION = 'I have a physical electronic technology device that now needs to be manufactured, marketed and sold.';
const payload = [
  ['ShallowReactive', 1],                                  // 0 root
  { data: 2, state: 3, vuex: 4, serverRendered: 5 },       // 1
  ['ShallowReactive', 6],                                  // 2
  {},                                                      // 3
  { 'proposal-details': 7, interview: 8 },                 // 4
  true,                                                    // 5
  {},                                                      // 6
  { proposalDetailsV3Response: 9 },                        // 7
  { coverLetter: 10 },                                     // 8 (another store's coverLetter — must be ignored)
  { application: 11, jobDetails: 12 },                     // 9
  'interview draft',                                       // 10
  { coverLetter: 13, status: 14, terms: 15, questionsAnswers: 16 }, // 11
  { opening: 17 },                                         // 12
  LETTER,                                                  // 13
  7,                                                       // 14
  { chargeRate: 18 },                                      // 15
  [19],                                                    // 16
  { job: 20 },                                             // 17
  { amount: 21 },                                          // 18
  { question: 22, answer: 23 },                            // 19
  { info: 24, description: 25 },                           // 20
  90,                                                      // 21
  'Why you?',                                              // 22
  'Shipped hardware twice.',                               // 23
  { title: 26 },                                           // 24
  DESCRIPTION,                                             // 25
  'Tech Startup Consultant Needed',                        // 26
];

describe('reviveNuxtPayload', () => {
  it('unwraps reactive wrappers and resolves indices', () => {
    const root = reviveNuxtPayload(payload) as Record<string, any>;
    expect(root.serverRendered).toBe(true);
    expect(root.vuex['proposal-details'].proposalDetailsV3Response.application.coverLetter).toBe(LETTER);
  });

  it('survives shared and cyclic references', () => {
    const cyclic = [{ self: 0, name: 1 }, 'x'];
    const root = reviveNuxtPayload(cyclic) as Record<string, any>;
    expect(root.self).toBe(root);
    expect(root.name).toBe('x');
  });
});

describe('proposalFromNuxtData', () => {
  it('reads the full letter, description, title, status, rate and answers', () => {
    const f = proposalFromNuxtData(JSON.stringify(payload))!;
    expect(f.hasApplication).toBe(true);
    expect(f.coverLetter).toBe(LETTER);
    expect(f.jobDescription).toBe(DESCRIPTION);
    expect(f.jobTitle).toBe('Tech Startup Consultant Needed');
    expect(f.status).toBe('7');
    expect(f.bidAmount).toBe('90');
    expect(f.answers).toEqual([{ question: 'Why you?', answer: 'Shipped hardware twice.' }]);
  });

  it('returns null for missing, malformed or proposal-less payloads', () => {
    expect(proposalFromNuxtData(null)).toBeNull();
    expect(proposalFromNuxtData('not json')).toBeNull();
    expect(proposalFromNuxtData(JSON.stringify([{ vuex: 1 }, {}]))).toBeNull();
  });
});
