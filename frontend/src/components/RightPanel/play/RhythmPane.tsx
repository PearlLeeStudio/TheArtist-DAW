// Height: screen 56 + 8 + HARM/BASS rows 28 + 8 + 5 key rows 146 + 8 + bass key 30 = 284px at any width.
import type { CSSProperties } from 'react';
import { HARMONY_RHYTHM_PRESETS, instrumentLabel } from '../../../engine/genreTables';
import {
  autoRhythmPreset,
  bassInstrumentFor,
  bassPatternFor,
  harmonyStrikes,
  meterRhythm,
  normalizeGenre,
  patternSteps,
  resolveHarmonyRhythm,
} from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import KeyButton from './ui/KeyButton';
import Screen from './ui/Screen';
import StepRow from './ui/StepRow';
import LedLegend from './LedLegend';
import { genreTag } from './genreTag';
import { usePlayStep } from './usePlayStep';

/** 56px like the other panes' screens: 12 padding + 14 header + two 14px lines = 54. */
const SCREEN_HEIGHT = 56;
const ROW_HEIGHT = 12;
const SCREEN_TEXT: CSSProperties = { letterSpacing: '0.04em' };
const LINE: CSSProperties = { height: 14 };

const SUBDIVISIONS: [number, string][] = [
  [0, ''], [0.25, 'e'], [1 / 3, '⅓'], [0.5, '&'], [2 / 3, '⅔'], [0.75, 'a'],
];

/** A beat position as counted in the bar: 0 → 1, 1.5 → 2&, 2/3 → 1⅔. */
function countLabel(pos: number): string {
  const beat = Math.floor(pos + 1e-6);
  const name = SUBDIVISIONS.find(([f]) => Math.abs(pos - beat - f) < 1e-3)?.[1];
  return name === undefined ? (pos + 1).toFixed(2) : `${beat + 1}${name}`;
}

/** Harmony comping rhythm (Auto or one of the presets) and the bass layer. */
export default function RhythmPane() {
  const settings = usePlayStore((s) => s.settings);
  const setHarmonyRhythmId = usePlayStore((s) => s.setHarmonyRhythmId);
  const setBassEnabled = usePlayStore((s) => s.setBassEnabled);
  const genre = useSongStore((s) => s.song.genre);
  const beats = useSongStore((s) => s.song.timeSignature[0]);
  const step = usePlayStep();

  const isAuto = settings.harmonyRhythmId === null;
  const auto = autoRhythmPreset(genre);
  const playing = resolveHarmonyRhythm(settings, genre);
  // As the engine lays them on this meter.
  const harmPattern = meterRhythm(playing.pattern, beats);
  const strikes = harmonyStrikes(harmPattern, beats).length;
  const harmCells = patternSteps(harmPattern, beats).map((on) => ({ level: on ? 1 : 0 }));
  const bassCells = patternSteps(meterRhythm(bassPatternFor(genre), beats), beats).map((on) => ({ level: on ? 1 : 0 }));
  const bassOn = settings.bassEnabled;
  const bassName = instrumentLabel(bassInstrumentFor(genre));
  const hasGenre = normalizeGenre(genre) !== null;
  const tag = genreTag(genre);

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <Screen label="RHYTHM" style={{ height: SCREEN_HEIGHT }}>
        <div className="flex flex-col uppercase" style={SCREEN_TEXT}>
          <div className="flex items-center gap-1.5" style={LINE}>
            <span className="flex-1 min-w-0 truncate">{playing.label}</span>
            <span className="shrink-0" style={{ opacity: 0.5 }} title="Chord strikes per bar">
              {strikes}/bar
            </span>
          </div>
          <div className="flex items-center gap-1.5" style={LINE}>
            {isAuto ? (
              <>
                <span className="shrink-0" style={{ color: 'var(--led-alt)' }}>auto</span>
                <span className="min-w-0 truncate" style={{ opacity: 0.5 }}>· {tag}</span>
              </>
            ) : (
              <span style={{ color: 'var(--led-on)' }}>pick</span>
            )}
          </div>
        </div>
      </Screen>

      <div className="flex flex-col gap-1">
        <StepRow label="HARM" cells={harmCells} playhead={step} height={ROW_HEIGHT} />
        <StepRow label="BASS" cells={bassCells} playhead={step} height={ROW_HEIGHT} dim={!bassOn} />
      </div>

      <div className="grid grid-cols-3 gap-1">
        <KeyButton
          size="sm"
          label="Auto"
          sublabel={auto.short}
          active={isAuto}
          led={isAuto ? 'on' : 'off'}
          onClick={() => setHarmonyRhythmId(null)}
          title={hasGenre
            ? `Auto: the ${tag} comping rhythm (${auto.label})`
            : `Auto: no genre set, so ${auto.label}`}
        />
        {HARMONY_RHYTHM_PRESETS.map((p) => {
          const picked = settings.harmonyRhythmId === p.id;
          const autoPlays = isAuto && p.id === auto.id;
          const counts = harmonyStrikes(meterRhythm(p.pattern, beats), beats).map((s) => countLabel(s.pos)).join(', ');
          return (
            <KeyButton
              key={p.id}
              size="sm"
              label={p.short}
              active={picked}
              led={picked ? 'on' : autoPlays ? 'alt' : 'off'}
              onClick={() => setHarmonyRhythmId(p.id)}
              title={`${p.label}: strikes on ${counts}${autoPlays ? ` · Auto plays this for ${tag}` : ''}`}
            />
          );
        })}
        <LedLegend />
      </div>

      <KeyButton
        size="md"
        label="Bass"
        sublabel={bassName}
        active={bassOn}
        led={bassOn ? 'on' : 'off'}
        onClick={() => setBassEnabled(!bassOn)}
        title={`Bass ${bassOn ? 'on' : 'off'}: ${bassName} plays each chord's root on the ${hasGenre ? tag : 'default'} bass rhythm`}
      />
    </div>
  );
}
