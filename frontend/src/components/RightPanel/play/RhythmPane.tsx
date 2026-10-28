// Rhythm choices sit below the permanent playback status windows.
import type { KeyboardEvent } from 'react';
import { HARMONY_RHYTHM_PRESETS, instrumentLabel } from '../../../engine/genreTables';
import {
  autoRhythmPreset,
  bassInstrumentFor,
  harmonyStrikes,
  meterRhythm,
  normalizeGenre,
} from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import ToggleSwitch from './ui/ToggleSwitch';
import { genreTag } from './genreTag';

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

  const isAuto = settings.harmonyRhythmId === null;
  const auto = autoRhythmPreset(genre);
  const bassOn = settings.bassEnabled;
  const bassName = instrumentLabel(bassInstrumentFor(genre));
  const hasGenre = normalizeGenre(genre) !== null;
  const tag = genreTag(genre);
  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const radios = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]'));
    const index = radios.indexOf(event.target as HTMLButtonElement);
    if (index < 0) return;
    let next: number;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % radios.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + radios.length - 1) % radios.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = radios.length - 1;
    else return;
    event.preventDefault();
    radios[next]?.click();
    radios[next]?.focus();
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-2">
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-[3px]">
      <div className="grid gap-1" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(104px, 1fr))' }} role="radiogroup" aria-label="Harmony rhythm" onKeyDown={handleKey}>
        <ToggleSwitch
          label="Auto"
          checked={isAuto}
          onSelect={() => setHarmonyRhythmId(null)}
          title={hasGenre
            ? `Auto: the ${tag} comping rhythm (${auto.label})`
            : `Auto: no genre set, so ${auto.label}`}
        />
        {HARMONY_RHYTHM_PRESETS.map((p) => {
          const picked = settings.harmonyRhythmId === p.id;
          const autoPlays = isAuto && p.id === auto.id;
          const counts = harmonyStrikes(meterRhythm(p.pattern, beats), beats).map((s) => countLabel(s.pos)).join(', ');
          return (
            <ToggleSwitch
              key={p.id}
              label={p.label}
              checked={picked}
              onSelect={() => setHarmonyRhythmId(p.id)}
              title={`${p.label}: strikes on ${counts}${autoPlays ? ` · Auto plays this for ${tag}` : ''}`}
            />
          );
        })}
      </div>
      </div>

      <div className="shrink-0">
      <ToggleSwitch
        kind="switch"
        label={`Bass · ${bassName}`}
        checked={bassOn}
        onSelect={() => setBassEnabled(!bassOn)}
        title={`Bass ${bassOn ? 'on' : 'off'}: ${bassName} plays each chord's root on the ${hasGenre ? tag : 'default'} bass rhythm`}
      />
      </div>
    </div>
  );
}
