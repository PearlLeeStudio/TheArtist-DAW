import { test } from 'node:test';
import assert from 'node:assert/strict';
import { openDawBridge } from './dawBridge.ts';
import { MIDI_BRIDGE_ORIGIN } from './midiBridge.ts';

test('DAW handoff accepts only its own popup, origin and nonce, and cleans up', async () => {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location');
  const listeners = new Set<(event: MessageEvent) => void>();
  const sent: unknown[][] = [];
  let token = '';
  const popup = { closed: false, postMessage: (...args: unknown[]) => sent.push(args), close() { this.closed = true; } };
  Object.defineProperty(globalThis, 'location', { configurable: true, value: { origin: 'https://artist-daw.pearlleestudio.co' } });
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    open(url: string) { token = new URL(url).searchParams.get('token')!; return popup; },
    addEventListener(_: string, listener: (event: MessageEvent) => void) { listeners.add(listener); },
    removeEventListener(_: string, listener: (event: MessageEvent) => void) { listeners.delete(listener); },
  } });
  const bridge = openDawBridge(new AbortController().signal);
  const emit = (data: object, origin = MIDI_BRIDGE_ORIGIN, source: unknown = popup) => {
    for (const listener of listeners) listener({ origin, source, data: { protocol: 'theartist-daw-v1', token, ...data } } as MessageEvent);
  };
  try {
    const pending = bridge.send('logic', 'Test score', new Blob(['MThd']));
    emit({type:'ready'}, 'https://attacker.example');
    emit({type:'ready'}, MIDI_BRIDGE_ORIGIN, {});
    emit({type:'ready', token:'wrong'});
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(sent.length, 0);
    emit({type:'ready'});
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(sent.length, 1);
    assert.equal(sent[0][1], MIDI_BRIDGE_ORIGIN);
    emit({type:'result',action:'open'});
    assert.equal(await pending, 'open');
  } finally {
    bridge.close();
    assert.equal(popup.closed, true);
    assert.equal(listeners.size, 0);
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow); else Reflect.deleteProperty(globalThis, 'window');
    if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation); else Reflect.deleteProperty(globalThis, 'location');
  }
});
