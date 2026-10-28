import { SCORE_MEASURES_PER_ROW, scoreMeasureLayout } from './scoreLayout.ts';

export const PDF_WIDTH = 960;
export const PDF_HEIGHT = 1409;
export const PDF_BARS_PER_PAGE = SCORE_MEASURES_PER_ROW * 7;
export const PDF_SCORE_TOP = 110;

export function pdfPageRanges(measureCount: number): { start: number; end: number }[] {
  if (!Number.isInteger(measureCount) || measureCount < 1 || measureCount > 512) {
    throw new Error('PDF export supports 1–512 bars.');
  }
  return Array.from({ length: Math.ceil(measureCount / PDF_BARS_PER_PAGE) }, (_, page) => ({
    start: page * PDF_BARS_PER_PAGE, end: Math.min(measureCount, (page + 1) * PDF_BARS_PER_PAGE),
  }));
}

export function pdfMeasureLayout(indexOnPage: number) {
  return scoreMeasureLayout(indexOnPage, PDF_WIDTH, { top: PDF_SCORE_TOP });
}

/** Remove jsPDF's automatic work timestamp without moving any PDF xref offsets. */
export function withoutPdfCreationDate(buffer: ArrayBuffer): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(buffer.slice(0));
  const marker = '/CreationDate (';
  const markerBytes = Array.from(marker, (char) => char.charCodeAt(0));
  for (let i = 0; i <= bytes.length - marker.length; i++) {
    if (bytes[i] !== 47 || !markerBytes.every((byte, offset) => bytes[i + offset] === byte)) continue;
    let end = i + marker.length;
    while (end < bytes.length && bytes[end] !== 41) end++;
    if (end < bytes.length) bytes.fill(32, i, end + 1);
  }
  return bytes;
}
