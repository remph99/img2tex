"""Desktop entry point and explicit model preparation/validation commands."""

import argparse
import json
import multiprocessing
import os
import sys
import time
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Img2Tex 本地公式识别")
    parser.add_argument("--download-model", action="store_true", help="准备固定版本本地模型后退出")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--check-device", action="store_true")
    parser.add_argument("--smoke", type=Path, help="用实际模型识别一张图，并输出 JSON")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from .model_setup import default_model_dir, download_model

    try:
        if args.download_model or args.check_device or args.smoke:
            from .paths import configure_runtime
            configure_runtime()
        if args.download_model:
            print(download_model(args.model_dir), flush=True)
            return 0
        if args.check_device:
            import torch

            from . import __version__
            from .paths import app_data_dir, is_portable
            print(json.dumps({
                "version": __version__, "portable": is_portable(), "data_dir": str(app_data_dir()),
                "default_model_dir": str(default_model_dir()), "python_executable": sys.executable,
                "torch": torch.__version__, "cpu": True, "cuda": torch.cuda.is_available(),
                "cuda_runtime": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            }, ensure_ascii=False), flush=True)
            return 0
        if args.smoke:
            from .engine import ModelProcess
            engine = ModelProcess()
            started = time.perf_counter()
            result = None
            try:
                engine.load(str(args.model_dir or default_model_dir()), args.device)
                deadline = time.monotonic() + args.timeout
                sent = False
                while time.monotonic() < deadline:
                    for event in engine.poll():
                        if event["type"] == "ready" and not sent:
                            engine.recognize(args.smoke.read_bytes(), uuid.uuid4().hex, args.max_tokens)
                            sent = True
                        elif event["type"] == "error":
                            raise RuntimeError(event["message"])
                        elif event["type"] == "result":
                            result = event
                            result["total_seconds_including_load"] = time.perf_counter() - started
                            break
                    if result:
                        break
                    time.sleep(.025)
                if result is None:
                    raise TimeoutError("模型验证超时；当前任务已结束。")
            finally:
                engine.stop()
            text = json.dumps(result, ensure_ascii=False, indent=2)
            print(text, flush=True)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf8")
            return 0
        from .ui.main import run
        return run()
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts third-party failures into a nonzero exit
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
