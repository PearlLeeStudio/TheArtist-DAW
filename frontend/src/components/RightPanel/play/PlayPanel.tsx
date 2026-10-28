/**
 * Play mode as one device panel: the transport on top, a rail of pane keys
 * with the BPM and drum-level knobs on the left, and the open pane on the
 * right. Every part has a fixed height, so nothing here scrolls.
 */
// ~470px tall on a 1366×768 window and needs 344: frame 18 + transport 30 + 8
// + rail 288 (keys 156 + spacer ≥ 8 + knobs 58 + 8 + 58). The pane (≤ 284px
// tall) gets the rest of the row: ~197px wide at the 300px minimum panel
// width, ~217px at the default 320px.
import { useId } from 'react';
import type { KeyboardEvent } from 'react';
import { useSongStore } from '../../../store/songStore';
import { usePlayStore } from '../../../store/playStore';
import type { PlayPane } from '../../../store/playStore';
import { DEFAULT_PLAY_SETTINGS } from '../../../engine/playSettings';
import KeyButton from './ui/KeyButton';
import Knob from './ui/Knob';
import Transport from './Transport';
import VisualPane from './VisualPane';
import InstrumentPane from './InstrumentPane';
import RhythmPane from './RhythmPane';
import DrumsPane from './DrumsPane';

/** Rail keys: `label` on the key cap, `name` for screen readers. */
const PANES: { id: PlayPane; label: string; name: string; title: string }[] = [
  { id: 'visual', label: 'VISUAL', name: 'Visual', title: 'Visual: keyboard or fretboard voicing' },
  { id: 'instrument', label: 'INSTR', name: 'Instrument', title: 'Instrument: the harmony sound' },
  { id: 'rhythm', label: 'RHYTHM', name: 'Rhythm', title: 'Rhythm: comping rhythm and bass' },
  { id: 'drums', label: 'DRUMS', name: 'Drums', title: 'Drums: drum pattern' },
];

const RAIL_WIDTH = 52;

/** The range songStore.setBpm / setBpmLive clamp to (SongSettings' input
 *  too), so a typed tempo is never pulled to the knob's ends; a new song
 *  starts at 80. */
const BPM_MIN = 20;
const BPM_MAX = 300;
const BPM_DEFAULT = 80;
const DRUM_DEFAULT = Math.round(DEFAULT_PLAY_SETTINGS.drumVolume * 100);

const formatInt = (v: number): string => String(Math.round(v));

interface PlayPanelProps {
  midiActiveNotes: number[];
}

export default function PlayPanel({ midiActiveNotes }: PlayPanelProps) {
  const pane = usePlayStore((s) => s.pane);
  const setPane = usePlayStore((s) => s.setPane);
  const drumVolume = usePlayStore((s) => s.settings.drumVolume);
  const setDrumVolume = usePlayStore((s) => s.setDrumVolume);
  const bpm = useSongStore((s) => s.song.bpm);
  const setBpmLive = useSongStore((s) => s.setBpmLive);
  const baseId = useId();
  const tabId = (id: PlayPane) => `${baseId}-tab-${id}`;
  const panelId = `${baseId}-panel`;

  const open = PANES.find((p) => p.id === pane) ?? PANES[0];

  // A vertical tablist: only the open pane's key is a Tab stop; Up/Down
  // (and Home/End) move from the focused key and open the pane they reach.
  const handleRailKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const tabs = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]'));
    const i = tabs.indexOf(e.target as HTMLElement);
    if (i < 0) return;
    let next: number;
    if (e.key === 'ArrowDown') next = (i + 1) % PANES.length;
    else if (e.key === 'ArrowUp') next = (i + PANES.length - 1) % PANES.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = PANES.length - 1;
    else return;
    e.preventDefault();
    setPane(PANES[next].id);
    tabs[next]?.focus();
  };

  return (
    <div
      className="h-full min-h-0 flex flex-col gap-2 p-2 overflow-hidden"
      style={{
        background: 'var(--panel-bg)',
        border: '1px solid var(--panel-border)',
        borderRadius: 6,
        color: 'var(--key-text)',
        fontFamily: 'var(--font-device)',
      }}
    >
      <Transport />

      <div className="flex-1 min-h-0 flex gap-2">
        {/* Rail: pane keys on top, knobs at the bottom. */}
        <div className="shrink-0 flex flex-col" style={{ width: RAIL_WIDTH }}>
          <div
            role="tablist"
            aria-label="Play panes"
            aria-orientation="vertical"
            className="shrink-0 flex flex-col gap-1"
            onKeyDown={handleRailKey}
          >
            {PANES.map((p) => (
              <KeyButton
                key={p.id}
                size="lg"
                label={p.label}
                title={p.title}
                ariaLabel={p.name}
                role="tab"
                id={tabId(p.id)}
                ariaControls={panelId}
                tabIndex={pane === p.id ? 0 : -1}
                active={pane === p.id}
                ariaSelected={pane === p.id}
                led={pane === p.id ? 'on' : 'off'}
                onClick={() => setPane(p.id)}
              />
            ))}
          </div>

          <div className="flex-1 min-h-2" />

          <div className="shrink-0 flex flex-col items-center gap-2">
            <Knob
              label="BPM"
              value={bpm}
              min={BPM_MIN}
              max={BPM_MAX}
              step={1}
              defaultValue={BPM_DEFAULT}
              onChange={setBpmLive}
              format={formatInt}
            />
            <Knob
              label="DRUM"
              value={Math.round(drumVolume * 100)}
              min={0}
              max={100}
              step={1}
              defaultValue={DRUM_DEFAULT}
              onChange={(v: number) => setDrumVolume(v / 100)}
              format={formatInt}
            />
          </div>
        </div>

        {/* No clip here: the panel frame clips, and keys on the pane's
            edges keep their whole focus ring. */}
        <div role="tabpanel" id={panelId} aria-labelledby={tabId(open.id)} className="flex-1 min-w-0 min-h-0">
          {pane === 'visual' && <VisualPane midiActiveNotes={midiActiveNotes} />}
          {pane === 'instrument' && <InstrumentPane />}
          {pane === 'rhythm' && <RhythmPane />}
          {pane === 'drums' && <DrumsPane />}
        </div>
      </div>
    </div>
  );
}
