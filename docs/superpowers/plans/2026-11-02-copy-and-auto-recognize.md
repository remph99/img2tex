# Copy controls and automatic recognition amendment

User requested split copy controls like SimpleTex and automatic recognition after pasting a new image.

Design: replace the separate wrapper combo with a Copy LaTeX split button. Its exclusive menu selects and persists one of plain, $…$, $$…$$, \(…\), \[…\], or equation wrappers. The primary button copies current edited LaTeX with that wrapper; source/history are not rewritten. Expose Copy MathML(Word) and Copy PNG directly, retaining the existing additional export actions in their menus.

Pasted clipboard images and copied local image files trigger recognition. Load the selected local model when needed. Keep only the latest pasted image while a model loads or a cancelled worker task stops. Respect explicit cancellation, model changes, history restoration and failed downloads; do not re-run historical images. File import/drop remain existing manual workflows. Existing CPU/CUDA choice and no-global-hotkeys constraints remain.

- [x] Add failing regression checks for split copy/default persistence and auto-paste scheduling/lifecycle.
- [x] Implement only UI changes plus a public worker busy property to avoid racing physical cancellation.
- [x] Run focused/full conda pytest, static checks and a real-model auto-paste integration check.
- [x] Rebuild and verify the Windows folder release; update usage/validation docs.
