"""PyInstaller entry point (package imports remain absolute)."""
import multiprocessing
import sys

from img2tex.__main__ import main

if __name__ == "__main__":
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        from img2tex.paths import configure_runtime
        try:
            import os
            data = configure_runtime()
            stream = (data / "logs" / f"runtime-{os.getpid()}.log").open("a", encoding="utf8", buffering=1)
            if sys.stdout is None:
                sys.stdout = stream
            if sys.stderr is None:
                sys.stderr = stream
        except OSError:
            # The GUI startup boundary displays the actionable directory error.
            pass
    multiprocessing.freeze_support()
    raise SystemExit(main())
