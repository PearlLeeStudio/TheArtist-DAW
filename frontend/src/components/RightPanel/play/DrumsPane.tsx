// The shared playback status stays visible above this selection grid.
import type { KeyboardEvent } from 'react';
import { DRUM_PATTERNS, drumPatternById } from '../../../engine/drumPatterns';
import { genreDrumPatternId } from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import ToggleSwitch from './ui/ToggleSwitch';
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
    <div className="h-full min-h-0 min-w-0 overflow-y-auto overscroll-contain p-[3px]" style={{ scrollbarGutter: 'stable' }}>
        <div
          role="radiogroup"
          aria-label="Drum pattern"
          onKeyDown={handleKey}
          className="mx-auto grid w-full gap-[3px]"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(104px, 1fr))' }}
        >
          {choices.map((choice) => (
            <ToggleSwitch
              key={choice.id}
              label={choice.label}
              ariaLabel={choice.ariaLabel}
              checked={choice.checked}
              onSelect={choice.onSelect}
              title={choice.title}
            />
          ))}
        </div>
    </div>
  );
}
