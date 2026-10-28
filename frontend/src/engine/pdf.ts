import { CanvasContext, Renderer, Stave } from 'vexflow';
import { jsPDF } from 'jspdf';
import type { Chord, Song } from '../models/types';
import { getChordDisplayParts } from './chordDisplay';
import { sectionAt, sectionColor, sectionDisplayLabel } from './songForm';
import {
  PDF_WIDTH, PDF_HEIGHT, pdfPageRanges, pdfMeasureLayout, withoutPdfCreationDate,
} from './pdfLayout';

export type PdfTheme = 'current' | 'light' | 'dark';
const FONT = '-apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';
const PALETTES = {
  light: { background: '#ffffff', ink: '#171717', chord: '#404040', muted: '#525252' },
  dark: { background: '#0a0a0a', ink: '#eaeaea', chord: '#d6d6d6', muted: '#9e9e9e' },
};
type Palette = typeof PALETTES.light;
// VexFlow supplies its own OffscreenCanvas type. Use its actual context contract.
type DrawingContext = CanvasContext['context2D'];
const KEY_SIGS: Record<string, string> = {
  'C major': 'C', 'G major': 'G', 'D major': 'D', 'A major': 'A', 'E major': 'E',
  'B major': 'B', 'F# major': 'F#', 'Gb major': 'Gb', 'Db major': 'Db', 'C# major': 'C#',
  'Ab major': 'Ab', 'G# major': 'Ab', 'Eb major': 'Eb', 'D# major': 'Eb', 'Bb major': 'Bb',
  'A# major': 'Bb', 'F major': 'F', 'Cb major': 'Cb',
  'A minor': 'Am', 'E minor': 'Em', 'B minor': 'Bm', 'F# minor': 'F#m', 'C# minor': 'C#m',
  'G# minor': 'G#m', 'D# minor': 'D#m', 'Eb minor': 'Ebm', 'Bb minor': 'Bbm', 'A# minor': 'A#m',
  'F minor': 'Fm', 'C minor': 'Cm', 'G minor': 'Gm', 'D minor': 'Dm', 'Ab minor': 'Abm',
  'Db minor': 'C#m', 'Gb minor': 'F#m',
};

function fittedText(ctx: DrawingContext, text: string, x: number, y: number, width: number): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(Math.min(1, width / Math.max(1, ctx.measureText(text).width)), 1);
  ctx.fillText(text, 0, 0);
  ctx.restore();
}

function drawChord(ctx: DrawingContext, chord: Chord, cx: number, y: number, width: number, palette: Palette) {
  const parts = getChordDisplayParts(chord);
  const sup = parts.sup + (chord.extensions.length ? `(${chord.extensions.join(',')})` : '');
  ctx.font = `600 24px ${FONT}`;
  const rootWidth = ctx.measureText(parts.root).width;
  ctx.font = `12px ${FONT}`;
  const annotationWidth = Math.max(ctx.measureText(sup).width, ctx.measureText(parts.sub).width);
  ctx.font = `20px ${FONT}`;
  const bass = parts.bass ? `/${parts.bass}` : '';
  const bassWidth = ctx.measureText(bass).width;
  const total = rootWidth + annotationWidth + bassWidth + (annotationWidth ? 2 : 0);
  const scale = Math.min(1, Math.max(10, width - 14) / Math.max(total, 1));
  ctx.save();
  ctx.translate(cx, y);
  ctx.scale(scale, scale);
  ctx.fillStyle = palette.background;
  ctx.fillRect(-total / 2 - 5, -22, total + 10, 40);
  ctx.fillStyle = palette.chord;
  ctx.font = `600 24px ${FONT}`;
  ctx.fillText(parts.root, -total / 2, 8);
  ctx.font = `12px ${FONT}`;
  ctx.fillText(sup, -total / 2 + rootWidth + 2, -7);
  ctx.fillText(parts.sub, -total / 2 + rootWidth + 2, 14);
  ctx.font = `20px ${FONT}`;
  ctx.fillText(bass, -total / 2 + rootWidth + annotationWidth + (annotationWidth ? 2 : 0), 8);
  ctx.restore();
  ctx.fillStyle = palette.muted;
  ctx.font = `17px ${FONT}`;
  ctx.save();
  ctx.textAlign = 'center';
  fittedText(ctx, chord.romanNumeral, cx, y + 54, width - 14);
  ctx.restore();
}

/** Render a score snapshot, independent of the editor viewport, selection and theme changes. */
export async function createSongPdf(song: Song, theme: PdfTheme = 'current'): Promise<Blob> {
  const snapshot = structuredClone(song);
  const ranges = pdfPageRanges(snapshot.measures.length);
  if (snapshot.sections?.some((section) => section.pending)) throw new Error('Wait for section generation to finish before exporting.');
  const resolvedTheme = theme === 'current'
    ? document.documentElement.classList.contains('light') ? 'light' : 'dark'
    : theme;
  const palette = PALETTES[resolvedTheme];
  await document.fonts.load('16px Bravura');
  await document.fonts.ready;
  if (!document.fonts.check('16px Bravura')) throw new Error('The music font is not ready. Refresh the page and try exporting again.');
  const scratch = document.createElement('div');
  scratch.setAttribute('aria-hidden', 'true');
  scratch.style.cssText = 'position:fixed;left:-100000px;top:0;pointer-events:none;';
  const canvas = document.createElement('canvas');
  scratch.append(canvas);
  document.body.append(scratch);
  try {
    const renderer = new Renderer(canvas, Renderer.Backends.CANVAS);
    const context = renderer.getContext() as CanvasContext;
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
    for (const [pageIndex, range] of ranges.entries()) {
      context.resize(PDF_WIDTH, PDF_HEIGHT, 3);
      const ctx = context.context2D;
      ctx.fillStyle = palette.background;
      ctx.fillRect(0, 0, PDF_WIDTH, PDF_HEIGHT);
      ctx.fillStyle = palette.ink;
      ctx.font = `600 30px ${FONT}`;
      fittedText(ctx, snapshot.title.trim() || 'Untitled', 10, 42, PDF_WIDTH - 20);
      ctx.fillStyle = palette.muted;
      ctx.font = `16px ${FONT}`;
      const details = [snapshot.key, `${snapshot.bpm} BPM`, snapshot.timeSignature.join('/'), snapshot.genre].filter(Boolean).join('  ·  ');
      fittedText(ctx, details, 10, 75, PDF_WIDTH - 20);
      for (let index = range.start; index < range.end; index++) {
        const layout = pdfMeasureLayout(index - range.start);
        const stave = new Stave(layout.x, layout.y, layout.width);
        if (layout.isFirstInRow) {
          stave.addClef('treble');
          const key = KEY_SIGS[snapshot.key];
          if (!key) throw new Error(`Unsupported PDF key signature: ${snapshot.key}`);
          stave.addKeySignature(key);
        }
        if (index === 0) stave.addTimeSignature(snapshot.timeSignature.join('/'));
        context.setFillStyle(palette.ink);
        context.setStrokeStyle(palette.ink);
        stave.setContext(context).draw();
        const contentX = Math.max(layout.contentX, stave.getNoteStartX() + 5);
        const section = sectionAt(snapshot, index);
        if (section) {
          ctx.fillStyle = sectionColor(section.type);
          ctx.globalAlpha = resolvedTheme === 'dark' ? 0.17 : 0.12;
          ctx.fillRect(contentX, layout.y + 1, layout.x + layout.width - contentX, 23);
          ctx.globalAlpha = 1;
          if (index === section.startMeasure || layout.isFirstInRow) {
            ctx.fillStyle = palette.ink;
            ctx.font = `600 13px ${FONT}`;
            fittedText(ctx, sectionDisplayLabel(section), contentX + 4, layout.y + 17, layout.x + layout.width - contentX - 9);
          }
        }
        ctx.fillStyle = palette.muted;
        ctx.font = `11px ${FONT}`;
        ctx.fillText(String(index + 1), layout.x + 3, layout.y + 32);
        const slotWidth = (layout.x + layout.width - contentX - 5) / 2;
        snapshot.measures[index].chords.forEach((chord, slot) => {
          if (chord) drawChord(ctx, chord, contentX + slotWidth * (slot + 0.5), stave.getYForLine(2), slotWidth, palette);
        });
      }
      ctx.fillStyle = palette.muted;
      ctx.font = `13px ${FONT}`;
      ctx.fillText('TheArtist', 10, PDF_HEIGHT - 20);
      ctx.textAlign = 'right';
      ctx.fillText(`${pageIndex + 1} / ${ranges.length}`, PDF_WIDTH - 10, PDF_HEIGHT - 20);
      ctx.textAlign = 'left';
      if (pageIndex) pdf.addPage();
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 12, 12, 186, 273, undefined, 'FAST');
      // Let the page paint its busy state while longer scores render.
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    }
    return new Blob([withoutPdfCreationDate(pdf.output('arraybuffer'))], { type: 'application/pdf' });
  } finally {
    scratch.remove();
    canvas.width = 0;
    canvas.height = 0;
  }
}
