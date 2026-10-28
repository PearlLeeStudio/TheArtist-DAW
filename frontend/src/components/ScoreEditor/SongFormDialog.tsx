/**
 * SongFormDialog — "New from Song Form": pick a song-form section and how
 * many chords it gets, then generate it after the last used measure.
 *
 * Native <dialog> opened with showModal(), so Esc, focus trapping and the
 * inert page behind it come from the browser. Mount it to open it; it
 * calls onClose once it has closed (Esc, Cancel, or after a successful
 * generate). Closing while a generation runs cancels that generation and
 * takes its placement back off the staff.
 */
import { useEffect, useId, useRef, useState } from 'react';
import { useSongStore } from '../../store/songStore';
import { useGenerationStore } from '../../store/generationStore';
import GenerateProgress from '../RightPanel/GenerateProgress';
import {
  SECTION_GROUPS,
  SECTION_INFO,
  checkChordCount,
  chordCountSummary,
  isSectionType,
  sectionLabel,
  sectionPlacement,
  sectionsInGroup,
} from '../../engine/songForm';
import type { SectionType } from '../../models/types';

const DEFAULT_SECTION: SectionType = 'verse';

const fieldStyle: React.CSSProperties = {
  background: 'var(--btn-bg)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
};

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
};

function barRange(startMeasure: number, bars: number): string {
  return bars === 1
    ? `Bar ${startMeasure + 1}`
    : `Bars ${startMeasure + 1}–${startMeasure + bars}`;
}

interface SongFormDialogProps {
  /** Called once the dialog has closed. */
  onClose: () => void;
  /** Called after the new section's chords landed on the staff. */
  onGenerated: () => void;
}

export default function SongFormDialog({ onClose, onGenerated }: SongFormDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const sectionRef = useRef<HTMLSelectElement>(null);
  const runningRef = useRef(false);
  const id = useId();
  const headingId = `${id}-heading`;
  const sectionId = `${id}-section`;
  const chordsId = `${id}-chords`;
  const hintId = `${id}-hint`;

  const song = useSongStore((s) => s.song);
  const modelKey = useGenerationStore((s) => s.modelKey);
  const phase = useGenerationStore((s) => s.phase);
  const runSectionGenerate = useGenerationStore((s) => s.runSectionGenerate);
  const cancelSectionGenerate = useGenerationStore((s) => s.cancelSectionGenerate);

  const [sectionType, setSectionType] = useState<SectionType>(DEFAULT_SECTION);
  const [chordText, setChordText] = useState(String(SECTION_INFO[DEFAULT_SECTION].defaultChords));
  // Once the user types a count, picking another section keeps it.
  const [chordTyped, setChordTyped] = useState(false);
  const [running, setRunning] = useState(false);
  const [runStart, setRunStart] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelLabel, setModelLabel] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    sectionRef.current?.focus();
  }, []);

  // Friendly model name for the summary; the key shows until (or unless)
  // the model list answers.
  useEffect(() => {
    let alive = true;
    fetch('/api/models/list')
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { models?: Array<{ key: string; label: string }> } | null) => {
        const match = data?.models?.find((m) => m.key === modelKey);
        if (alive && match) setModelLabel(match.label);
      })
      .catch(() => { /* keep showing the key */ });
    return () => { alive = false; };
  }, [modelKey]);

  const check = checkChordCount(chordText);
  // While generating, the song already holds the new section, so a live
  // placement would point past it; show where this run put it instead.
  const startMeasure = running
    ? runStart
    : check.ok ? sectionPlacement(song, check.bars).startMeasure : null;

  const handleSectionChange = (value: string) => {
    if (!isSectionType(value)) return;
    setSectionType(value);
    if (!chordTyped) setChordText(String(SECTION_INFO[value].defaultChords));
  };

  const handleChordInput = (value: string) => {
    setChordText(value);
    setChordTyped(value.trim() !== '');
  };

  const handleGenerate = async () => {
    if (!check.ok || runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setRunStart(sectionPlacement(song, check.bars).startMeasure);
    setError(null);
    const result = await runSectionGenerate({ sectionType, chordCount: check.count });
    runningRef.current = false;
    setRunning(false);
    if (result.status === 'done') {
      onGenerated();
      dialogRef.current?.close();
    } else if (result.status === 'failed') {
      setError(result.message);
    }
  };

  // The one exit path: Esc and close() both end up here via the native
  // 'close' event.
  const handleClose = () => {
    if (runningRef.current) {
      runningRef.current = false;
      cancelSectionGenerate();
    }
    onClose();
  };

  return (
    <dialog
      ref={dialogRef}
      onClose={handleClose}
      aria-labelledby={headingId}
      className="m-auto p-0 backdrop:bg-black/60"
      style={{
        width: 'min(440px, calc(100vw - 32px))',
        background: 'var(--bg-surface)',
        color: 'var(--text-primary)',
        border: '1px solid var(--border)',
        borderTop: '3px solid var(--brand-yellow)',
      }}
    >
      <form
        className="p-5 space-y-4"
        aria-busy={running}
        onSubmit={(e) => {
          e.preventDefault();
          void handleGenerate();
        }}
      >
        <div>
          <h2
            id={headingId}
            className="font-display text-2xl leading-tight"
            style={{ color: 'var(--text-heading)', fontWeight: 700 }}
          >
            Build from Song Form
          </h2>
          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
            The section starts after the last measure that has chords.
          </p>
        </div>

        <div className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2.5">
          <label htmlFor={sectionId} className="text-[10px] uppercase tracking-wide font-semibold" style={labelStyle}>
            Section
          </label>
          <select
            id={sectionId}
            ref={sectionRef}
            value={sectionType}
            onChange={(e) => handleSectionChange(e.target.value)}
            disabled={running}
            className="w-full px-2 py-1.5 text-sm"
            style={fieldStyle}
          >
            {SECTION_GROUPS.map((group) => (
              <optgroup key={group.id} label={group.label}>
                {sectionsInGroup(group.id).map((type) => (
                  <option key={type} value={type}>{sectionLabel(type)}</option>
                ))}
              </optgroup>
            ))}
          </select>

          <label htmlFor={chordsId} className="text-[10px] uppercase tracking-wide font-semibold" style={labelStyle}>
            Chords
          </label>
          <div className="flex items-center gap-2 min-w-0">
            <input
              id={chordsId}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              value={chordText}
              onChange={(e) => handleChordInput(e.target.value)}
              disabled={running}
              aria-invalid={!check.ok}
              aria-describedby={hintId}
              className="tabular w-16 shrink-0 px-2 py-1.5 text-sm text-center"
              style={fieldStyle}
            />
            <span
              id={hintId}
              aria-live="polite"
              className="text-xs"
              style={{ color: check.ok ? 'var(--text-soft)' : 'var(--text-heading)' }}
            >
              {check.ok ? chordCountSummary(check.count) : check.message}
            </span>
          </div>
        </div>

        {/* Read-only: these follow the song settings above the staff and
            the model picked in Input → Generate. */}
        <dl
          className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs px-3 py-2"
          style={{ background: 'var(--btn-bg)', border: '1px solid var(--border)' }}
        >
          <dt style={labelStyle}>Key</dt>
          <dd style={{ color: 'var(--text-heading)' }}>{song.key}</dd>
          <dt style={labelStyle}>Genre</dt>
          <dd style={{ color: 'var(--text-heading)' }}>{song.genre ? song.genre.replace(/_/g, ' ') : 'none'}</dd>
          <dt style={labelStyle}>Model</dt>
          <dd style={{ color: 'var(--text-heading)' }}>{modelLabel ?? modelKey}</dd>
          <dt style={labelStyle}>Placed at</dt>
          <dd style={{ color: 'var(--text-heading)' }}>
            {startMeasure !== null && check.ok ? barRange(startMeasure, check.bars) : '—'}
          </dd>
        </dl>

        {running && (
          <>
            <GenerateProgress phase={phase} />
            {/* The chips are visual; screen readers get the phase line. */}
            <p className="sr-only" role="status">{phase?.label ?? 'Generating'}</p>
          </>
        )}

        {error && (
          <p
            role="alert"
            className="text-xs px-3 py-2"
            style={{
              color: 'var(--text-heading)',
              background: 'var(--btn-bg)',
              borderLeft: '3px solid var(--brand-yellow)',
            }}
          >
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => dialogRef.current?.close()}
            className="px-3 py-1.5 text-xs btn-hover"
            style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
            title={running ? 'Stop generating and close' : 'Close without generating'}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!check.ok || running}
            className="px-4 py-1.5 text-xs font-bold btn-hover"
            style={{
              background: 'var(--text-heading)',
              color: 'var(--bg-primary)',
              // undefined when enabled, so btn-hover's hover dimming applies
              opacity: !check.ok || running ? 0.6 : undefined,
            }}
          >
            {running ? 'Generating…' : 'Generate'}
          </button>
        </div>
      </form>
    </dialog>
  );
}
