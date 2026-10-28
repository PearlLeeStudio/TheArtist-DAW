// Height: screen 56 + 8 + two 88px channel rows + 8 + 8 + hint 24 = 280px.
import { DEFAULT_PLAY_SETTINGS, resolveDrumPatternId } from '../../../engine/playSettings';
import { usePlayStore } from '../../../store/playStore';
import { useSongStore } from '../../../store/songStore';
import Knob from './ui/Knob';
import Screen from './ui/Screen';

const percent = (value: number): string => `${Math.round(value)}%`;

/** Four independent mix controls; the master scales the complete mix. */
export default function ControllerPane() {
  const settings = usePlayStore((s) => s.settings);
  const setMasterVolume = usePlayStore((s) => s.setMasterVolume);
  const setHarmonyVolume = usePlayStore((s) => s.setHarmonyVolume);
  const setBassVolume = usePlayStore((s) => s.setBassVolume);
  const setDrumVolume = usePlayStore((s) => s.setDrumVolume);
  const genre = useSongStore((s) => s.song.genre);

  const drumsOn = resolveDrumPatternId(settings, genre) !== null;
  const channels = [
    { id: 'master', label: 'Master', value: settings.masterVolume, initial: DEFAULT_PLAY_SETTINGS.masterVolume, set: setMasterVolume },
    { id: 'harmony', label: 'Harmony', value: settings.harmonyVolume, initial: DEFAULT_PLAY_SETTINGS.harmonyVolume, set: setHarmonyVolume },
    { id: 'bass', label: 'Bass', value: settings.bassVolume, initial: DEFAULT_PLAY_SETTINGS.bassVolume, set: setBassVolume },
    { id: 'drums', label: 'Drums', value: settings.drumVolume, initial: DEFAULT_PLAY_SETTINGS.drumVolume, set: setDrumVolume },
  ];
  const allMuted = settings.masterVolume === 0 || (
    settings.harmonyVolume === 0 &&
    (!settings.bassEnabled || settings.bassVolume === 0) &&
    (!drumsOn || settings.drumVolume === 0)
  );
  const layerStatus = [
    settings.bassEnabled ? 'BASS ON' : 'BASS OFF',
    drumsOn ? 'DRUMS ON' : 'DRUMS OFF',
  ].join(' · ');

  return (
    <div role="group" aria-label="Controller view" className="flex min-w-0 flex-col gap-2">
      <Screen label="CONTROLLER" style={{ height: 56 }}>
        <div className="flex items-center justify-between gap-2" style={{ height: 14 }}>
          <span style={{ color: allMuted ? 'var(--led-alt)' : 'var(--screen-text)' }}>
            {allMuted ? 'MIX MUTED' : 'MASTER OUT'}
          </span>
          <span className="tabular" style={{ color: 'var(--mix-master)' }}>
            {percent(settings.masterVolume * 100)}
          </span>
        </div>
        <div className="truncate" style={{ height: 14, fontSize: 10, color: 'var(--screen-text-dim)' }}>
          {layerStatus}
        </div>
      </Screen>

      <div className="grid grid-cols-2 gap-2">
        {channels.map((channel) => (
          <div key={channel.id} className="te-channel flex min-w-0 items-center justify-center" style={{ height: 88, padding: 5 }}>
            <Knob
              label={channel.label}
              ariaLabel={`${channel.label} volume`}
              accent={`var(--mix-${channel.id})`}
              value={Math.round(channel.value * 100)}
              min={0}
              max={100}
              step={1}
              size={48}
              textSize={11}
              defaultValue={Math.round(channel.initial * 100)}
              onChange={(value) => channel.set(value / 100)}
              format={percent}
            />
          </div>
        ))}
      </div>

      <p className="m-0 text-center" style={{ fontSize: 10, lineHeight: '12px', color: 'var(--key-text-dim)' }}>
        Drag · Scroll · Arrow keys<br />
        Double-click to reset
      </p>
    </div>
  );
}
