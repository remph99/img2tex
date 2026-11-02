# Img2Tex 1.0.0 distribution specification

Approved by user: produce a Windows x64 installable edition and a fully offline portable edition from the completed local OCR application.

Both contain Python/Qt/PyTorch CPU+CUDA runtime, fixed Xiaomi-OCR-0 weights, offline renderer/fonts/converters and licenses. Keep existing recognition/copy behavior; target machines need neither conda nor Python. CUDA remains optional and requires a compatible NVIDIA driver. No signing certificate was provided, so deliver unsigned artifacts without changing system security settings.

Installer: current-user Inno Setup installation under LocalAppData/Programs/Img2Tex, optional desktop and Start Menu shortcuts, uninstall entry, stable AppId and upgrade preserving LocalAppData/Img2Tex user data. Bundled models installed beside EXE. Do not include portable.flag or test/developer data. Use single Setup.exe if compressed size permits, otherwise supported .bin slices distributed together.

Portable: ZIP64 archive containing one Img2Tex folder with EXE, _internal, models, portable.flag, docs/notices; clean empty data on first run. Managed history/settings/logs/cache stay in data. Store model locations inside application folder relatively; external custom model paths remain absolute by explicit user choice. Detect missing/unwritable portable data directories with actionable errors, never silently switch to a user-profile database.

Release metadata: version1.0.0, original Img2Tex x² icon, matching EXE/installer metadata, user guide, third-party notices and package/model SHA256 manifests. Clean artifacts only, no development history/screenshots/logs.

Acceptance: regression tests, offline CPU and CUDA real-model inference from packaged runtime, GUI startup and retained paste/copy behavior; moved portable directory with saved history/settings resolves bundled model; fresh install, upgrade, uninstall preserves user data. Test Chinese/spaced paths. Probe clean Windows isolation availability; explicitly document any untestable clean-machine condition rather than claiming it passed.
