# Windows installer and portable distribution implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task with final independent review.

**Goal:** Deliver Img2Tex1.0.0 installation and offline portable archives plus checksums.
**Architecture:** Keep the existing PyInstaller onedir runtime. Add one runtime-path authority and wrap the same clean runtime with Inno Setup and ZIP64.
**Tech Stack:** conda img2tex/Python3.12, PyInstaller, Inno Setup7, standard Python ZIP64.
**Spec:** docs/superpowers/specs/2026-11-02-distribution.md

## Global constraints
No user data in distributions; preserve installed user DB/settings; portable data relative to EXE; fixed model commit/hash; CPU remains available; all Python development in conda img2tex. No source algorithm change or automatic cloud requests. No signing/security-setting changes.

## Review focus
1. Portable folder moved after saving model paths and history.
2. Read-only media or absent bundled models must fail clearly without writing elsewhere.
3. Installer upgrades/uninstall preserve user data and do not delete unrelated files.
4. Artifact inputs exclude developer caches, tests, screenshots and absolute development settings.
5. New native packaging must retain Qt/torchvision/converter resources already fixed.

## Task 1: Runtime paths and release identity
Files: src/img2tex/paths.py, __main__.py, ui/main.py, model_setup.py, __init__.py, pyproject.toml, tests/test_paths.py, tests/test_ui.py.
- [x] RED tests normal/portable data paths, moved relative models, external paths, startup error behavior and persistence.
- [x] Implement centralized paths/cache/log initialization, integrate UI and CLI, preserve installed DB location, add version/icon metadata.
- [x] GREEN pytest/Ruff/compile checks and actual model inference.

## Task 2: Reproducible release packaging
Files: packaging/windows/Img2Tex.iss, version info/icon, scripts/build.ps1, scripts/release.py, release guide/notices.
- [x] Acquire official Inno Setup compiler under ignored build tools and verify signature.
- [x] Build clean runtime; stage installer and portable inputs from an explicit allowlist, include bundled model and licenses.
- [x] Compile installer and ZIP64 portable archive; create SHA256SUMS and build manifest; check archive contents and integrity.

## Task 3: Distribution acceptance and handoff
Files: release test scripts/docs/validation report.
- [x] Fresh reviewer audits paths and destructive/uninstall boundaries; resolve confirmed findings.
- [x] Test moved portable history/settings, offline CPU/CUDA and GUI startup; test installation/upgrade/uninstall in explicit isolated test directories.
- [x] Probe clean Windows test environment and record actual coverage/limitations.
- [x] Deliver both final files and checksums, update docs and commit task source.

Ruling: Release numbering1.0.0 is the first distribution, retaining existing product name. Use current-user installation to avoid requiring elevation. Use Inno Setup7.1.1 (official recommended release verified on2026-11-02); tool stays under build/tools.

Ruling: Do not collect unused Python QtQml/QtQuick bindings (the application uses Widgets/WebEngine), which otherwise pull in unrelated QML/plugin modules. Keep all native linked dependencies required by WebEngine and verify actual preview/rendering after packaging. Add original Qt LGPL/GPL/exception text copies alongside bundled dependency metadata.
