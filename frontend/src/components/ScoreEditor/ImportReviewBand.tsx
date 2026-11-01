import { useImportReviewStore } from '../../store/importReviewStore';
import { useSongStore } from '../../store/songStore';

const buttonStyle: React.CSSProperties = {
  background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)',
};

/** Above the staff while a background Meta reading checks an imported score,
 *  then its outcome: how many bars were flagged or filled, with the request id. */
export default function ImportReviewBand() {
  const review = useImportReviewStore();
  const songEpoch = useSongStore((s) => s.songEpoch);
  const selectSlot = useSongStore((s) => s.selectSlot);
  if (review.phase === 'idle' || review.songEpoch !== songEpoch) return null;
  const running = review.phase === 'running';
  const first = review.flagged[0];
  return (
    <div role="status" aria-live="polite" className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-xs"
      style={{ border: '1px solid var(--border)', borderLeft: '3px solid var(--brand-yellow)', background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
      <span className="font-semibold" style={{ color: 'var(--text-heading)' }}>Meta review</span>
      <span className="min-w-0 flex-1">{running ? review.label : review.summary}</span>
      {!running && review.requestId && <span>Request {review.requestId}</span>}
      {!running && first !== undefined && (
        <button type="button" className="px-2 py-1 btn-hover" style={buttonStyle}
          onClick={() => selectSlot({ measureIndex: first, slotIndex: 0 })}>
          Show bar {first + 1}
        </button>
      )}
      <button type="button" className="px-2 py-1 btn-hover" style={buttonStyle} onClick={running ? review.cancel : review.dismiss}>
        {running ? 'Cancel' : 'Dismiss'}
      </button>
    </div>
  );
}
