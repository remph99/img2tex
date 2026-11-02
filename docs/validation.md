# 本地验收记录

日期：2026-11-02。范围为本机 Windows x64；未把少量样例当作准确率基准。

## 环境

- 独立 conda 环境 `img2tex`，Python 3.12.16，`PYTHONNOUSERSITE=1`；未在 base 环境开发。
- CPU：AMD Ryzen 9 7900X，内存约 64 GB。CUDA：NVIDIA GeForce RTX 4070 Ti SUPER，显存 16 GB。
- PyTorch 2.14.0+cu130 / torchvision 0.29.0+cu130 / Transformers 5.17.0 / PySide6 6.12.0。
- 实际安装版本清单见 `environment-versions.txt`。CPU 路径使用 float32、最多 8 个线程；CUDA 使用 float16。
- 模型固定提交 `bbd8cf8d21f256b3644b44cb860f3a7cecb93c30`。
- 权重 1,746,937,856 bytes，SHA-256：`d4551e9f6127ac9e35cff7b4f7a72a90410e03e6c8676a36f0e2b7eaeb5d5348`。下载完成后校验，损坏分段不会发布为完整权重。

## 真实模型结果

所有结果由实际模型生成，没有替换为演示数据。下表为就绪模型的一次识别耗时（包含图像准备和生成，不包含模型加载），不能作为跨机器性能承诺。

| 输入 | CPU | CUDA | 本次结果核对 |
|---|---:|---:|---|
| `E = mc²` | 3.57 s | 1.89 s | 公式内容及上标正确，模型使用 `\mathrm` |
| 二次公式分式与根号 | 4.07 s | 1.67 s | 分子、根号、正负号、分母正确 |
| 2×2 圆括号矩阵 | 3.88 s | 1.10 s | 四个元素及行列正确，输出为 array + 定界符 |
| 分段函数 | 6.28 s | 1.72 s | 两个分支及条件正确，输出为 array + 左大括号 |

质能公式图片为本项目自制验收样例；其余三张由本地公式渲染器生成，再交给模型识别。它们验证干净印刷公式闭环，不覆盖真实拍照、模糊、复杂手写、整页文档或大量公式的质量分布。

原始 JSON、样例 PNG 和日志保存在本机 `artifacts/validation` 与 `build`（不纳入 Git）。`complex-formulas.json` 保存参考源码、原始/规范化输出、设备、耗时、参数、哈希和模型版本。

另外对真实模型进程验证了：CPU 任务取消 → 收到 cancelled 且没有泄漏成功结果 → 同进程重新识别成功 → 切换至 CUDA 重新加载并识别成功 → 进程干净结束。记录见 `artifacts/validation/lifecycle.json`。

## 自动化回归

复制/粘贴功能完成时：**159 tests passed，另有 9 subtests passed**；发行改造后的最新结果为 **170 tests passed，另有 9 subtests passed**，详见 [发行验收](distribution-validation.md)。Ruff、compileall、pip check 通过。

覆盖图片校验/白底/尺寸、保守定界符清理、原始输出不随编辑改变、历史恢复、任务取消和迟到结果过滤、CPU/CUDA 选择、模型目录失效、下载续传和哈希拒绝、离线预览、错误 LaTeX、公式 PNG 边界、独立 SVG，以及常见导出结构。

最终输入方式另有针对性回归：窗口内 Ctrl+V 图片粘贴、编辑器图片粘贴、纯文本正常粘贴、Ctrl+C 正常复制、其他窗口不被拦截、旧快捷键配置不被读取。已删除不再适用的内置截图/全局快捷键实现及其测试。

追加修改验证了三个分体复制按钮、LaTeX 六种默认格式（含 equation）的勾选/保存/恢复、直接 MathML 复制，以及粘贴后的自动加载/识别。连续粘贴等待旧任务物理取消后只提交最新图片；取消、历史恢复、无效图片、模型路径为空和模型/下载失败均有回归。源码或模型原始输出不随复制格式变化。模型加载或旧任务取消的等待期间手动编辑的源码同样保留，不会被识别结果覆盖。

真实 CPU GUI 集成（使用当前 MainWindow、ModelProcess、SQLite 和本地渲染器）完成：首次粘贴自动加载模型并识别 `E=mc²`，保留加载期间手动改为 `E=mc^{2}` 的编辑值 → 分体按钮复制 equation / MathML → 推理期间连续粘贴分式和矩阵 → 仅最新矩阵写入第二条历史。记录为 `artifacts/validation/copy-auto-integration.json`，UI/菜单截图为同目录 `copy-auto-ui.png`、`copy-formats-menu.png`。本次使用自己的测试窗口与离屏 Qt 测试，没有控制用户其他应用。

导出复核修复了两处语义缺陷：嵌套 token 操作符不再静默丢失内容；Typst 上下标使用 `attach`，不额外添加可见括号。不支持的结构明确拒绝。

## 可见桌面验收

- 完成文件导入 → CPU 模型加载 → 实际识别 → 本地 KaTeX 预览 → SQLite 成功历史。
- 将实际识别结果复制成 MathML，粘贴到本机 MathType 7.8 后显示 `E = mc²`。
- 本地导出 DOCX 后在 Word 打开，显示公式；选中时 Word 识别为公式并提供编辑控件。DOCX ZIP 中有原生 `m:oMath`，不是图片。
- 在完成上述检查后，用户按 Esc 停止了桌面自动操作；此后未继续控制桌面。最终 Ctrl+V 调整由 Qt 自动化测试验证，没有宣称为再次人工点击通过。

## 打包验证与修复

构建采用 conda 环境内 PyInstaller 文件夹发行版。已修复三个本机可复现问题：

1. 构建宿主 PATH 中 Codex Poppler 的 ICU78 被误收集，缺少 Qt 所需的无版本后缀符号。排除该 ICU 及其孤立数据 DLL，使用 Windows 系统 ICU，并清理构建 PATH。
2. 当前 torchvision 使用 `_C_stable.pyd` / `image_stable.pyd`，旧打包钩子只寻找 `_C`。显式收集新扩展与图像 codec DLL；修复后独立 EXE 的 CPU 真实识别已通过。
3. `latex2mathml` 的 `unimathsymbols.txt` 是运行时必需资源，只有 Python 模块和许可证不足以完成转换。显式收集该数据文件；补齐后以发行包的 PYZ/模块/数据运行 MathML、AsciiMath、Typst 与 DOCX 检查，均通过，未借用源码环境的转换器资源。

最终发行目录为 `dist/Img2Tex`（约 5.1 GiB，含模型及 CUDA 运行库），构建退出码 0。最终检查通过：

- 从项目目录之外启动 EXE，CPU 和 CUDA 实际识别均退出 0；两者结果一致，记录分别为 float32 / float16。运行时设置 `HF_HUB_OFFLINE=1`。
- 中文且带空格的输入/输出路径通过，使用 EXE 同级模型目录，不依赖源码 PYTHONPATH。
- Windows 平台默认 GUI 启动后持续运行，Qt WebEngine 子进程正常，stderr 无错误；只观察进程状态，没有继续桌面输入操作。Qt 加载的是 Windows 系统 ICU。
- 固定版本模型准备命令退出 0，正确复用并校验现有完整权重。网络分段中断/损坏校验另由本地 HTTP 回归测试覆盖。
- 发行包的 PYZ/模块/数据独立完成 MathML、AsciiMath、Typst 和可编辑 DOCX 检查；最终自动构建的符号表文件哈希匹配，DOCX 模板存在。
- 本地预览资源与源码文件哈希匹配。最终 PYZ 含 Ctrl+V，且不含已删除的截图/全局热键模块。
- 重新校验发行目录中的全部模型权重 SHA-256，与固定官方哈希一致。模型准备/下载逻辑及本地资源沿用已验证实现。

本机日志为 `build/release-{cpu,cuda,download,windows}.*`；原始结果、中文路径样例、DOCX 与 `release-integrity.json` 位于 `artifacts/validation`。以上为早期文件夹构建记录；1.0.0 便携版记录见 [发行验收](distribution-validation.md)，仍未签名。

复制菜单/粘贴自动识别更新已重新打包：`build/copy-auto-package-final.log` 构建退出 0。新版 EXE 在项目目录之外的离线 CPU/CUDA 实测均退出 0，结果一致；Windows GUI 启动并持续运行，stderr 为空。最终归档确认包含三个分体按钮、默认格式菜单、自动识别队列及等待期间编辑保护，转换符号表仍完整。对应日志为 `build/copy-auto-release-{cpu,cuda,gui}.*`，原始模型结果为 `artifacts/validation/copy-auto-release-{cpu,cuda}.json`。

## 适用限制

- 未在另一台干净 Windows 机器验收，也没有为每种驱动、Windows 版本和 CPU-only PyTorch 安装分别构建发行包。本机 CPU 推理是在 CUDA 版 PyTorch 上实测；安装脚本另外提供 CPU-only 选项。
- 未做完整手写公式、模糊图像、极长公式或多语言大规模精度评测；输出仍需用户核对。
- MathType 仅验收基础公式的 MathML 导入。复杂结构、旧版 MathType、剪贴板原生 MTEF/OLE 不作全面兼容承诺。
- AsciiMath/Typst 不是全功能 LaTeX 转译，无法保真时拒绝导出；MathML/DOCX 也受所支持结构范围限制。
- 未安装可选 fused CUDA kernel；当前模型使用可工作的 PyTorch 参考实现，日志可能提示这些可选加速库缺失。
- 1.0.0 当前仅分发便携版，尚无跨机器验收和代码签名；不含自动更新、PDF 整页解析、云端服务和批量识别。
