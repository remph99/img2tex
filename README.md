# Img2Tex · 本地公式识别

将公式图片转换为可编辑的 **LaTeX、MathML 和 Word 公式**。面向 Windows 的桌面应用，使用 **Xiaomi-OCR-0 在本机推理**，支持 CPU / CUDA 自由选择，日常识别、预览和导出可离线完成。

> 自行截图或复制图片 → 在窗口内按 **Ctrl+V** → 自动识别 → 编辑与预览 → 复制或导出。

## 功能

- **图片输入**：剪贴板粘贴、文件导入和拖拽；粘贴新图片后自动加载所选模型并识别。
- **本地推理**：CPU 使用 float32，CUDA 使用 float16。初始默认 CPU，不强制显卡，不在失败时悄悄切换设备。
- **编辑与预览**：LaTeX 源码可编辑，本地 KaTeX 实时预览，模型原始输出单独保留。
- **直接复制**：LaTeX、MathML(Word)、PNG 三个分体按钮，点击箭头展开格式菜单。
- **默认 LaTeX 格式**：支持无附加、`$…$`、`$$…$$`、`\(…\)`、`\[…\]`、`equation`，选择后自动记住。
- **导出**：MathML、含可编辑 OMML 的 DOCX、PNG、SVG，以及受支持结构的 AsciiMath / Typst。
- **本地历史**：SQLite 保存图像、原始/编辑后公式、设备和推理参数，可搜索与恢复。
- **离线便携包**：包含模型、Python/Qt/PyTorch 运行时，无需另装 Python 或 conda。

应用不提供内置截图或全局快捷键。截图与复制图片由用户自行完成；`Ctrl+V` 在应用窗口内粘贴图片，编辑器的纯文本粘贴及 `Ctrl+C` 复制保持正常行为。

## 下载与运行

从 [Releases](https://github.com/remph99/img2tex/releases) 下载 **v1.0.0**。仓库为私有，下载需要登录有访问权限的 GitHub 账号。

| 版本 | 合并后的文件 | 大小 | 使用方式 |
| --- | --- | --- | --- |
| 离线便携版 | `Img2Tex-1.0.0-Windows-x64-Portable.zip` | 约 3.66 GB | 完整解压后运行 `Img2Tex\Img2Tex.exe`，移动时保留整个文件夹 |

GitHub Release 单个附件需小于 2 GiB，便携版分为 **2 个分卷**。**分卷不是单独可运行的安装程序或 ZIP，必须先合并。**

1. 下载便携版的**全部两个分卷**（`.part01`、`.part02`），以及 `Join-Release.ps1`、`SHA256SUMS.txt`、`SHA256SUMS.parts.txt`，放在同一文件夹。
2. 在该文件夹的 PowerShell 中执行相应命令：

```powershell
# 合并便携版
.\Join-Release.ps1
```

脚本先校验分卷 SHA-256，再合并并校验完整文件；不会覆盖已有成品。随后解压 Portable.zip 并运行其中的 Img2Tex.exe。脚本源码见 [Join-Release.ps1](packaging/windows/Join-Release.ps1)。

若本机策略不允许运行脚本，可在命令提示符中使用系统 `copy /b` 合并，然后核对完整文件哈希：

```bat
copy /b Img2Tex-1.0.0-Windows-x64-Portable.zip.part01+Img2Tex-1.0.0-Windows-x64-Portable.zip.part02 Img2Tex-1.0.0-Windows-x64-Portable.zip
```

```powershell
Get-FileHash -Algorithm SHA256 .\Img2Tex-1.0.0-Windows-x64-Portable.zip
# 与 SHA256SUMS.txt 比对
```

发行文件未签名。当前在 Windows 11 x64 验证；Windows 10 22H2 为最低目标版本，尚未完成该系统和另一台干净 Windows 的验收。CUDA 模式需要兼容 NVIDIA 驱动，不需另装 CUDA Toolkit。统一发行包携带 CUDA 运行库，因此体积较大；CPU 模式仍可直接选择。

## 使用方法

1. 打开应用，在「模型与设置」中选择 CPU 或 CUDA。随包模型自动定位，之后记住设备选择。
2. 自行截图/复制公式图片，在应用内按 **Ctrl+V** 或点击「粘贴图片」，自动开始识别。连续粘贴时只识别最新图片。
3. 修改 LaTeX，查看实时预览；成功识别自动写入历史，编辑内容同步保存。等待加载或识别时的手动编辑不会被结果覆盖。
4. 点击「复制 LaTeX」「复制 MathML(Word)」「复制 PNG」直接复制；用右侧箭头选择默认格式或其他导出项。

导入/拖入文件后使用「开始识别」，该按钮也可手动重试。取消、恢复历史或切换设备会使旧任务失效，迟到结果不会覆盖当前内容。关闭主窗口会退出程序。

### 数据保存在哪里？

| 模式 | 历史、设置、日志与应用缓存 |
| --- | --- |
| 源码运行 | `%LOCALAPPDATA%\Img2Tex` |
| 便携版 | `Img2Tex.exe` 同级的 `data` |

便携版由同级 `portable.flag` 标识；请放在可写磁盘，退出后再备份或移动整个文件夹。随包模型使用相对路径，跟随程序迁移；手动选择的外部模型仍依赖绝对路径。

历史数据库为 `history.sqlite3`，包含公式图像与源码。不要将使用过的 `data` 加入重新发行的压缩包。数据目录不可写时明确报错，不会切换到其他历史库。

## 从源码开发

需要 Windows x64、Git 和 conda。Python 开发、测试和打包使用独立 **`img2tex` conda 环境**，禁用用户 site-packages。

```powershell
git clone https://github.com/remph99/img2tex.git
cd img2tex

# 创建环境并安装 CPU 版依赖
.\scripts\setup.ps1 -TorchBuild cpu
# 或使用 CUDA 13.0 版依赖，同样支持 CPU 模式
# .\scripts\setup.ps1 -TorchBuild cuda

conda activate img2tex
python -s -m img2tex --check-device
python -s -m img2tex --download-model --model-dir .\models\xiaomi-ocr-0
python -s -m img2tex
```

setup 脚本只针对 `img2tex` 环境；重新执行会重装所选 PyTorch 版本。核心版本：Python 3.12、PySide6 6.12.0、PyTorch 2.14.0、torchvision 0.29.0、Transformers 5.17.0，详见 [pyproject.toml](pyproject.toml) 和 [environment.yml](environment.yml)。

源码仓库不包含模型、conda 环境、构建目录或使用历史；GitHub 自动生成的 “Source code” 下载不包含可运行的软件及权重。

### 模型与离线推理

模型来自官方 [Xiaomi-OCR-0](https://github.com/xiaomi-research/Xiaomi-OCR-0)，模型仓库 `xiaomi-research/Xiaomi-OCR-0` 固定提交：

```text
bbd8cf8d21f256b3644b44cb860f3a7cecb93c30
```

权重约 1.75 GB，下载器分段续传并验证 SHA-256。下载是单独操作，不上传输入图片；权重、渲染器和字体准备完整后，日常使用不依赖识别 API。发行包已经包含这些文件。

默认优先使用项目/EXE 同级 `models\xiaomi-ocr-0`，可在界面选择其他完整本地模型目录。没有匹配固定版本清单的模型，其历史版本标识为 `local-unverified`。

## 工作流与目录

```mermaid
flowchart LR
    A[粘贴 / 文件 / 拖拽] --> B[图片校验与预处理]
    B --> C[独立模型进程 CPU / CUDA]
    C --> D[原始输出与 LaTeX]
    D --> E[编辑与本地预览]
    D --> F[(SQLite 历史)]
    E --> F
    E --> G[复制 / 图片 / MathML / Word]
```

| 路径 | 内容 |
| --- | --- |
| `src/img2tex/ui/` | 桌面界面、本地渲染与剪贴板交互 |
| `src/img2tex/engine.py` | 推理进程、设备选择、取消与任务隔离 |
| `src/img2tex/model_setup.py` | 固定模型版本、下载与完整性校验 |
| `src/img2tex/exports.py` | 公式格式转换与导出 |
| `src/img2tex/storage.py` / `paths.py` | 历史设置、安装与便携路径 |
| `scripts/` / `packaging/` | conda 环境、Windows 构建与发行工具 |
| `tests/` / `docs/` | 回归测试、工作流与验收记录 |

## 测试与构建

```powershell
conda activate img2tex
$env:QT_QPA_PLATFORM='offscreen'
$env:QT_OPENGL='software'
$env:QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --disable-gpu-compositing'
python -s -m pytest -q
python -s -m ruff check src tests scripts
```

完成离屏测试后，关闭该终端或移除上述 Qt 测试变量，再启动可见桌面。

```powershell
# 正常 conda 终端中验证实际模型
python -s -m img2tex --smoke .\tests\fixtures\energy.png --device cpu --max-tokens 96 --output .\artifacts\cpu.json
python -s -m img2tex --smoke .\tests\fixtures\energy.png --device cuda --max-tokens 96 --output .\artifacts\cuda.json

# 生成 dist\Img2Tex，需已准备完整模型
.\scripts\build.ps1

```

正式便携发行包见 Releases；`dist` 是构建中间目录。版本唯一来源为 `src/img2tex/__init__.py`。

v1.0.0 已通过 **170 项测试及 9 项子测试**，并在本机验证离线 CPU/CUDA 真实识别、便携目录迁移、历史与设置保留，以及可见界面的预览、复制和粘贴自动识别。分卷合并脚本另有发行工具检查。详见 [发行验收](docs/distribution-validation.md)、[功能验收](docs/validation.md)、[工作流](docs/workflow.md)。

## 兼容范围与限制

- MathType 通过 MathML 导入，本机 MathType 7.8 验证过基础公式；不直接生成 MTEF/OLE 对象。
- DOCX 内含可编辑 OMML；剪贴板 MathML 与 DOCX 导出是不同链路，粘贴效果取决于接收软件。
- AsciiMath/Typst 只覆盖支持的常见结构，无法保真时明确报错，不是完整 LaTeX 编译器。
- 输入最长边最多缩至 2048，限制 50 MiB / 4000 万像素；识别结果需核对，尚无大规模手写、模糊图片或复杂公式精度承诺。
- 未在另一台干净 Windows 或无 NVIDIA 驱动的实体机器验收；本机 CPU 测试包含隐藏 CUDA 设备的检查。
- 当前不包含 PDF 整页解析、批量识别、云账号、翻译、AI 编辑和自动更新。

## 第三方组件

推理模型采用 Xiaomi-OCR-0；界面采用 PySide6/Qt，预览采用 KaTeX/MathJax，转换使用 latex2mathml、mathml2omml 与 python-docx。感谢各上游项目。

第三方组件各自遵循其许可证；模型为 Apache-2.0，其他许可和原始文本见 [THIRD_PARTY_NOTICES](packaging/THIRD_PARTY_NOTICES.txt)、[导出依赖说明](docs/export-notices.md) 及发行目录中的许可证。项目当前未另行声明自身源码的开源许可证。
