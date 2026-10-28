// Family buttons keep every sound reachable without a scrolling list.
import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import { genreHarmonyInstrument } from '../../../engine/playSettings';
import { HARMONY_INSTRUMENTS, instrumentLabel } from '../../../engine/genreTables';
import type { InstrumentFamily } from '../../../engine/genreTables';
import { genreTag } from './genreTag';

const GROUPS: { id: string; emoji: string; label: string; families: InstrumentFamily[] }[] = [
  { id: 'keys', emoji: '🎹', label: 'Keys', families: ['keys'] },
  { id: 'guitar', emoji: '🎸', label: 'Guitar', families: ['guitar'] },
  { id: 'strings', emoji: '🎻', label: 'Strings', families: ['strings'] },
  { id: 'woodwinds', emoji: '🪈', label: 'Woodwinds', families: ['winds', 'reeds'] },
  { id: 'brass', emoji: '🎺', label: 'Brass', families: ['brass'] },
];

/** Full, readable names for the compact labels used elsewhere on the device. */
const NAMES: Record<string, string> = {
  electric_piano_1: 'Electric piano',
  clavinet: 'Clavinet',
  pad_2_warm: 'Warm pad',
  acoustic_guitar_nylon: 'Nylon guitar',
  acoustic_guitar_steel: 'Steel guitar',
  electric_guitar_clean: 'Clean guitar',
  overdriven_guitar: 'Overdrive',
  distortion_guitar: 'Distortion',
  pizzicato_strings: 'Pizzicato',
  soprano_sax: 'Soprano sax',
  alto_sax: 'Alto sax',
  tenor_sax: 'Tenor sax',
  baritone_sax: 'Baritone sax',
  french_horn: 'French horn',
  brass_section: 'Brass section',
  muted_trumpet: 'Muted trumpet',
};

/** Every harmony sound remains available through its family. The bass follows the genre. */
export default function InstrumentPane() {
  const override = usePlayStore((s) => s.settings.harmonyOverride);
  const setHarmonyOverride = usePlayStore((s) => s.setHarmonyOverride);
  const genre = useSongStore((s) => s.song.genre);

  const genreDefault = genreHarmonyInstrument(genre);
  const tag = genreTag(genre);
  const [openGroup, setOpenGroup] = useState(() => {
    const sound = HARMONY_INSTRUMENTS.find((instrument) => instrument.name === (override ?? genreDefault));
    return GROUPS.find((group) => sound && group.families.includes(sound.family))?.id ?? 'keys';
  });
  const group = GROUPS.find((item) => item.id === openGroup) ?? GROUPS[0];
  const instruments = HARMONY_INSTRUMENTS.filter((instrument) => group.families.includes(instrument.family));

  const autoTitle = genreDefault
    ? `Auto: the ${tag} default (${instrumentLabel(genreDefault)})`
    : 'Auto: no genre set, so the built-in piano';

  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const radios = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[data-instrument-choice]'));
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
    <div className="te-instrument-list min-w-0 h-full p-[3px]"
      style={{ display: 'grid', gridTemplateRows: '26px 36px 1fr', gap: 4 }} role="group" aria-label="Harmony instrument" onKeyDown={handleKey}>
      <button type="button" aria-pressed={override === null} data-instrument-choice
        data-active={override === null ? '' : undefined} onClick={() => setHarmonyOverride(null)} title={autoTitle}
        className="te-key btn-hover flex w-full items-center justify-between gap-2 px-2 text-left"
        style={{ fontSize: 12, lineHeight: '14px', letterSpacing: 'normal', fontWeight: override === null ? 700 : 400,
          borderColor: override === null ? 'var(--key-text)' : 'var(--key-border)' }}>
        <span>Auto</span>
        <span style={{ color: 'var(--key-text-dim)', fontWeight: 400 }}>Genre default</span>
      </button>

      <div className="grid grid-cols-5 gap-[3px]" role="group" aria-label="Instrument families">
        {GROUPS.map((family) => <button key={family.id} type="button" className="te-key btn-hover flex min-w-0 flex-col items-center justify-center"
          aria-pressed={family.id === openGroup} data-active={family.id === openGroup ? '' : undefined}
          onClick={() => setOpenGroup(family.id)} title={family.label} style={{ letterSpacing: 'normal' }}>
          <span aria-hidden="true" style={{ fontSize: 14, lineHeight: '16px' }}>{family.emoji}</span>
          <span style={{ fontSize: 10, lineHeight: '12px' }}>{family.id === 'woodwinds' ? 'Winds' : family.label}</span>
        </button>)}
      </div>
      <div className="grid grid-cols-4 content-start gap-[3px]" role="group" aria-label={`${group.label} instruments`}>
            {instruments.map((instrument) => {
              const selected = override === instrument.name;
              const label = NAMES[instrument.name] ?? instrument.label;
              return (
                <button key={instrument.name} type="button" aria-pressed={selected} data-instrument-choice
                  aria-label={`${label}, ${group.label}`}
                  data-active={selected ? '' : undefined} onClick={() => setHarmonyOverride(instrument.name)}
                  title={`${group.label} · ${label}`} className="te-key btn-hover min-w-0 px-1 py-1 text-left"
                  style={{ minHeight: 28, fontSize: 11, lineHeight: '12px', letterSpacing: 'normal',
                    whiteSpace: 'normal', overflowWrap: 'anywhere', fontWeight: selected ? 700 : 400,
                    borderColor: selected ? 'var(--key-text)' : 'var(--key-border)' }}>
                  {label}
                </button>
              );
            })}
      </div>
    </div>
  );
}
