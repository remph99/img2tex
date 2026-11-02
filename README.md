# Img2Tex 本地公式识别

Windows 桌面应用：图片文件、拖拽或剪贴板 → 本地 Xiaomi-OCR-0 → LaTeX 编辑与预览 → 复制、导出、本地历史。

## 直接运行

正式发行文件位于 `release\1.0.0`，两种版本均包含模型和 CPU/CUDA 运行库，无需安装 Python、conda 或另行下载权重：

| 版本 | 文件 | 使用方式 |
| --- | --- | --- |
| 安装版 | `Img2Tex-1.0.0-Windows-x64-Setup.exe`（约 3.45 GB） | 运行安装向导，默认安装到当前用户目录，可创建快捷方式 |
| 离线便携版 | `Img2Tex-1.0.0-Windows-x64-Portable.zip`（约 3.66 GB） | 完整解压后双击 `Img2Tex.exe`，移动时保留整个文件夹 |

安装版的历史、配置、日志和应用缓存保存在 `%LOCALAPPDATA%\Img2Tex`，卸载保留这些数据。便携版由同级 `portable.flag` 标识，使用同级 `data` 目录；须放在可写磁盘，退出后再移动或备份。随包模型使用相对路径，移动整个便携目录后继续可用；手动选择的外部模型仍依赖原绝对路径。

发行文件未签名。可用 `Get-FileHash -Algorithm SHA256 <文件路径>` 与同目录 `SHA256SUMS.txt` 比对完整性。当前在 Windows 11 x64 本机验收，尚未在另一台干净 Windows 机器验证；详细记录见 [发行验收](docs/distribution-validation.md)。

本机开发环境已经创建：`conda activate img2tex`。在本项目目录执行：

```powershell
python -s -m img2tex
```

构建中间运行目录位于 `dist\Img2Tex`，约 5.0 GiB，包含模型及 CUDA 运行库。正式分发请使用上面的安装包或便携压缩包；模型不嵌入 EXE。

1. 在「模型与设置」选择 **CPU** 或 **CUDA** 和模型目录。初始为 CPU，之后记住你的选择；也可以提前点击「加载模型」。
2. 自行用截图工具截图或复制图片，在应用窗口内按 `Ctrl+V` 或点击「粘贴图片」，即可自动识别；模型尚未加载时会自动加载所选本地模型。连续粘贴只识别最新图片。文件导入/拖拽仍可点击「开始识别」，该按钮也可手动重试。
3. 编辑 LaTeX，预览自动刷新；「模型原始输出」保留原始文本。成功结果自动进入本地历史，编辑同步保存。
4. 点击「复制 LaTeX」「复制 MathML(Word)」或「复制 PNG」直接复制；点击按钮右侧箭头展开菜单。LaTeX 菜单可选无特殊附加、`$…$`、`$$…$$`、`\(…\)`、`\[…\]`、`equation`，选中后记住默认格式，后续点击复制会自动附加。编辑器源码不随格式选择而改写。其他按钮的下拉菜单保留 AsciiMath、Typst、SVG、PNG 保存及可编辑 DOCX 导出。

`Ctrl+V` 在本应用窗口内粘贴图片；编辑器中粘贴纯文本仍按正常文本粘贴处理。`Ctrl+C` 保持正常文本复制，也可使用「复制 LaTeX」按钮。应用不注册全局快捷键，也不提供内置截图。截图与将图片放入剪贴板由用户自行完成。托盘菜单可粘贴、恢复窗口与退出；关闭主窗口会退出程序。

## CPU 与 CUDA

两种设备共用同一份权重。CPU 使用 float32；CUDA 使用 float16，需要兼容的 NVIDIA 驱动。切换设备会结束旧模型进程，再加载新模型。CUDA 不可用会显示错误，请选择 CPU；不会悄悄换设备。CUDA 版 PyTorch 也能执行 CPU 推理。

本机已安装 CUDA 版 PyTorch，并实际验证 CPU 与 RTX 4070 Ti SUPER 推理。两份发行包均可选择 CPU，无需另装 CUDA Toolkit；CUDA 模式需要兼容 NVIDIA 驱动。从源码部署时也可以安装体积较小的 CPU 版依赖。当前统一发行包包含 CUDA 运行库，因此体积较大。

## 从源码搭建 conda 环境

需要已有 conda、Windows x64。所有 Python 开发、测试和打包均在独立 `img2tex` 环境，禁用用户 site-packages。

```powershell
# 创建环境并安装 CPU 版依赖
.\scripts\setup.ps1 -TorchBuild cpu
# 或安装 CUDA 13.0 版 PyTorch，同样支持 CPU 模式
.\scripts\setup.ps1 -TorchBuild cuda
conda activate img2tex
python -s -m img2tex --check-device
python -s -m img2tex
```

脚本只修改 `img2tex` 环境，不安装系统 CUDA Toolkit。已有环境中重新执行 setup 会重装所选 PyTorch 版本。主要固定版本：Python 3.12、PySide6 6.12.0、Transformers 5.17.0、PyTorch 2.14.0、torchvision 0.29.0；具体依赖见 `pyproject.toml`。

## 模型准备与离线运行

采用官方 [Xiaomi-OCR-0](https://github.com/xiaomi-research/Xiaomi-OCR-0)，模型仓库 `xiaomi-research/Xiaomi-OCR-0` 固定版本 `bbd8cf8d21f256b3644b44cb860f3a7cecb93c30`。权重约 1.75 GB，首次下载需要网络。当前机器已下载并校验完毕。

```powershell
conda activate img2tex
python -s -m img2tex --download-model --model-dir .\models\xiaomi-ocr-0
```

也可以点击界面「下载固定版本模型」。下载分段续传，校验 SHA-256 后发布权重；失败可在同一目录重试。不要将 `.part` 文件改名充当完整模型。

默认优先使用项目/EXE 同级 `models\xiaomi-ocr-0`，否则为 `%LOCALAPPDATA%\Img2Tex\models\xiaomi-ocr-0`；便携版始终优先同级模型路径。界面可选择现有完整目录，设置中保存的目录优先。同级模型设置以相对路径保存，外部模型保存绝对路径。模型目录没有下载器的匹配清单时，历史版本记录为 `local-unverified`。

日常识别仅加载本地权重，不调用识别 API；KaTeX、MathJax、字体及所有导出均在本地。模型下载是单独操作，不上传输入图片。历史和设置位于数据目录的 `history.sqlite3`，包含白底合成后的原尺寸 PNG、原始/规范化/编辑后源码、设备、耗时、推理参数和图像哈希。最多显示最近 100 条匹配历史。备份数据库时先退出程序。

## 兼容范围

- MathType：复制 MathML 后粘贴到 MathType。本机 MathType 7.8 已验证基础公式；不声称直接生成 MTEF/OLE 对象。
- Word：导出的 DOCX 内含 OMML 可编辑公式；与剪贴板纯文本 MathML 是两条链路。
- PNG 为渲染后的公式裁剪，SVG 为本地 MathJax 生成的独立路径图。
- AsciiMath/Typst 为常见结构转换。无法保真或不支持的结构明确报错，源码保持不变；它们不是完整 LaTeX 编译器。带字体样式等结构可能只能导出 MathML/DOCX/图片。
- 输入长边最多缩到 2048，限制 50 MiB/4000 万像素；透明图合成白底，修正 EXIF。截图工具由用户自行选择。
- 识别精度取决于图像与模型，需核对复杂公式。取消使当前任务失效，模型在 token 边界停止；失败、取消或达到输出上限的结果不写成功历史。
- 本版不含 PDF 整页解析、翻译、云账号、AI 编辑和批量识别。

## 验证和构建

```powershell
conda activate img2tex
$env:QT_QPA_PLATFORM='offscreen'
$env:QT_OPENGL='software'
$env:QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --disable-gpu-compositing'
python -s -m pytest -q
python -s -m ruff check src tests scripts
# 完成测试后关闭本终端，或移除上述 Qt 测试变量，再运行可见桌面
```

真实模型验证示例：

```powershell
python -s -m img2tex --smoke .\tests\fixtures\energy.png --device cpu --max-tokens 96 --output .\artifacts\cpu.json
python -s -m img2tex --smoke .\tests\fixtures\energy.png --device cuda --max-tokens 96 --output .\artifacts\cuda.json
.\scripts\build.ps1
```

打包脚本生成中间运行目录；如项目存在完整模型目录，会同时复制到发行目录。然后在同一 conda 环境执行：

```powershell
python -s scripts/release.py
# 编译器不在默认位置时：
python -s scripts/release.py --compiler 'C:\Tools\Inno Setup 7\ISCC.exe' --output .\release\new-build
```

需要 Inno Setup 7 编译器，本机已验证的 7.1.1 位于 `build\tools\InnoSetup\ISCC.exe`。发布脚本校验模型 SHA-256，从明确清单复制干净运行时，生成安装包、ZIP64 便携包和校验文件。输出目录必须尚不存在，脚本不会覆盖旧发行文件；不要把使用过的 `data` 加入发行包。版本唯一来源为 `src/img2tex/__init__.py`，图标与 Windows 版本资源由 `scripts/prepare_release.py` 生成。

详细实测、边界和未覆盖项见 `docs/validation.md`、`docs/distribution-validation.md`；工作流及模块见 `docs/workflow.md`。第三方许可证保留在本地 assets、发行目录 `_internal` 的包元数据和 notices 中，转换依赖另见 `docs/export-notices.md`。
