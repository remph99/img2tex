# Img2Tex 2.0 Optimization Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Ship smaller full and -cpuonly offline 2.0.0 portable editions with automatic warmup and simpler device settings.

**Architecture:** Keep the current spawned persistent model worker and shared UI. Put device detection/warmup in that worker; build edition metadata identifies CPU-only without importing torch into the UI. Parameterize existing packaging rather than creating a parallel packager.

**Tech Stack:** Python 3.12, PySide6, PyTorch 2.14.0, Transformers, PyInstaller.

**Spec:** docs/superpowers/specs/2026-11-02-v2-optimization-design.md

## Global Constraints

- Version 2.0.0; complete fixed checkpoint and unchanged inference semantics.
- CPU-only filename suffix -cpuonly; preserve original releases and user data.
- No GPU/CPU dual residency, no unrequested model quantization or engine replacement.
- No claim of clean/no-driver machine acceptance without that actual environment.

## Review Focus

- A saved CUDA choice moved to CPU-only or incompatible GPU must not prevent startup.
- Initialization failure must stop automatic image retry loops and allow deliberate retry.
- Old worker messages, queued paste cancellation, and manual edits must remain isolated.
- Resource trimming must not break localized Qt startup, previews or conversion assets.
- Both build modes must reject mismatched torch/torchvision and never mix artifacts.

### Task 1: Edition-aware packaging and resource trimming

Files: img2tex.spec, scripts/build.ps1, scripts/setup.ps1, scripts/release.py,
src/img2tex/__init__.py, src/img2tex/edition.py, tests/test_release.py.

- [x] Add failing behavioral tests for edition detection, suffixes, clean manifests and resource selection.
- [x] Implement shared edition metadata, parameterized isolated build/release paths, CPU wheel validation, Qt debug/locale exclusions.
- [x] Verify packaging tests and inspect native DLL retention; retain baseline release.

### Task 2: Persistent startup detection and warmup

Files: src/img2tex/engine.py, model_setup.py, __main__.py, tests/test_engine.py,
tests/test_model_setup.py.

- [x] Add failing tests for auto device selection, CPU-only avoiding CUDA, failed GPU probe/fallback, warmup before ready, unchanged task isolation.
- [x] Implement detection and short real inference warmup before ready, initialization stages and timings, one CPU fallback. Reuse model generation preparation for warmup and requests.
- [x] Verify worker tests and real CPU/CUDA smoke commands; measure staged timings.

### Task 3: Menus, device dialog, About, automatic startup

Files: src/img2tex/ui/main.py, tests/test_ui.py, src/img2tex/paths.py.

- [x] Add failing tests for menus, About version/edition, scheduled startup, settings apply idempotence, queued input during warmup, legacy model fallback.
- [x] Replace model dock and GUI downloader with device dialog and menu actions; keep four primary actions and copies; migrate path handling out of widgets.
- [x] Update applicable regression tests to new interfaces; remove obsolete GUI downloader tests, retain CLI download tests.
- [x] Verify full regression suite, lint and real GUI/render/export acceptance.

### Task 4: Build, release and acceptance

Files: packaging/ReadMe.txt, README.md, docs/v2-validation.md, scripts/accept_v2.py.

- [x] Build full edition, verify real frozen CPU/CUDA and GUI flows after trimming.
- [x] Prepare isolated CPU-only environment, build and verify no GPU runtimes and real offline CPU.
- [x] Package both portable editions, validate archive CRC, model hashes and checksums; compare baseline sizes and measured timings.
- [x] Document hardware/no-driver limits, run final full suite, lint, whitespace and code review.

Execution: continue directly under the user's explicit approval. Keep changes reviewable in the current clean feature checkout; do not publish, push or merge.

Execution ledger: full and CPU-only source suites each passed 183 tests and 9 subtests. Ruff, compileall and pip check passed. Independent review found no remaining actionable issues after queued-manual-cancel and installer suffix fixes. Final binaries were rebuilt with --clean after detecting stale incremental PYZ cache; embedded EXE modules now match current source. Both actual final archives passed CRC, fixed model hash and relocated/offline inference checks. Both visible interfaces were inspected on 2026-11-03; CPU end-to-end PNG/paste/history/MathML/DOCX and full CUDA startup -> CPU settings switch passed. No-driver/other-machine/Windows 10 acceptance remains outside available hardware. No merge, push or publication performed.

Final delivery: release/2.0.0 and release/2.0.0-cpuonly, each with SHA256SUMS.txt. Historical 1.0.0 ZIP hash unchanged. Detailed measurements and verification limits: docs/v2-validation.md.
