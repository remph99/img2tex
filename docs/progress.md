# Implementation ledger — docs/superpowers/plans/2026-11-02-local-ocr.md

User approved A and execution, adding CPU/CUDA selection and a new conda env.
Existing root contained analysis only. No original product files to preserve except analysis. Environment img2tex created successfully (Python 3.12.16).
Pre-flight: UI/engine/storage/exports consume the exact interfaces frozen in the spec.
Ruling: New product repository in designated directory; no linked worktree needed because there was no pre-existing Git repository/branch or product code.
Ruling: CUDA wheel may also run CPU; GUI exposes explicit CPU/CUDA, initial CPU, no hidden fallback. CPU-only installation documented separately.

Completed core, local exports and desktop implementation. Dedicated img2tex env uses Python3.12.16, torch2.14.0+cu130, Transformers5.17.0 and PySide6.12.0. Fixed model revision and SHA256 verified; real CPU/CUDA energy, fraction/root, matrix and cases samples passed manual content checks. Real worker cancellation/retry/device-switch/clean-stop passed.

Latest user amendment supersedes initial screenshot scope: screenshots/copying images are external, no global hotkeys or built-in screenshot. Ctrl+V pastes clipboard images only inside the app; text paste and Ctrl+C copy keep normal editor behavior. Obsolete capture/hotkey modules and tests removed; old stored hotkey values ignored and preserved.

Initial implementation tests:138 passed +9subtests, Ruff/compileall/pip check passed. Read-only reviews found and then verified fixes for nested-token export loss, Typst visible grouping and custom-model identity. UI input changes reviewed without remaining actionable findings.

Visible desktop acceptance: actual CPU recognition/history/preview, MathML paste into MathType7.8, DOCX rendered and recognized as editable formula by Word. User then stopped Computer Use via physical Esc; further validation uses code/tests/CLI, no further desktop controls.

Packaging issues reproduced and fixed: Poppler ICU78 from host PATH shadowed Windows ICU (filter bad ICU, sanitize PATH); torchvision0.29 stable .pyd modules absent from old PyInstaller hook (collect stable extensions + codecs explicitly); latex2mathml Unicode symbol table missing (collect required runtime data). Final folder release built successfully with model, notices and docs.

Final package acceptance passed: real offline CPU/CUDA inference from outside source cwd, Chinese/spaced paths, fixed-revision model preparation/reuse, default Windows GUI/WebEngine startup, packaged MathML/AsciiMath/Typst/OMML exports, static preview asset hashes and full model SHA256. Final executable byte-identical to the accepted CPU/CUDA/startup build; resource-only final collection verified. No remaining required implementation tasks. No cross-machine clean Windows/signing/installer or broad OCR accuracy claims; detailed limits and evidence in docs/validation.md.

User follow-up: split Copy LaTeX / MathML(Word) / PNG buttons, persisted six-format LaTeX menu, automatic recognition on pasted images. Implemented window-local paste auto-load/queue with latest-image cancellation and worker is_busy property. File import/drop and history restore retain their existing behavior. TDD observed14 RED failures; all new/existing cases GREEN159+9subtests, Ruff/compileall passed. Reviewer caught blank-model-path busy-state defect, reproduced RED and fixed GREEN. Waiting-time manual edit preservation reproduced2RED and fixed with paste-time revision snapshots; narrow re-review found no remaining findings. Real CPU GUI auto-paste, loading-time edits, equation/MathML copy and latest-only history integration passed. Updated Windows folder release built successfully; fresh standalone offline CPU/CUDA inference exits0, Windows GUI alive/no stderr, final PYZ copy/queue/edit protection verified. No required amendment work remains.

# Distribution ledger — docs/superpowers/plans/2026-11-02-distribution.md

User approved creation of installation and offline portable editions. Continue from baseline c114f12 on feat/local-ocr, no unrelated user edits present. Applying executing-plans and verification-before-completion; implementation inline, independent final review completed.

Pre-flight: paths.py supplies app/data/model roots to UI/model setup/CLI; release.py stages the same frozen runtime for installer and portable; version metadata reads __version__ only. Existing installed SQLite location is unchanged.

Task 1 complete: runtime path authority, portable writable data/cache/log roots and relative contained-model settings, actionable startup errors, version1.0.0/icon. Path/persistence regressions observed RED then GREEN. Existing CPU/CUDA recognition architecture retained.

Task 2 complete: official Inno Setup7.1.1 compiler signature verified, clean allowlist stages, original license texts, frozen runtime and installer compilation exit0, ZIP64 CRC and artifact SHA256 passed. Installer3,445,596,921 bytes; portable3,657,210,795 bytes. No signing certificate supplied; no security settings changed.

Final review: two P2 findings fixed via RED→GREEN tests: release output must be new (no stale artifacts), and model loading/downloading use the same resolved path displayed/saved by UI. Latest suite170 tests+9subtests, Ruff/compileall/pip check green. Narrow review confirms fixes; no remaining code findings.

Ruling: First release1.0.0 uses current-user installation and stable AppId, single EXE because compression fits. Cost if wrong: later releases must deliberately manage versions/AppId; stable identity is now documented.
Ruling: Exclude unused Python QtQml/QtQuick bindings to avoid unrelated module trees, retain native WebEngine-linked DLLs and verify visible packaged preview/copy. Cost if wrong: a future QML feature must explicitly add its binding/resources back.
Ruling: Clean Windows Sandbox/Hyper-V unavailable; do not enable OS features or reboot. Report local strict-PATH/offline/hidden-CUDA coverage explicitly. Cost if wrong: cross-machine/driver gaps remain and require a clean-machine release qualification later.

Task 3 acceptance complete: final ZIP extracted, moved to Chinese/spaced path with settings/history retained, real offline CPU/CUDA passed; CPU tested with CUDA_VISIBLE_DEVICES=-1. Actual installation, offline installed CPU inference, same-version overinstallation and uninstallation passed; user settings/history and unrelated file preserved, owned program/uninstall registry entry removed. Native portable GUI preview → PNG clipboard → Ctrl+V auto CPU recognition/history passed; actual equation and MathML clipboard content verified, six-format menu/default check observed. Test window closed, no GUI stderr. Harness environment-key casing and Windows console decoding issues corrected without changing product/artifacts. Clean-machine qualification remains explicitly unverified, not required as an unavailable local capability; final user guide/report documents this limitation. Final artifacts and SHA256SUMS are in release/1.0.0. Preserve current branch/workspace; no remote publishing or merge requested.
