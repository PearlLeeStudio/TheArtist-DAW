// The shared playback status stays visible above this selection grid.
import type { KeyboardEvent } from 'react';
import { DRUM_PATTERNS, drumPatternById } from '../../../engine/drumPatterns';
import { genreDrumPatternId } from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import { genreTag } from './genreTag';

/** Drums: follow the genre (Auto), off, or one of the 15 patterns. A pick
 *  stays when the genre changes. */
export default function DrumsPane() {
  const settings = usePlayStore((s) => s.settings);
  const setDrumAuto = usePlayStore((s) => s.setDrumAuto);
  const setDrumPattern = usePlayStore((s) => s.setDrumPattern);
  const genre = useSongStore((s) => s.song.genre);

  const isAuto = settings.drumMode === 'auto';
  const isOff = !isAuto && settings.drumPatternId === null;
  const genreId = genreDrumPatternId(genre);
  const genrePattern = drumPatternById(genreId);
  const tag = genreTag(genre);
  const choices = [
    {
      id: 'auto', label: 'Auto', ariaLabel: 'Auto drum pattern', checked: isAuto,
      onSelect: setDrumAuto,
      title: genrePattern
        ? `Auto: drums follow the genre (${genrePattern.name} for ${tag})`
        : 'Auto: no genre set, so no drums',
    },
    {
      id: 'off', label: 'Off', ariaLabel: 'Drums off', checked: isOff,
      onSelect: () => setDrumPattern(null), title: 'No drums, whatever the genre',
    },
    ...DRUM_PATTERNS.map((pattern) => ({
      id: pattern.id,
      label: pattern.name,
      ariaLabel: pattern.name,
      checked: !isAuto && settings.drumPatternId === pattern.id,
      onSelect: () => setDrumPattern(pattern.id),
      title: `${pattern.name}${pattern.swing ? ' · swing' : ''}${isAuto && pattern.id === genreId ? ` · Auto plays this for ${tag}` : ''}`,
    })),
  ];

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
    <div className="te-choice-grid h-full min-h-0 min-w-0 p-[3px]">
        <div
          role="radiogroup"
          aria-label="Drum pattern"
          onKeyDown={handleKey}
          className="grid h-full w-full gap-[3px]"
          style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gridTemplateRows: `repeat(${Math.ceil(choices.length / 4)}, minmax(26px, 1fr))` }}
        >
          {choices.map((choice) => (
            <button key={choice.id} type="button" role="radio" aria-label={choice.ariaLabel}
              aria-checked={choice.checked} tabIndex={choice.checked ? 0 : -1}
              data-active={choice.checked ? '' : undefined} onClick={choice.onSelect} title={choice.title}
              className="te-key btn-hover min-w-0"
              style={{ minHeight: 26, padding: '0 3px', fontSize: 12, lineHeight: '12px', letterSpacing: 'normal',
                whiteSpace: 'normal', overflowWrap: 'anywhere', fontWeight: choice.checked ? 700 : 400,
                borderColor: choice.checked ? 'var(--key-text)' : 'var(--key-border)' }}>
              {choice.label}
            </button>
          ))}
        </div>
    </div>
  );
}
