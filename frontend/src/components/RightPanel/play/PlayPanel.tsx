/**
 * Transport, always-visible voicing, then the four arrangement controls.
 * The compact visual leaves the existing controls their full height.
 */
// Frame 18 + transport 30 + two 8px gaps + visual 132 + up to 280px controls.
// At 300px panel width the controls keep ~197px; shorter viewports can scroll
// the controls while transport and the chord display remain in place.
import { useId } from 'react';
import type { KeyboardEvent } from 'react';
import { useSongStore } from '../../../store/songStore';
import { usePlayStore } from '../../../store/playStore';
import type { PlayPane } from '../../../store/playStore';
import KeyButton from './ui/KeyButton';
import Knob from './ui/Knob';
import Transport from './Transport';
import VisualPane from './VisualPane';
import InstrumentPane from './InstrumentPane';
import RhythmPane from './RhythmPane';
import DrumsPane from './DrumsPane';
import ControllerPane from './ControllerPane';

/** Rail keys: `label` on the key cap, `name` for screen readers. */
const PANES: { id: PlayPane; label: string; name: string; title: string }[] = [
  { id: 'instrument', label: 'INSTR', name: 'Instrument', title: 'Instrument: the harmony sound' },
  { id: 'rhythm', label: 'RHYTHM', name: 'Rhythm', title: 'Rhythm: comping rhythm and bass' },
  { id: 'drums', label: 'DRUMS', name: 'Drums', title: 'Drums: drum pattern' },
  { id: 'controller', label: 'CTRL', name: 'Controller', title: 'Controller: master, harmony, bass and drum volumes' },
];

const RAIL_WIDTH = 52;

/** The range songStore.setBpm / setBpmLive clamp to (SongSettings' input
 *  too), so a typed tempo is never pulled to the knob's ends; a new song
 *  starts at 80. */
const BPM_MIN = 20;
const BPM_MAX = 300;
const BPM_DEFAULT = 80;

const formatInt = (v: number): string => String(Math.round(v));

interface PlayPanelProps {
  midiActiveNotes: number[];
}

export default function PlayPanel({ midiActiveNotes }: PlayPanelProps) {
  const pane = usePlayStore((s) => s.pane);
  const setPane = usePlayStore((s) => s.setPane);
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
      className="te-device h-full min-h-0 flex flex-col gap-2 p-2 overflow-hidden"
      style={{
        color: 'var(--key-text)',
        fontFamily: 'var(--font-device)',
      }}
    >
      <Transport />
      <div className="shrink-0">
        <VisualPane midiActiveNotes={midiActiveNotes} compact />
      </div>

      <div className="flex-1 min-h-0 flex gap-2">
        {/* Rail: pane keys on top, tempo always within reach at the bottom. */}
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
          </div>
        </div>

        <div role="tabpanel" id={panelId} aria-labelledby={tabId(open.id)} className="flex-1 min-w-0 min-h-0 overflow-y-auto overscroll-contain">
          {pane === 'instrument' && <InstrumentPane />}
          {pane === 'rhythm' && <RhythmPane />}
          {pane === 'drums' && <DrumsPane />}
          {pane === 'controller' && <ControllerPane />}
        </div>
      </div>
    </div>
  );
}
