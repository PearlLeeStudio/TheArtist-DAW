import { useReharmonizeStore } from '../../store/reharmonizeStore';

const FAMILY = { common_tones: 'Shared tones', modal: 'Modal color', dominant: 'Dominant approach' };

/** This remains on the score while the user switches to the existing Play controls. */
export default function ReharmBand() {
  const { comparison, result, loading, error, active, preview, close } = useReharmonizeStore();
  if (!comparison) return null;
  const measures = comparison.original.map(c => c.address.measureIndex + 1);
  const range = Math.min(...measures) === Math.max(...measures) ? `M${measures[0]}` : `M${Math.min(...measures)}–${Math.max(...measures)}`;
  return <section aria-label="Reharmonization comparison" className="p-3 space-y-2 rounded-md"
    style={{ color: 'var(--text-primary)', background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="text-xs font-semibold">Reharmonize · {range}</div>
      <button onClick={close} className="text-[11px] underline" aria-label="Close comparison and keep the score">
        {loading ? 'Close search' : 'Keep current & close'}
      </button>
    </div>
    {loading && <p role="status" className="text-xs">Exploring substitutions with Meta and the Music Transformer…</p>}
    {error && <p role="alert" className="text-xs">{error}</p>}
    {result && <>
      <div className="flex items-center gap-3">
        <button aria-pressed={active === null} onClick={() => preview(null)} className="px-3 py-1 text-xs font-semibold rounded"
          style={{ background: active === null ? 'var(--text-heading)' : 'var(--btn-bg)',
            color: active === null ? 'var(--bg-primary)' : 'var(--text-primary)' }}>Original</button>
        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Choose a version, then use Play. A/B/C stay here.</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {result.candidates.map((candidate, index) => <button key={candidate.id} aria-pressed={active === index}
          aria-label={`Preview candidate ${'ABC'[index]} on the score`} onClick={() => preview(index)}
          className="min-w-0 text-left px-2 py-2 rounded space-y-1"
          style={{ background: active === index ? 'var(--brand-yellow)' : 'var(--btn-bg)',
            color: active === index ? '#1a1a1a' : 'var(--text-primary)', border: '1px solid var(--border)' }}>
          <div className="flex flex-wrap items-center gap-x-2 text-xs font-semibold">
            <span>{'ABC'[index]}{active === index ? ' · On score' : ''}</span>
            <span className="text-[10px] font-normal">{FAMILY[candidate.family]}</span>
          </div>
          {candidate.changes.map(c => <div key={`${c.address.measureIndex}-${c.address.slotIndex}`} className="text-xs break-words">
            <span className="text-[10px]">M{c.address.measureIndex + 1}.{c.address.slotIndex + 1} </span>
            <span className="opacity-60">{c.before}</span> → <strong>{c.after}</strong>
          </div>)}
          <div className="text-[10px] opacity-75">
            {candidate.changes.map(c => `${c.commonTones} shared tones`).join(' · ')}
          </div>
        </button>)}
      </div>
    </>}
  </section>;
}
