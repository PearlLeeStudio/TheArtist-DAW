// ~163px tall at 200px wide (keyboard), ~214px (fretboard), at most 277px: screen 56 + 8 + mode keys 30 + 8 + frame 14 + drawing (≤ 306px wide).
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import { resolveHarmonyInstrument, resolveVoicingMode } from '../../../engine/playSettings';
import type { VoicingMode } from '../../../engine/playSettings';
import { instrumentLabel } from '../../../engine/genreTables';
import { generateGuitarVoicing, midiToNoteName, resolvePianoVoicing } from '../../../engine/voicingEngine';
import { chordToString } from '../../../engine/chordParser';
import type { Chord, Measure, SlotAddress, VisualMode } from '../../../models/types';
import PianoKeyboard from '../PianoKeyboard';
import GuitarFretboard from '../GuitarFretboard';
import KeyButton from './ui/KeyButton';
import Screen from './ui/Screen';

const SCREEN_HEIGHT = 56;
/** The drawing frame's widest size, which caps the pane's height. */
const DRAWING_MAX_WIDTH = 320;
const MUTED_FRETS = [-1, -1, -1, -1, -1, -1];

/** Where the drawn chord comes from, highest priority first. */
type Source = 'midi-chord' | 'midi-raw' | 'playback' | 'selection';

const SOURCE_TAG: Record<Source, string> = {
  'midi-chord': 'MIDI',
  'midi-raw': 'MIDI',
  playback: 'PLAY',
  selection: 'SEL',
};

/** Key highlight per source: green for MIDI, the playback yellow, the selection yellow. */
const SOURCE_COLOR: Record<Source, string> = {
  'midi-chord': 'var(--text-accent)',
  'midi-raw': 'var(--text-accent)',
  playback: 'var(--playback-bar)',
  selection: 'var(--brand-yellow)',
};

const MODES: { mode: VisualMode; label: string }[] = [
  { mode: 'auto', label: 'Auto' },
  { mode: 'piano', label: 'Piano' },
  { mode: 'guitar', label: 'Guitar' },
];

const SHAPE_LABEL: Record<VoicingMode, string> = { piano: 'Piano', guitar: 'Guitar' };

function chordAt(measures: Measure[], slot: SlotAddress): Chord | null {
  return measures[slot.measureIndex]?.chords[slot.slotIndex] ?? null;
}

/** MIDI-detected chord > raw MIDI notes > playback position > first selected slot. */
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
  return { source: null, chord: null };
}

function noteNames(notes: number[]): string {
  return [...new Set(notes)].sort((a, b) => a - b).map(midiToNoteName).join(' ');
}

function modeTitle(mode: VisualMode, autoShape: string): string {
  const same = 'playback voices chords the same way';
  if (mode === 'auto') return `Auto: follows the harmony instrument (now ${autoShape}); ${same}`;
  if (mode === 'piano') return `Piano: keyboard voicings; ${same}`;
  return `Guitar: guitar shapes; ${same}`;
}

/** The active chord on a keyboard or fretboard, and the shape it is voiced in. */
export default function VisualPane({ midiActiveNotes }: { midiActiveNotes: number[] }) {
  const measures = useSongStore((s) => s.song.measures);
  const genre = useSongStore((s) => s.song.genre);
  const selectedSlots = useSongStore((s) => s.selectedSlots);
  const playbackPosition = useSongStore((s) => s.playbackPosition);
  const midiCandidates = useSongStore((s) => s.midiCandidates);
  const settings = usePlayStore((s) => s.settings);
  const setVisualMode = usePlayStore((s) => s.setVisualMode);

  // The shape decides both the drawing and how the harmony layer voices chords.
  const shape = resolveVoicingMode(settings, genre);
  const autoShape = resolveVoicingMode({ ...settings, visualMode: 'auto' }, genre);
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

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <Screen style={{ height: SCREEN_HEIGHT }}>
        {/* Header in the look of Screen's label row: source (or the pane name), rule, instrument. */}
        <div
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
        </div>
        <div className="flex items-center" style={{ height: 28 }}>
          {showHint ? (
            <span style={{ color: 'var(--screen-text-dim)' }}>Select a chord</span>
          ) : source === 'midi-raw' ? (
            <span className="min-w-0 truncate" style={{ fontSize: 13 }}>{noteNames(midiActiveNotes)}</span>
          ) : chordName ? (
            <span className="min-w-0 truncate" style={{ fontSize: 22, lineHeight: '28px', fontWeight: 600 }}>
              {chordName}
            </span>
          ) : (
            // an empty slot under the playhead
            <span style={{ fontSize: 22, lineHeight: '28px', color: 'var(--screen-text-dim)' }}>—</span>
          )}
        </div>
      </Screen>

      <div className="grid grid-cols-3 gap-[4px]" role="group" aria-label="Voicing shape">
        {MODES.map(({ mode, label }) => {
          const chosen = settings.visualMode === mode;
          const autoPlays = settings.visualMode === 'auto' && mode === shape;
          return (
            <KeyButton
              key={mode}
              size="md"
              label={label}
              sublabel={mode === 'auto' ? `→ ${SHAPE_LABEL[autoShape]}` : undefined}
              active={chosen}
              led={chosen ? 'on' : autoPlays ? 'alt' : 'off'}
              onClick={() => setVisualMode(mode)}
              title={modeTitle(mode, autoShape)}
            />
          );
        })}
      </div>

      <div
        className="w-full mx-auto"
        role="img"
        aria-label={`${shape === 'guitar' ? 'Guitar shape' : 'Keyboard voicing'}${chordName ? ` of ${chordName}` : ''}`}
        style={{
          maxWidth: DRAWING_MAX_WIDTH,
          padding: 6,
          border: '1px solid var(--key-border)',
          borderRadius: 3,
        }}
      >
        {shape === 'guitar' ? (
          <GuitarFretboard frets={guitarFrets} highlightColor={highlight} />
        ) : (
          <PianoKeyboard activeNotes={pianoNotes} highlightColor={highlight} />
        )}
      </div>
    </div>
  );
}
