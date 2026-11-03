# Img2Tex 2.0.0 approved design

The user approved implementation on 2026-11-02 after reviewing the resource,
startup, CPU-only distribution, and menu redesign proposals in this chat.

- Keep the fixed Xiaomi-OCR-0 BF16 checkpoint, inference settings, exports, and
  existing history format. Both editions contain complete local model files.
- Trim unused Qt debug and locale resources only after testing the real frozen
  application. Keep dynamically required native libraries and licenses.
- Show a menu bar (File, View, Settings, Help). Keep Import, Paste, Recognize,
  Cancel visible. Keep existing copy controls. Replace the bottom model dock
  with a device settings dialog, and add About using the sole version source.
- Automatically resolve the bundled model; preserve valid legacy custom paths,
  fall back with a notice from invalid paths to the valid bundled model. Remove
  GUI download/path controls and their unused code; retain CLI model preparation.
- Start the model worker after the window is shown. Detect GPU support, load and
  warm up the selected model, then report ready. Queue the latest pasted image;
  never write warmup output to history. Reuse the worker for subsequent images.
- Full edition initially prefers working CUDA, then respects saved CPU/CUDA
  preference. CUDA initialization/load/warmup failure falls back once to CPU
  with an explicit reason. CPU-only never initializes CUDA.
- Settings apply only changed devices; disable switching during recognition.
  Retain a retry entry for model initialization errors.
- Version is 2.0.0. CPU-only release names end in -cpuonly before the extension.
  Keep Img2Tex.exe internally, show CPU Only in the title and About.
- Share source and build configuration; isolate build environments, work paths,
  runtime metadata and output directories. Preserve the 1.0.0 release.
- Deliver two portable ZIPs with checksums and complete weights, compare size
  and startup/recognition time, and document verification limits explicitly.

Alternatives considered: keeping only a universal package gives limited savings;
CPU-only removes GPU runtime weight without changing the model. Quantization and
engine replacement were excluded because they expand compatibility/accuracy risk.
