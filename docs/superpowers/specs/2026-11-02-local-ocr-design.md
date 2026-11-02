# Img2Tex 本地公式识别：已批准设计

用户批准方案 A，并要求开发使用新建 conda 环境、CPU/CUDA 可选。此文档固定当前执行范围。

## 目标
Windows 桌面程序，图片/拖拽/剪贴板 → 本地 Xiaomi-OCR-0 → LaTeX 编辑和预览 → 本地复制导出及历史。
执行中用户修订：删除内置截图和全局截图/粘贴快捷键，截图及复制图片由用户自行完成；窗口内使用 Ctrl+V 粘贴图片，不注册全局快捷键。Ctrl+C 保留标准文本复制，编辑器内的文本粘贴也保持正常。
追加修订：粘贴成功后自动识别并按需加载所选本地模型，连续粘贴只处理最新图片；取消和历史恢复清除待识别请求。复制区为 LaTeX / MathML(Word) / PNG 分体按钮，LaTeX 下拉选择并记住六种格式（含 equation），仅复制结果附加定界符。
首版提供 LaTeX/MathML/PNG/SVG、本地 DOCX、AsciiMath/Typst；复杂不支持结构应明确报错，不能静默导出错误公式。
PDF 整页、翻译、云账号和 AI 编辑不在本次范围。

## 选型
方案 A：PySide6 原生桌面、单独常驻 Python/Transformers 模型进程、本地 KaTeX/MathJax、SQLite。
备选 Electron+Python 会增加运行时/通信复杂度，用户已选 A。原型分析资料保留，不复用厂商二进制/提取代码。

## 执行条件
- conda 环境 img2tex，Python 3.12，所有 Python 开发/运行/测试在此环境中，禁用用户 site-packages。
- 同一套模型权重支持 CPU(float32) 与 CUDA(float16)。界面显式选择，切换先停止旧模型进程再重新加载。
- 初始选择 CPU；记住用户选择。CUDA 不可用时清楚报告，CPU 始终可选，不以 CUDA 为启动条件。
- 官方模型 xiaomi-research/Xiaomi-OCR-0 固定 revision bbd8cf8d21f256b3644b44cb860f3a7cecb93c30；固定公式提示词、enable_thinking=False、do_sample=False。
- 图像 EXIF 校正、白底合成、RGB、长边最多 2048。保存原图与送模图哈希。只剥离匹配外层围栏/数学定界符。
- 结果区分 raw_output、latex_normalized、latex_edited；编辑不篡改 raw。失败/取消不写成功历史，不虚构置信度。
- 单个模型进程同时处理一个任务；task_id 隔离迟到结果；取消先逻辑失效，再 token 边界物理停止。
- 所有预览脚本/字体/转换本地，日常工作无公网依赖。下载模型是明确的独立准备步骤。
- SQLite 是设置和历史唯一持久化来源。输入图片由用户外部截图、复制或提供文件；应用只接收文件/拖拽/剪贴板。
- MathType 7.8/Word 本机新文档验收；MathML 文本与原生 OLE 不等价。DOCX 内用 OMML，不以公式图片冒充可编辑对象。

## 完成标准
真实模型 CPU 和 CUDA 各完成样例推理；桌面完整输入/编辑/导出闭环可用；关键回归测试通过；Windows 包可启动。
质量/耗时/设备/内存按实测报告，不承诺等同 SimpleTex 模型。若环境确实阻止某项验证，保留实际错误和未通过项。

## 公共接口（各模块约定）
- src/img2tex/images.py: prepare_image(data: bytes) -> PreparedImage(original_png, model_png, width, height, sha256, model_sha256)。字段均 bytes/int/str；可用 .model_png 送模型。
- src/img2tex/engine.py: ModelProcess().load(model_dir: str, device: str), recognize(image_png: bytes, task_id: str, max_new_tokens: int=1024), cancel(), poll()->list[dict], stop()；属性 is_alive 和 is_busy（物理任务是否仍在执行/取消中）。
- 事件 dict: type=loading/ready/result/error/cancelled，带 device；result 含 task_id,raw_output,latex_normalized,elapsed_seconds,device,model_revision；error 带 message 和可选 task_id。CPU/CUDA 切换由 GUI stop/load 控制。
- src/img2tex/storage.py: Store(path: Path).get_setting(key,default=None), set_setting(key,value), add_result(result:dict,image_png:bytes)->int, update_edited(id:int,latex:str), list_history(search:str="",limit:int=100)->list[dict], get_record(id)->dict|None, delete(id), close()。历史字段 id,created_at,latex_edited,latex_normalized,raw_output,device,elapsed_seconds,model_revision,image_png。
- src/img2tex/exports.py: to_mathml(latex:str)->str, to_asciimath(latex:str)->str, to_typst(latex:str)->str, write_docx(latex:str,path:Path)->None。无法保真时抛 ValueError；GUI 报错并保留编辑值。
- src/img2tex/ui/main.py: run()->int；MainWindow 为主窗口，依赖上述接口；渲染/PNG/SVG、窗口内 Ctrl+V 图片粘贴和托盘由 UI 模块负责。
- src/img2tex/__main__.py: main()->int，默认启动GUI；另提供下载模型、设备诊断和真实模型smoke CLI。
