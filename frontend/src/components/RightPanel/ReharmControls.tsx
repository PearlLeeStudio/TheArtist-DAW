import { useState } from 'react';
import { useSongStore } from '../../store/songStore';
import { useReharmonizeStore } from '../../store/reharmonizeStore';
import { useGenerationStore } from '../../store/generationStore';
import { REHARM_MODES, reharmSelectionError, reharmTargets } from '../../engine/reharmonize';
import type { ReharmMode } from '../../engine/reharmonize';

export default function ReharmControls({ modelKey }: { modelKey: string }) {
  const song = useSongStore(s => s.song);
  const slots = useSongStore(s => s.selectedSlots);
  const loading = useReharmonizeStore(s => s.loading);
  const generating = useGenerationStore(s => s.loading);
  const run = useReharmonizeStore(s => s.run);
  const [maxChanges, setMaxChanges] = useState<1 | 2>(1);
  const [mode, setMode] = useState<ReharmMode>('auto');
  const problem = reharmSelectionError(song, slots);
  const targetCount = reharmTargets(song, slots).length;
  const disabled = loading || generating || !!problem;
  const selectStyle = { background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' };
  return <div className="space-y-3">
    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
      Explore three substitutes in context. Switch A/B/C on the score and use Play to compare.
    </p>
    <label className="flex items-center justify-between gap-2 text-xs">
      Change up to
      <select aria-label="Maximum changed chords per candidate" value={maxChanges}
        onChange={e => setMaxChanges(e.target.value === '2' ? 2 : 1)} className="px-2 py-1" style={selectStyle}>
        <option value={1}>1 chord</option><option value={2}>2 chords</option>
      </select>
    </label>
    <label className="flex items-center justify-between gap-2 text-xs">
      Mode
      <select aria-label="Mode preference for substitutes" value={mode}
        onChange={e => setMode(e.target.value as ReharmMode)} className="px-2 py-1 capitalize" style={selectStyle}>
        {REHARM_MODES.map(m => <option key={m} value={m}>{m === 'auto' ? 'Auto · In context' : m}</option>)}
      </select>
    </label>
    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
      {mode === 'auto' ? 'Considers familiar substitutions and how they connect to surrounding chords.'
        : 'Only substitutes compatible with this parallel mode.'}
    </p>
    {!problem && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
      {targetCount} {targetCount === 1 ? 'chord' : 'chords'} selected. Empty slots stay unchanged.
    </p>}
    <button disabled={disabled} onClick={() => void run(modelKey, maxChanges, mode)}
      className="w-full px-3 py-2 text-sm font-bold"
      style={{ background: 'var(--brand-yellow)', color: '#1a1a1a', opacity: disabled ? .55 : 1 }}>
      {loading ? 'Exploring substitutes…' : 'Find 3 alternatives'}
    </button>
    {problem && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{problem}</p>}
  </div>;
}
