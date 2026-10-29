import { test } from 'node:test';
import assert from 'node:assert/strict';
import { metaHeaders, metaSessionId } from './metaSession.ts';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** A Map-backed localStorage (Node's own wants a storage file); returns the map. */
function useStorage(entries: Record<string, string> = {}): Map<string, string> {
  const storage = new Map(Object.entries(entries));
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => { storage.set(key, value); },
  } });
  return storage;
}

test('the id is created once, kept in localStorage and sent as X-TheArtist-Session', () => {
  const storage = useStorage();
  const first = metaHeaders();
  assert.deepEqual(Object.keys(first), ['X-TheArtist-Session']);
  assert.match(first['X-TheArtist-Session'], UUID);
  assert.deepEqual(metaHeaders(), first);
  assert.equal(storage.get('theartist-meta-session'), first['X-TheArtist-Session']);
});

test('a stored id is reused across page loads, and one the server would refuse is replaced', () => {
  useStorage({ 'theartist-meta-session': 'browser-a' });
  assert.equal(metaSessionId(), 'browser-a');
  const storage = useStorage({ 'theartist-meta-session': 'x'.repeat(129) });
  const id = metaSessionId();
  assert.match(id, UUID);
  assert.equal(storage.get('theartist-meta-session'), id);
});

test('a page without crypto.randomUUID (plain http) still gets a random id', (t) => {
  const storage = useStorage();
  // randomUUID lives on the prototype: shadow it on the instance, then uncover it again
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: undefined });
  t.after(() => { delete (crypto as Partial<Crypto>).randomUUID; });
  const id = metaSessionId();
  assert.match(id, /^[0-9a-f]{32}$/);
  assert.equal(metaSessionId(), id);
  assert.equal(storage.get('theartist-meta-session'), id);
});

// Last: the per-page fallback id lives for the rest of this module's life.
test('when storage throws, one id is kept for the page load and nothing is stored', () => {
  const fail = () => { throw new DOMException('denied', 'SecurityError'); };
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: fail, setItem: fail } });
  const id = metaSessionId();
  assert.match(id, UUID);
  assert.equal(metaSessionId(), id);
  assert.deepEqual(metaHeaders(), { 'X-TheArtist-Session': id });
  // Storage that reads but cannot write falls back to the same page id
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null, setItem: fail } });
  assert.equal(metaSessionId(), id);
});
