import { useEffect } from 'react';
import { useImportReviewStore } from '../../store/importReviewStore';
import { useSongStore } from '../../store/songStore';

/** How long a finished check stays on screen before it clears itself. */
const LINGER_MS = 20_000;

/** One quiet line above the staff while an imported score is checked against its
 *  original, then a box with the outcome: yellow when Meta read the original and the
 *  check ran, plain when the local reader stood in or the check failed. It clears
 *  itself after a while or when dismissed. */
export default function ImportReviewBand() {
  const review = useImportReviewStore();
  const songEpoch = useSongStore((s) => s.songEpoch);
  const selectSlot = useSongStore((s) => s.selectSlot);
  const running = review.phase === 'running';
  const shown = review.phase !== 'idle' && review.songEpoch === songEpoch;
  useEffect(() => {
    if (!shown || running) return;
    const timer = window.setTimeout(() => useImportReviewStore.getState().dismiss(), LINGER_MS);
    return () => window.clearTimeout(timer);
  }, [shown, running, review.summary]);
  if (!shown) return null;
  if (running) {
    return (
      <p role="status" aria-live="polite" className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: 'var(--text-soft)' }}>
        <span className="min-w-0 flex-1">{review.label}</span>
        <button type="button" className="underline" onClick={review.cancel} aria-label="Cancel the check">Cancel</button>
      </p>
    );
  }
  const meta = review.phase === 'done' && review.outcome === 'meta';
  const title = meta ? `✓ Meta ${review.model ?? ''} checked this score against the original`.replace(/\s{2,}/g, ' ')
    : review.phase === 'failed' ? 'Meta check failed'
      : review.outcome === 'local' ? 'Local reader kept the score' : 'Check finished';
  const first = review.flagged[0];
  return (
    <div role="status" aria-live="polite" className="mb-3 px-3 py-2 text-xs" style={meta
      ? { background: 'var(--brand-yellow)', color: '#1a1a1a' }
      : { border: '1px solid var(--border)', color: 'var(--text-primary)' }}>
      <strong className="block text-sm">{title}</strong>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-0 flex-1">{review.summary}{meta && review.requestId ? ` · request ${review.requestId}` : ''}</span>
        {first !== undefined && (
          <button type="button" className="underline" onClick={() => selectSlot({ measureIndex: first, slotIndex: 0 })}>
            Show bar {first + 1}
          </button>
        )}
        <button type="button" className="underline" onClick={review.dismiss} aria-label="Dismiss">×</button>
      </span>
    </div>
  );
}
