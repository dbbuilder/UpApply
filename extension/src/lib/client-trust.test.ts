import { describe, expect, it } from 'vitest';
import { keepClientTrust, signalStyle, tierBadgeClass, type ClientTrust } from './client-trust';

const card: ClientTrust = {
  tier: 'Proceed with Caution',
  signals: [{ label: 'Reposted', value: 'Same title seen once in the last 30 days', effect: 'caution' }],
};

describe('client trust card helpers', () => {
  it('maps tiers to the existing badge classes', () => {
    expect(tierBadgeClass('High Confidence')).toBe('badge-green');
    expect(tierBadgeClass('Proceed with Caution')).toBe('badge-yellow');
    expect(tierBadgeClass('Suspicious')).toBe('badge-red');
    expect(tierBadgeClass('anything else')).toBe('badge-gray');
  });

  it('styles each signal effect', () => {
    expect(signalStyle('positive').className).toBe('text-green-600');
    expect(signalStyle('caution').mark).toBe('!');
    expect(signalStyle('neutral').className).toBe('text-gray-500');
  });

  it('keeps the list card when an action response has none', () => {
    const previous: { id: string; client_trust?: ClientTrust | null } = { id: '1', client_trust: card };
    expect(keepClientTrust({ id: '1', client_trust: null }, previous).client_trust).toBe(card);
    const fresh = { ...card, tier: 'High Confidence' as const };
    expect(keepClientTrust({ id: '1', client_trust: fresh }, previous).client_trust).toBe(fresh);
  });
});
