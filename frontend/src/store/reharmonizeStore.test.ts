import { test } from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import { transpileModule, JsxEmit, ModuleKind } from 'typescript';
import type { Song } from '../models/types.ts';
import { parseChordName } from '../engine/chordParser.ts';
import { reharmSymbol } from '../engine/reharmonize.ts';
import type { ReharmResult } from '../engine/reharmonize.ts';

const SRC_URL = new URL('../', import.meta.url).href;
const CONTROLS_URL = `${SRC_URL}components/RightPanel/ReharmControls.tsx`;
registerHooks({
  resolve(specifier, context, nextResolve) {
    // Render the real controls against the current real stores without a DOM.
    // Only component hooks are adapted; actions, validation and autosave run normally.
    if (context.parentURL === CONTROLS_URL) {
      if (specifier === 'react') return { shortCircuit: true,
        url: 'data:text/javascript,export const useState = initial => [initial, () => {}];' };
      const store = specifier.match(/^\.\.\/\.\.\/store\/(\w+)$/)?.[1];
      if (store) {
        const hook = `use${store[0].toUpperCase()}${store.slice(1)}`;
        return { shortCircuit: true, url: 'data:text/javascript,' + encodeURIComponent(
          `import { ${hook} as store } from '${SRC_URL}store/${store}.ts'; export const ${hook} = selector => selector(store.getState());`) };
      }
    }
    if (context.parentURL?.startsWith(SRC_URL) && /^\.\.?\//.test(specifier) && !/\.\w+$/.test(specifier)) {
      specifier += specifier.endsWith('/OperationProgress') ? '.tsx' : '.ts';
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.startsWith(SRC_URL) && url.endsWith('.css')) return { format: 'module', shortCircuit: true, source: '' };
    if (url.startsWith(SRC_URL) && url.endsWith('.tsx')) return { format: 'module', shortCircuit: true,
      source: transpileModule(readFileSync(new URL(url), 'utf8'), {
        compilerOptions: { jsx: JsxEmit.ReactJSX, module: ModuleKind.ESNext },
      }).outputText };
    if (url === `${SRC_URL}engine/playback.ts`) return { format: 'module', shortCircuit: true,
      source: 'export function cancelPendingStart() {}\nexport function setLiveBpm() {}\nexport function stopPlayback() {}' };
    return nextLoad(url, context);
  },
});
const storage = new Map<string, string>();
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
} });
let nextTimer = 0;
const timers = new Map<number, () => void>();
Object.defineProperty(globalThis, 'window', { configurable: true, value: {
  setTimeout: (callback: () => void) => { timers.set(++nextTimer, callback); return nextTimer; },
  clearTimeout: (id: number) => timers.delete(id),
} });
const { useSongStore } = await import('./songStore.ts');
const { useReharmonizeStore } = await import('./reharmonizeStore.ts');
const { default: ReharmControls } = await import('../components/RightPanel/ReharmControls.tsx');
const editor = () => useSongStore.getState();
const reharm = () => useReharmonizeStore.getState();
const fixture: Song = { id: 'reharm-store', title: 'Test passage', bpm: 80, key: 'C major',
  genre: null, timeSignature: [4, 4], sections: [], autoTitle: false,
  measures: [['Dm7', 'G7'], ['Cmaj7', 'Am7']].map((chords, index) => ({ id: `bar-${index}`, index,
    chords: chords.map(parseChordName) as Song['measures'][0]['chords'] })),
};
const response: ReharmResult = { modelUsed: 'Music Transformer', metaModel: 'muse-spark-1.3', contextMeasures: [0, 1],
  candidates: ['Db7', 'Fm7', 'G9'].map((after, index) => ({ id: String(index), family: 'common_tones',
    changes: [{ address: { measureIndex: 0, slotIndex: index === 1 ? 0 : 1 },
      before: index === 1 ? 'Dm7' : 'G7', after, commonTones: 2, modes: [] }],
    pitchDistance: .5, originalPitchDistance: .8, bassMotion: 2, originalBassMotion: 3, mathScore: 1, modelScore: -2 })),
};
function saved(): Song {
  for (const [id, callback] of timers) { timers.delete(id); callback(); }
  return JSON.parse(storage.get('theartist-song')!);
}
function symbols(song: Song, measure = 0) { return song.measures[measure].chords.map(c => c && reharmSymbol(c)); }

interface ControlNode {
  type?: unknown;
  props?: { children?: unknown; role?: string; disabled?: boolean; onClick?: () => void };
}
function nodes(tree: unknown): ControlNode[] {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!tree || typeof tree !== 'object') return [];
  const node = tree as ControlNode;
  return [node, ...nodes(node.props?.children)];
}
function controls() {
  const tree = nodes(ReharmControls({ modelKey: 'ft_f1' }));
  return {
    apply: tree.find(node => node.type === 'button' && /^Appl/.test(String(node.props?.children)))!.props!,
    status: tree.find(node => node.props?.role === 'status')?.props?.children,
  };
}

test('Apply enables for combined previews and distinguishes an already applied combination', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  editor().setSong(fixture);
  editor().selectSlotRange({ measureIndex: 0, slotIndex: 0 }, { measureIndex: 0, slotIndex: 1 });
  await reharm().run('ft_f1', 1, 'auto');
  assert.equal(controls().apply.disabled, true);
  assert.match(String(controls().status), /Choose an alternative/);
  reharm().preview(0);
  reharm().preview(1);
  assert.equal(controls().apply.disabled, false);
  assert.match(String(controls().status), /Alter 1 \+ Alter 2 selected/);
  controls().apply.onClick!();
  assert.deepEqual(symbols(saved()), ['Fm7', 'Db7']);
  assert.equal(controls().apply.disabled, true);
  assert.equal(controls().apply.children, 'Applied ✓');
  assert.match(String(controls().status), /Alter 1 \+ Alter 2 applied/);

  reharm().preview(2);
  assert.equal(controls().apply.disabled, false);
  assert.equal(controls().apply.children, 'Apply');
  assert.match(String(controls().status), /Alter 2 \+ Alter 3 selected/);
  reharm().preview(0);
  assert.equal(controls().apply.children, 'Applied ✓', 'returning to the saved combination explains why Apply is disabled');
  reharm().preview(null);
  assert.equal(controls().apply.disabled, false);
  assert.match(String(controls().status), /Origin selected/);
  controls().apply.onClick!();
  assert.equal(controls().apply.children, 'Applied ✓');
  assert.match(String(controls().status), /Origin applied/);
  assert.deepEqual(symbols(saved()), ['Dm7', 'G7']);
  reharm().close();
});

test('real stores autosave the last Apply, retain manual edits, and cancel only pending previews', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  editor().setSong(fixture);
  editor().selectSlotRange({ measureIndex: 0, slotIndex: 0 }, { measureIndex: 0, slotIndex: 1 });
  await reharm().run('ft_f1', 1, 'auto');
  reharm().preview(0);
  reharm().preview(1);
  assert.deepEqual(symbols(editor().song), ['Fm7', 'Db7']);
  assert.deepEqual(symbols(saved()), ['Dm7', 'G7']);
  reharm().apply();
  assert.deepEqual(symbols(saved()), ['Fm7', 'Db7']);
  reharm().preview(2);
  editor().setChord({ measureIndex: 1, slotIndex: 0 }, parseChordName('Ab'));
  assert.deepEqual(symbols(saved()), ['Fm7', 'Db7']);
  assert.equal(symbols(saved(), 1)[0], 'Ab');
  reharm().close();
  assert.deepEqual(symbols(editor().song), ['Fm7', 'Db7']);
  assert.equal(symbols(editor().song, 1)[0], 'Ab');
  assert.equal(editor().chordPreview, null);
});

test('replacing a song clears previews without reentrant rollback into the replacement', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  editor().setSong(fixture);
  editor().selectSlotRange({ measureIndex: 0, slotIndex: 0 }, { measureIndex: 0, slotIndex: 1 });
  await reharm().run('ft_f1', 1, 'auto');
  reharm().preview(0);
  editor().setSong(fixture);
  assert.equal(editor().chordPreview, null);
  assert.equal(reharm().comparison, null);
  assert.deepEqual(symbols(editor().song), ['Dm7', 'G7']);
  assert.deepEqual(symbols(saved()), ['Dm7', 'G7']);
});
