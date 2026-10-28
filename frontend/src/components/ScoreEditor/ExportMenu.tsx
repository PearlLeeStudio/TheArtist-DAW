import { useEffect, useId, useRef, useState } from 'react';
import { useSongStore } from '../../store/songStore';
import { usePlayStore } from '../../store/playStore';
import {
  buildExportSpec, downloadExportBlob, exportResponseError,
  isLoopbackHostname, requestMidiExport, safeExportFilename,
} from '../../engine/exportSpec';
import type { PdfTheme } from '../../engine/pdf';

interface DawTarget { id: 'logic' | 'ableton'; name: string; available: boolean; action: 'open' | 'reveal' }
type ExportAction = 'midi' | PdfTheme | 'logic' | 'ableton';

export default function ExportMenu() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);
  const [targets, setTargets] = useState<DawTarget[] | null>(null);
  const [targetError, setTargetError] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);
  const requestRef = useRef<AbortController | null>(null);
  const panelId = useId();
  const local = isLoopbackHostname(window.location.hostname);

  useEffect(() => () => requestRef.current?.abort(), []);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !local) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10_000);
    void (async () => {
      try {
        const response = await fetch('/api/daw/targets', { signal: controller.signal });
        if (!response.ok) throw await exportResponseError(response);
        const body: { targets?: DawTarget[] } = await response.json();
        if (!Array.isArray(body.targets)) throw new Error('Could not read installed DAWs.');
        if (!controller.signal.aborted) setTargets(body.targets);
      } catch (error) {
        if (!controller.signal.aborted) setTargetError(error instanceof Error ? error.message : 'Could not check installed DAWs.');
        else if (!controller.signal.reason || controller.signal.reason.name === 'AbortError') setTargetError('DAW detection did not finish. Download MIDI is still available.');
      } finally { clearTimeout(timer); }
    })();
    return () => { clearTimeout(timer); controller.abort('closed'); };
  }, [open, local]);

  const runExport = async (action: ExportAction) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setFeedback(null);
    const controller = new AbortController();
    requestRef.current = controller;
    const song = structuredClone(useSongStore.getState().song);
    const settings = { ...usePlayStore.getState().settings };
    try {
      if (action === 'midi') {
        const blob = await requestMidiExport(buildExportSpec(song, settings), controller.signal);
        downloadExportBlob(blob, safeExportFilename(song.title, 'mid'));
        setFeedback({ text: 'MIDI downloaded. Import it into a DAW to choose sounds and continue arranging.', error: false });
      } else if (action === 'logic' || action === 'ableton') {
        if (!local) throw new Error('Download MIDI and open it on your computer. DAW handoff requires localhost.');
        const spec = buildExportSpec(song, settings);
        let timedOut = false;
        const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 60_000);
        try {
          const response = await fetch('/api/daw/open', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: action, spec }), signal: controller.signal,
          });
          if (!response.ok) throw await exportResponseError(response);
          const result: { action?: string; path?: string } = await response.json();
          if (result.action !== 'open' && result.action !== 'reveal') throw new Error('The DAW did not confirm the handoff.');
          setFeedback({ text: result.action === 'reveal'
            ? 'MIDI shown in Finder. Drag it into Ableton Live to continue.'
            : 'MIDI sent to Logic Pro. Choose or create a project there to continue.', error: false });
        } catch (error) {
          if (timedOut) throw new Error('DAW handoff timed out. Check the DAW before trying again.', { cause: error });
          throw error;
        } finally { clearTimeout(timer); }
      } else {
        const { createSongPdf } = await import('../../engine/pdf');
        const blob = await createSongPdf(song, action);
        downloadExportBlob(blob, safeExportFilename(song.title, 'pdf'));
        setFeedback({ text: 'PDF downloaded.', error: false });
      }
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : 'Export failed. Please try again.', error: true });
    } finally {
      busyRef.current = false;
      setBusy(false);
      requestRef.current = null;
    }
  };

  const actionButton = (label: string, action: ExportAction, disabled = false, title?: string) => (
    <button type="button" onClick={() => { void runExport(action); }} disabled={busy || disabled} title={title}
      className="block w-full px-3 py-2 text-left text-xs btn-hover disabled:opacity-40 disabled:cursor-not-allowed"
      style={{ color: 'var(--text-primary)' }}>{label}</button>
  );
  const dawButton = (id: 'logic' | 'ableton', label: string) => {
    const target = targets?.find((item) => item.id === id);
    const reason = !local ? 'Available on localhost. Download MIDI for use on this computer.'
      : targetError || (!targets ? 'Checking installed DAWs…' : !target?.available ? 'This DAW is not installed on the server computer.' : undefined);
    return actionButton(label, id, !local || !target?.available, reason);
  };

  return (
    <div className="relative" ref={root}>
      <button ref={trigger} type="button" aria-expanded={open} aria-controls={panelId}
        onClick={() => {
          if (!open) { setTargets(null); setTargetError(''); }
          setOpen(!open);
        }}
        className="px-3 py-1 text-xs font-bold whitespace-nowrap btn-hover"
        style={{ background: 'var(--btn-bg)', color: 'var(--text-heading)', border: '1px solid var(--border)' }}>
        {busy ? 'Exporting…' : 'Export ▾'}
      </button>
      {open && <div id={panelId} className="absolute right-0 top-full mt-2 z-50 py-1 w-72 max-w-[calc(100vw-2rem)] shadow-xl"
        aria-label="Export options" aria-busy={busy}
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
        {actionButton('Download MIDI', 'midi')}
        <p className="px-3 pb-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>Harmony, bass and drums · DAW sounds may differ.</p>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {actionButton('PDF · Current theme', 'current')}
          {actionButton('PDF · Light (print)', 'light')}
          {actionButton('PDF · Dark', 'dark')}
        </div>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {dawButton('logic', 'Open in Logic Pro')}
          {dawButton('ableton', 'Show MIDI for Ableton Live')}
        </div>
        <p className="px-3 py-2 text-[10px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {!local ? 'Download .mid, then import it into your DAW. Automatic handoff is available on localhost.'
            : targetError || (!targets ? 'Checking installed DAWs…' : 'Local Mac: Logic opens the MIDI; Ableton uses drag from Finder.')}
        </p>
        {busy && <p role="status" className="px-3 pb-2 text-xs" style={{ color: 'var(--text-soft)' }}>Preparing export…</p>}
        {feedback && <p role={feedback.error ? 'alert' : 'status'} className="px-3 py-2 text-xs leading-relaxed break-words"
          style={{ color: feedback.error ? '#d97070' : 'var(--text-accent)', borderTop: '1px solid var(--border)' }}>{feedback.text}</p>}
      </div>}
    </div>
  );
}
