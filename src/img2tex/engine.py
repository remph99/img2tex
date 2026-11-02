"""Spawned, device-explicit model worker. Importing the desktop never loads torch."""

import io
import multiprocessing as mp
import os
import queue
import time
from collections import deque

from .model_setup import FORMULA_PROMPT, check_model_directory, device_options, model_revision
from .results import normalize_latex


def describe_error(exc: Exception) -> str:
    parts = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        parts.append(str(exc))
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return " · ".join(parts)


def _worker_main(commands, events, cancel_event, model_dir: str, device: str):
    try:
        path = check_model_directory(model_dir)
        revision = model_revision(path)
        # This process loads local assets only. Downloads are a separate explicit action.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        import torch
        from PIL import Image
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
            StoppingCriteria,
            StoppingCriteriaList,
        )

        from .images import prepare_image

        selected, dtype_name = device_options(device, cuda_available=torch.cuda.is_available())
        if selected == "cpu":
            torch.set_num_threads(min(8, os.cpu_count() or 1))
        dtype = getattr(torch, dtype_name)
        processor = AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False)
        model = AutoModelForImageTextToText.from_pretrained(
            path, dtype=dtype, local_files_only=True, trust_remote_code=False, attn_implementation="eager",
        ).to(selected).eval()

        class Cancelled(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return cancel_event.is_set()

        events.put({"type": "ready", "device": selected})
        while True:
            command = commands.get()
            if command is None:
                break
            task_id = command["task_id"]
            try:
                if cancel_event.is_set():
                    events.put({"type": "cancelled", "task_id": task_id, "device": selected})
                    continue
                start = time.perf_counter()
                prepared = prepare_image(command["image_png"])
                image = Image.open(io.BytesIO(prepared.model_png)).convert("RGB")
                messages = [{"role": "user", "content": [
                    {"type": "image", "image": image}, {"type": "text", "text": FORMULA_PROMPT},
                ]}]
                inputs = processor.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                    return_tensors="pt", enable_thinking=False,
                ).to(selected)
                budget = max(16, min(int(command["max_new_tokens"]), 4096))
                with torch.inference_mode():
                    output = model.generate(
                        **inputs, max_new_tokens=budget, do_sample=False,
                        stopping_criteria=StoppingCriteriaList([Cancelled()]),
                    )
                if cancel_event.is_set():
                    events.put({"type": "cancelled", "task_id": task_id, "device": selected})
                    continue
                new_tokens = output[:, inputs["input_ids"].shape[1]:]
                eos = model.generation_config.eos_token_id
                eos = eos if isinstance(eos, list) else [eos]
                if new_tokens.shape[1] >= budget and int(new_tokens[0, -1]) not in eos:
                    raise ValueError("公式输出达到长度上限，结果未保存。请缩小选区或提高输出上限后重试。")
                raw = processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
                latex = normalize_latex(raw)
                events.put({
                    "type": "result", "task_id": task_id, "device": selected,
                    "raw_output": raw, "latex_normalized": latex,
                    "elapsed_seconds": time.perf_counter() - start, "model_revision": revision,
                    "image_sha256": prepared.sha256, "model_image_sha256": prepared.model_sha256,
                    "parameters": {"max_new_tokens": budget, "do_sample": False,
                                   "enable_thinking": False, "dtype": dtype_name},
                    "prompt": FORMULA_PROMPT, "preprocess_version": 1,
                })
            except Exception as exc:  # noqa: BLE001 - worker boundary must report model/library failures
                if cancel_event.is_set():
                    events.put({"type": "cancelled", "task_id": task_id, "device": selected})
                else:
                    message = describe_error(exc)
                    if "out of memory" in message.lower():
                        message = "内存/显存不足，请减小图像或输出长度，或切换 CPU。" + message
                    events.put({"type": "error", "task_id": task_id, "device": selected, "message": message})
    except Exception as exc:  # noqa: BLE001 - initialization errors must reach the desktop process
        events.put({"type": "error", "device": device, "message": describe_error(exc)})


class ModelProcess:
    def __init__(self):
        self._ctx = mp.get_context("spawn")
        self._process = None
        self._commands = None
        self._events = None
        self._cancel_event = self._ctx.Event()
        self._pending = deque()
        self._active_task = None
        self._physical_task = None
        self._ready = False
        self._device = "cpu"
        self._exit_reported = False

    @property
    def is_alive(self):
        return self._process is not None and self._process.is_alive()

    @property
    def is_busy(self):
        return self._physical_task is not None

    def load(self, model_dir: str, device: str):
        if device not in {"cpu", "cuda"}:
            raise ValueError("请选择 CPU 或 CUDA。")
        self.stop()
        self._device = device
        self._cancel_event.clear()
        self._commands = self._ctx.Queue()
        self._events = self._ctx.Queue()
        self._pending.append({"type": "loading", "device": device})
        self._process = self._ctx.Process(
            target=_worker_main, args=(self._commands, self._events, self._cancel_event, model_dir, device),
            name="Img2TexModel", daemon=True,
        )
        self._process.start()
        self._exit_reported = False

    def recognize(self, image_png: bytes, task_id: str, max_new_tokens: int = 1024):
        if not self._ready or not self.is_alive:
            raise RuntimeError("模型未就绪，请先加载模型。")
        if self._physical_task is not None:
            raise RuntimeError("上一项任务仍在执行或取消中，请稍候。")
        self._cancel_event.clear()
        self._active_task = task_id
        self._physical_task = task_id
        self._commands.put({"task_id": task_id, "image_png": image_png, "max_new_tokens": max_new_tokens})

    def cancel(self):
        self._active_task = None
        self._cancel_event.set()

    def poll(self) -> list[dict]:
        messages = list(self._pending)
        self._pending.clear()
        while self._events is not None:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            kind = event["type"]
            task_id = event.get("task_id")
            if kind == "ready":
                self._ready = True
            if task_id and task_id == self._physical_task and kind in {"result", "error", "cancelled"}:
                self._physical_task = None
            if task_id and kind in {"result", "error"}:
                if task_id != self._active_task:
                    continue
                self._active_task = None
            messages.append(event)
        if self._process and self._process.exitcode not in (None, 0) and not self._exit_reported:
            self._exit_reported = True
            self._ready = False
            messages.append({"type": "error", "device": self._device,
                             "message": f"模型进程异常退出（{self._process.exitcode}），请重新加载。"})
        return messages

    def stop(self):
        self.cancel()
        if self._process is not None:
            if self._process.is_alive():
                self._commands.put(None)
                self._process.join(timeout=.5)
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=2)
            self._process.close()
        for transport in (self._commands, self._events):
            if transport is not None and hasattr(transport, "close"):
                transport.cancel_join_thread()
                transport.close()
        self._process = self._commands = self._events = None
        self._pending.clear()
        self._active_task = self._physical_task = None
        self._ready = False
