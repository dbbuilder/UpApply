// Client trust card (API: app/services/client_trust.py). Kept separate from the match score.

export type TrustEffect = 'positive' | 'neutral' | 'caution';

export interface TrustSignal {
  label: string;
  value: string;
  effect: TrustEffect;
}

export interface ClientTrust {
  tier: 'High Confidence' | 'Proceed with Caution' | 'Suspicious';
  signals: TrustSignal[];
  notes?: string[];
}

/** Existing badge class for a tier chip. */
export function tierBadgeClass(tier: string): string {
  if (tier === 'High Confidence') return 'badge-green';
  if (tier === 'Suspicious') return 'badge-red';
  if (tier === 'Proceed with Caution') return 'badge-yellow';
  return 'badge-gray';
}

/** Marker and text colour for one signal line. */
export function signalStyle(effect: string): { mark: string; className: string } {
  if (effect === 'positive') return { mark: '✓', className: 'text-green-600' };
  if (effect === 'caution') return { mark: '!', className: 'text-yellow-600' };
  return { mark: '•', className: 'text-gray-500' };
}

/** Keep the trust card from the list response when a single-item update omits it. */
export function keepClientTrust<T extends { client_trust?: ClientTrust | null }>(updated: T, previous: T): T {
  return updated.client_trust ? updated : { ...updated, client_trust: previous.client_trust };
}
