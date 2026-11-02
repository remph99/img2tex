# Implementation ledger — docs/superpowers/plans/2026-11-02-local-ocr.md

User approved A and execution, adding CPU/CUDA selection and a new conda env.
Existing root contained analysis only. No original product files to preserve except analysis. Environment img2tex created successfully (Python 3.12.16).
Pre-flight: UI/engine/storage/exports consume the exact interfaces frozen in the spec.
Ruling: New product repository in designated directory; no linked worktree needed because there was no pre-existing Git repository/branch or product code.
Ruling: CUDA wheel may also run CPU; GUI exposes explicit CPU/CUDA, initial CPU, no hidden fallback. CPU-only installation documented separately.

Completed core, local exports and desktop implementation. Dedicated img2tex env uses Python3.12.16, torch2.14.0+cu130, Transformers5.17.0 and PySide6.12.0. Fixed model revision and SHA256 verified; real CPU/CUDA energy, fraction/root, matrix and cases samples passed manual content checks. Real worker cancellation/retry/device-switch/clean-stop passed.

Latest user amendment supersedes initial screenshot scope: screenshots/copying images are external, no global hotkeys or built-in screenshot. Ctrl+V pastes clipboard images only inside the app; text paste and Ctrl+C copy keep normal editor behavior. Obsolete capture/hotkey modules and tests removed; old stored hotkey values ignored and preserved.

Fresh source tests:138 passed +9subtests, Ruff/compileall/pip check passed. Read-only reviews found and then verified fixes for nested-token export loss, Typst visible grouping and custom-model identity. UI input changes reviewed without remaining actionable findings.

Visible desktop acceptance: actual CPU recognition/history/preview, MathML paste into MathType7.8, DOCX rendered and recognized as editable formula by Word. User then stopped Computer Use via physical Esc; further validation uses code/tests/CLI, no further desktop controls.

Packaging issues reproduced and fixed: Poppler ICU78 from host PATH shadowed Windows ICU (filter bad ICU, sanitize PATH); torchvision0.29 stable .pyd modules absent from old PyInstaller hook (collect stable extensions + codecs explicitly); latex2mathml Unicode symbol table missing (collect required runtime data). Final folder release built successfully with model, notices and docs.

Final package acceptance passed: real offline CPU/CUDA inference from outside source cwd, Chinese/spaced paths, fixed-revision model preparation/reuse, default Windows GUI/WebEngine startup, packaged MathML/AsciiMath/Typst/OMML exports, static preview asset hashes and full model SHA256. Final executable byte-identical to the accepted CPU/CUDA/startup build; resource-only final collection verified. No remaining required implementation tasks. No cross-machine clean Windows/signing/installer or broad OCR accuracy claims; detailed limits and evidence in docs/validation.md.
