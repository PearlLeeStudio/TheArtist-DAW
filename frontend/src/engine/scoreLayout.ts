/** Shared score geometry for the editor, saved projects and PDF pages. */
export const SCORE_MEASURES_PER_ROW = 4;
export const SCORE_ROW_HEIGHT = 170;
export const SCORE_TOP = 18;

export interface ScoreMeasureLayout {
  x: number;
  y: number;
  width: number;
  isFirstInRow: boolean;
  contentX: number;
}

export function scoreMeasureLayout(
  index: number,
  width: number,
  options: { top?: number; rowHeight?: number } = {},
): ScoreMeasureLayout {
  const col = index % SCORE_MEASURES_PER_ROW;
  const row = Math.floor(index / SCORE_MEASURES_PER_ROW);
  const baseWidth = Math.max(120, (width - 20 - 60) / SCORE_MEASURES_PER_ROW);
  const x = 10 + col * baseWidth + (col ? 60 : 0);
  const isFirstInRow = col === 0;
  return {
    x, y: (options.top ?? SCORE_TOP) + row * (options.rowHeight ?? SCORE_ROW_HEIGHT),
    width: baseWidth + (isFirstInRow ? 60 : 0), isFirstInRow,
    contentX: x + (isFirstInRow ? 70 : 10),
  };
}
