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
  const autoTitle = hasGenre
    ? `Auto: the ${tag} comping rhythm (${auto.label})`
    : `Auto: no genre set, so ${auto.label}`;
  const choices = HARMONY_RHYTHM_PRESETS.map((preset) => {
    const autoPlays = isAuto && preset.id === auto.id;
    const counts = harmonyStrikes(meterRhythm(preset.pattern, beats), beats).map((s) => countLabel(s.pos)).join(', ');
    return {
      id: preset.id,
      label: preset.label,
      checked: settings.harmonyRhythmId === preset.id,
      onSelect: () => setHarmonyRhythmId(preset.id),
      title: `${preset.label}: strikes on ${counts}${autoPlays ? ` · Auto plays this for ${tag}` : ''}`,
    };
  });
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
    <div className="te-choice-grid flex h-full min-h-0 min-w-0 flex-col gap-1 p-[3px]">
      <button type="button" aria-pressed={bassOn} data-active={bassOn ? '' : undefined}
        onClick={() => setBassEnabled(!bassOn)}
        className="te-key btn-hover w-full shrink-0 px-2"
        style={{ height: 26, minHeight: 26, fontSize: 12, lineHeight: '14px', letterSpacing: 'normal',
          whiteSpace: 'nowrap', fontWeight: bassOn ? 700 : 400 }}
        title={`Bass ${bassOn ? 'on' : 'off'}: ${bassName} plays each chord's root on the ${hasGenre ? tag : 'default'} bass rhythm`}
      >
        Bass {bassOn ? 'on' : 'off'} · {bassName}
      </button>

      <div className="flex min-h-0 flex-1 flex-col gap-1" role="radiogroup" aria-label="Harmony rhythm" onKeyDown={handleKey}>
        <button type="button" role="radio" aria-checked={isAuto} tabIndex={isAuto ? 0 : -1}
          data-active={isAuto ? '' : undefined} onClick={() => setHarmonyRhythmId(null)} title={autoTitle}
          className="te-key btn-hover w-full shrink-0 px-2"
          style={{ height: 26, minHeight: 26, fontSize: 12, lineHeight: '14px', letterSpacing: 'normal', fontWeight: isAuto ? 700 : 400 }}>
          Auto
        </button>
        <div className="grid min-h-0 flex-1 gap-[3px]"
          style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gridTemplateRows: `repeat(${Math.ceil(choices.length / 4)}, minmax(26px, 1fr))` }}>
          {choices.map((choice) => (
            <button key={choice.id} type="button" role="radio" aria-checked={choice.checked}
              tabIndex={choice.checked ? 0 : -1} data-active={choice.checked ? '' : undefined}
              onClick={choice.onSelect} title={choice.title}
              className="te-key btn-hover h-full min-w-0"
              style={{ minHeight: 26, padding: '0 3px', fontSize: 12, lineHeight: '12px', letterSpacing: 'normal',
                whiteSpace: 'normal', overflowWrap: 'anywhere', fontWeight: choice.checked ? 700 : 400 }}>
              {choice.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
