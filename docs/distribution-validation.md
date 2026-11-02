# Img2Tex 1.0.0 发行验收

2026-11-02；Windows 11 x64，Ryzen 9 7900X、64 GB、RTX 4070 Ti SUPER 16 GB。构建、测试和发布工具全部使用独立 conda `img2tex` 环境，Python 3.12.16。

## 成品

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `Img2Tex-1.0.0-Windows-x64-Setup.exe` | 3445596921 | `53736aac58003b0da0c4e98ac98a3559f90005121927ad34c1fe9480d42ed645` |
| `Img2Tex-1.0.0-Windows-x64-Portable.zip` | 3657210795 | `a64006a78b7567224f20026badb841882d726ce8825347f9e1df216b006ef957` |

均位于 `release/1.0.0`，内含固定 Xiaomi-OCR-0 提交 `bbd8cf8d21f256b3644b44cb860f3a7cecb93c30` 及权重。两种模式共用同一份识别代码和 CPU/CUDA 运行时。安装版压缩后可使用单独 EXE，无需配套 BIN 分卷；便携版使用 ZIP64。发行文件未签名。

## 构建与回归

- PyInstaller 6.22.3 构建退出 0；Inno Setup 7.1.1 编译退出 0。编译器安装文件 Authenticode 为有效签名，发布应用本身无签名证书。
- 最新回归：170 tests passed，9 subtests passed；Ruff、compileall、pip check、Git 空白检查通过。
- 测试涵盖正常/便携数据目录、相对模型设置迁移、外部模型绝对路径、数据路径不可写不回退、实际 SQLite 历史设置迁移、路径输入归一化、干净发行清单和拒绝覆盖已有发布目录。
- 独立代码审查发现的两个问题已建立 RED→GREEN 回归：旧输出目录混入上次产物、相对模型目录按不同基准保存和加载。均已修复。
- 发布从明确清单复制 EXE、运行库、固定模型文件、用户说明和许可证。安装版不带 `portable.flag` 或用户数据；便携版仅带 `portable.flag` 和空白数据目录说明。归档不含开发数据库、历史图片、测试或日志。
- ZIP 完整 CRC 检查及最终两个成品 SHA-256 复核通过。每个 payload 的 `build-manifest.json` 记录文件哈希、版本和固定模型标识。
- 保留之前已修复的 Windows ICU、torchvision stable 扩展、转换符号表资源。移除未使用的 Python QtQml/QtQuick 绑定，仍保留 WebEngine 所需的原生 DLL；发行目录约 5.0 GiB。

## 实际发行包验证

验收使用实际最终 ZIP/Setup.exe，所有测试数据位于独立 `build/acceptance` 目录，未使用原开发历史数据库。启动时工作目录不在程序目录，`PYTHONPATH` 为空，PATH 只含 Windows 系统目录，`HF_HUB_OFFLINE=1`；未断开系统网络或修改防火墙设置。

便携版已完整解压，保存测试历史、默认 equation 复制格式及相对模型路径后，将整个目录移动到中文且含空格的新路径。实际 EXE 的数据目录、模型目录随移动更新，设置和历史仍可读取，没有回退到测试用户目录。随后使用随包模型完成 CPU 与 CUDA 真实公式识别；CPU 测试额外设置 `CUDA_VISIBLE_DEVICES=-1`，确认没有可见 CUDA 设备仍能推理。

可见界面直接使用从最终 ZIP 解压、迁移后的 EXE，PATH 仅系统目录，CPU 模式且隐藏 CUDA：编辑 `\frac{a}{b}+x^2` → KaTeX 显示分式和上标 → 复制 PNG → Ctrl+V → 自动加载模型并识别 → 正确显示 `\frac {a}{b} + x ^ {2}`，新增第二条历史。直接复制 LaTeX 得到已保存的 `equation` 外层格式，MathML 剪贴板可解析且保留 `mfrac`/`msup`。菜单显示六种格式，并勾选原保存的 equation。退出测试窗口后，SQLite 中的模型仍为相对路径，历史和默认格式已保存。程序 stderr 为空。

安装版使用实际 Setup.exe 静默安装到独立中文含空格目录：首次安装成功，无 `portable.flag`，数据位置仍为测试用户的 `LocalAppData/Img2Tex`；实际安装后 EXE 完成离线 CPU 识别。随后同版覆盖安装成功，原历史、设置及安装目录中自建的非安装器管理文件均保留。运行实际卸载器后，程序文件和卸载注册项移除，原历史、设置与额外文件仍保留。测试没有使用或改动真实用户的 Img2Tex 数据库。

## 范围与限制

- 本机缺少 Windows Sandbox 可执行文件和 Hyper-V 命令，未启用系统功能、重启或修改安全设置。因此尚未在另一台干净 Windows 机器验证，也不能将精简 PATH 等同于干净系统验收。
- CPU 隐藏 CUDA 的检查发生在装有 NVIDIA 驱动的本机；尚未在无 NVIDIA 驱动的实体机器验证。CPU/CUDA 的软件选择和真实推理已覆盖。
- 数据目录不可写由错误条件回归验证，没有在真实只读移动介质或各类企业 ACL 上验收。
- Windows 10 22H2 为安装器最低目标版本，尚无该系统实测记录。不同显卡驱动、旧硬件和复杂公式的质量范围沿用 `validation.md` 中的限制。
- 安装器验收使用同版覆盖安装；没有假称跨版本数据库迁移或未来版本升级已通过。

本机原始证据：`build/release-build.json`、`build/distribution-acceptance.json`、`build/distribution-acceptance.log`、`build/distribution-tests.log`、`build/installer-compile.log` 和 `build/acceptance` 下各次验收的输入输出与安装日志。上述开发证据不放入发行包。
