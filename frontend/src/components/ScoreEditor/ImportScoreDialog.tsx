import { useEffect, useId, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import type { Song } from '../../models/types';
import { STANDARD_KEYS } from '../../engine/keySignatures';
import { SECTION_GROUPS, isSectionType, sectionLabel, sectionsInGroup } from '../../engine/songForm';
import {
  buildScoreImportForEditor,
  checkScoreFile,
  createScoreImportDraft,
  IMPORT_TIME_SIGNATURES,
  MAX_SCORE_IMPORT_BYTES,
  readScoreImportResponse,
  scoreImportRequestBody,
  validateScoreImportForEditor,
} from '../../engine/scoreImport';
import type { ScoreImportDraft, ScoreMime } from '../../engine/scoreImport';

interface ImportScoreDialogProps {
  onClose: () => void;
  onImported: (song: Song) => void;
}

interface SourceFile {
  file: File;
  mimeType: ScoreMime;
  previewUrl: string;
}

const fieldStyle: CSSProperties = {
  background: 'var(--btn-bg)', border: '1px solid var(--border)', color: 'var(--text-primary)',
};
const mutedStyle: CSSProperties = { color: 'var(--text-muted)' };
const buttonStyle: CSSProperties = {
  background: 'var(--btn-bg)', border: '1px solid var(--border)', color: 'var(--text-primary)',
};
const IMPORT_MODE = 'infer_harmony';

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = body.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((item) => item && typeof item === 'object' && typeof item.msg === 'string' ? [item.msg] : []);
      if (messages.length) return messages.join('; ');
    }
  }
  return `Score recognition failed (${status}). Please try again.`;
}

async function fileBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const chunks: string[] = [];
  for (let start = 0; start < bytes.length; start += 0x8000) {
    chunks.push(String.fromCharCode(...bytes.subarray(start, start + 0x8000)));
  }
  return btoa(chunks.join(''));
}

/** Original → recognition → editable review → explicit replacement. The
 *  local File and blob URL only live for this dialog's lifetime. */
export default function ImportScoreDialog({ onClose, onImported }: ImportScoreDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const sourceRef = useRef<SourceFile | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const sequenceRef = useRef(0);
  const runningRef = useRef(false);
  const mountedRef = useRef(true);
  const closedRef = useRef(false);
  const id = useId();
  const [source, setSource] = useState<SourceFile | null>(null);
  const [draft, setDraft] = useState<ScoreImportDraft | null>(null);
  const [reading, setReading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('');

  useEffect(() => {
    mountedRef.current = true;
    sequenceRef.current++;
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
    fileRef.current?.focus();
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
      if (sourceRef.current) URL.revokeObjectURL(sourceRef.current.previewUrl);
    };
  }, []);

  const validation = draft ? validateScoreImportForEditor(draft) : null;
  const canImport = !!draft && !!validation?.valid && !running && !reading;
  const correctionCount = validation ? validation.errors.length + validation.sectionErrors.filter(Boolean).length : 0;
  const importBlockReason = reading ? 'Wait for the file check to finish.' : running ? 'Wait for the score analysis to finish.'
    : !draft ? 'Choose a score to analyze.'
      : !validation?.valid ? `Fix ${correctionCount} highlighted ${correctionCount === 1 ? 'field' : 'fields'} to enable import.`
        : '';
  const firstSectionError = validation?.sectionErrors.findIndex(Boolean) ?? -1;
  const sourceMeters = draft ? [...new Set(draft.measures.flatMap((measure) => measure.timeSignature ? [measure.timeSignature.join('/')] : []))] : [];
  const changesMeter = !!draft && sourceMeters.some((meter) => meter !== draft.timeSignature);
  const focusReviewField = (fieldId: string) => {
    const field = document.getElementById(fieldId);
    const details = field?.closest('details');
    if (details) details.open = true;
    field?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    field?.focus({ preventScroll: true });
  };

  const cancelRecognition = () => {
    sequenceRef.current++;
    controllerRef.current?.abort();
    controllerRef.current = null;
    runningRef.current = false;
    setRunning(false);
    setReading(false);
    setStatus('Analysis cancelled.');
  };

  const handleClose = () => {
    if (closedRef.current) return;
    closedRef.current = true;
    sequenceRef.current++;
    controllerRef.current?.abort();
    runningRef.current = false;
    onClose();
  };

  const chooseFile = async (file: File | undefined) => {
    if (!file) return;
    cancelRecognition();
    const sequence = ++sequenceRef.current;
    if (sourceRef.current) URL.revokeObjectURL(sourceRef.current.previewUrl);
    sourceRef.current = null;
    setSource(null);
    setDraft(null);
    setError(null);
    setStatus('');
    setReading(true);
    try {
      // Reject oversize files before reading any bytes.
      if (file.size > MAX_SCORE_IMPORT_BYTES) throw new Error('Choose a file no larger than 8 MiB.');
      const header = new Uint8Array(await file.slice(0, 16).arrayBuffer());
      if (!mountedRef.current || sequence !== sequenceRef.current) return;
      const checked = checkScoreFile(file, header);
      if (!checked.ok) throw new Error(checked.message);
      if (checked.mimeType !== 'application/pdf') throw new Error('Choose a PDF score. Image import is not available yet.');
      const selected = { file, mimeType: checked.mimeType, previewUrl: URL.createObjectURL(file) };
      sourceRef.current = selected;
      setSource(selected);
      setReading(false);
      void recognize(selected, sequence);
    } catch (caught) {
      if (mountedRef.current && sequence === sequenceRef.current) {
        setError(caught instanceof Error ? caught.message : 'The file could not be read.');
      }
    } finally {
      if (mountedRef.current && sequence === sequenceRef.current) setReading(false);
    }
  };

  const recognize = async (selected: SourceFile, sequence: number) => {
    if (!mountedRef.current || closedRef.current || sequence !== sequenceRef.current || runningRef.current) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    runningRef.current = true;
    setRunning(true);
    setDraft(null);
    setError(null);
    setStatus('Analyzing score…');
    let timedOut = false;
    const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, 100_000);
    try {
      const dataBase64 = await fileBase64(selected.file);
      if (sequence !== sequenceRef.current) return;
      if (controller.signal.aborted) throw new Error('Recognition was interrupted.');
      const response = await fetch('/api/import/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scoreImportRequestBody(selected.file.name, selected.mimeType, dataBase64, IMPORT_MODE, false)),
        signal: controller.signal,
      });
      const body: unknown = await response.json().catch(() => null);
      if (!mountedRef.current || sequence !== sequenceRef.current) return;
      if (!response.ok) throw new Error(errorMessage(body, response.status));
      const recognized = readScoreImportResponse(body, IMPORT_MODE, 'local');
      setDraft(createScoreImportDraft(recognized, selected.file.name));
      setStatus('Ready to review.');
    } catch (caught) {
      if (!mountedRef.current || sequence !== sequenceRef.current) return;
      setStatus('');
      setError(timedOut ? 'Analysis timed out. Try a smaller file.'
        : controller.signal.aborted ? 'Analysis cancelled.'
          : caught instanceof Error ? caught.message : 'The score could not be analyzed. Try again.');
    } finally {
      window.clearTimeout(timer);
      if (mountedRef.current && sequence === sequenceRef.current) {
        runningRef.current = false;
        controllerRef.current = null;
        setRunning(false);
      }
    }
  };

  const retryAnalysis = () => {
    const selected = sourceRef.current;
    if (!selected || runningRef.current || reading) return;
    void recognize(selected, ++sequenceRef.current);
  };

  const edit = (update: (current: ScoreImportDraft) => ScoreImportDraft) => {
    setDraft((current) => current ? update(current) : current);
  };

  const apply = () => {
    if (!canImport || !draft) return;
    try {
      const imported = buildScoreImportForEditor(draft);
      onImported(imported);
      dialogRef.current?.close();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The reviewed score could not be imported.');
    }
  };

  return (
    <dialog
      ref={dialogRef}
      onClose={handleClose}
      aria-labelledby={`${id}-heading`}
      className="m-auto p-0 backdrop:bg-black/60"
      style={{ width: 'min(1040px, calc(100vw - 24px))', maxHeight: 'calc(100dvh - 24px)', overflow: 'hidden', background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderTop: '3px solid var(--brand-yellow)' }}
    >
      <form className="flex min-h-0 flex-col" style={{ maxHeight: 'calc(100dvh - 28px)' }} onSubmit={(e) => { e.preventDefault(); apply(); }} onKeyDown={(e) => { if (e.key === 'Enter' && e.target instanceof HTMLInputElement && e.target.type !== 'file') e.preventDefault(); }}>
        <header className="flex shrink-0 items-start justify-between gap-4 px-5 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <h2 id={`${id}-heading`} className="font-display text-2xl font-bold" style={{ color: 'var(--text-heading)' }}>Import Score</h2>
            <p className="mt-1 text-xs" style={mutedStyle}>Printed chords stay as written; passages without chords are analyzed from the notes.</p>
          </div>
          <button type="button" className="shrink-0 px-3 py-1.5 text-xs btn-hover" style={buttonStyle} onClick={() => dialogRef.current?.close()}>Close</button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <label className="flex min-w-0 flex-col gap-1 text-xs" style={mutedStyle}>
              PDF score · up to 8 MiB
              <input ref={fileRef} type="file" accept=".pdf,application/pdf" className="max-w-full text-sm" onChange={(e) => { void chooseFile(e.target.files?.[0]); e.target.value = ''; }} />
            </label>
            <div className="flex gap-2">
              {(reading || running) && <button type="button" className="px-3 py-2 text-xs btn-hover" style={buttonStyle} onClick={cancelRecognition}>Cancel</button>}
              {source && !draft && !running && !reading && <button type="button" onClick={retryAnalysis} className="px-3 py-2 text-xs btn-hover" style={buttonStyle}>Try again</button>}
            </div>
          </div>

          {(reading || status) && <p role="status" className="text-sm" style={mutedStyle}>{reading ? 'Checking the file…' : status}</p>}
          {(reading || running) && <progress role="progressbar" aria-label={reading ? 'Checking score file' : 'Analyzing score'} className="h-2 w-full" style={{ accentColor: 'var(--brand-yellow)' }} />}

          {source && (
            <div className={draft ? 'grid grid-cols-1 items-start gap-5 md:grid-cols-[minmax(220px,0.8fr)_minmax(0,1.2fr)]' : ''}>
              <details open className="min-w-0 md:sticky md:top-0" style={{ border: '1px solid var(--border)' }}>
                <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Original score</summary>
                <div className="space-y-2 px-3 pb-3">
                  <p className="break-words text-xs" style={mutedStyle}>{source.file.name}</p>
                  {source.mimeType === 'application/pdf' ? (
                    <object data={source.previewUrl} type="application/pdf" aria-label="Original PDF preview" className="w-full" style={{ height: 360, background: '#ffffff' }}>
                      <p className="p-3 text-sm" style={mutedStyle}>The browser cannot display this PDF here. Open the original to review it.</p>
                    </object>
                  ) : (
                    <img src={source.previewUrl} alt={`Original score: ${source.file.name}`} className="w-full object-contain" style={{ maxHeight: 430, background: '#ffffff' }} />
                  )}
                  <a href={source.previewUrl} target="_blank" rel="noreferrer" className="text-xs underline" style={{ color: 'var(--text-heading)' }}>Open original in a new tab</a>
                </div>
              </details>

              {draft && validation && (
                <div className="min-w-0 space-y-4">
                  <div className="space-y-2">
                    <h3 className="font-display text-xl font-semibold" style={{ color: 'var(--text-heading)' }}>Review score</h3>
                    <p className="text-xs" style={mutedStyle}>Check the key and meter. Chords can be reviewed in the score view.</p>
                    {changesMeter && <p className="text-xs" style={mutedStyle}>The original uses {sourceMeters.join(', ')}. The editor uses {draft.timeSignature || 'one chosen meter'} throughout.</p>}
                  </div>

                  <div id={`${id}-score-fields`} tabIndex={-1} className="grid grid-cols-2 gap-3">
                    <label className="col-span-2 flex flex-col gap-1 text-xs">Title<input value={draft.title} maxLength={120} onChange={(e) => edit((d) => ({ ...d, title: e.target.value }))} className="w-full px-2 py-1.5 text-sm" style={fieldStyle} /></label>
                    <label className="flex min-w-0 flex-col gap-1 text-xs">Key<input list={`${id}-keys`} value={draft.key} placeholder="Choose key" onChange={(e) => edit((d) => ({ ...d, key: e.target.value }))} className="min-w-0 w-full px-2 py-1.5 text-sm" style={fieldStyle} /></label>
                    <datalist id={`${id}-keys`}>{STANDARD_KEYS.map((key) => <option key={key} value={key} />)}</datalist>
                    <label className="flex min-w-0 flex-col gap-1 text-xs">Time signature<select value={draft.timeSignature} onChange={(e) => edit((d) => ({ ...d, timeSignature: e.target.value }))} className="w-full px-2 py-1.5 text-sm" style={fieldStyle}>
                      <option value="">Choose meter</option>
                      {draft.timeSignature && !(IMPORT_TIME_SIGNATURES as readonly string[]).includes(draft.timeSignature) && <option value={draft.timeSignature}>{draft.timeSignature} — review</option>}
                      {IMPORT_TIME_SIGNATURES.map((meter) => <option key={meter} value={meter}>{meter}</option>)}
                    </select></label>
                    <label className="col-span-2 flex items-center gap-2 text-xs">Playback tempo<input type="text" inputMode="numeric" value={draft.bpm} onChange={(e) => edit((d) => ({ ...d, bpm: e.target.value }))} className="w-16 px-2 py-1.5 text-center text-sm" style={fieldStyle} /> BPM <span style={mutedStyle}>(set here, not read from the score)</span></label>
                  </div>
                  {validation.errors.length > 0 && <ul className="list-disc space-y-1 pl-4 text-xs" aria-label="Score fields to correct">{validation.errors.map((message) => <li key={message}>{message}</li>)}</ul>}

                  <details style={{ border: '1px solid var(--border)' }}>
                    <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Song form · {draft.sections.length} sections</summary>
                    <div className="space-y-3 px-3 pb-3">
                      <p className="text-xs" style={mutedStyle}>Inferred sections are suggestions, not labels found on the score. Editing them keeps that origin visible.</p>
                      {draft.sections.map((section, index) => (
                        <div key={index} id={`${id}-section-${index}`} tabIndex={-1} className="space-y-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold">{section.origin === 'inferred' ? 'Inferred — verify' : section.origin === 'explicit' ? 'Written on score' : 'Added manually'}</span>
                            <button type="button" onClick={() => edit((d) => ({ ...d, sections: d.sections.filter((_, i) => i !== index) }))} className="px-2 py-1 text-xs btn-hover" style={buttonStyle} aria-label={`Remove section ${index + 1}`}>Remove</button>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <label className="flex min-w-0 flex-col gap-1 text-xs">Name<input value={section.label} maxLength={80} onChange={(e) => edit((d) => ({ ...d, sections: d.sections.map((s, i) => i === index ? { ...s, label: e.target.value } : s) }))} className="w-full min-w-0 px-2 py-1.5 text-sm" style={fieldStyle} /></label>
                            <label className="flex min-w-0 flex-col gap-1 text-xs">Type<select value={section.type ?? ''} onChange={(e) => { const value = e.target.value; edit((d) => ({ ...d, sections: d.sections.map((s, i) => i === index ? { ...s, type: isSectionType(value) ? value : null } : s) })); }} className="min-w-0 w-full px-2 py-1.5 text-sm" style={fieldStyle}>
                              <option value="">Unknown</option>
                              {SECTION_GROUPS.map((group) => <optgroup key={group.id} label={group.label}>{sectionsInGroup(group.id).map((type) => <option key={type} value={type}>{sectionLabel(type)}</option>)}</optgroup>)}
                            </select></label>
                            <label className="flex items-center gap-2 text-xs">From bar<input type="text" inputMode="numeric" value={section.startBar} onChange={(e) => edit((d) => ({ ...d, sections: d.sections.map((s, i) => i === index ? { ...s, startBar: e.target.value } : s) }))} className="w-14 min-w-0 px-2 py-1.5 text-sm" style={fieldStyle} /></label>
                            <label className="flex items-center gap-2 text-xs">To bar<input type="text" inputMode="numeric" value={section.endBar} onChange={(e) => edit((d) => ({ ...d, sections: d.sections.map((s, i) => i === index ? { ...s, endBar: e.target.value } : s) }))} className="w-14 min-w-0 px-2 py-1.5 text-sm" style={fieldStyle} /></label>
                          </div>
                          {section.note && <p className="text-xs" style={mutedStyle}>{section.note}</p>}
                          {validation.sectionErrors[index] && <p className="text-xs" role="status">{validation.sectionErrors[index]}</p>}
                        </div>
                      ))}
                      <button type="button" disabled={draft.sections.length >= 64} onClick={() => edit((d) => ({ ...d, sections: [...d.sections, { type: null, label: 'Section', startBar: '1', endBar: String(d.measures.length || 1), origin: 'manual', note: '' }] }))} className="px-3 py-1.5 text-xs btn-hover" style={buttonStyle}>Add section</button>
                    </div>
                  </details>

                </div>
              )}
            </div>
          )}
        </div>

        <footer className="flex shrink-0 flex-col items-stretch gap-3 px-5 py-3 sm:flex-row sm:items-end" style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
          <div className="min-w-0 flex-1 text-xs" style={mutedStyle}>
            <p>Import replaces the current score. You can undo the import in the editor.</p>
            {importBlockReason && <p id={`${id}-import-block`} role="status" className="mt-1">{importBlockReason}</p>}
            {(error || (validation && !validation.valid)) && <div className="mt-1 max-h-20 overflow-y-auto pr-1">
              {error && <p role="alert" className="border-l-2 px-2 py-1" style={{ background: 'var(--btn-bg)', borderColor: 'var(--brand-yellow)', color: 'var(--text-primary)' }}>{error}</p>}
              {validation && !validation.valid && <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {validation.errors.length > 0 && <button type="button" className="text-left underline" onClick={() => focusReviewField(`${id}-score-fields`)}>{validation.errors.join(' ')}</button>}
              {firstSectionError >= 0 && <button type="button" className="text-left underline" onClick={() => focusReviewField(`${id}-section-${firstSectionError}`)}>Fix section {firstSectionError + 1}: {validation.sectionErrors[firstSectionError]}</button>}
              </div>}
            </div>}
          </div>
          <button type="submit" disabled={!canImport} aria-describedby={importBlockReason ? `${id}-import-block` : undefined} className="shrink-0 whitespace-nowrap px-4 py-2 text-xs font-bold btn-hover" style={{ background: 'var(--brand-yellow)', color: '#1a1a1a', opacity: !canImport ? 0.45 : undefined }}>Import reviewed score</button>
        </footer>
      </form>
    </dialog>
  );
}
