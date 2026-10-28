import { useState, useCallback, useEffect, useId } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useSongStore } from '../../store/songStore';
import { useGenerationStore } from '../../store/generationStore';
import { useSessionStore, selectStarredSessions } from '../../store/sessionStore';
import GenerateProgress from './GenerateProgress';
import { getChordDisplayParts } from '../../engine/chordDisplay';
import { parseSuggestionChords } from '../../engine/chordGenerator';
import { canApplyComparison, compareCandidate, matchesCapturedRange, slotKey } from '../../engine/generationComparison';
import {
  MAX_SECTION_BARS,
  SECTION_GROUPS,
  isSectionType,
  sectionContaining,
  sectionLabel,
  sectionsInGroup,
} from '../../engine/songForm';
import type { Chord, SectionType, SlotAddress } from '../../models/types';

const ROOTS = ['C', 'C#', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

/**
 * Infer the song's genre from the picked model. Model pick always syncs
 * song.genre — Pearl 2026-05-10 found "first-time-only" sync confusing
 * (e.g. switching from blues LoRA to F4 left genre=blues, not jazz).
 * If the user wants a different genre than what the model implies, they
 * can override via SongSettings after picking the model.
 *
 * Mapping:
 *   ft_f1_lora_X        → X (LoRA carries genre tag in its key)
 *   ft_f1 / phase0      → pop  (F1/Phase0 are pop-leaning)
 *   ft_f2..f5 → jazz (jazz fine-tunes with varying pop mix)
 */
function inferGenreForModelPick(modelKey: string): string | null {
  const lora = modelKey.match(/^ft_f1_lora_(.+)$/);
  if (lora) return lora[1];
  if (modelKey === 'ft_f1' || modelKey === 'phase0') return 'pop';
  if (modelKey.startsWith('ft_f')) return 'jazz';
  return null;
}

/** 'M5' or 'M5–M12' for the measures a set of suggestions applies to. */
function measureRangeLabel(slots: SlotAddress[]): string {
  if (slots.length === 0) return '';
  const measures = slots.map((s) => s.measureIndex + 1);
  const first = Math.min(...measures);
  const last = Math.max(...measures);
  return first === last ? `M${first}` : `M${first}–M${last}`;
}

function comparisonChordLabel(chord: Chord | null): string {
  if (!chord) return '—';
  const quality = chord.quality === 'maj' ? '' : chord.quality === 'min' ? 'm' : chord.quality;
  const extensions = chord.extensions.length > 0 ? `(${chord.extensions.join(',')})` : '';
  return `${chord.root}${quality}${extensions}${chord.bass ? `/${chord.bass}` : ''}`;
}

const BASE_QUALITIES = [
  { label: 'Maj', value: 'maj' },
  { label: 'Min', value: 'min' },
  { label: 'Dim', value: 'dim' },
  { label: 'Aug', value: 'aug' },
  { label: '5', value: '5' },
];

const EXTENSIONS = [
  { label: '-', value: '' },
  { label: '6', value: '6' },
  { label: '7', value: '7' },
  { label: 'M7', value: 'maj7' },
  { label: '9', value: '9' },
  { label: 'M9', value: 'maj9' },
  { label: '11', value: '11' },
  { label: '13', value: '13' },
];

const ADD_OPTIONS = [
  { label: '-', value: '' },
  { label: 'add2', value: 'add2' },
  { label: 'add4', value: 'add4' },
  { label: 'add9', value: 'add9' },
  { label: 'add11', value: 'add11' },
];

const SUS_OPTIONS = [
  { label: '-', value: '' },
  { label: 'sus2', value: 'sus2' },
  { label: 'sus4', value: 'sus4' },
];

const ALTERATIONS = [
  { label: 'b5', value: 'b5' },
  { label: '#5', value: '#5' },
  { label: 'b9', value: 'b9' },
  { label: '#9', value: '#9' },
  { label: '#11', value: '#11' },
  { label: 'b13', value: 'b13' },
];

function resolveQuality(base: string, ext: string, add: string, sus: string): string {
  if (sus) return ext ? `${ext}${sus}` : sus;
  if (add) return base === 'min' ? `m(${add})` : add;
  if (base === '5') return ext === '7' ? '7(no3)' : '5';

  if (base === 'min') {
    if (ext === 'maj7') return 'mMaj7';
    if (ext === '7') return 'm7';
    if (ext === '9') return 'm9';
    if (ext === '11') return 'm11';
    if (ext === '13') return 'm13';
    if (ext === '6') return 'm6';
    if (ext === '') return 'min';
    return `m${ext}`;
  }
  if (base === 'dim') {
    if (ext === '7') return 'dim7';
    if (ext === '') return 'dim';
    return 'm7b5';
  }
  if (base === 'aug') return ext === '7' ? 'aug7' : 'aug';

  if (ext === '7') return '7';
  if (ext) return ext;
  return 'maj';
}

const btnStyle = (active: boolean) => ({
  background: active ? 'var(--text-heading)' : 'var(--btn-bg)',
  color: active ? 'var(--bg-primary)' : 'var(--text-primary)',
});

interface ChordActionsProps {
  /**
   * Which slice of the chord-actions UI to render.
   * - 'all'      → Generate + manual builder (legacy default).
   * - 'generate' → Model selector + Generate button + Suggestions only.
   * - 'manual'   → Manual chord builder forced open (no toggle button).
   * Used by Layout to back the right-panel Input tabs.
   */
  view?: 'all' | 'generate' | 'manual';
}

export default function ChordActions({ view = 'all' }: ChordActionsProps) {
  const selectedSlots = useSongStore((s) => s.selectedSlots);
  const song = useSongStore((s) => s.song);
  const songEpoch = useSongStore((s) => s.songEpoch);
  const setGenre = useSongStore((s) => s.setGenre);
  const setChord = useSongStore((s) => s.setChord);
  const resetPlayback = useSongStore((s) => s.resetPlayback);

  // In tab-mode 'manual', the builder is the entire view, so always open.
  const [expandedState, setExpandedState] = useState({ songEpoch, open: view === 'manual' });
  const expanded = expandedState.songEpoch === songEpoch && expandedState.open;
  const setExpanded = useCallback((open: boolean) => setExpandedState({ songEpoch, open }), [songEpoch]);
  const [root, setRoot] = useState('C');
  const [base, setBase] = useState('maj');
  const [ext, setExt] = useState('');
  const [add, setAdd] = useState('');
  const [sus, setSus] = useState('');
  const [alts, setAlts] = useState<string[]>([]);
  const [bass, setBass] = useState('');

  // AI suggestion state — hoisted to generationStore (Pearl 2026-05-10) so
  // the in-flight generate keeps running and its result lands even if the
  // user navigates away (Play tab / MyPage) before completion. Previously
  // this state lived in component-local useState and died on unmount,
  // losing the result.
  const suggestions = useGenerationStore((s) => s.suggestions);
  const loading = useGenerationStore((s) => s.loading);
  const phase = useGenerationStore((s) => s.phase);
  const generationError = useGenerationStore((s) => s.error);
  const showSuggestions = useGenerationStore((s) => s.showSuggestions);
  const activeSuggestionIdx = useGenerationStore((s) => s.activeSuggestionIdx);
  const source = useGenerationStore((s) => s.source);
  const targetSlots = useGenerationStore((s) => s.targetSlots);
  const comparison = useGenerationStore((s) => s.comparison);
  const applySuggestion = useGenerationStore((s) => s.applySuggestion);
  const restoreOriginal = useGenerationStore((s) => s.restoreOriginal);
  const clearSuggestions = useGenerationStore((s) => s.clearSuggestions);
  const runGenerate = useGenerationStore((s) => s.runGenerate);
  const runFavoriteGenerate = useGenerationStore((s) => s.runFavoriteGenerate);
  const generateSectionType = useGenerationStore((s) => s.generateSectionType);
  const setGenerateSectionType = useGenerationStore((s) => s.setGenerateSectionType);
  const sectionSelectId = useId();

  // Model selection — same store, persists to localStorage.
  const modelKey = useGenerationStore((s) => s.modelKey);
  const setModelKey = useGenerationStore((s) => s.setModelKey);
  const [modelList, setModelList] = useState<Array<{ key: string; label: string; available: boolean }>>([]);

  // Starred sessions feed Favorite Generate — one suggestion per preset.
  // useShallow keeps the snapshot reference stable across renders;
  // without it, selectStarredSessions returns a fresh array each call
  // and useSyncExternalStore enters an infinite re-render loop.
  const starredSessions = useSessionStore(useShallow(selectStarredSessions));

  // Fetch available models once on mount. Backend returns a flat `models`
  // list combining paper F-series + R4 LoRA adapters; both visible in one
  // dropdown (Pearl 2026-05-09 — single-selector preference).
  useEffect(() => {
    fetch('/api/models/list')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.models) {
          // Only surface usable checkpoints — hide any the backend reports
          // unavailable on this install so the dropdown
          // lists only models the user can actually pick.
          const usable: Array<{ key: string; label: string; available: boolean }> =
            data.models.filter((m: { available: boolean }) => m.available);
          setModelList(usable);
          // modelKey persists across reloads, so it can name a checkpoint
          // this install does not have. Move it to the backend default and
          // re-sync the genre, as a model pick would.
          const current = useGenerationStore.getState().modelKey;
          if (
            data.default &&
            !usable.some((m) => m.key === current) &&
            usable.some((m) => m.key === data.default)
          ) {
            setModelKey(data.default);
            const inferred = inferGenreForModelPick(data.default);
            if (inferred) setGenre(inferred);
          }
        }
      })
      .catch(() => { /* fallback: model list unavailable */ });
  }, [setModelKey, setGenre]);

  // Mount-time genre sync. song.genre and modelKey both persist across
  // reloads, so they normally come back in step; a song without a genre
  // (first visit, after ?reset=1 or Initialize) takes the one the
  // current model implies. Without this nudge the harmony rhythm would
  // route to the fallback pattern until the user manually picked a genre
  // in SongSettings.
  useEffect(() => {
    if (!song.genre) {
      const inferred = inferGenreForModelPick(modelKey);
      if (inferred) setGenre(inferred);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const firstSlot = selectedSlots[0] ?? null;
  // Song-form section the drag-path Generate sends: the explicit pick, or
  // for 'auto' the section that contains the whole selection (else none).
  const selectedMeasures = [...new Set(selectedSlots.map((s) => s.measureIndex))];
  const autoSection = sectionContaining(song, selectedMeasures);
  const resolvedSectionType: SectionType | null =
    generateSectionType === 'auto' ? autoSection?.type ?? null : generateSectionType;
  const tooManyMeasures = selectedMeasures.length > MAX_SECTION_BARS;
  const quality = resolveQuality(base, ext, add, sus);
  const previewParts = getChordDisplayParts({ root, quality, bass: bass || undefined, romanNumeral: '', voicing: [], extensions: alts });
  const comparisonReady = comparison !== null && canApplyComparison(comparison, song, songEpoch);
  const originalActive = activeSuggestionIdx === null && comparison !== null && matchesCapturedRange(comparison, song, songEpoch);
  const originalEmptySection = comparison?.kind === 'section' && comparison.original.every((slot) => slot.chord === null);

  const handleSet = useCallback(() => {
    if (!firstSlot) return;
    const chord: Chord = {
      root, quality,
      bass: bass || undefined,
      romanNumeral: '', voicing: [], extensions: alts,
    };
    setChord(firstSlot, chord);
    setExpanded(false);
  }, [firstSlot, root, quality, bass, alts, setChord, setExpanded]);

  const toggleAlt = (alt: string) => {
    setAlts(prev => prev.includes(alt) ? prev.filter(a => a !== alt) : [...prev, alt]);
  };

  const handleGenerate = () => {
    if (selectedSlots.length === 0 || tooManyMeasures) return;
    // Stop any ongoing playback — the user is reshaping the song; what's
    // playing won't reflect what they're about to see.
    resetPlayback();
    // Fire-and-forget: store owns the async lifecycle so navigation away
    // from this panel during generate doesn't kill the request.
    void runGenerate(song, selectedSlots, modelKey, resolvedSectionType);
  };

  // Favorite Generate — runs the generate pipeline once per starred
  // session, taking the top-ranked suggestion from each. Result count
  // equals starred-session count, so the user gets one option per
  // preset they marked. Calls run in parallel so total time is bounded
  // by the slowest single generate, not the sum.
  const handleFavoriteGenerate = () => {
    if (selectedSlots.length === 0 || starredSessions.length === 0 || tooManyMeasures) return;
    resetPlayback();
    void runFavoriteGenerate(song, selectedSlots, starredSessions, resolvedSectionType);
  };

  const slotLabel = selectedSlots.length === 1
    ? `M${firstSlot!.measureIndex + 1} Beat ${firstSlot!.slotIndex === 0 ? 1 : 3}`
    : selectedSlots.length > 0 ? `${selectedSlots.length} slots` : 'no selection';

  if (!firstSlot && !loading && !generationError && !(view !== 'manual' && showSuggestions && suggestions.length > 0)) {
    return (
      <div className="space-y-2">
        <h3 className="text-xs uppercase tracking-wide font-semibold" style={{ color: 'var(--text-heading)' }}>Chords</h3>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Select a slot on the staff</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-wide font-semibold" style={{ color: 'var(--text-heading)' }}>
        Chords <span className="font-normal normal-case">— {slotLabel}</span>
      </h3>

      {/* ---------- Generate (model) UI ---------- */}
      {(view === 'all' || view === 'generate') && (
      <>
      {/* Model selector (single dropdown — paper F-series + R4 LoRA adapters
          all visible together, Pearl 2026-05-09 preference). Picking a LoRA
          also auto-syncs song.genre (Pearl 2026-05-10) so the harmony rhythm
          pattern in playback.ts routes correctly without a second click. */}
      {modelList.length > 0 && (
        <div className="space-y-1">
          <label className="text-[10px] uppercase tracking-wide font-semibold" style={{ color: 'var(--text-muted)' }}>
            Model
          </label>
          <select
            value={modelKey}
            onChange={(e) => {
              const newKey = e.target.value;
              setModelKey(newKey);
              const inferred = inferGenreForModelPick(newKey);
              if (inferred) setGenre(inferred);
            }}
            className="w-full px-2 py-1.5  text-xs"
            style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
          >
            {modelList.map(m => (
              <option key={m.key} value={m.key}>{m.label}</option>
            ))}
          </select>
        </div>
      )}

      {/* Song-form section sent with Generate. Auto names what it resolved
          to: the section containing the whole selection, or none (no
          song-form rules). */}
      <div className="flex items-center gap-2">
        <label
          htmlFor={sectionSelectId}
          className="text-[10px] uppercase tracking-wide font-semibold shrink-0"
          style={{ color: 'var(--text-muted)' }}
        >
          Section
        </label>
        <select
          id={sectionSelectId}
          value={generateSectionType}
          onChange={(e) => {
            const v = e.target.value;
            setGenerateSectionType(isSectionType(v) ? v : 'auto');
          }}
          className="flex-1 min-w-0 px-2 py-1 text-xs"
          style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
        >
          <option value="auto">Auto ({autoSection?.type ? sectionLabel(autoSection.type) : 'none'})</option>
          {SECTION_GROUPS.map((group) => (
            <optgroup key={group.id} label={group.label}>
              {sectionsInGroup(group.id).map((type) => (
                <option key={type} value={type}>{sectionLabel(type)}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {tooManyMeasures && (
        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          Select at most {MAX_SECTION_BARS} measures to generate.
        </p>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading || tooManyMeasures || !firstSlot}
        className="w-full px-3 py-2  text-sm font-bold"
        style={{ background: 'var(--text-heading)', color: 'var(--bg-primary)', opacity: loading || tooManyMeasures || !firstSlot ? 0.6 : 1 }}
      >
        {loading ? 'Generating...' : `Generate ${selectedSlots.length > 1 ? `(${selectedSlots.length} slots)` : 'Chord'}`}
      </button>

      {/* Favorite Generate — runs once per starred session, returning one
          suggestion per preset. Hidden until the user has at least one
          starred session on MyPage. */}
      {starredSessions.length > 0 && (
        <button
          onClick={handleFavoriteGenerate}
          disabled={loading || tooManyMeasures || !firstSlot}
          className="w-full px-3 py-2 text-sm font-bold"
          style={{
            background: 'var(--brand-yellow)',
            color: '#1a1a1a',
            opacity: loading || tooManyMeasures || !firstSlot ? 0.6 : 1,
          }}
          title={`Generate one option per starred preset (${starredSessions.length})`}
        >
          ★ Favorite Generate ({starredSessions.length})
        </button>
      )}

      {/* Live progress — driven by SSE phase events from /api/generate/stream.
          Each pipeline stage gets a chip; the active one is highlighted.
          Only shown for regular Generate; Favorite Generate runs N parallel
          calls and the chip flow would race across them. */}
      {loading && phase && <GenerateProgress phase={phase} />}
      {generationError && <p role="alert" className="text-xs px-3 py-2" style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)', borderLeft: '2px solid var(--brand-yellow)' }}>{generationError}</p>}

      {/* AI Suggestions */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="space-y-1.5" style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
          <p className="text-[10px] uppercase tracking-wide font-semibold" style={{ color: 'var(--text-muted)' }}>
            Compare versions
            {targetSlots.length > 0 && <span className="normal-case"> · {measureRangeLabel(targetSlots)}</span>}
          </p>
          <p className="text-[11px]" role="status" aria-live="polite" style={{ color: 'var(--text-soft)' }}>
            {originalActive
              ? originalEmptySection ? 'Original empty section is on the score.' : 'Original is on the score.'
              : activeSuggestionIdx !== null
                ? `${suggestions[activeSuggestionIdx]?.label ?? 'Candidate'} is on the score.`
                : 'The score has your own edits in this range.'}
            {' '}Pick a version, then play the range to compare.
          </p>
          {comparison && (
            <button
              onClick={restoreOriginal}
              disabled={!comparisonReady || loading}
              aria-pressed={originalActive}
              className="w-full text-left px-3 py-2 text-xs font-semibold"
              style={{ ...btnStyle(originalActive), opacity: comparisonReady && !loading ? 1 : 0.5 }}
              title={`Restore the chords in ${measureRangeLabel(targetSlots)} as they were before this generation`}
            >
              {originalActive ? '▸ ' : ''}Original{originalEmptySection ? ' · empty section' : ''}
            </button>
          )}
          {originalEmptySection && (
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Original clears these generated chords and keeps the section.
            </p>
          )}
          {source === 'rules' && (
            <p
              className="text-[11px]"
              style={{ color: 'var(--text-soft)', borderLeft: '2px solid var(--brand-yellow)', paddingLeft: '6px' }}
            >
              Model unavailable — rule-based chords
            </p>
          )}
          {suggestions.map((s, idx) => {
            const rows = comparison ? compareCandidate(comparison, parseSuggestionChords(s)) : [];
            const changes = rows.filter((row) => row.changed);
            const chordPreview = rows.map((row) => comparisonChordLabel(row.after)).join(' | ');
            const isActive = idx === activeSuggestionIdx;
            return (
              <div
                key={idx}
                className=" text-sm"
                style={{
                  background: isActive ? 'var(--text-heading)' : 'var(--btn-bg)',
                  color: isActive ? 'var(--bg-primary)' : 'var(--text-primary)',
                  border: isActive ? '1px solid var(--text-heading)' : '1px solid transparent',
                }}
              >
                <button
                  onClick={() => applySuggestion(idx)}
                  disabled={!comparisonReady || loading}
                  aria-pressed={isActive}
                  className="w-full text-left px-3 py-2"
                >
                  <div
                    className="font-semibold text-xs truncate"
                    style={{ color: isActive ? 'var(--bg-primary)' : 'var(--text-heading)' }}
                    title={s.label}
                  >
                    {isActive ? '▸ ' : ''}{s.label}
                  </div>
                  <div
                    className="text-xs mt-0.5 truncate"
                    style={{
                      color: isActive ? 'var(--bg-primary)' : 'var(--text-muted)',
                      opacity: isActive ? 0.85 : 1,
                      fontFamily: 'monospace',
                    }}
                    title={chordPreview}
                  >
                    {chordPreview}
                  </div>
                  <div className="text-[10px] mt-1" style={{ opacity: 0.8 }}>
                    {changes.length} of {rows.length} chord symbols changed
                  </div>
                </button>
                {changes.length > 0 && (
                  <details className="px-3 pb-2 text-[10px]">
                    <summary className="cursor-pointer">Changes from Original</summary>
                    <table className="w-full mt-1 table-fixed text-left" aria-label={`${s.label}: changes from Original`}>
                      <thead>
                        <tr>
                          <th className="w-12 font-normal">Slot</th>
                          <th className="font-normal">Original</th>
                          <th className="font-normal">Candidate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {changes.slice(0, 4).map((row) => (
                          <tr key={slotKey(row.address)}>
                            <td className="py-0.5">{row.address.measureIndex + 1}.{row.address.slotIndex + 1}</td>
                            <td className="truncate pr-1" title={comparisonChordLabel(row.before)}>{comparisonChordLabel(row.before)}</td>
                            <td className="truncate" title={comparisonChordLabel(row.after)}>{comparisonChordLabel(row.after)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {changes.length > 4 && <p className="mt-1">And {changes.length - 4} more changed slots.</p>}
                  </details>
                )}
                {s.explanations && s.explanations.length > 0 && (
                  <details className="px-3 pb-2">
                    <summary
                      className="cursor-pointer text-[10px] uppercase tracking-wide"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      Theory ({s.explanations.length} transitions)
                    </summary>
                    <ul className="mt-1 space-y-1.5 text-[11px]">
                      {s.explanations.map((e, eIdx) => (
                        <li
                          key={eIdx}
                          style={{ color: 'var(--text-primary)', borderLeft: '2px solid var(--border)', paddingLeft: '6px' }}
                        >
                          <div>
                            <span style={{ fontFamily: 'monospace', color: 'var(--text-heading)' }}>
                              {e.chord_a} → {e.chord_b}
                            </span>
                            <span style={{ color: 'var(--text-muted)', marginLeft: '6px' }}>[{e.concept}]</span>
                            {e.page_start > 0 && (
                              <span style={{ color: 'var(--text-muted)', marginLeft: '6px' }}>
                                p{e.page_start}{e.page_end > e.page_start ? `-${e.page_end}` : ''}
                              </span>
                            )}
                          </div>
                          {e.explanation && (
                            <div className="mt-0.5" style={{ color: 'var(--text-muted)', lineHeight: 1.4 }}>
                              {e.explanation}
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            );
          })}
          <button
            onClick={() => clearSuggestions()}
            className="w-full px-3 py-1  text-xs"
            style={{ background: 'var(--btn-bg)', color: 'var(--text-muted)' }}
            title="Keep the chords currently on the score and close this comparison"
          >
            Keep current version
          </button>
        </div>
      )}
      </>
      )}
      {/* ---------- end Generate UI ---------- */}

      {/* Set Chord toggle (legacy 'all' layout only). Clear-in-selection
          lives in the top toolbar so destructive actions are co-located. */}
      {view === 'all' && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full px-3 py-1.5  text-sm"
          style={{ background: expanded ? 'var(--text-heading)' : 'var(--btn-bg)', color: expanded ? 'var(--bg-primary)' : 'var(--text-primary)' }}
        >
          {expanded ? 'Cancel' : 'Set Chord'}
        </button>
      )}

      {/* ---------- Manual chord builder ----------
          Always shown in 'manual' view; collapsible in 'all'; hidden in 'generate'. */}
      {(view === 'manual' || (view === 'all' && expanded)) && (
        <div className="space-y-2 pt-1" style={{ borderTop: '1px solid var(--border)' }}>
          {/* Preview */}
          <div className="flex items-center justify-center py-1.5 " style={{ background: 'var(--btn-bg)' }}>
            <span className="text-2xl font-bold" style={{ color: 'var(--text-heading)' }}>{previewParts.root}</span>
            <span className="flex flex-col ml-0.5 leading-tight" style={{ color: 'var(--text-heading)' }}>
              <span className="text-xs font-semibold -mb-0.5">{previewParts.sup || '\u00A0'}</span>
              <span className="text-xs">{previewParts.sub || '\u00A0'}</span>
            </span>
            {previewParts.bass && (
              <span className="text-lg font-bold ml-0.5" style={{ color: 'var(--text-heading)' }}>/{previewParts.bass}</span>
            )}
          </div>

          {/* Root */}
          <div>
            <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Root</label>
            <div className="flex flex-wrap gap-0.5">
              {ROOTS.map(r => (
                <button key={r} onClick={() => setRoot(r)} className="px-1.5 py-0.5  text-[11px] font-bold" style={btnStyle(r === root)}>{r}</button>
              ))}
            </div>
          </div>

          {/* Base + Sus in one row */}
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Base</label>
              <div className="flex gap-0.5">
                {BASE_QUALITIES.map(q => (
                  <button key={q.value} onClick={() => { setBase(q.value); setSus(''); }} className="flex-1 px-1 py-0.5  text-[11px]" style={btnStyle(q.value === base && !sus)}>{q.label}</button>
                ))}
              </div>
            </div>
            <div className="w-24">
              <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Sus</label>
              <div className="flex gap-0.5">
                {SUS_OPTIONS.map(s => (
                  <button key={s.value || 'n'} onClick={() => setSus(s.value)} className="flex-1 px-1 py-0.5  text-[10px]" style={btnStyle(s.value === sus)}>{s.label}</button>
                ))}
              </div>
            </div>
          </div>

          {/* Extension */}
          <div>
            <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Ext</label>
            <div className="flex flex-wrap gap-0.5">
              {EXTENSIONS.map(e => (
                <button key={e.value || 'n'} onClick={() => setExt(e.value)} className="px-1.5 py-0.5  text-[11px]" style={btnStyle(e.value === ext)}>{e.label}</button>
              ))}
            </div>
          </div>

          {/* Add */}
          <div>
            <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Add</label>
            <div className="flex gap-0.5">
              {ADD_OPTIONS.map(a => (
                <button key={a.value || 'n'} onClick={() => setAdd(a.value)} className="px-1.5 py-0.5  text-[11px]" style={btnStyle(a.value === add)}>{a.label}</button>
              ))}
            </div>
          </div>

          {/* Alterations */}
          <div>
            <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Alt</label>
            <div className="flex gap-0.5">
              {ALTERATIONS.map(a => (
                <button key={a.value} onClick={() => toggleAlt(a.value)} className="px-1.5 py-0.5  text-[11px]"
                  style={alts.includes(a.value) ? { background: 'var(--text-accent)', color: 'var(--bg-primary)' } : { background: 'var(--btn-bg)', color: 'var(--text-primary)' }}
                >{a.label}</button>
              ))}
            </div>
          </div>

          {/* Bass (slash chord) */}
          <div>
            <label className="text-[10px] block mb-0.5" style={{ color: 'var(--text-muted)' }}>Bass /</label>
            <div className="flex flex-wrap gap-0.5">
              <button onClick={() => setBass('')} className="px-1.5 py-0.5  text-[11px]" style={btnStyle(!bass)}>-</button>
              {ROOTS.map(r => (
                <button key={r} onClick={() => setBass(r)} className="px-1.5 py-0.5  text-[11px]" style={btnStyle(r === bass)}>{r}</button>
              ))}
            </div>
          </div>

          <button onClick={handleSet} className="w-full px-3 py-2  text-sm font-bold" style={{ background: 'var(--text-heading)', color: 'var(--bg-primary)' }}>
            Apply
          </button>
        </div>
      )}
    </div>
  );
}
