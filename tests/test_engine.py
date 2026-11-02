import tempfile
import time
import unittest

from img2tex.engine import ModelProcess, describe_error


def test_worker_reports_root_cause_hidden_by_lazy_model_import():
    cause = ModuleNotFoundError("No module named 'runtime_dependency'")
    outer = RuntimeError("Could not import module AutoProcessor")
    outer.__cause__ = cause
    assert "runtime_dependency" in describe_error(outer)
    assert "AutoProcessor" in describe_error(outer)


class EngineTests(unittest.TestCase):
    def test_busy_clears_even_when_cancelled_task_result_is_filtered(self):
        import queue
        service = ModelProcess()
        service._events = queue.Queue()
        service._physical_task = "cancelled"
        self.assertTrue(service.is_busy)
        service._events.put({"type": "result", "task_id": "cancelled", "raw_output": "late"})
        self.assertEqual(service.poll(), [])
        self.assertFalse(service.is_busy)

    def test_missing_model_exits_without_network_or_hanging(self):
        service = ModelProcess()
        try:
            with tempfile.TemporaryDirectory() as temp:
                service.load(temp, "cpu")
                messages = []
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    messages.extend(service.poll())
                    if any(m["type"] == "error" for m in messages):
                        break
                    time.sleep(.02)
                errors = [m for m in messages if m["type"] == "error"]
                self.assertTrue(errors)
                self.assertIn("config.json", errors[0]["message"])
        finally:
            service.stop()
        self.assertFalse(service.is_alive)

    def test_cancelled_or_old_task_results_are_not_delivered(self):
        # Only transport is replaced; production poll filtering runs unchanged.
        import queue
        service = ModelProcess()
        service._events = queue.Queue()
        service._active_task = "new"
        service._events.put({"type": "result", "task_id": "old", "raw_output": "wrong"})
        service._events.put({"type": "result", "task_id": "new", "raw_output": "correct"})
        self.assertEqual([m["raw_output"] for m in service.poll()], ["correct"])
        service._active_task = "cancel-me"
        service.cancel()
        service._events.put({"type": "result", "task_id": "cancel-me", "raw_output": "late"})
        self.assertEqual([m for m in service.poll() if m["type"] == "result"], [])
