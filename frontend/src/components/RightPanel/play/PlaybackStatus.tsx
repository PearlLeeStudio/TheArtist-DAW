import { DRUM_PATTERNS, drumGrid } from '../../../engine/drumPatterns';
import { bassPatternFor, meterRhythm, patternSteps, resolveDrumPatternId, resolveHarmonyRhythm } from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import StepRow from './ui/StepRow';
import { usePlayStep } from './usePlayStep';

/** Playback indicators are permanent, independently of the selected control tab. */
export default function PlaybackStatus() {
  const settings = usePlayStore((state) => state.settings);
  const genre = useSongStore((state) => state.song.genre);
  const beats = useSongStore((state) => state.song.timeSignature[0]);
  const step = usePlayStep();
  const rhythm = resolveHarmonyRhythm(settings, genre);
  const harmony = patternSteps(meterRhythm(rhythm.pattern, beats), beats).map((on) => ({ level: on ? 1 : 0 }));
  const bass = patternSteps(meterRhythm(bassPatternFor(genre), beats), beats).map((on) => ({ level: on ? 1 : 0 }));
  const drum = DRUM_PATTERNS.find((pattern) => pattern.id === resolveDrumPatternId(settings, genre)) ?? null;
  const rows = drumGrid(drum, beats * 4);

  return (
    <div className="te-playback-status shrink-0 grid grid-cols-1 gap-1" aria-label="Live rhythm and drum status">
      <section className="te-status-window" aria-label="Rhythm playback">
        <p className="te-status-title"><span className="te-status-type">Rhythm</span><span className="min-w-0 truncate">{rhythm.label}</span></p>
        <div className="flex flex-col gap-[2px]">
          <StepRow label="HARM" cells={harmony} playhead={step} height={10} labelSize={11} dim={settings.harmonyVolume === 0} />
          <StepRow label="BASS" cells={bass} playhead={step} height={10} labelSize={11} dim={!settings.bassEnabled} />
        </div>
      </section>
      <section className="te-status-window" aria-label="Drum playback">
        <p className="te-status-title" title={drum?.name ?? 'Drums off'}>
          <span className="te-status-type">Drums</span><span className="min-w-0 truncate">{drum?.name ?? 'Off'}</span>
        </p>
        <div className="flex flex-col gap-[2px]">
          {rows.map((row) => <StepRow key={row.label} label={row.label} cells={row.cells} playhead={drum ? step : null} dim={!drum} height={10} labelSize={11} />)}
        </div>
      </section>
    </div>
  );
}
