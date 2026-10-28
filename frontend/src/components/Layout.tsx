import { useState, useCallback, useEffect, useRef } from 'react';

type InputMode = 'generate' | 'midi' | 'manual';
// Order matters — Generate is the default and the most-used path, so it
// occupies the leftmost tab. MIDI and Set Chord sit in declining-frequency
// order to its right.
const INPUT_TABS: { id: InputMode; label: string }[] = [
  { id: 'generate', label: 'Generate' },
  { id: 'midi', label: 'MIDI' },
  { id: 'manual', label: 'Set Chord' },
];
import Staff from './ScoreEditor/Staff';
import SongFormDialog from './ScoreEditor/SongFormDialog';
import ImportScoreDialog from './ScoreEditor/ImportScoreDialog';
import SectionsDialog from './ScoreEditor/SectionsDialog';
import ExportMenu from './ScoreEditor/ExportMenu';
import PlayPanel from './RightPanel/play/PlayPanel';
import SongSettings from './RightPanel/SongSettings';
import ChordActions from './RightPanel/ChordActions';
import MidiStatus from './RightPanel/MidiStatus';
import MyPage from './MyPage/MyPage';
import ThemeToggle from './RightPanel/ThemeToggle';
import { useSongStore } from '../store/songStore';
import { useSessionStore } from '../store/sessionStore';
import { useGenerationStore } from '../store/generationStore';
import { usePlayStore } from '../store/playStore';
import type { Song } from '../models/types';

/** The Play panel needs this much width for its rail and one pane. */
const MIN_PANEL_WIDTH = 300;

/** The MIDI tab. MidiStatus is the only MIDI source, and on unmount it
 *  disconnects without clearing the notes and chord it last passed on (no
 *  key release follows), so they are cleared here; otherwise the Play
 *  panel's Visual pane would keep showing them. */
function MidiTab({ onMidiNotes }: { onMidiNotes: (notes: number[]) => void }) {
  const setMidiCandidates = useSongStore((s) => s.setMidiCandidates);
  useEffect(() => () => {
    onMidiNotes([]);
    setMidiCandidates([]);
  }, [onMidiNotes, setMidiCandidates]);
  return <MidiStatus onMidiNotes={onMidiNotes} />;
}

export default function Layout() {
  const song = useSongStore((s) => s.song);
  const setTitle = useSongStore((s) => s.setTitle);
  const clearSong = useSongStore((s) => s.clearSong);
  const selectedSlots = useSongStore((s) => s.selectedSlots);
  const setChord = useSongStore((s) => s.setChord);
  const addSession = useSessionStore((s) => s.add);
  const sessionCount = useSessionStore((s) => s.sessions.length);
  const modelKey = useGenerationStore((s) => s.modelKey);
  const playSettings = usePlayStore((s) => s.settings);
  const resetPlayback = useSongStore((s) => s.resetPlayback);
  const importSong = useSongStore((s) => s.importSong);
  const previousImportSong = useSongStore((s) => s.previousImportSong);
  const undoImport = useSongStore((s) => s.undoImport);
  const [saveMessage, setSaveMessage] = useState('');

  // Bundle the Play-panel settings with the saved score, so MyPage replays
  // the session the way the editor played it at Save time (bpm + genre are
  // already inside `song`).
  const handleSaveSession = useCallback(() => {
    try {
      addSession(song, { model: modelKey, genre: song.genre, ...playSettings });
      setSaveMessage('Saved in this browser. Open Projects to download a backup.');
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : 'The project could not be saved.');
    }
  }, [addSession, song, modelKey, playSettings]);

  const [midiActiveNotes, setMidiActiveNotes] = useState<number[]>([]);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelWidth, setPanelWidth] = useState(320);
  const [panelMode, setPanelMode] = useState<'play' | 'input'>('input');
  const [inputMode, setInputMode] = useState<InputMode>('generate');
  // Top-level view: editor (staff + right panel) vs full-page MyPage.
  // MyPage is its own page, not a panel mode — sessions render as
  // read-only staves there, which needs the whole canvas width.
  const [view, setView] = useState<'editor' | 'my'>('editor');
  const [songFormOpen, setSongFormOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [sectionsOpen, setSectionsOpen] = useState(false);
  const resizingRef = useRef(false);

  // After New from Song Form lands, show Input → Generate so the A/B/C
  // suggestions for the new section are right there to swap.
  const handleSongFormGenerated = useCallback(() => {
    setPanelOpen(true);
    setPanelMode('input');
    setInputMode('generate');
  }, []);

  const handleImported = useCallback((imported: Song) => {
    importSong(imported);
    setPanelOpen(true);
    setPanelMode('input');
    setInputMode('generate');
  }, [importSong]);

  const startResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const next = window.innerWidth - ev.clientX - 20;
      setPanelWidth(Math.min(640, Math.max(MIN_PANEL_WIDTH, next)));
    };
    const onUp = () => {
      resizingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, []);

  const handleClear = useCallback(() => {
    if (window.confirm('Reset the entire song? This cannot be undone.')) {
      clearSong();
    }
  }, [clearSong]);

  const handleClearSelection = useCallback(() => {
    for (const slot of selectedSlots) setChord(slot, null);
  }, [selectedSlots, setChord]);

  const handleMidiNotes = useCallback((notes: number[]) => {
    setMidiActiveNotes(notes);
  }, []);

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      {/* Top header — editorial brand lockup, compact so the right panel
          can fit a full-screen viewport without scrolling. */}
      <header className="shrink-0 py-4 px-4 relative text-center" style={{ borderBottom: '1px solid var(--border)' }}>
        <h1
          className="font-display text-4xl leading-none"
          style={{ color: 'var(--text-heading)', fontWeight: 700 }}
        >
          PearlLeeStudio
        </h1>
        <p
          className="font-display text-base mt-1"
          style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontWeight: 400 }}
        >
          TheArtist
        </p>
        <div className="absolute top-3 right-4 flex items-center gap-2">
          <ThemeToggle />
          <button
            onClick={() => {
              // Whatever is playing belongs to the view being left.
              resetPlayback();
              setView(view === 'my' ? 'editor' : 'my');
            }}
            className="px-3 py-1.5 text-sm btn-hover"
            style={{
              background: view === 'my' ? 'var(--text-heading)' : 'var(--btn-bg)',
              color: view === 'my' ? 'var(--bg-primary)' : 'var(--text-primary)',
            }}
            title={view === 'my' ? 'Back to editor' : 'Open saved projects'}
          >
            {view === 'my' ? 'Editor' : 'Projects'}
          </button>
        </div>
      </header>

      {view === 'my' ? (
        <MyPage onExitToEditor={() => setView('editor')} />
      ) : (
      <div className="flex flex-1 min-h-0">
        {/* Left Panel - Score Editor */}
        <div className="flex-1 overflow-y-auto p-4 min-w-0">
          {/* Top bar: song-form entry left, title centered, Save/Clear
              right-aligned */}
          <div className="flex flex-wrap items-center mb-4 gap-3">
            {/* Left group — flex-1 like the right group, so the title
                stays centered */}
            <div className="flex-1 flex items-center justify-start gap-2">
              <button
                onClick={() => setImportOpen(true)}
                className="px-3 py-1 text-xs font-bold whitespace-nowrap btn-hover"
                style={{ background: 'var(--btn-bg)', color: 'var(--text-heading)', border: '1px solid var(--border)' }}
                title="Import and review a PDF or image with chord symbols"
                aria-haspopup="dialog"
              >
                Import Score
              </button>
              <button
                onClick={() => setSongFormOpen(true)}
                className="px-3 py-1 text-xs font-bold whitespace-nowrap btn-hover"
                style={{ background: 'var(--brand-yellow)', color: '#1a1a1a' }}
                title="Pick a song-form section and how many chords to generate"
                aria-haspopup="dialog"
              >
                New from Song Form
              </button>
            </div>

            {/* Song title — centered, editorial. Typing here turns the
                automatic section-based title off (songStore.setTitle). */}
            <input
              type="text"
              value={song.title}
              onChange={(e) => setTitle(e.target.value)}
              className="font-display text-2xl bg-transparent outline-none text-center shrink min-w-0"
              style={{ color: 'var(--text-heading)', fontStyle: 'italic', fontWeight: 500 }}
              placeholder="Untitled"
              aria-label="Song title"
            />

            {/* Save / Clear — right. "Clear selection" only appears when
                the user has slots selected; it lives next to the global
                Clear so the two destructive actions are co-located. */}
            <div className="flex-1 flex items-center justify-end gap-2">
              <ExportMenu />
              <button
                onClick={handleSaveSession}
                className="px-3 py-1  text-xs font-bold btn-hover"
                style={{ background: 'var(--text-heading)', color: 'var(--bg-primary)' }}
                title={`Save current song + settings as a session (${sessionCount} saved)`}
              >
                Save
              </button>
              {selectedSlots.length > 0 && (
                <button
                  onClick={handleClearSelection}
                  className="px-3 py-1  text-xs btn-hover"
                  style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)' }}
                  title="Reset chords in the selected slots"
                >
                  Clear
                </button>
              )}
              <button
                onClick={handleClear}
                className="px-3 py-1  text-xs btn-hover"
                style={{ background: 'var(--btn-bg)', color: 'var(--text-muted)' }}
                title="Reset the entire song to its initial state"
              >
                Initialize
              </button>
            </div>
          </div>

          {saveMessage && <p role="status" className="text-xs mb-3" style={{ color: 'var(--text-soft)' }}>{saveMessage}</p>}

          {/* Inline song settings — sits above the staff so the user can
              click straight on BPM / Time / Key / Genre to change them
              instead of hunting in a side panel. */}
          <div className="mb-3 pb-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <SongSettings />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 mb-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span>{song.sections?.length ? 'Click a section name or drag across chords to select a range.' : 'Drag across chords to generate a variation.'}</span>
            <div className="flex gap-2">
              {previousImportSong && <button onClick={() => {
                if (window.confirm('Restore the song from before the import? Changes made after importing will be replaced.')) undoImport();
              }} className="px-2 py-1 btn-hover" style={{ background: 'var(--btn-bg)' }}>Undo import</button>}
              <button onClick={() => setSectionsOpen(true)} className="px-2 py-1 btn-hover" style={{ background: 'var(--btn-bg)' }} aria-haspopup="dialog">Edit Song Form</button>
            </div>
          </div>
          <Staff />
        </div>

        {/* Toggle column — short yellow chevron button at the top
            (sized to roughly match the Play/Input tab row), plus a
            transparent resize handle filling the rest when the panel
            is open. Drag the handle to resize, click the button to
            collapse. */}
        <div className="shrink-0 flex flex-col" style={{ width: '20px' }}>
          <button
            onClick={() => setPanelOpen(!panelOpen)}
            className="flex items-center justify-center btn-hover"
            style={{
              background: 'var(--brand-yellow)',
              color: '#1a1a1a',
              height: '52px',
              fontSize: '14px',
              fontWeight: 700,
            }}
            title={panelOpen ? 'Hide panel' : 'Show panel'}
          >
            {panelOpen ? '▶' : '◀'}
          </button>
          {panelOpen && (
            <div
              onMouseDown={startResize}
              className="flex-1 cursor-col-resize"
              title="Drag to resize panel"
            />
          )}
        </div>

        {/* Right Panel — collapsible. A column: the Play/Input tabs, then
            the mode's content filling the rest. Play never scrolls (one
            pane at a time); Input scrolls inside its own area. */}
        {panelOpen && (
          <div
            className="shrink-0 flex flex-col min-h-0 p-3 gap-3"
            style={{
              width: `${panelWidth}px`,
              borderLeft: '1px solid var(--border)',
              background: 'var(--bg-surface)',
            }}
          >
            {/* Top-level mode tabs — Play / Input. Saved sessions live on
                their own full-page route (header "My" button) so they get
                room to render each session as a real staff. */}
            <div
              className="shrink-0 flex items-end justify-between"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              {(['play', 'input'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setPanelMode(mode)}
                  className="font-display text-2xl leading-none px-1 pt-1 pb-2 transition-colors btn-hover"
                  style={{
                    color: panelMode === mode ? 'var(--brand-yellow)' : 'var(--text-muted)',
                    borderTop: panelMode === mode ? '3px solid var(--brand-yellow)' : '3px solid transparent',
                    fontWeight: 700,
                    background: 'transparent',
                  }}
                >
                  {mode === 'play' ? 'Play' : 'Input'}
                </button>
              ))}
            </div>

            {/* Mode content */}
            {panelMode === 'play' && (
              <div className="flex-1 min-h-0">
                <PlayPanel midiActiveNotes={midiActiveNotes} />
              </div>
            )}

            {panelMode === 'input' && (
              <div className="flex-1 min-h-0 overflow-y-auto space-y-3">
                {/* Sub-tab bar — three input methods. */}
                <div className="flex" style={{ borderBottom: '1px solid var(--border)' }}>
                  {INPUT_TABS.map((t) => {
                    const active = inputMode === t.id;
                    return (
                      <button
                        key={t.id}
                        onClick={() => setInputMode(t.id)}
                        className="flex-1 px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors btn-hover"
                        style={{
                          color: active ? 'var(--text-heading)' : 'var(--text-muted)',
                          borderTop: active ? '2px solid var(--brand-yellow)' : '2px solid transparent',
                          background: 'transparent',
                        }}
                      >
                        {t.label}
                      </button>
                    );
                  })}
                </div>

                {inputMode === 'midi' && <MidiTab onMidiNotes={handleMidiNotes} />}
                {inputMode === 'generate' && <ChordActions view="generate" />}
                {inputMode === 'manual' && <ChordActions view="manual" />}
              </div>
            )}
          </div>
        )}

      </div>
      )}

      {/* Mounted only while open; the dialog opens itself as a modal. */}
      {songFormOpen && (
        <SongFormDialog
          onClose={() => setSongFormOpen(false)}
          onGenerated={handleSongFormGenerated}
        />
      )}
      {importOpen && <ImportScoreDialog onClose={() => setImportOpen(false)} onImported={handleImported} />}
      {sectionsOpen && <SectionsDialog onClose={() => setSectionsOpen(false)} />}
    </div>
  );
}
