import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { transpileModule, JsxEmit, ModuleKind } from 'typescript';
import { Stave } from 'vexflow';
import { scoreStaveLayout } from './scoreStaveLayout.ts';
import type { Song } from '../models/types.ts';

const SRC_URL = new URL('../', import.meta.url).href;
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.startsWith(SRC_URL) && /^\.\.?\//.test(specifier) && !/\.\w+$/.test(specifier)) {
      specifier += specifier.endsWith('/ImportedMeasureReview') ? '.tsx' : '.ts';
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url === `${SRC_URL}store/songStore.ts`) {
      return {
        format: 'module', shortCircuit: true,
        source: `
          export const useSongStore = selector => selector(globalThis.staffTestState);
          export const isSlotInList = (slot, slots) => slots.some(item =>
            item.measureIndex === slot.measureIndex && item.slotIndex === slot.slotIndex);
        `,
      };
    }
    if (url.startsWith(SRC_URL) && url.endsWith('.tsx')) {
      return {
        format: 'module', shortCircuit: true,
        source: transpileModule(readFileSync(new URL(url), 'utf8'), {
          compilerOptions: { jsx: JsxEmit.ReactJSX, module: ModuleKind.ESNext },
        }).outputText,
      };
    }
    return nextLoad(url, context);
  },
});

// Render without effects or animation frames, as when a background Safari tab
// has not delivered its next frame. Chords and hit zones must already exist.
Object.defineProperty(globalThis, 'document', {
  configurable: true, value: {
    documentElement: { className: '' },
    createElement(tag: string) {
      assert.equal(tag, 'canvas');
      return { getContext: () => ({ measureText: () => ({
        width: 0, actualBoundingBoxAscent: 0, actualBoundingBoxDescent: 0,
      }) }) };
    },
  },
});
const { default: Staff } = await import('../components/ScoreEditor/Staff.tsx');
const { default: SessionStaff } = await import('../components/MyPage/SessionStaff.tsx');
const song: Song = {
  id: 'render-test', title: 'Original sketch', key: 'C major', bpm: 120,
  genre: 'pop', timeSignature: [4, 4], autoTitle: false,
  measures: Array.from({ length: 16 }, (_, index) => ({
    id: `bar-${index}`, index,
    chords: [{ root: 'C', quality: 'maj', extensions: [], romanNumeral: 'I', voicing: [60, 64, 67] }, null],
  })),
  sections: [{ id: 'verse', type: 'verse', startMeasure: 0, length: 16 }],
};
Object.defineProperty(globalThis, 'staffTestState', {
  configurable: true, value: {
    song, selectedSlots: [{ measureIndex: 0, slotIndex: 0 }], playbackPosition: null,
    selectSlot() {}, selectSlotRange() {}, addMeasures() {},
  },
});

test('overlay geometry matches VexFlow before drawing, across rows and narrow widths', () => {
  for (const width of [0, 320, 960, 1440]) {
    for (const index of [0, 1, 3, 4, 15]) {
      const layout = scoreStaveLayout(index, width);
      const stave = new Stave(layout.x, layout.y, layout.width);
      assert.equal(layout.midLineY, stave.getYForLine(2));
      assert.ok(Number.isFinite(layout.midLineY));
      assert.ok(layout.contentX < layout.x + layout.width);
    }
  }
});

test('editor initial render and remount include chords, sections and selection without a frame', () => {
  for (let mount = 0; mount < 2; mount++) {
    const html = renderToStaticMarkup(createElement(Staff));
    assert.equal((html.match(/>C<\/text>/g) ?? []).length, 16);
    assert.equal((html.match(/pointer-events-auto cursor-pointer"/g) ?? []).length, 34);
    assert.match(html, /Select Verse, bars 1 to 16/);
    assert.match(html, /var\(--selection-bg\)/);
    assert.match(html, /var\(--selection-bar\)/);
  }
});

test('saved project initial render and remount retain the first four bars without a frame', () => {
  for (let mount = 0; mount < 2; mount++) {
    const html = renderToStaticMarkup(createElement(SessionStaff, { song }));
    assert.equal((html.match(/>C<\/text>/g) ?? []).length, 4);
    assert.equal((html.match(/>I<\/text>/g) ?? []).length, 4);
  }
});
