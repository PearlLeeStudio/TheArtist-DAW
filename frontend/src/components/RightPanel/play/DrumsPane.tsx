// The live K/S/H beat rows sit above the pattern controls.
import type { CSSProperties } from 'react';
import { DRUM_PATTERNS, drumGrid, drumPatternById } from '../../../engine/drumPatterns';
import { genreDrumPatternId, resolveDrumPatternId } from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import { drumKeyLabel } from './drumLabels';
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

/** Drums: follow the genre (Auto), off, or one of the 15 patterns. A pick
 *  stays when the genre changes. */
export default function DrumsPane() {
  const settings = usePlayStore((s) => s.settings);
  const setDrumAuto = usePlayStore((s) => s.setDrumAuto);
  const setDrumPattern = usePlayStore((s) => s.setDrumPattern);
  const genre = useSongStore((s) => s.song.genre);
  const beats = useSongStore((s) => s.song.timeSignature[0]);
  const step = usePlayStep();

  const isAuto = settings.drumMode === 'auto';
  const isOff = !isAuto && settings.drumPatternId === null;
  const genreId = genreDrumPatternId(genre);
  const genrePattern = drumPatternById(genreId);
  const playing = drumPatternById(resolveDrumPatternId(settings, genre));
  const rows = drumGrid(playing, beats * 4);
  const tag = genreTag(genre);

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <Screen label="DRUMS" style={{ height: SCREEN_HEIGHT }}>
        <div className="flex flex-col uppercase" style={SCREEN_TEXT}>
          <div className="flex items-center gap-1.5" style={LINE}>
            <span className="flex-1 min-w-0 truncate" style={playing ? undefined : { opacity: 0.45 }}>
              {playing ? playing.name : 'No drums'}
            </span>
            {playing?.swing ? <span className="shrink-0" style={{ opacity: 0.5 }}>swing</span> : null}
          </div>
          <div className="flex items-center gap-1.5" style={LINE}>
            {isAuto ? (
              <>
                <span className="shrink-0" style={{ color: 'var(--led-alt)' }}>auto</span>
                <span className="min-w-0 truncate" style={{ opacity: 0.5 }}>· {tag}</span>
              </>
            ) : isOff ? (
              <span style={{ opacity: 0.5 }}>off</span>
            ) : (
              <span style={{ color: 'var(--led-on)' }}>pick</span>
            )}
          </div>
        </div>
      </Screen>

      <div className="flex flex-col gap-1">
        {rows.map((row) => (
          <StepRow
            key={row.label}
            label={row.label}
            cells={row.cells}
            playhead={playing ? step : null}
            dim={!playing}
            height={ROW_HEIGHT}
          />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-1">
        <KeyButton
          size="md"
          label="Auto"
          sublabel={genreId === null ? '—' : drumKeyLabel(genreId)}
          active={isAuto}
          led={isAuto ? 'on' : 'off'}
          onClick={() => setDrumAuto()}
          title={genrePattern
            ? `Auto: drums follow the genre (${genrePattern.name} for ${tag})`
            : 'Auto: no genre set, so no drums'}
        />
        <KeyButton
          size="md"
          label="Off"
          active={isOff}
          led={isOff ? 'on' : 'off'}
          onClick={() => setDrumPattern(null)}
          title="No drums, whatever the genre"
        />
      </div>

      <div className="grid grid-cols-4 gap-1">
        {DRUM_PATTERNS.map((p) => {
          const picked = !isAuto && settings.drumPatternId === p.id;
          const autoPlays = isAuto && p.id === genreId;
          return (
            <KeyButton
              key={p.id}
              size="sm"
              label={drumKeyLabel(p.id)}
              active={picked}
              led={picked ? 'on' : autoPlays ? 'alt' : 'off'}
              onClick={() => setDrumPattern(p.id)}
              title={`${p.name}${p.swing ? ' · swing' : ''}${autoPlays ? ` · Auto plays this for ${tag}` : ''}`}
            />
          );
        })}
        <LedLegend />
      </div>

    </div>
  );
}
