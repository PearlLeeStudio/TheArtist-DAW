# MIDI keyboard input

Open the editor's **Input** tab and choose **Enable MIDI**. Connection and live
monitoring work without selecting a score slot. Writing a chord requires exactly
one selected slot and the Input tab to be active. No selection, multiple selected
slots, another tab, or a replaced song cannot receive a pending capture. Holding
three or more notes for three seconds commits once and advances the selection;
releasing early opens the existing review/confirm flow.

## Chrome

Automatic uses native Web MIDI over HTTPS, without requesting SysEx. Allow MIDI
for the current site when Chrome asks. If access was previously denied, change
that site's MIDI permission and reconnect. The app attaches connected input ports,
responds to unplug/replug, and clears notes whose release could have been lost.
Matching notes on different channels/ports release independently. A controller's
all-notes-off/all-sound-off message clears only its own channel.

Chrome can also use **Local bridge (Mac)** when direct access is unavailable.
Switch connection mode while MIDI is disabled.

## Safari on Mac

Safari does not natively expose Web MIDI. The Mac bridge reads
[CoreMIDI input](https://developer.apple.com/documentation/coremidi/midiinputportcreatewithblock(_:_:_:_:))
and forwards note/control messages through a local connection window. Browser
support is documented in [MDN's compatibility table](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/requestMIDIAccess#browser_compatibility).

1. On the Mac physically connected to the keyboard, use Python 3 and Apple's
   command-line developer tools (which provide Swift). No Python packages are needed.
2. Run `tools/midi-bridge/run.py` from this checkout using its absolute file path:
   `python3 /absolute/path/to/TheArtist-DAW/tools/midi-bridge/run.py`.
   The launcher builds its helper and module cache inside `tools/midi-bridge/.build/`,
   which Git ignores. Keep the process running while using MIDI.
3. In Safari, open TheArtist-DAW's **Input → Enable MIDI**. Automatic chooses the
   local bridge when Web MIDI is unavailable. Allow the connection window to open
   and keep that small window open while playing.
4. Select one score slot to enter chords. Without a target, the connection only
   monitors. Closing the connection window clears held notes and disconnects it.

The bridge runs at `http://127.0.0.1:8768` on that Mac. It belongs on the user's
computer, not the DigitalOcean model server. It supports the production Artist and
Artist-DAW origins and local port 5173. Preview origins are deliberately not allowed;
an additional origin must be explicitly added to the bridge allowlist.

The HTTPS app does not fetch an insecure HTTP resource. A top-level local page
receives a same-origin event stream, then uses `postMessage` to its exact app
origin. The app checks the local origin, opened window and fresh connection nonce.
The helper binds loopback only, checks the Host header, grants no cross-origin
event access, and exposes no command execution endpoint. It opens no MIDI output
port. Notes are not uploaded, written to disk, or recorded; the live queue is bounded.

Native input-port enumeration and the actual local HTTP/SSE connection were checked
on a Mac with three available input ports. Native parsing tests cover note-on/off,
running status, interleaved realtime events, SysEx exclusion and all-notes-off.
Frontend tests cover stale connections, message provenance and target-only capture.
These checks do not replace playing the physical keyboard in both browsers;
physical keypress/browser confirmation remains a manual check.

Mobile Safari is not a target for this Mac helper. A phone has no access to a
keyboard attached to another machine's `127.0.0.1`.
