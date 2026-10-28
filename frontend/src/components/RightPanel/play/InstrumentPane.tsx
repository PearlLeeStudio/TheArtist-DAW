// 208px tall at any width: screen 56 + 8 + family keys 56 + 8 + caption 12 + 4 + instrument keys 64.
import { useState } from 'react';
import type { CSSProperties } from 'react';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import {
  bassInstrumentFor,
  genreHarmonyInstrument,
  resolveHarmonyInstrument,
} from '../../../engine/playSettings';
import { HARMONY_INSTRUMENTS, INSTRUMENT_FAMILIES, instrumentLabel } from '../../../engine/genreTables';
import type { InstrumentFamily } from '../../../engine/genreTables';
import KeyButton from './ui/KeyButton';
import Screen from './ui/Screen';
import LedLegend from './LedLegend';
import { genreTag } from './genreTag';

const SCREEN_HEIGHT = 56;
const LINE: CSSProperties = { height: 14, lineHeight: '14px' };

/** Key-cap labels; INSTRUMENT_FAMILIES has the full names. */
const FAMILY_KEY_LABELS: Record<InstrumentFamily, string> = {
  keys: 'Keys',
  guitar: 'Guitar',
  strings: 'String',
  winds: 'Winds',
  reeds: 'Reeds',
  brass: 'Brass',
};

function familyOf(name: string | null): InstrumentFamily | null {
  return HARMONY_INSTRUMENTS.find((i) => i.name === name)?.family ?? null;
}

/** One screen line: layer tag, instrument, status. */
function ScreenLine({ tag, name, status, nameStyle, title }: {
  tag: string;
  name: string;
  status: string;
  nameStyle: CSSProperties;
  title: string;
}) {
  return (
    <div className="flex items-baseline gap-[6px] overflow-hidden" style={LINE} title={title}>
      <span className="shrink-0 uppercase" style={{ width: 30, opacity: 0.65 }}>{tag}</span>
      <span className="min-w-0 flex-1 truncate" style={nameStyle}>{name}</span>
      <span className="shrink-0 uppercase" style={{ opacity: 0.65 }}>{status}</span>
    </div>
  );
}

/** Harmony instrument: Auto (the genre default) or one of the 31, browsed by
 *  family. The bass follows the genre. */
export default function InstrumentPane() {
  const settings = usePlayStore((s) => s.settings);
  const setHarmonyOverride = usePlayStore((s) => s.setHarmonyOverride);
  const genre = useSongStore((s) => s.song.genre);

  const override = settings.harmonyOverride;
  const genreDefault = genreHarmonyInstrument(genre);
  const playing = resolveHarmonyInstrument(settings, genre);
  const bassOn = settings.bassEnabled;
  const tag = genreTag(genre);

  // The family whose keys are shown; browsing never changes the sound.
  const [openFamily, setOpenFamily] = useState<InstrumentFamily>(
    () => familyOf(override) ?? familyOf(genreDefault) ?? 'keys',
  );
  const pickFamily = familyOf(override);
  const autoFamily = override === null ? familyOf(genreDefault) : null;
  const family = INSTRUMENT_FAMILIES.find((f) => f.id === openFamily) ?? INSTRUMENT_FAMILIES[0];
  const instruments = HARMONY_INSTRUMENTS.filter((i) => i.family === openFamily);
  // Two rows for every family: 4 → 2 columns, 5–6 → 3.
  const columns = Math.ceil(instruments.length / 2);

  const autoTitle = genreDefault
    ? `Auto: the ${tag} default (${instrumentLabel(genreDefault)})`
    : 'Auto: no genre set, so the built-in piano';

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <Screen label="INSTRUMENT" style={{ height: SCREEN_HEIGHT }}>
        <ScreenLine
          tag="harm"
          name={playing ? instrumentLabel(playing) : 'Built-in piano'}
          status={override ? 'pick' : 'auto'}
          nameStyle={{ color: 'var(--led-on)' }}
          title={override
            ? `Harmony: your pick; Auto would play ${genreDefault ? instrumentLabel(genreDefault) : 'the built-in piano'}`
            : autoTitle}
        />
        <ScreenLine
          tag="bass"
          name={instrumentLabel(bassInstrumentFor(genre))}
          status={bassOn ? 'genre' : 'off'}
          nameStyle={{ opacity: bassOn ? 1 : 0.45 }}
          title={bassOn ? `Bass: follows the genre (${tag}), no override` : 'Bass: off'}
        />
      </Screen>

      <div className="grid grid-cols-4 gap-[4px]" role="group" aria-label="Harmony instrument families">
        <KeyButton
          size="sm"
          label="Auto"
          active={override === null}
          led={override === null ? 'on' : 'off'}
          onClick={() => setHarmonyOverride(null)}
          title={autoTitle}
        />
        {INSTRUMENT_FAMILIES.map((f) => (
          <KeyButton
            key={f.id}
            size="sm"
            label={FAMILY_KEY_LABELS[f.id]}
            active={openFamily === f.id}
            led={f.id === pickFamily ? 'on' : f.id === autoFamily ? 'alt' : 'off'}
            onClick={() => setOpenFamily(f.id)}
            title={`${f.label}: show its instruments (the sound changes only when you pick one)`}
          />
        ))}
        <LedLegend />
      </div>

      <div className="flex flex-col gap-[4px]">
        <div
          aria-hidden
          className="flex items-center gap-[6px] uppercase"
          style={{
            height: 12,
            fontFamily: 'var(--font-device)',
            fontSize: 9,
            lineHeight: '12px',
            letterSpacing: '0.1em',
            color: 'var(--key-text-dim)',
          }}
        >
          <span className="shrink-0">{family.label}</span>
          <span className="flex-1" style={{ height: 1, background: 'currentColor', opacity: 0.3 }} />
        </div>
        <div
          className="grid gap-[4px]"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          role="group"
          aria-label={`${family.label} instruments`}
        >
          {instruments.map((inst) => {
            const picked = override === inst.name;
            const isDefault = genreDefault === inst.name;
            return (
              <KeyButton
                key={inst.name}
                size="md"
                label={inst.label}
                active={picked}
                led={picked ? 'on' : override === null && isDefault ? 'alt' : 'off'}
                onClick={() => setHarmonyOverride(inst.name)}
                title={`${inst.label} (${inst.name})${isDefault ? ` · the ${tag} default` : ''}`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
