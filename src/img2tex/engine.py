"""Spawned, device-explicit model worker. Importing the desktop never loads torch."""

import gc
import io
import multiprocessing as mp
import os
import queue
import time
from collections import deque

from .edition import cpu_only
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


def select_device(requested, torch, *, only_cpu=False):
    info = {"device": "cpu", "cuda_available": None, "reason": "", "gpu": None}
    if only_cpu:
        return {**info, "cuda_available": False, "reason": "此发行版仅支持 CPU"}
    if requested == "cpu":
        return info
    try:
        if not torch.version.cuda or not torch.cuda.is_available():
            raise RuntimeError("CUDA 不可用，请检查 NVIDIA 显卡及驱动；当前完整包需要兼容 CUDA 13 的驱动")
        capability = torch.cuda.get_device_capability()
        if int(torch.version.cuda.split(".")[0]) >= 13 and capability < (7, 5):
            raise RuntimeError("随包 CUDA 13 需要计算能力 7.5 或更新的 NVIDIA GPU")
        # An actual kernel detects unsupported binaries/driver errors missed by is_available.
        tensor = torch.ones((2, 2), device="cuda")
        torch.mm(tensor, tensor)
        torch.cuda.synchronize()
        free, total = torch.cuda.mem_get_info()
        return {**info, "device": "cuda", "cuda_available": True,
                "gpu": torch.cuda.get_device_name(0), "free_vram_bytes": free, "total_vram_bytes": total}
    except Exception as exc:  # noqa: BLE001 - driver errors are a recoverable CPU fallback
        return {**info, "cuda_available": False, "reason": describe_error(exc)}


def _generate(torch, processor, model, image, device, budget, stopping_criteria=None):
    messages = [{"role": "user", "content": [
        {"type": "image", "image": image}, {"type": "text", "text": FORMULA_PROMPT},
    ]}]
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_dict=True,
        return_tensors="pt", enable_thinking=False,
    ).to(device)
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=budget, do_sample=False,
                                stopping_criteria=stopping_criteria)
    return output[:, inputs["input_ids"].shape[1]:]


def _worker_main(commands, events, cancel_event, model_dir: str, device: str):
    started = time.perf_counter()
    try:
        path = check_model_directory(model_dir)
        revision = model_revision(path)
        # This process loads local assets only. Downloads are a separate explicit action.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        import torch
        from PIL import Image, ImageDraw
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
            StoppingCriteria,
            StoppingCriteriaList,
        )

        from .images import prepare_image

        info = select_device(device, torch, only_cpu=cpu_only() or torch.version.cuda is None)
        selected = info["device"]
        events.put({"type": "device_info", **info})
        processor = AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False)

        def load_and_warmup(target):
            if target == "cpu":
                torch.set_num_threads(min(8, os.cpu_count() or 1))
            _, dtype_name = device_options(target, cuda_available=target == "cuda")
            events.put({"type": "loading", "device": target})
            load_start = time.perf_counter()
            loaded = AutoModelForImageTextToText.from_pretrained(
                path, dtype=getattr(torch, dtype_name), local_files_only=True,
                trust_remote_code=False, attn_implementation="eager",
            ).to(target).eval()
            load_seconds = time.perf_counter() - load_start
            events.put({"type": "warming", "device": target})
            warm_start = time.perf_counter()
            image = Image.new("RGB", (224, 96), "white")
            ImageDraw.Draw(image).text((24, 30), "x^2 + 1", fill="black", font_size=26)
            _generate(torch, processor, loaded, image, target, 8)
            if target == "cuda":
                torch.cuda.synchronize()
            return loaded, dtype_name, load_seconds, time.perf_counter() - warm_start

        model = None
        failure = None
        try:
            model, dtype_name, load_seconds, warm_seconds = load_and_warmup(selected)
        except Exception as exc:
            if selected != "cuda":
                raise
            failure = describe_error(exc)
        if failure:
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except RuntimeError:
                pass
            selected = "cpu"
            info = {**info, "device": "cpu", "cuda_available": False, "reason": failure}
            events.put({"type": "device_info", **info})
            model, dtype_name, load_seconds, warm_seconds = load_and_warmup("cpu")

        class Cancelled(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return cancel_event.is_set()

        events.put({"type": "ready", **info, "load_seconds": load_seconds, "warmup_seconds": warm_seconds,
                    "startup_seconds": time.perf_counter() - started})
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
                budget = max(16, min(int(command["max_new_tokens"]), 4096))
                new_tokens = _generate(torch, processor, model, image, selected, budget,
                                       StoppingCriteriaList([Cancelled()]))
                if cancel_event.is_set():
                    events.put({"type": "cancelled", "task_id": task_id, "device": selected})
                    continue
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
        if device not in {"cpu", "cuda", "auto"}:
            raise ValueError("请选择 CPU、CUDA 或自动检测。")
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
                self._device = event["device"]
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
