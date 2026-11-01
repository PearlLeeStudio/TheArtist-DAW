import { useEffect } from 'react';
import { useImportReviewStore } from '../../store/importReviewStore';
import { useSongStore } from '../../store/songStore';

/** How long a finished check stays on screen before it clears itself. */
const LINGER_MS = 12_000;

/** One quiet line above the staff while an imported score is checked against
 *  its original, then the outcome until it clears itself or is dismissed. */
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
  const first = review.flagged[0];
  return (
    <p role="status" aria-live="polite" className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: 'var(--text-soft)' }}>
      <span className="min-w-0 flex-1">{running ? review.label : review.summary}</span>
      {!running && first !== undefined && (
        <button type="button" className="underline" onClick={() => selectSlot({ measureIndex: first, slotIndex: 0 })}>
          Show bar {first + 1}
        </button>
      )}
      <button type="button" className="underline" onClick={running ? review.cancel : review.dismiss}
        aria-label={running ? 'Cancel the check' : 'Dismiss'}>
        {running ? 'Cancel' : '×'}
      </button>
    </p>
  );
}
