// The chord readout and drawing remain above every selection tab.
import { usePlayStore } from '../../../store/playStore';
import type { KeyboardEvent } from 'react';
import { useSongStore } from '../../../store/songStore';
import { resolveHarmonyInstrument } from '../../../engine/playSettings';
import type { VisualDisplayMode } from '../../../store/playStore';
import { instrumentLabel } from '../../../engine/genreTables';
import { generateGuitarVoicing, midiToNoteName, resolvePianoVoicing } from '../../../engine/voicingEngine';
import { chordToString } from '../../../engine/chordParser';
import type { Chord, Measure, SlotAddress } from '../../../models/types';
import PianoKeyboard from '../PianoKeyboard';
import GuitarFretboard from '../GuitarFretboard';
import KeyButton from './ui/KeyButton';
import Screen from './ui/Screen';

const SCREEN_HEIGHT = 56;
/** The drawing frame's widest size, which caps the pane's height. */
const DRAWING_MAX_WIDTH = 320;
const MUTED_FRETS = [-1, -1, -1, -1, -1, -1];

/** Where the drawn chord comes from, highest priority first. */
type Source = 'midi-chord' | 'midi-raw' | 'playback' | 'selection' | 'score';

const SOURCE_TAG: Record<Source, string> = {
  'midi-chord': 'MIDI',
  'midi-raw': 'MIDI',
  playback: 'PLAY',
  selection: 'SEL',
  score: 'CHORD',
};

/** Key highlight per source: green for MIDI, the playback yellow, the selection yellow. */
const SOURCE_COLOR: Record<Source, string> = {
  'midi-chord': 'var(--text-accent)',
  'midi-raw': 'var(--text-accent)',
  playback: 'var(--playback-bar)',
  selection: 'var(--brand-yellow)',
  score: 'var(--brand-yellow)',
};

const MODES: { mode: VisualDisplayMode; label: string; emoji: string }[] = [
  { mode: 'piano', label: 'Piano', emoji: '🎹' },
  { mode: 'guitar', label: 'Guitar', emoji: '🎸' },
];

function chordAt(measures: Measure[], slot: SlotAddress): Chord | null {
  return measures[slot.measureIndex]?.chords[slot.slotIndex] ?? null;
}

/** MIDI > playback > selected slot > the score's first readable chord. */
function pickSource(
  midiChord: Chord | null,
  midiNotes: number[],
  playing: SlotAddress | null,
  selected: SlotAddress | null,
  measures: Measure[],
): { source: Source | null; chord: Chord | null } {
  if (midiChord) return { source: 'midi-chord', chord: midiChord };
  if (midiNotes.length > 0) return { source: 'midi-raw', chord: null };
  if (playing) return { source: 'playback', chord: chordAt(measures, playing) };
  if (selected) return { source: 'selection', chord: chordAt(measures, selected) };
  for (const measure of measures) {
    for (const chord of measure.chords) {
      if (chord) return { source: 'score', chord };
    }
  }
  return { source: null, chord: null };
}

function noteNames(notes: number[]): string {
  return [...new Set(notes)].sort((a, b) => a - b).map(midiToNoteName).join(' ');
}

function modeTitle(mode: VisualDisplayMode): string {
  return mode === 'piano' ? 'Show the chord on a piano keyboard' : 'Show the chord on a guitar fretboard';
}

/** The active chord on a keyboard or fretboard, and the shape it is voiced in. */
export default function VisualPane({ midiActiveNotes, compact = false }: { midiActiveNotes: number[]; compact?: boolean }) {
  const measures = useSongStore((s) => s.song.measures);
  const genre = useSongStore((s) => s.song.genre);
  const selectedSlots = useSongStore((s) => s.selectedSlots);
  const playbackPosition = useSongStore((s) => s.playbackPosition);
  const midiCandidates = useSongStore((s) => s.midiCandidates);
  const settings = usePlayStore((s) => s.settings);
  const shape = usePlayStore((s) => s.displayMode);
  const setDisplayMode = usePlayStore((s) => s.setDisplayMode);

  // This switch chooses the drawing independently of the playback sound.
  const instrument = resolveHarmonyInstrument(settings, genre);
  const instrumentName = instrument ? instrumentLabel(instrument) : 'Built-in piano';

  const { source, chord } = pickSource(
    midiCandidates[0] ?? null,
    midiActiveNotes,
    playbackPosition,
    selectedSlots[0] ?? null,
    measures,
  );
  const showHint = source === null || (source === 'selection' && chord === null);
  const highlight = source ? SOURCE_COLOR[source] : 'var(--brand-yellow)';
  const chordName = chord ? chordToString(chord) : null;

  const pianoNotes = source === 'midi-raw' ? midiActiveNotes : chord ? resolvePianoVoicing(chord) : [];
  const guitarFrets = chord ? generateGuitarVoicing(chord) : MUTED_FRETS;

  const handleDisplayKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const radios = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]'));
    if (!radios.includes(event.target as HTMLButtonElement)) return;
    let next: number;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight' || event.key === 'End') next = 1;
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft' || event.key === 'Home') next = 0;
    else return;
    event.preventDefault();
    radios[next]?.click();
    radios[next]?.focus();
  };

  return (
    <div role="group" aria-label="Visual voicing" className="flex flex-col min-w-0 gap-2">
      <Screen style={{ height: compact ? 48 : SCREEN_HEIGHT, padding: compact ? '8px' : undefined }}>
        {/* Header in the look of Screen's label row: source (or the pane name), rule, instrument. */}
        {!compact && <div
          className="flex items-center uppercase"
          style={{
            height: 12,
            marginBottom: 2,
            gap: 6,
            fontSize: 9,
            lineHeight: '12px',
            letterSpacing: '0.1em',
            color: 'var(--screen-text-dim)',
          }}
        >
          {showHint || !source ? (
            <span className="shrink-0">Visual</span>
          ) : (
            <span className="flex items-center gap-[4px] shrink-0" title="Where the chord comes from">
              <span
                aria-hidden
                style={{ width: 5, height: 5, borderRadius: '50%', background: highlight, boxShadow: `0 0 4px ${highlight}` }}
              />
              <span style={{ color: 'var(--screen-text)' }}>{SOURCE_TAG[source]}</span>
            </span>
          )}
          <span className="flex-1" style={{ height: 1, background: 'currentColor', opacity: 0.3 }} />
          <span className="min-w-0 truncate" title="Harmony instrument">{instrumentName}</span>
        </div>}
        <div className="flex items-center gap-2" style={{ height: compact ? 32 : 28 }}>
          {compact && <span className="shrink-0 text-[11px] uppercase" style={{ color: highlight }}>{source ? SOURCE_TAG[source] : 'Visual'}</span>}
          {showHint ? (
            <span style={{ color: 'var(--screen-text-dim)' }}>Select a chord</span>
          ) : source === 'midi-raw' ? (
            <span className="min-w-0 flex-1 truncate" style={{ fontSize: 13 }}>{noteNames(midiActiveNotes)}</span>
          ) : chordName ? (
            <span className="min-w-0 flex-1 truncate" style={{ fontSize: 24, lineHeight: '32px', fontWeight: 600 }}>
              {chordName}
            </span>
          ) : (
            // an empty slot under the playhead
            <span style={{ fontSize: 22, lineHeight: '28px', color: 'var(--screen-text-dim)' }}>—</span>
          )}
          {compact && <span className="ml-auto min-w-0 truncate" style={{ maxWidth: 78, fontSize: 12, color: 'var(--screen-text-dim)' }} title={instrumentName}>{instrumentName}</span>}
        </div>
      </Screen>

      <div className={compact ? 'grid min-w-0 items-center gap-1.5' : 'flex min-w-0 flex-col gap-2'} style={compact ? { gridTemplateColumns: 'minmax(0, 1fr) 32px', height: shape === 'piano' ? 72 : 'clamp(72px, 8dvh, 132px)' } : undefined}>
      <div className={`te-visual-selector grid gap-[3px] ${compact ? 'grid-cols-1' : 'grid-cols-2'}`} role="radiogroup" aria-label="Piano or guitar display" onKeyDown={handleDisplayKey} style={compact ? { gridColumn: 2, gridRow: 1 } : undefined}>
        {MODES.map(({ mode, label, emoji }) => {
          const chosen = shape === mode;
          return (
            <KeyButton
              key={mode}
              label={label}
              ariaLabel={label}
              active={chosen}
              role="radio"
              tabIndex={chosen ? 0 : -1}
              onClick={() => setDisplayMode(mode)}
              className="te-visual-key"
              title={modeTitle(mode)}
            ><span aria-hidden="true" style={{ fontSize: 17, lineHeight: '20px' }}>{emoji}</span></KeyButton>
          );
        })}
      </div>

      <div
        className="te-voicing-drawing w-full mx-auto"
        role="img"
        aria-label={`${shape === 'guitar' ? 'Guitar shape' : 'Keyboard voicing'}${chordName ? ` of ${chordName}` : ''}`}
        style={{
          maxWidth: compact && shape === 'guitar' ? 220 : DRAWING_MAX_WIDTH,
          padding: compact ? 4 : 6,
          gridColumn: compact ? 1 : undefined,
          gridRow: compact ? 1 : undefined,
          background: 'transparent',
        }}
      >
        {shape === 'guitar' ? (
          <GuitarFretboard frets={guitarFrets} highlightColor={highlight} />
        ) : (
          <PianoKeyboard activeNotes={pianoNotes} highlightColor={highlight} />
        )}
      </div>
      </div>
    </div>
  );
}
