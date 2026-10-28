import { useEffect, useRef, useMemo, useState } from 'react';
import { Renderer, Stave } from 'vexflow';
import { getChordDisplayParts } from '../../engine/chordDisplay';
import { scoreMeasureLayout, SCORE_MEASURES_PER_ROW, SCORE_ROW_HEIGHT, SCORE_TOP } from '../../engine/scoreLayout';
import type { Song } from '../../models/types';

const KEY_SIG_MAP: Record<string, string> = {
  'C major': 'C', 'G major': 'G', 'D major': 'D', 'A major': 'A',
  'E major': 'E', 'B major': 'B', 'F# major': 'F#', 'Gb major': 'Gb',
  'Db major': 'Db', 'Ab major': 'Ab', 'Eb major': 'Eb', 'Bb major': 'Bb',
  'F major': 'F',
  'A minor': 'Am', 'E minor': 'Em', 'B minor': 'Bm', 'F# minor': 'F#m',
  'C# minor': 'C#m', 'G# minor': 'G#m', 'Eb minor': 'Ebm', 'Bb minor': 'Bbm',
  'F minor': 'Fm', 'C minor': 'Cm', 'G minor': 'Gm', 'D minor': 'Dm',
};

interface StaveLayout {
  x: number;
  y: number;
  width: number;
  isFirstInRow: boolean;
  contentX: number;
  midLineY: number;
}

interface SessionStaffProps {
  song: Song;
}

export default function SessionStaff({ song }: SessionStaffProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(960);
  const [theme, setTheme] = useState(document.documentElement.className);
  const [staveLayouts, setStaveLayouts] = useState<StaveLayout[]>([]);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setTheme(document.documentElement.className);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

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

  const baseLayouts = useMemo((): Omit<StaveLayout, 'midLineY'>[] => {
    return Array.from({ length: song.measures.length }, (_, i) => scoreMeasureLayout(i, containerWidth));
  }, [song.measures.length, containerWidth]);

  const rows = Math.ceil(song.measures.length / SCORE_MEASURES_PER_ROW);
  const totalWidth = containerWidth;
  const totalHeight = rows * SCORE_ROW_HEIGHT + SCORE_TOP + 10;

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    container.innerHTML = '';

    const renderer = new Renderer(container, Renderer.Backends.SVG);
    renderer.resize(totalWidth, totalHeight);
    const context = renderer.getContext();
    const keySig = KEY_SIG_MAP[song.key] || 'C';

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

      const midY = stave.getYForLine(2);
      measured.push({ ...bl, midLineY: midY });
    }
    setStaveLayouts(measured);
  }, [song.measures.length, song.key, song.timeSignature, baseLayouts, totalWidth, totalHeight, theme]);

  return (
    <div ref={wrapperRef} className="relative select-none w-full pointer-events-none">
      <svg
        width={totalWidth}
        height={totalHeight}
        className="absolute top-0 left-0 pointer-events-none"
        style={{ zIndex: 1 }}
      >
        {song.measures.map((measure, mi) => {
          const layout = staveLayouts[mi];
          if (!layout) return null;

          const contentWidth = layout.x + layout.width - layout.contentX;
          const slotWidth = contentWidth / 2;

          return ([0, 1] as const).map((si) => {
            const chord = measure.chords[si];
            const slotX = layout.contentX + si * slotWidth;

            if (!chord) return null;

            const cx = slotX + slotWidth / 2;
            const chordY = layout.midLineY;
            const parts = getChordDisplayParts(chord);
            const rootSize = 20;
            const annoSize = 11;
            const rootW = parts.root.length * rootSize * 0.6;

            return (
              <g key={`${mi}-${si}`}>
                <rect
                  x={cx - slotWidth * 0.45}
                  y={chordY - 16}
                  width={slotWidth * 0.9}
                  height={32}
                  rx={4}
                  fill="var(--bg-primary)"
                  opacity={0.85}
                />
                <text
                  x={cx - (parts.sup || parts.sub ? rootW * 0.15 : 0)}
                  y={chordY}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="var(--chord-color)"
                  fontSize={rootSize}
                  fontWeight="bold"
                  fontFamily="system-ui, sans-serif"
                >
                  {parts.root}
                </text>
                {parts.sup && (
                  <text
                    x={cx + rootW * 0.35}
                    y={chordY - 8}
                    textAnchor="start"
                    dominantBaseline="central"
                    fill="var(--chord-color)"
                    fontSize={annoSize}
                    fontFamily="system-ui, sans-serif"
                  >
                    {parts.sup}
                  </text>
                )}
                {parts.sub && (
                  <text
                    x={cx + rootW * 0.35}
                    y={chordY + 8}
                    textAnchor="start"
                    dominantBaseline="central"
                    fill="var(--chord-color)"
                    fontSize={annoSize}
                    fontFamily="system-ui, sans-serif"
                  >
                    {parts.sub}
                  </text>
                )}
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
                  >
                    /{parts.bass}
                  </text>
                )}
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
                  >
                    {chord.romanNumeral}
                  </text>
                )}
              </g>
            );
          });
        })}
      </svg>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
