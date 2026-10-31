import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker from '../frontend/public/_worker.js';

test('an unconnected or invalid server returns explicit, uncached failure', async () => {
  for (const origin of [undefined, 'http://server.test', 'https://u:p@server.test',
    'https://server.test/path', 'https://artist.test', 'https://server.test?q=1']) {
    const response = await worker.fetch(new Request('https://artist.test/api/health'),
      { BACKEND_ORIGIN: origin });
    assert.equal(response.status, 503);
    assert.match((await response.json()).detail, /not connected/);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
  }
});

test('API proxy preserves body, session and stream without forwarding browser credentials', async (t) => {
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode('data: {"ok":true}\n\n'));
    controller.close();
  } });
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.equal(String(url), 'https://backend.test/api/plan/song/stream?mode=live');
    assert.equal(init.method, 'POST');
    assert.equal(await new Response(init.body).text(), '{"bars":8}');
    assert.equal(init.headers.get('X-TheArtist-Session'), 'session');
    assert.equal(init.headers.get('Authorization'), null);
    assert.equal(init.headers.get('Cookie'), null);
    assert.equal(init.redirect, 'manual');
    return new Response(stream, { headers: {
      'Content-Type': 'text/event-stream', 'Set-Cookie': 'unwanted=1',
    } });
  });
  const request = new Request('https://artist.test/api/plan/song/stream?mode=live', {
    method: 'POST', body: '{"bars":8}', headers: {
      'Content-Type': 'application/json', 'X-TheArtist-Session': 'session',
      Authorization: 'browser-secret', Cookie: 'private=1',
    },
  });
  const response = await worker.fetch(request, { BACKEND_ORIGIN: 'https://backend.test' });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Content-Type'), 'text/event-stream');
  assert.equal(response.headers.get('Set-Cookie'), null);
  assert.equal(await response.text(), 'data: {"ok":true}\n\n');
});

test('backend failures stay failures and redirects are not followed', async (t) => {
  for (const status of [422, 429, 503, 302]) {
    t.mock.method(globalThis, 'fetch', async () => new Response('failure', { status }));
    const response = await worker.fetch(new Request('https://artist.test/api/generate'),
      { BACKEND_ORIGIN: 'https://backend.test' });
    assert.equal(response.status, status === 302 ? 502 : status);
  }
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('offline'); });
  assert.equal((await worker.fetch(new Request('https://artist.test/api/health'),
    { BACKEND_ORIGIN: 'https://backend.test' })).status, 502);
});

test('non-API routes use Pages static assets', async () => {
  const response = await worker.fetch(new Request('https://artist.test/projects'), {
    ASSETS: { fetch: async () => new Response('editor') },
  });
  assert.equal(await response.text(), 'editor');
});
