import { MIDI_BRIDGE_ORIGIN } from './midiBridge.ts';

/** One user-initiated export window; independent from the MIDI input connection. */
export function openDawBridge(signal: AbortSignal) {
  const token = crypto.randomUUID();
  const popup = window.open(`${MIDI_BRIDGE_ORIGIN}/daw?origin=${encodeURIComponent(location.origin)}&token=${token}`,
    'theartist-daw-handoff', 'popup,width=420,height=180');
  if (!popup) throw new Error('Allow the DAW connection window, then try Open in Logic Pro again.');
  let resolveReady!: () => void;
  let rejectReady!: (error: Error) => void;
  let resolveResult!: (action: 'open' | 'reveal') => void;
  let rejectResult!: (error: Error) => void;
  const ready = new Promise<void>((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
  const result = new Promise<'open' | 'reveal'>((resolve, reject) => { resolveResult = resolve; rejectResult = reject; });
  // A failure may arrive while the server is still preparing the MIDI blob.
  void ready.catch(() => {});
  void result.catch(() => {});
  const fail = (message: string) => { const error = new Error(message); rejectReady(error); rejectResult(error); };
  const receive = (event: MessageEvent) => {
    const value = event.data;
    if (event.origin !== MIDI_BRIDGE_ORIGIN || event.source !== popup ||
      value?.protocol !== 'theartist-daw-v1' || value.token !== token) return;
    if (value.type === 'ready') resolveReady();
    if (value.type === 'result') {
      if (value.action === 'open' || value.action === 'reveal') resolveResult(value.action);
      else fail(typeof value.error === 'string' ? value.error : 'The Mac could not open the MIDI.');
    }
  };
  const cancel = () => fail('DAW handoff cancelled.');
  const timer = setTimeout(() => fail('Start TheArtist MIDI Bridge on your Mac, then retry. No handoff was confirmed.'), 60_000);
  const closed = setInterval(() => { if (popup.closed) fail('The DAW connection window was closed.'); }, 300);
  window.addEventListener('message', receive);
  signal.addEventListener('abort', cancel, { once: true });
  return {
    async send(target: 'logic' | 'ableton', title: string, blob: Blob) {
      await ready;
      if (signal.aborted) throw new Error('DAW handoff cancelled.');
      if (blob.size > 4 * 1024 * 1024) throw new Error('The MIDI file is too large for direct handoff. Download MIDI instead.');
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
      if (signal.aborted) throw new Error('DAW handoff cancelled.');
      popup.postMessage({protocol:'theartist-daw-v1',token,type:'open',target,title,midi:btoa(binary)}, MIDI_BRIDGE_ORIGIN);
      return result;
    },
    close() {
      clearTimeout(timer); clearInterval(closed);
      window.removeEventListener('message', receive);
      signal.removeEventListener('abort', cancel);
      popup.close();
    },
  };
}
