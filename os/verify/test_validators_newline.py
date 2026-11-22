"""Regression: Python's `$` also matches before a trailing newline, so an id like "abc\\n" slipped through `^...$` validators."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import aiws_boot_slots, aiws_egress_proxy, aiws_events, aiws_local_model, aiws_mandate, aiws_model_registry

class TrailingNewline(unittest.TestCase):
    def test_validators_reject_a_trailing_newline(self):
        cases = [(aiws_events.SAFE_NAME, "run-1"), (aiws_boot_slots.DIGEST, "a" * 64), (aiws_boot_slots.RELEASE, "1.0"), (aiws_boot_slots.NAME, "slot-a"),
                 (aiws_local_model.TRASH_ID, "a" * 32), (aiws_mandate.TOOL_NAME, "Read"), (aiws_model_registry.DIGEST, "b" * 64), (aiws_egress_proxy.LABEL, "example")]
        for rx, ok in cases:
            self.assertTrue(rx.match(ok), (rx.pattern, "valid value must still match"))
            self.assertIsNone(rx.match(ok + "\n"), rx.pattern)
    def test_event_with_newline_session_is_rejected(self):
        with self.assertRaises(aiws_events.EventError):
            aiws_events.make_event(1.0, "claude", "run-1\n", "start")
        with self.assertRaises(aiws_events.EventError):
            aiws_events.make_event(1.0, "claude", "run-1", "tool", tool="Read\n")

if __name__ == "__main__":
    unittest.main()
