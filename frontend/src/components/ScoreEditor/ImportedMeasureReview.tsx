import type { Song, SlotAddress } from '../../models/types';

interface ImportedMeasureReviewProps {
  song: Song;
  selectedSlots: SlotAddress[];
}

/** Source evidence stays separate from the editable chords. Only the selected
 *  bar is shown, so a long imported score does not become another analysis table. */
export default function ImportedMeasureReview({ song, selectedSlots }: ImportedMeasureReviewProps) {
  const sources = song.importSource?.measures;
  if (!sources?.length) return null;
  const unresolved = sources.reduce((count, source, index) => {
    const measure = song.measures[index];
    if (!measure) return count;
    const explicitNoChord = measure.chords.every((chord) => chord === null) && (source.originalNoChord || source.userNoChord);
    return count + Number(!explicitNoChord && measure.chords.some((chord) => chord === null));
  }, 0);
  const index = selectedSlots[0]?.measureIndex;
  const source = index === undefined ? undefined : sources[index];
  const measure = index === undefined ? undefined : song.measures[index];
  const selectedCount = new Set(selectedSlots.map((slot) => slot.measureIndex)).size;
  const explicitNoChord = !!measure && measure.chords.every((chord) => chord === null) && !!(source?.originalNoChord || source?.userNoChord);
  const hasUnresolved = !!measure && !explicitNoChord && measure.chords.some((chord) => chord === null);

  return (
    <div className="mb-3 space-y-1 text-xs" style={{ color: 'var(--text-muted)' }}>
      <p>{unresolved > 0 ? `${unresolved} imported ${unresolved === 1 ? 'bar has' : 'bars have'} unresolved chord slots. ` : ''}Select a bar and use Input → Set Chord or MIDI to edit its chords.</p>
      {source && measure && index !== undefined && (
        <details key={`${song.id}-${index}`} style={{ borderLeft: '2px solid var(--border)', paddingLeft: 10 }}>
          <summary className="cursor-pointer" style={{ color: 'var(--text-soft)' }}>
            Bar {index + 1} · {hasUnresolved ? 'Unresolved' : explicitNoChord ? 'N.C.' : source.chordBasis === 'inferred' ? 'Inferred harmony' : 'Imported chords'} · Source details{selectedCount > 1 ? ` · first of ${selectedCount} selected bars` : ''}
          </summary>
          <div className="mt-2 space-y-1 break-words leading-relaxed">
            <p>Source details retain the original import order and stay unchanged when you edit the score.</p>
            {source.editorReview && <p role="status">Import note: {source.editorReview}</p>}
            <p>
              Original bar {(source.sourceMeasureIndex ?? index) + 1} · {source.chordBasis === 'inferred' ? 'Proposed' : 'Read'}: {source.originalChords.join(' · ') || (source.originalNoChord ? 'N.C.' : 'No chord identified')} · {source.confidence} confidence.
            </p>
            {source.userNoChord && <p>You chose N.C. at import; the original did not state N.C.</p>}
            {hasUnresolved && <p>Unresolved slots have no chord assigned. They are not marked N.C.; choose their harmony in the editor.</p>}
            {source.writtenNotes?.length ? <p>Written notes: {source.writtenNotes.join(' · ')}</p> : null}
            {source.notes?.length && (!source.writtenNotes?.length || JSON.stringify(source.writtenNotes) !== JSON.stringify(source.notes)) ? <p>{source.writtenNotes?.length ? 'Sounding notes' : 'Notes'}: {source.notes.join(' · ')}</p> : null}
            {source.bassNotes?.length ? <p>Bass: {source.bassNotes.join(' · ')}</p> : null}
            {source.timeSignature && <p>Source meter: {source.timeSignature.join('/')}</p>}
            {source.evidence && <p>{source.evidence}</p>}
          </div>
        </details>
      )}
    </div>
  );
}
