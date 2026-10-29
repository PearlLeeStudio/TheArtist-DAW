import { useEffect, useRef, useMemo, useCallback, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Renderer, Stave } from 'vexflow';
import { useSongStore, isSlotInList } from '../../store/songStore';
import { getChordDisplayParts } from '../../engine/chordDisplay';
import { sectionColor, sectionDisplayLabel } from '../../engine/songForm';
import type { Measure, SlotAddress, SongSection } from '../../models/types';
import { scoreMeasureLayout } from '../../engine/scoreLayout';
import { keySignatureFor } from '../../engine/keySignatures';
import ImportedMeasureReview from './ImportedMeasureReview';
import { hasEmptySlot, isExplicitNoChord, needsSourceReview } from './importedBars';

const MEASURES_PER_ROW = 4;
const CHORD_AREA_HEIGHT = 8;
const STAVE_HEIGHT = 170;
const PADDING_Y = 10;
const PADDING_X = 10;
const ADD_BTN_HEIGHT = 50;
// Song-form section label baseline, below the stave's y. VexFlow puts the
// top stave line 40px below y and chord symbols sit on the middle line, so
// this band holds only the label (and the clef, which the label clears by
// starting at contentX).
const SECTION_LABEL_DY = 16;
/** Longest section name drawn on the score; its tooltip has the full name. */
const SECTION_LABEL_MAX_CHARS = 22;
/** Baseline of an imported bar's Review/Unresolved marker, below the Roman numerals. */
const IMPORT_MARKER_DY = 127;

interface StaveLayout {
  x: number;
  y: number;
  width: number;
  isFirstInRow: boolean;
  contentX: number;
  midLineY: number; // actual Y of the 3rd (middle) stave line — set after VexFlow render
}

/** Keyboard activation (Enter or Space) for SVG text that acts as a button. */
function onEnterOrSpace(action: () => void) {
  return (event: KeyboardEvent<SVGTextElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    action();
  };
}

/** The bar's first empty chord slot; slot 0 when both hold chords. */
function firstEmptySlot(measure: Measure): 0 | 1 {
  return measure.chords[0] === null ? 0 : measure.chords[1] === null ? 1 : 0;
}

function sectionOriginHint(origin: SongSection['origin']): string {
  if (origin === 'inferred') return 'Suggested from the score';
  if (origin === 'explicit') return 'Label read from the score';
  return 'Click to select this region';
}

interface ImportPlaceholderProps {
  /** Left edge and width of the box the label is centred in. */
  x: number;
  width: number;
  midLineY: number;
  noChord: boolean;
}

/** Stands in for a missing imported chord: "Unresolved" in one slot, or "N.C."
 *  across a bar the source marked N.C. */
function ImportPlaceholder({ x, width, midLineY, noChord }: ImportPlaceholderProps) {
  return (
    <>
      <rect
        x={x + width * .05}
        y={midLineY - 12}
        width={width * .9}
        height={24}
        rx={3}
        fill="var(--bg-primary)"
        opacity={.85}
        className="pointer-events-none"
      />
      <text
        x={x + width / 2}
        y={midLineY}
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--text-soft)"
        fontSize={noChord ? 14 : 10}
        fontFamily="system-ui, sans-serif"
        className="pointer-events-none"
      >
        {noChord ? 'N.C.' : 'Unresolved'}
      </text>
    </>
  );
}

export default function Staff() {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const song = useSongStore((s) => s.song);
  const selectedSlots = useSongStore((s) => s.selectedSlots);
  const playbackPosition = useSongStore((s) => s.playbackPosition);
  const selectSlot = useSongStore((s) => s.selectSlot);
  const selectSlotRange = useSongStore((s) => s.selectSlotRange);
  const addMeasures = useSongStore((s) => s.addMeasures);

  const [dragStart, setDragStart] = useState<SlotAddress | null>(null);
  const [containerWidth, setContainerWidth] = useState(960);
  const [theme, setTheme] = useState(document.documentElement.className);

  // Watch for theme class changes
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setTheme(document.documentElement.className);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  // Track container width
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    setContainerWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const [staveLayouts, setStaveLayouts] = useState<StaveLayout[]>([]);

  const baseLayouts = useMemo((): Omit<StaveLayout, 'midLineY'>[] => {
    return Array.from({ length: song.measures.length }, (_, i) => scoreMeasureLayout(i, containerWidth));
  }, [song.measures.length, containerWidth]);

  const rows = Math.ceil(song.measures.length / MEASURES_PER_ROW);
  const totalWidth = containerWidth;
  const totalHeight = rows * STAVE_HEIGHT + PADDING_Y * 2 + CHORD_AREA_HEIGHT + ADD_BTN_HEIGHT;

  // Drag handlers
  const handleSlotMouseDown = useCallback((slot: SlotAddress) => {
    setDragStart(slot);
    selectSlot(slot);
  }, [selectSlot]);

  const handleSlotMouseEnter = useCallback((slot: SlotAddress) => {
    if (dragStart) {
      selectSlotRange(dragStart, slot);
    }
  }, [dragStart, selectSlotRange]);

  const handleMouseUp = useCallback(() => {
    setDragStart(null);
  }, []);

  useEffect(() => {
    window.addEventListener('mouseup', handleMouseUp);
    return () => window.removeEventListener('mouseup', handleMouseUp);
  }, [handleMouseUp]);

  // Render VexFlow
  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    container.innerHTML = '';

    const renderer = new Renderer(container, Renderer.Backends.SVG);
    renderer.resize(totalWidth, totalHeight);
    const context = renderer.getContext();
    const keySig = keySignatureFor(song.key);
    if (!keySig) return;

    // Get stave color from CSS variable
    const staveColor = getComputedStyle(document.documentElement).getPropertyValue('--stave-color').trim() || '#000';
    context.setStrokeStyle(staveColor);
    context.setFillStyle(staveColor);

    const measured: StaveLayout[] = [];
    for (let i = 0; i < song.measures.length; i++) {
      const bl = baseLayouts[i];
      const stave = new Stave(bl.x, bl.y, bl.width);

      if (bl.isFirstInRow) {
        stave.addClef('treble');
        stave.addKeySignature(keySig);
        if (i === 0) {
          stave.addTimeSignature(`${song.timeSignature[0]}/${song.timeSignature[1]}`);
        }
      }

      stave.setContext(context).draw();

      // Get the actual Y of the middle (3rd) stave line
      const midY = stave.getYForLine(2);
      measured.push({ ...bl, midLineY: midY });
    }
    const frame = requestAnimationFrame(() => setStaveLayouts(measured));
    return () => cancelAnimationFrame(frame);
  }, [song.measures.length, song.key, song.timeSignature, baseLayouts, totalWidth, totalHeight, theme]);

  // Position for add button
  const lastRow = rows - 1;
  const addBtnY = PADDING_Y + CHORD_AREA_HEIGHT + (lastRow + 1) * STAVE_HEIGHT + 8;

  if (!keySignatureFor(song.key)) {
    return (
      <div ref={wrapperRef} role="alert" className="p-3 text-sm">
        Unsupported key signature: {song.key}. Choose a standard key in the Key control to display the score.
      </div>
    );
  }

  return (
    <>
    <ImportedMeasureReview song={song} selectedSlots={selectedSlots} />
    <div ref={wrapperRef} className="relative select-none w-full">
      {/* SVG overlay for chord labels + click/drag zones + add button */}
      <svg
        width={totalWidth}
        height={totalHeight}
        className="absolute top-0 left-0 pointer-events-none"
        style={{ zIndex: 1 }}
        onContextMenu={(e) => {
          e.preventDefault();
          selectSlot(null);
        }}
      >
        {/* Low-contrast form bands remain separate from selection and the playhead. */}
        {(song.sections ?? []).flatMap((section) =>
          Array.from({ length: section.length }, (_, offset) => {
            const layout = staveLayouts[section.startMeasure + offset];
            if (!layout) return null;
            return <rect key={`${section.id}-${offset}`} x={layout.contentX} y={layout.y - CHORD_AREA_HEIGHT}
              width={layout.x + layout.width - layout.contentX} height={STAVE_HEIGHT - 10}
              fill={sectionColor(section.type)} fillOpacity={0.09} className="pointer-events-none" />;
          }),
        )}
        {song.measures.map((measure, mi) => {
          const layout = staveLayouts[mi];
          if (!layout) return null;

          const contentWidth = layout.x + layout.width - layout.contentX;
          const slotWidth = contentWidth / 2;
          const importSource = song.importSource?.measures?.[mi];
          const explicitNoChord = !!importSource && isExplicitNoChord(measure, importSource);

          return ([0, 1] as const).map((si) => {
            const chord = measure.chords[si];
            const slotX = layout.contentX + si * slotWidth;
            const slot: SlotAddress = { measureIndex: mi, slotIndex: si };
            const isSelected = isSlotInList(slot, selectedSlots);
            const isPlaying = playbackPosition?.measureIndex === mi && playbackPosition?.slotIndex === si;

            // Full stave height for click/highlight zone
            const zoneY = layout.y - CHORD_AREA_HEIGHT;
            const zoneHeight = STAVE_HEIGHT;

            return (
              <g key={`${mi}-${si}`}>
                {/* Click/drag zone covering chord area + entire stave */}
                <rect
                  x={slotX}
                  y={zoneY}
                  width={slotWidth}
                  height={zoneHeight}
                  fill={
                    isPlaying ? 'var(--playback-bg)' :
                    isSelected ? 'var(--selection-bg)' :
                    'transparent'
                  }
                  className="pointer-events-auto cursor-pointer"
                  onMouseDown={() => handleSlotMouseDown(slot)}
                  onMouseEnter={() => handleSlotMouseEnter(slot)}
                />

                {/* Top indicator bar — playback wins over selection so the
                    cursor is always obvious mid-play. */}
                {(isSelected || isPlaying) && (
                  <rect
                    x={slotX}
                    y={zoneY}
                    width={slotWidth}
                    height={2}
                    fill={isPlaying ? 'var(--playback-bar)' : 'var(--selection-bar)'}
                    rx={1}
                  />
                )}

                {/* An N.C. bar gets one label across the whole bar, drawn with slot 0. */}
                {!chord && importSource && (!explicitNoChord || si === 0) && (
                  <ImportPlaceholder
                    x={explicitNoChord ? layout.contentX : slotX}
                    width={explicitNoChord ? contentWidth : slotWidth}
                    midLineY={layout.midLineY}
                    noChord={explicitNoChord}
                  />
                )}

                {chord && (() => {
                  const cx = slotX + slotWidth / 2;
                  const chordY = layout.midLineY; // exact 3rd line from VexFlow
                  const parts = getChordDisplayParts(chord);
                  // Estimate root width for positioning sup/sub
                  const rootSize = 20;
                  const annoSize = 11;
                  const rootW = parts.root.length * rootSize * 0.6;
                  return (
                    <>
                      <rect
                        x={cx - slotWidth * 0.45}
                        y={chordY - 16}
                        width={slotWidth * 0.9}
                        height={32}
                        rx={4}
                        fill="var(--bg-primary)"
                        opacity={0.85}
                        className="pointer-events-none"
                      />
                      {/* Root — large */}
                      <text
                        x={cx - (parts.sup || parts.sub ? rootW * 0.15 : 0)}
                        y={chordY}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill="var(--chord-color)"
                        fontSize={rootSize}
                        fontWeight="bold"
                        fontFamily="system-ui, sans-serif"
                        className="pointer-events-none"
                      >
                        {parts.root}
                      </text>
                      {/* Superscript — extension (top-right) */}
                      {parts.sup && (
                        <text
                          x={cx + rootW * 0.35}
                          y={chordY - 8}
                          textAnchor="start"
                          dominantBaseline="central"
                          fill="var(--chord-color)"
                          fontSize={annoSize}
                          fontFamily="system-ui, sans-serif"
                          className="pointer-events-none"
                        >
                          {parts.sup}
                        </text>
                      )}
                      {/* Subscript — base modifier (bottom-right) */}
                      {parts.sub && (
                        <text
                          x={cx + rootW * 0.35}
                          y={chordY + 8}
                          textAnchor="start"
                          dominantBaseline="central"
                          fill="var(--chord-color)"
                          fontSize={annoSize}
                          fontFamily="system-ui, sans-serif"
                          className="pointer-events-none"
                        >
                          {parts.sub}
                        </text>
                      )}
                      {/* Bass note — slash chord */}
                      {parts.bass && (
                        <text
                          x={cx + rootW * 0.35 + (parts.sup.length || parts.sub.length) * annoSize * 0.55 + 2}
                          y={chordY}
                          textAnchor="start"
                          dominantBaseline="central"
                          fill="var(--chord-color)"
                          fontSize={rootSize * 0.8}
                          fontWeight="bold"
                          fontFamily="system-ui, sans-serif"
                          className="pointer-events-none"
                        >
                          /{parts.bass}
                        </text>
                      )}
                      {/* Roman numeral — below stave. Theory analysis,
                          read as secondary information, so it sits in
                          the muted-grey tier rather than fighting the
                          chord symbol above for attention. */}
                      {chord.romanNumeral && (
                        <text
                          x={cx}
                          y={layout.y + 100}
                          textAnchor="middle"
                          dominantBaseline="central"
                          fill="var(--text-soft)"
                          fontSize={18}
                          fontWeight="bold"
                          fontFamily="system-ui, sans-serif"
                          className="pointer-events-none"
                        >
                          {chord.romanNumeral}
                        </text>
                      )}
                    </>
                  );
                })()}
              </g>
            );
          });
        })}

        {/* Imported uncertainty is visible on the score, without blocking edits. */}
        {song.importSource?.measures?.map((source, index) => {
          const measure = song.measures[index];
          const layout = staveLayouts[index];
          if (!measure || !layout || isExplicitNoChord(measure, source)) return null;
          const pending = hasEmptySlot(measure);
          if (!pending && !needsSourceReview(source)) return null;
          const select = () => selectSlot({ measureIndex: index, slotIndex: firstEmptySlot(measure) });
          return (
            <text key={`import-review-${index}`} x={layout.x + layout.width - 8} y={layout.y + IMPORT_MARKER_DY}
              textAnchor="end" fill="var(--text-soft)" fontSize={10} fontWeight={600}
              fontFamily="system-ui, sans-serif" className="pointer-events-auto cursor-pointer"
              role="button" tabIndex={0} aria-label={`Review imported bar ${index + 1}${pending ? ', unresolved chord slots' : ''}`}
              onClick={select} onKeyDown={onEnterOrSpace(select)}>
              <title>{source.editorReview || (pending ? 'Choose the unresolved chord slots in the editor.' : 'Compare the imported harmony with its source.')}</title>
              {pending ? 'Unresolved' : 'Review'}
            </text>
          );
        })}

        {/* Labels select the whole region; drag zones still select individual chords. */}
        {(song.sections ?? []).map((section) => {
          const layout = staveLayouts[section.startMeasure];
          if (!layout) return null;
          const label = sectionDisplayLabel(section);
          const selectSection = () => selectSlotRange(
            { measureIndex: section.startMeasure, slotIndex: 0 },
            { measureIndex: section.startMeasure + section.length - 1, slotIndex: 1 },
          );
          return (
            <text
              key={section.id}
              x={layout.contentX}
              y={layout.y + SECTION_LABEL_DY}
              fill="var(--text-soft)"
              fontSize={11}
              fontWeight={700}
              letterSpacing="0.08em"
              fontFamily="system-ui, sans-serif"
              className="pointer-events-auto cursor-pointer"
              role="button"
              tabIndex={0}
              aria-label={`Select ${label}, bars ${section.startMeasure + 1} to ${section.startMeasure + section.length}`}
              onClick={selectSection}
              onKeyDown={onEnterOrSpace(selectSection)}
            >
              <title>{label} · {sectionOriginHint(section.origin)}</title>
              {label.slice(0, SECTION_LABEL_MAX_CHARS).toUpperCase()}{section.origin === 'inferred' ? ' ?' : ''}
            </text>
          );
        })}

        {/* Add measures button inside the score area */}
        <g className="pointer-events-auto cursor-pointer" onClick={() => addMeasures()}>
          <rect
            x={PADDING_X}
            y={addBtnY}
            width={totalWidth - PADDING_X * 2}
            height={36}
            rx={6}
            fill="none"
            stroke="var(--border)"
            strokeWidth={1.5}
            strokeDasharray="6 4"
          />
          <text
            x={totalWidth / 2}
            y={addBtnY + 22}
            textAnchor="middle"
            fill="var(--text-muted)"
            fontSize={13}
            fontFamily="system-ui, sans-serif"
          >
            + Add 4 Measures
          </text>
        </g>
      </svg>

      {/* VexFlow renders here */}
      <div ref={containerRef} className="w-full vf-staff" />
    </div>
    </>
  );
}
