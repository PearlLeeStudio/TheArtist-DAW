"""Deployment transactions must preserve the current service when a candidate fails."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, call

SPEC = importlib.util.spec_from_file_location(
    "autodeploy", Path(__file__).resolve().parents[2] / "deploy/autodeploy.py")
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class AutoDeployTest(unittest.TestCase):
    def setUp(self):
        self.host = MagicMock(spec=deploy.Host)
        self.host.inspect.return_value = ("a" * 40, "b" * 40)
        self.host.changes.return_value = ["backend/app/main.py"]
        self.host.current_image.return_value = "sha256:old"
        self.state = {"deployed_revision": "a" * 40, "observed_revision": "a" * 40}
        self.saved = []

    def save(self, state):
        # Capture values at each boundary, including recovery information.
        self.saved.append(__import__("copy").deepcopy(state))

    def run_deploy(self, **kwargs):
        return deploy.run_once(self.host, self.state, self.save, **kwargs)

    def test_docs_only_updates_checkout_without_touching_service(self):
        self.host.changes.return_value = ["README.md", "deploy/vps.md", "backend/tests/test_x.py"]
        self.assertEqual(self.run_deploy(), "documentation-only")
        self.host.build.assert_not_called()
        self.host.start.assert_not_called()
        self.assertEqual(self.state["deployed_revision"], "a" * 40)
        self.assertEqual(self.state["observed_revision"], "b" * 40)

    def test_build_failure_preserves_running_image_and_restores_checkout(self):
        self.host.build.side_effect = RuntimeError("build failed")
        with self.assertRaisesRegex(RuntimeError, "build failed"):
            self.run_deploy()
        self.host.start.assert_not_called()
        self.host.checkout.assert_has_calls([call("b" * 40), call("a" * 40)])
        self.host.tag.assert_called_once_with("sha256:old", deploy.PREVIOUS)
        self.assertEqual(self.state["failed_revision"], "b" * 40)
        self.assertNotIn("pending", self.state)

    def test_bad_generation_rolls_back_and_verifies_previous_service(self):
        self.host.smoke.side_effect = [RuntimeError("wrong model"), None]
        with self.assertRaisesRegex(RuntimeError, "wrong model"):
            self.run_deploy()
        self.host.tag.assert_has_calls([
            call("sha256:old", deploy.PREVIOUS), call(deploy.CANDIDATE, deploy.IMAGE),
            call("sha256:old", deploy.IMAGE)])
        self.assertEqual(self.host.start.call_count, 2)
        self.assertEqual(self.host.smoke.call_count, 2)
        self.assertEqual(self.state["deployed_revision"], "a" * 40)

    def test_start_failure_also_rolls_back(self):
        self.host.start.side_effect = [RuntimeError("unhealthy"), None]
        with self.assertRaisesRegex(RuntimeError, "unhealthy"):
            self.run_deploy()
        self.assertEqual(self.host.start.call_count, 2)
        self.host.smoke.assert_called_once()

    def test_unavailable_diagnostics_do_not_block_rollback(self):
        self.host.smoke.side_effect = [RuntimeError("wrong model"), None]
        self.host.diagnostics.side_effect = RuntimeError("logs unavailable")
        with self.assertRaisesRegex(RuntimeError, "wrong model"):
            self.run_deploy()
        self.assertEqual(self.host.start.call_count, 2)
        self.assertEqual(self.state["deployed_revision"], "a" * 40)
        self.assertNotIn("pending", self.state)

    def test_failed_revision_waits_for_a_new_push(self):
        self.state["failed_revision"] = "b" * 40
        self.assertEqual(self.run_deploy(), "failed-revision-skipped")
        self.host.build.assert_not_called()
        self.assertEqual(self.run_deploy(retry=True), "deployed")
        self.assertNotIn("failed_revision", self.state)

    def test_recovery_after_killed_switch_precedes_new_work(self):
        self.state["pending"] = dict(checkout="a" * 40, image="sha256:old",
                                     target="b" * 40, phase="switching")
        self.assertEqual(self.run_deploy(), "failed-revision-skipped")
        self.host.start.assert_called_once()
        self.host.smoke.assert_called_once()
        self.host.build.assert_not_called()
        self.assertLess(self.host.mock_calls.index(call.smoke()),
                        self.host.mock_calls.index(call.inspect()))

    def test_rollback_failure_keeps_recovery_record(self):
        self.host.start.side_effect = RuntimeError("daemon unavailable")
        with self.assertRaisesRegex(RuntimeError, "daemon unavailable"):
            self.run_deploy()
        self.assertEqual(self.state["pending"]["image"], "sha256:old")
        self.assertEqual(self.saved[-1]["pending"]["phase"], "switching")

    def test_success_commits_revision_only_after_smoke(self):
        self.assertEqual(self.run_deploy(), "deployed")
        self.assertEqual(self.state["deployed_revision"], "b" * 40)
        self.assertNotIn("pending", self.state)
        self.assertEqual(self.saved[-2]["pending"]["phase"], "switching")
        self.host.smoke.assert_called_once()

    def test_dirty_checkout_is_never_overwritten(self):
        self.host.inspect.side_effect = RuntimeError("dirty checkout")
        with self.assertRaisesRegex(RuntimeError, "dirty checkout"):
            self.run_deploy()
        self.host.checkout.assert_not_called()
        self.host.start.assert_not_called()

    def test_unknown_and_deleted_runtime_paths_trigger_build(self):
        self.assertTrue(deploy.runtime_changed(["new-file.json"]))
        self.assertTrue(deploy.runtime_changed([".dockerignore"]))
        self.assertTrue(deploy.runtime_changed(["deploy/runtime/uv.lock"]))
        self.assertFalse(deploy.runtime_changed(["HACKATHON.md"]))


if __name__ == "__main__":
    unittest.main()
