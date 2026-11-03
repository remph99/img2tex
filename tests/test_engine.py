import tempfile
import time
import unittest

from img2tex.engine import ModelProcess, describe_error


def test_cpu_selection_never_touches_cuda():
    from img2tex.engine import select_device

    class Runtime:
        @property
        def cuda(self):
            raise AssertionError("CPU-only must not initialize CUDA")

    assert select_device("auto", Runtime(), only_cpu=True)["device"] == "cpu"
    assert select_device("cpu", Runtime())["device"] == "cpu"


def test_cuda_probe_failure_falls_back_with_reason():
    from types import SimpleNamespace

    from img2tex.engine import select_device

    runtime = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False),
                              version=SimpleNamespace(cuda="13.0"))
    info = select_device("auto", runtime)
    assert info["device"] == "cpu"
    assert info["cuda_available"] is False
    assert info["reason"]


def test_old_gpu_is_rejected_before_allocating_cuda_tensors():
    from types import SimpleNamespace

    from img2tex.engine import select_device

    runtime = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True,
                              get_device_capability=lambda: (6, 1)), version=SimpleNamespace(cuda="13.0"))
    info = select_device("cuda", runtime)
    assert info["device"] == "cpu"
    assert "7.5" in info["reason"]


def test_failed_gpu_warmup_retries_once_on_cpu_before_ready(tmp_path, monkeypatch):
    import queue
    import sys
    import threading
    from types import SimpleNamespace

    from img2tex import engine

    loaded = []
    warmed = []

    class Model:
        def to(self, target):
            loaded.append(target)
            return self

        def eval(self):
            return self

    def warmup(torch, processor, model, image, target, budget):
        warmed.append(target)
        if target == "cuda":
            raise RuntimeError("out of memory during warmup")

    monkeypatch.setattr(engine, "check_model_directory", lambda path: tmp_path)
    monkeypatch.setattr(engine, "cpu_only", lambda: False)
    monkeypatch.setattr(engine, "select_device", lambda *a, **kw: {"device": "cuda", "cuda_available": True})
    monkeypatch.setattr(engine, "_generate", warmup)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        version=SimpleNamespace(cuda="13.0"), float16="float16", float32="float32",
        set_num_threads=lambda count: None, cuda=SimpleNamespace(empty_cache=lambda: None)))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoProcessor=SimpleNamespace(from_pretrained=lambda *a, **kw: object()),
        AutoModelForImageTextToText=SimpleNamespace(from_pretrained=lambda *a, **kw: Model()),
        StoppingCriteria=object, StoppingCriteriaList=list))
    commands, events = queue.Queue(), queue.Queue()
    commands.put(None)
    engine._worker_main(commands, events, threading.Event(), str(tmp_path), "auto")
    messages = []
    while not events.empty():
        messages.append(events.get_nowait())
    assert loaded == ["cuda", "cpu"]
    assert warmed == ["cuda", "cpu"]
    assert [m["type"] for m in messages].count("ready") == 1
    assert messages[-1]["type"] == "ready"
    assert messages[-1]["device"] == "cpu"
    assert "warmup" in messages[-1]["reason"]
    assert not any(m["type"] == "result" for m in messages)


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
