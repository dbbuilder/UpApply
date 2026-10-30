import { signalStyle, tierBadgeClass, type ClientTrust } from '../../lib/client-trust';

/** Client trust tier chip and signal list; shown beside, never mixed into, the match score. */
export default function ClientTrustCard({ trust, compact = false }: { trust: ClientTrust; compact?: boolean }) {
  return (
    <div className={compact ? 'space-y-1' : 'mb-3'}>
      <div className="flex items-center gap-2 mb-1">
        {!compact && <h5 className="text-sm font-medium text-gray-700">Client</h5>}
        <span className={`badge ${tierBadgeClass(trust.tier)}${compact ? ' text-[10px] px-1.5' : ''}`}>
          {trust.tier}
        </span>
      </div>
      {trust.signals.length > 0 && (
        <ul className={`${compact ? 'text-[10px]' : 'text-sm'} space-y-0.5`}>
          {trust.signals.map((signal) => {
            const { mark, className } = signalStyle(signal.effect);
            return (
              <li key={signal.label} className={className}>
                {mark} {signal.label}: {signal.value}
              </li>
            );
          })}
        </ul>
      )}
      {!compact && trust.notes?.map((note) => (
        <p key={note} className="text-xs text-gray-400 mt-1">{note}</p>
      ))}
    </div>
  );
}
