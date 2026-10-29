/**
 * SongFormDialog — "New from Song Form", two tabs:
 *
 *   Section    pick a song-form section and how many chords it gets, then
 *              generate it after the last used measure.
 *   Full form  "Complete the form": Muse Spark plans the rest of the form
 *              after the sketch and the author's model writes every
 *              section (planStore); the run shows in the band above the
 *              staff and lands only on Apply there. "Genre default form"
 *              runs the same with the rules planner and no Meta call.
 *
 * Native <dialog> opened with showModal(), so Esc, focus trapping and the
 * inert page behind it come from the browser. Mount it to open it; it
 * calls onClose once it has closed (Esc, Cancel, after a successful
 * generate, or once a plan run started). Closing while a section
 * generation runs cancels that generation and takes its placement back
 * off the staff.
 */
import { useEffect, useId, useRef, useState } from 'react';
import { useSongStore } from '../../store/songStore';
import { useGenerationStore } from '../../store/generationStore';
import { usePlanStore } from '../../store/planStore';
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
import {
  CONTRASTS,
  TARGET_BARS,
  availableTargetBars,
  fetchMetaCapability,
  planBlocker,
  planGenre,
  sketchBars,
  type MetaCapability,
  type PlanContrast,
  type PlannerKind,
  type TargetBars,
} from '../../engine/planClient';
import type { SectionType } from '../../models/types';

const DEFAULT_SECTION: SectionType = 'verse';
/** The length the Full form tab starts from when the sketch leaves room for it. */
const DEFAULT_TARGET_BARS: TargetBars = 32;

type FormTab = 'section' | 'full';
const FORM_TABS: { id: FormTab; label: string }[] = [
  { id: 'section', label: 'Section' },
  { id: 'full', label: 'Full form' },
];

const fieldStyle: React.CSSProperties = {
  background: 'var(--btn-bg)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
};

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
};

const valueStyle: React.CSSProperties = {
  color: 'var(--text-heading)',
};

function barRange(startMeasure: number, bars: number): string {
  return bars === 1
    ? `Bar ${startMeasure + 1}`
    : `Bars ${startMeasure + 1}–${startMeasure + bars}`;
}

interface ChoiceRowProps<T extends string | number | boolean> {
  label: string;
  options: ReadonlyArray<{ value: T; label: string; disabled?: boolean }>;
  value: T;
  onChange: (value: T) => void;
}

/** One labelled row of chips, exactly one of them pressed. */
function ChoiceRow<T extends string | number | boolean>({ label, options, value, onChange }: ChoiceRowProps<T>) {
  return (
    <>
      <span className="text-[10px] uppercase tracking-wide font-semibold" style={labelStyle}>{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const pressed = option.value === value;
          return (
            <button
              key={String(option.value)}
              type="button"
              aria-pressed={pressed}
              disabled={option.disabled}
              onClick={() => onChange(option.value)}
              className="px-2.5 py-1 text-xs btn-hover disabled:opacity-40 disabled:cursor-not-allowed"
              style={pressed
                ? { background: 'var(--text-heading)', color: 'var(--bg-primary)', border: '1px solid var(--text-heading)', fontWeight: 700 }
                : fieldStyle}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </>
  );
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
  const startPlan = usePlanStore((s) => s.startPlan);

  const [tab, setTab] = useState<FormTab>('section');
  const [sectionType, setSectionType] = useState<SectionType>(DEFAULT_SECTION);
  const [chordText, setChordText] = useState(String(SECTION_INFO[DEFAULT_SECTION].defaultChords));
  // Once the user types a count, picking another section keeps it.
  const [chordTyped, setChordTyped] = useState(false);
  const [running, setRunning] = useState(false);
  const [runStart, setRunStart] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelLabel, setModelLabel] = useState<string | null>(null);

  // Full form: the sketch is the song up to its last used measure.
  const sketch = sketchBars(song);
  const targets = availableTargetBars(sketch);
  const [targetBars, setTargetBars] = useState<TargetBars>(
    () => targets.includes(DEFAULT_TARGET_BARS) ? DEFAULT_TARGET_BARS : (targets[0] ?? DEFAULT_TARGET_BARS));
  const [wantOutro, setWantOutro] = useState(true);
  const [contrast, setContrast] = useState<PlanContrast>('medium');
  // null until /api/capabilities answers (or when it does not): a run then
  // shows the server's own answer in the band.
  const [meta, setMeta] = useState<MetaCapability | null>(null);

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

  useEffect(() => {
    const controller = new AbortController();
    fetchMetaCapability(controller.signal)
      .then((capability) => setMeta(capability))
      .catch(() => { /* unknown: the primary button stays enabled and a run reports the server's answer */ });
    return () => controller.abort();
  }, []);

  const check = checkChordCount(chordText);
  // While generating, the song already holds the new section, so a live
  // placement would point past it; show where this run put it instead.
  const startMeasure = running
    ? runStart
    : check.ok ? sectionPlacement(song, check.bars).startMeasure : null;
  const generateDisabled = !check.ok || running;

  const blocker = planBlocker(song);
  const metaOff = meta?.enabled === false;
  const planDisabled = blocker !== null || metaOff;
  const sectionCount = song.sections?.length ?? 0;

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

  // The run shows in the band above the staff; the dialog has nothing left to do.
  const startRun = (planner: PlannerKind) => {
    if (blocker !== null || (planner === 'meta' && metaOff)) return;
    void startPlan({ targetBars, wantOutro, contrast, planner, modelKey });
    dialogRef.current?.close();
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
          if (tab === 'section') void handleGenerate();
          else startRun('meta');
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
            {tab === 'section'
              ? 'The section starts after the last measure that has chords.'
              : 'The rest of the form is planned after the sketch and written section by section; nothing lands until Apply.'}
          </p>
        </div>

        {/* Section / Full form tabs, in the Input sub-tab style. Locked
            while a section generation runs, so its progress stays in view. */}
        <div role="tablist" className="flex" style={{ borderBottom: '1px solid var(--border)' }}>
          {FORM_TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={active}
                disabled={running}
                onClick={() => setTab(t.id)}
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

        {tab === 'section' && (
          <>
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
          <dd style={valueStyle}>{song.key}</dd>
          <dt style={labelStyle}>Genre</dt>
          <dd style={valueStyle}>{song.genre ? song.genre.replace(/_/g, ' ') : 'none'}</dd>
          <dt style={labelStyle}>Model</dt>
          <dd style={valueStyle}>{modelLabel ?? modelKey}</dd>
          <dt style={labelStyle}>Placed at</dt>
          <dd style={valueStyle}>
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
            disabled={generateDisabled}
            className="px-4 py-1.5 text-xs font-bold btn-hover"
            style={{
              background: 'var(--text-heading)',
              color: 'var(--bg-primary)',
              // undefined when enabled, so btn-hover's hover dimming applies
              opacity: generateDisabled ? 0.6 : undefined,
            }}
          >
            {running ? 'Generating…' : 'Generate'}
          </button>
        </div>
          </>
        )}

        {tab === 'full' && (
          <>
            <div className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2.5">
              <ChoiceRow
                label="Length"
                options={TARGET_BARS.map((bars) => ({ value: bars, label: `${bars} bars`, disabled: !targets.includes(bars) }))}
                value={targetBars}
                onChange={setTargetBars}
              />
              <ChoiceRow
                label="Outro"
                options={[{ value: true, label: 'yes' }, { value: false, label: 'no' }]}
                value={wantOutro}
                onChange={setWantOutro}
              />
              <ChoiceRow
                label="Contrast"
                options={CONTRASTS.map((level) => ({ value: level, label: level }))}
                value={contrast}
                onChange={setContrast}
              />
            </div>

            {/* Read-only: the sketch as the planner sees it, and the model
                picked in Input → Generate. */}
            <dl
              className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs px-3 py-2"
              style={{ background: 'var(--btn-bg)', border: '1px solid var(--border)' }}
            >
              <dt style={labelStyle}>Sketch</dt>
              <dd style={valueStyle}>
                {sketch === 0 ? 'empty score' : `${sketch} ${sketch === 1 ? 'bar' : 'bars'}${sectionCount ? `, ${sectionCount} ${sectionCount === 1 ? 'section' : 'sections'}` : ''}`}
                {` → ${targetBars} bars`}
              </dd>
              <dt style={labelStyle}>Key</dt>
              <dd style={valueStyle}>{song.key}</dd>
              <dt style={labelStyle}>Genre</dt>
              <dd style={valueStyle}>{planGenre(song)?.replace(/_/g, ' ') ?? 'none'}</dd>
              <dt style={labelStyle}>Model</dt>
              <dd style={valueStyle}>{modelLabel ?? modelKey}</dd>
            </dl>

            <p className="text-xs" style={{ color: 'var(--text-soft)' }}>
              Muse Spark plans the form; the author&apos;s model ({modelLabel ?? modelKey}) writes every chord.
            </p>

            {(blocker || (meta?.enabled && !meta.configured)) && (
              <p
                role="alert"
                className="text-xs px-3 py-2"
                style={{
                  color: 'var(--text-heading)',
                  background: 'var(--btn-bg)',
                  borderLeft: '3px solid var(--brand-yellow)',
                }}
              >
                {blocker ?? 'No Meta key is configured on this server, so a Muse Spark run will fail; the genre default form still works.'}
              </p>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => startRun('rules')}
                disabled={blocker !== null}
                className="px-3 py-1.5 text-xs btn-hover disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                title="The genre's default form through the song-form rules, written by the author's model; no Meta call, labelled rules"
              >
                Genre default form (own model only, no planner)
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => dialogRef.current?.close()}
                  className="px-3 py-1.5 text-xs btn-hover"
                  style={{ background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  title="Close without planning"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={planDisabled}
                  className="px-4 py-1.5 text-xs font-bold btn-hover"
                  style={{
                    background: 'var(--text-heading)',
                    color: 'var(--bg-primary)',
                    // undefined when enabled, so btn-hover's hover dimming applies
                    opacity: planDisabled ? 0.6 : undefined,
                  }}
                  title={metaOff ? 'THEARTIST_META_ENABLED=0 on the server' : 'Muse Spark plans the form; the run shows above the staff'}
                >
                  {metaOff ? 'Meta features are disabled on this server' : sketch === 0 ? 'Plan a new song' : 'Complete the form'}
                </button>
              </div>
            </div>
          </>
        )}
      </form>
    </dialog>
  );
}
