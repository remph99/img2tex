"""PyInstaller entry point (package imports remain absolute)."""
import multiprocessing

from img2tex.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
