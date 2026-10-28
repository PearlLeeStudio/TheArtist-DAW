// All choices share the space left by the permanent visual. Only this grid scrolls.
import type { KeyboardEvent } from 'react';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import { genreHarmonyInstrument } from '../../../engine/playSettings';
import { HARMONY_INSTRUMENTS, INSTRUMENT_FAMILIES, instrumentLabel } from '../../../engine/genreTables';
import ToggleSwitch from './ui/ToggleSwitch';
import { genreTag } from './genreTag';

/** Every harmony sound remains available in one list. The bass follows the genre. */
export default function InstrumentPane() {
  const override = usePlayStore((s) => s.settings.harmonyOverride);
  const setHarmonyOverride = usePlayStore((s) => s.setHarmonyOverride);
  const genre = useSongStore((s) => s.song.genre);

  const genreDefault = genreHarmonyInstrument(genre);
  const tag = genreTag(genre);

  const autoTitle = genreDefault
    ? `Auto: the ${tag} default (${instrumentLabel(genreDefault)})`
    : 'Auto: no genre set, so the built-in piano';

  const choices = [
    { name: null, label: 'Auto', ariaLabel: 'Auto harmony instrument', title: autoTitle },
    ...HARMONY_INSTRUMENTS.map((instrument) => {
      const family = INSTRUMENT_FAMILIES.find((item) => item.id === instrument.family);
      return {
        name: instrument.name,
        label: instrument.label,
        ariaLabel: `${instrument.label}, ${family?.label ?? instrument.family}`,
        title: `${family?.label ?? instrument.family} · ${instrument.name.replaceAll('_', ' ')}`,
      };
    }),
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
          className="grid gap-[3px]"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(44px, 1fr))' }}
          role="radiogroup"
          aria-label="Harmony instrument"
          onKeyDown={handleKey}
        >
          {choices.map((choice) => <ToggleSwitch key={choice.name ?? 'auto'} label={choice.label}
            ariaLabel={choice.ariaLabel} checked={override === choice.name}
            onSelect={() => setHarmonyOverride(choice.name)} title={choice.title} />)}
        </div>
    </div>
  );
}
