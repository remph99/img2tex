from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata, get_package_paths
from pathlib import Path

root = Path(SPECPATH)
datas = collect_data_files('img2tex')
datas += [(str(root / 'docs' / 'export-notices.md'), 'notices')]
for package in ('transformers', 'torch', 'tokenizers', 'huggingface_hub', 'safetensors', 'tqdm', 'regex', 'numpy', 'Pillow', 'PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'latex2mathml', 'mathml2omml', 'python-docx'):
    datas += copy_metadata(package)
hidden = collect_submodules('transformers.models.qwen3_5')
hidden += ['img2tex.engine', 'img2tex.ui.main', 'PIL.ImageQt', 'latex2mathml.converter', 'mathml2omml']
vision_path = Path(get_package_paths('torchvision')[1])
# torchvision 0.29 loads _C_stable.pyd dynamically; older hooks only know _C.
binaries = collect_dynamic_libs('torchvision')
binaries += [(str(path), 'torchvision') for path in vision_path.glob('*.pyd')]
a = Analysis(
    [str(root / 'scripts' / 'desktop_entry.py')], pathex=[str(root / 'src')],
    binaries=binaries, datas=datas, hiddenimports=hidden,
    excludes=['pytest', 'matplotlib', 'sklearn', 'pandas', 'scipy', 'IPython', 'tkinter',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets'],
    noarchive=False,
)
# Qt uses Windows' unsuffixed ICU API. Poppler on the build host's PATH can
# otherwise contribute an incompatible ICU78 with only versioned exports.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
# Converter imports its Unicode symbol table at runtime.
a.datas += [(str(Path(destination) / Path(source).name), source, 'DATA')
            for source, destination in collect_data_files('latex2mathml')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Img2Tex', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, icon=str(root / 'src/img2tex/assets/app.ico'),
          version=str(root / 'build/version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Img2Tex')
