import importlib.util
from pathlib import Path
import unittest


def load_bridge():
    path = Path(__file__).resolve().parents[2] / "tools" / "midi-bridge" / "bridge.py"
    spec = importlib.util.spec_from_file_location("local_midi_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MidiBridgeTest(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()

    def test_only_explicit_app_origins_with_bounded_nonce_open_a_connection(self):
        query = "origin=https%3A%2F%2Fartist-daw.pearlleestudio.co&token=12345678-1234-1234-1234-123456789abc"
        self.assertEqual(self.bridge.connection(query)[0], "https://artist-daw.pearlleestudio.co")
        for invalid in (query.replace("artist-daw.pearlleestudio.co", "attacker.example"),
                        "origin=https%3A%2F%2Fartist-daw.pearlleestudio.co&token=short"):
            with self.assertRaises(ValueError):
                self.bridge.connection(invalid)

    def test_helper_page_uses_same_origin_stream_and_exact_postmessage_target(self):
        page = self.bridge.page("https://artist-daw.pearlleestudio.co", "nonce").decode()
        self.assertIn("new EventSource('/events?", page)
        self.assertIn("config.origin)", page)
        self.assertNotIn("postMessage('*'", page)
        self.assertIn("if (!window.opener)", page)

    def test_native_failure_replaces_ready_state_and_buffer_is_bounded(self):
        events = self.bridge.Events()
        events.publish({"type": "state", "devices": [{"id": "1", "name": "test"}]})
        events.publish({"type": "error", "message": "input stopped"})
        self.assertEqual(events.state["error"], "input stopped")
        self.assertEqual(events.state["devices"], [])
        for _ in range(1100):
            events.publish({"type": "midi", "data": [144, 60, 1], "port": "1"})
        self.assertEqual(len(events.events), 1024)
