import { useEffect, useId, useRef, useState } from 'react';
import { useSongStore } from '../../store/songStore';
import { checkSectionRanges, isSectionType, SECTION_TYPES, sectionLabel } from '../../engine/songForm';
import type { SongSection } from '../../models/types';

const fieldStyle = { background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' };

export default function SectionsDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  const song = useSongStore((s) => s.song);
  const setSections = useSongStore((s) => s.setSections);
  const [sections, updateSections] = useState<SongSection[]>(() => structuredClone(song.sections ?? []));
  const error = checkSectionRanges(sections, song.measures.length);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const change = (id: string, patch: Partial<SongSection>) => {
    updateSections((items) => items.map((s) => s.id === id ? { ...s, ...patch, origin: 'manual' } : s));
  };
  const add = () => {
    const occupied = [...sections].sort((a, b) => a.startMeasure - b.startMeasure);
    let start = 0;
    for (const s of occupied) {
      if (s.startMeasure > start) break;
      start = Math.max(start, s.startMeasure + s.length);
    }
    if (start >= song.measures.length) return;
    updateSections((items) => [...items, {
      id: crypto.randomUUID(), type: null, label: '', startMeasure: start, length: 1, origin: 'manual',
    }]);
  };
  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby={heading} className="m-auto p-0 backdrop:bg-black/60"
      style={{ width: 'min(720px, calc(100vw - 32px))', maxHeight: 'calc(100dvh - 32px)', background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
      <form className="p-5 space-y-4" onSubmit={(e) => {
        e.preventDefault();
        if (!setSections(sections)) dialog.current?.close();
      }}>
        <h2 id={heading} className="font-display text-2xl" style={{ color: 'var(--text-heading)' }}>Song Form</h2>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Name the regions you know. Leave the type unassigned when the score does not identify its role.
        </p>
        <div className="space-y-3">
          {sections.map((s, i) => (
            <fieldset key={s.id} className="p-3 space-y-2" style={{ border: '1px solid var(--border)' }}>
              <legend className="text-xs px-1">Region {i + 1}{s.origin === 'inferred' ? ' · suggested' : ''}</legend>
              <div className="flex flex-wrap gap-2 items-end">
                <label className="text-xs flex-1 min-w-28">Name
                  <input aria-label={`Region ${i + 1} name`} value={s.label ?? ''} placeholder={sectionLabel(s.type)} maxLength={80}
                    onChange={(e) => change(s.id, { label: e.target.value })} className="block w-full p-2 mt-1" style={fieldStyle} />
                </label>
                <label className="text-xs">Type
                  <select aria-label={`Region ${i + 1} type`} value={s.type ?? ''} onChange={(e) => change(s.id, { type: isSectionType(e.target.value) ? e.target.value : null })}
                    className="block p-2 mt-1" style={fieldStyle}>
                    <option value="">Unassigned</option>
                    {SECTION_TYPES.map((type) => <option key={type} value={type}>{sectionLabel(type)}</option>)}
                  </select>
                </label>
                <label className="text-xs">From bar
                  <input type="number" min={1} max={song.measures.length} value={s.startMeasure + 1}
                    onChange={(e) => change(s.id, { startMeasure: Number(e.target.value) - 1 })} className="block w-20 p-2 mt-1" style={fieldStyle} />
                </label>
                <label className="text-xs">To bar
                  <input type="number" min={1} max={song.measures.length} value={s.startMeasure + s.length}
                    onChange={(e) => change(s.id, { length: Number(e.target.value) - s.startMeasure })} className="block w-20 p-2 mt-1" style={fieldStyle} />
                </label>
                <button type="button" className="text-xs px-2 py-2 btn-hover" style={fieldStyle}
                  onClick={() => updateSections((items) => items.filter((item) => item.id !== s.id))}>Remove</button>
              </div>
            </fieldset>
          ))}
        </div>
        <button type="button" onClick={add} className="px-3 py-2 text-xs btn-hover" style={fieldStyle}>Add region</button>
        {error && <p role="alert" className="text-sm" style={{ color: 'var(--text-heading)' }}>{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => dialog.current?.close()} className="px-3 py-2 text-xs btn-hover" style={fieldStyle}>Cancel</button>
          <button type="submit" disabled={!!error} className="px-4 py-2 text-xs font-bold btn-hover disabled:opacity-50"
            style={{ background: 'var(--brand-yellow)', color: '#1a1a1a' }}>Apply sections</button>
        </div>
      </form>
    </dialog>
  );
}
