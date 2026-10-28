/**
 * Transport, chord display and live status remain above the control tabs.
 */
import { useId } from 'react';
import type { KeyboardEvent } from 'react';
import { usePlayStore } from '../../../store/playStore';
import type { PlayPane } from '../../../store/playStore';
import KeyButton from './ui/KeyButton';
import Transport from './Transport';
import VisualPane from './VisualPane';
import PlaybackStatus from './PlaybackStatus';
import InstrumentPane from './InstrumentPane';
import RhythmPane from './RhythmPane';
import DrumsPane from './DrumsPane';
import ControllerPane from './ControllerPane';

/** Rail keys: `label` on the key cap, `name` for screen readers. */
const PANES: { id: PlayPane; label: string; name: string; title: string }[] = [
  { id: 'instrument', label: 'INSTR', name: 'Instrument', title: 'Instrument: the harmony sound' },
  { id: 'rhythm', label: 'RHYTHM', name: 'Rhythm', title: 'Rhythm: comping rhythm and bass' },
  { id: 'drums', label: 'DRUMS', name: 'Drums', title: 'Drums: drum pattern' },
];

interface PlayPanelProps {
  midiActiveNotes: number[];
}

export default function PlayPanel({ midiActiveNotes }: PlayPanelProps) {
  const pane = usePlayStore((s) => s.pane);
  const setPane = usePlayStore((s) => s.setPane);
  const baseId = useId();
  const tabId = (id: PlayPane) => `${baseId}-tab-${id}`;
  const panelId = `${baseId}-panel`;

  const open = PANES.find((p) => p.id === pane) ?? PANES[0];

  // Roving focus follows the horizontal tab row.
  const handleRailKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const tabs = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]'));
    const i = tabs.indexOf(e.target as HTMLElement);
    if (i < 0) return;
    let next: number;
    if (e.key === 'ArrowRight') next = (i + 1) % PANES.length;
    else if (e.key === 'ArrowLeft') next = (i + PANES.length - 1) % PANES.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = PANES.length - 1;
    else return;
    e.preventDefault();
    setPane(PANES[next].id);
    tabs[next]?.focus();
  };

  return (
    <div
      className="te-device h-full min-h-0 flex flex-col gap-3 p-2 overflow-y-auto overscroll-contain"
      style={{
        color: 'var(--key-text)',
        fontFamily: 'var(--font-device)',
      }}
    >
      <Transport />
      <div className="te-live-display shrink-0 flex flex-col gap-2">
        <VisualPane midiActiveNotes={midiActiveNotes} compact />
        <PlaybackStatus />
      </div>

      <div className="shrink-0 flex items-end gap-2">
          <div
            role="tablist"
            aria-label="Play panes"
            aria-orientation="horizontal"
            className="min-w-0 flex-1 grid grid-cols-3 gap-1"
            onKeyDown={handleRailKey}
          >
            {PANES.map((p) => (
              <KeyButton
                key={p.id}
                size="sm"
                label={p.name}
                title={p.title}
                ariaLabel={p.name}
                role="tab"
                id={tabId(p.id)}
                ariaControls={panelId}
                tabIndex={pane === p.id ? 0 : -1}
                active={pane === p.id}
                ariaSelected={pane === p.id}
                onClick={() => setPane(p.id)}
                className="te-pane-tab"
              />
            ))}
          </div>

      </div>

      <div role="tabpanel" id={panelId} aria-labelledby={tabId(open.id)} className="te-selection-pane min-w-0 shrink-0">
          {pane === 'instrument' && <InstrumentPane />}
          {pane === 'rhythm' && <RhythmPane />}
          {pane === 'drums' && <DrumsPane />}
      </div>
      <div className="shrink-0 pt-2" style={{ borderTop: '1px solid var(--panel-border)' }}>
        <ControllerPane />
      </div>
    </div>
  );
}
