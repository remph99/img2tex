"""Chinese native desktop UI. SQLite owns settings and model output history."""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QMimeData, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from img2tex import __version__
from img2tex.edition import cpu_only, edition_label
from img2tex.model_setup import check_model_directory, default_model_dir
from img2tex.paths import app_data_dir, configure_runtime, resolve_model_path, serialize_model_path

from .preview import FormulaPreview, pixmap_png

LATEX_COPY_FORMATS = (
    ("plain", "无特殊附加", "", ""),
    ("inline_dollars", "$ … $ 格式", "$", "$"),
    ("display_dollars", "$$ … $$ 格式", "$$", "$$"),
    ("inline_parens", r"\( … \) 格式", r"\(", r"\)"),
    ("display_brackets", r"\[ … \] 格式", r"\[", r"\]"),
    ("equation", r"\begin{equation} … \end{equation} 格式", "\\begin{equation}\n", "\n\\end{equation}"),
)


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#6d5dfc"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 64, 64, 16, 16)
    painter.setPen(Qt.GlobalColor.white)
    painter.setFont(QFont("Cambria Math", 29))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "x²")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self, store=None, engine=None, preview=None, enable_system_integration=True):
        super().__init__()
        self._owns_store = store is None
        if store is None:
            from img2tex.storage import Store
            store = Store(app_data_dir() / "history.sqlite3")
        if engine is None:
            from img2tex.engine import ModelProcess
            engine = ModelProcess()
        self.store = store
        self.engine = engine
        self.current_image = None
        self.current_record_id = None
        self._active_task = None
        self._auto_recognition_pending = False
        self._auto_editor_revision = 0
        self._task_image = None
        self._editor_revision = 0
        self._task_editor_revision = 0
        self._programmatic_edit = False
        self._model_ready = False
        self._loading_model = False
        self._closed = False
        self._initialization_failed = False
        self._device_reason = ""
        self._requested_device = "cpu" if cpu_only() else self.store.get_setting("device", "auto")
        if self._requested_device not in {"cpu", "cuda", "auto"}:
            self._requested_device = "auto"
        if cpu_only():
            self.store.set_setting("device", "cpu")
        self._device = "cuda" if self._requested_device == "cuda" else "cpu"
        saved_model = self.store.get_setting("model_dir")
        self._model_dir = resolve_model_path(saved_model) if saved_model else str(default_model_dir())
        self.tray = None
        self.setWindowTitle("Img2Tex · 本地公式识别" + (" · CPU Only" if cpu_only() else ""))
        self.setWindowIcon(app_icon())
        self.resize(1240, 840)
        self.setMinimumSize(880, 600)
        self.setAcceptDrops(True)
        self._build_ui(preview)
        self._build_history()
        self._build_settings()
        self._build_toolbar()
        self._build_menu()
        self._style()
        self._refresh_history()
        QApplication.instance().installEventFilter(self)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(80)
        self.poll_timer.timeout.connect(self._poll_engine)
        self.poll_timer.start()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self._render_source)
        self.editor.textChanged.connect(self._editor_changed)
        self.preview.error.connect(self._preview_error)
        self.preview.rendered.connect(lambda: self.preview_status.setText("本地预览 · KaTeX"))
        if enable_system_integration:
            self._system_integration()
        self.device_indicator = QLabel("设备准备中")
        self.statusBar().addPermanentWidget(self.device_indicator)
        self._notify("即将加载本地模型…")

    def _build_ui(self, preview):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 12)
        header = QHBoxLayout()
        title = QLabel("公式，从图片到文字")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        local = QLabel("●  本地处理 · 离线编辑")
        local.setObjectName("localBadge")
        header.addWidget(local)
        layout.addLayout(header)
        subtitle = QLabel("粘贴公式图片即可自动识别，识别后可直接编辑与复制。")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        image_panel = QFrame()
        image_panel.setObjectName("panel")
        image_layout = QVBoxLayout(image_panel)
        self.image_info = QLabel("输入图片")
        self.image_info.setObjectName("sectionTitle")
        image_layout.addWidget(self.image_info)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.image_label = QLabel("将公式图片拖到这里\n\n或点击「导入图片」「粘贴图片」")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(180, 180)
        self.image_label.setObjectName("imageDrop")
        scroll.setWidget(self.image_label)
        image_layout.addWidget(scroll, 1)
        self.image_hint = QLabel("支持 PNG / JPEG / WEBP / BMP / TIFF\nCtrl+V 粘贴后自动识别")
        self.image_hint.setObjectName("muted")
        image_layout.addWidget(self.image_hint)
        splitter.addWidget(image_panel)
        result_panel = QFrame()
        result_panel.setObjectName("panel")
        result_layout = QVBoxLayout(result_panel)
        self.preview_status = QLabel("本地预览 · KaTeX")
        self.preview_status.setObjectName("sectionTitle")
        result_layout.addWidget(self.preview_status)
        self.preview = preview if preview is not None else FormulaPreview()
        self.preview.setMinimumHeight(170)
        result_layout.addWidget(self.preview, 2)
        self.source_tabs = QTabWidget()
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("latexEditor")
        self.editor.setPlaceholderText(r"识别结果会显示在这里，也可以直接输入 LaTeX，例如 \frac{a}{b}")
        self.editor.setFont(QFont("Cascadia Code", 12))
        self.raw_output = QPlainTextEdit()
        self.raw_output.setReadOnly(True)
        self.raw_output.setPlaceholderText("保留模型原始输出，编辑不会改变此处内容。")
        self.source_tabs.addTab(self.editor, "LaTeX 源码")
        self.source_tabs.addTab(self.raw_output, "模型原始输出")
        result_layout.addWidget(self.source_tabs, 3)
        copy_row = QHBoxLayout()
        self.copy_latex_button = QToolButton()
        self.copy_latex_button.setText("复制 LaTeX")
        self.copy_latex_button.setObjectName("copyButton")
        self.copy_latex_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.copy_latex_button.clicked.connect(self.copy_latex)
        latex_menu = QMenu(self.copy_latex_button)
        self.latex_copy_group = QActionGroup(self)
        self.latex_copy_group.setExclusive(True)
        self._latex_wrapper_actions = {}
        saved_wrapper = self.store.get_setting("latex_wrapper", "plain")
        if saved_wrapper not in {item[0] for item in LATEX_COPY_FORMATS}:
            saved_wrapper = "plain"
        for format_id, label, _, _ in LATEX_COPY_FORMATS:
            action = latex_menu.addAction(label)
            action.setData(format_id)
            action.setCheckable(True)
            self.latex_copy_group.addAction(action)
            action.setChecked(format_id == saved_wrapper)
            action.triggered.connect(lambda checked=False, key=format_id: self._select_latex_wrapper(key))
            self._latex_wrapper_actions[format_id] = action
        self.copy_latex_button.setMenu(latex_menu)
        self.copy_latex_button.setToolTip("默认复制格式：" + self._latex_wrapper_actions[saved_wrapper].text())
        copy_row.addWidget(self.copy_latex_button)
        self.copy_mathml_button = QToolButton()
        self.copy_mathml_button.setText("复制 MathML(Word)")
        self.copy_mathml_button.setObjectName("copyButton")
        self.copy_mathml_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.copy_mathml_button.clicked.connect(lambda: self.copy_text_format("MathML"))
        text_menu = QMenu(self.copy_mathml_button)
        for title, callback in [
            ("复制 AsciiMath", lambda: self.copy_text_format("AsciiMath")),
            ("复制 Typst", lambda: self.copy_text_format("Typst")),
            ("保存可编辑 DOCX…", self.save_docx),
        ]:
            text_menu.addAction(title, callback)
        self.copy_mathml_button.setMenu(text_menu)
        copy_row.addWidget(self.copy_mathml_button)
        self.copy_png_button = QToolButton()
        self.copy_png_button.setText("复制 PNG")
        self.copy_png_button.setObjectName("copyButton")
        self.copy_png_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.copy_png_button.clicked.connect(self.copy_png)
        image_menu = QMenu(self.copy_png_button)
        for title, callback in [
            ("保存 PNG…", lambda: self.save_formula("PNG")),
            ("复制 SVG 源码", self.copy_svg),
            ("保存 SVG…", lambda: self.save_formula("SVG")),
        ]:
            image_menu.addAction(title, callback)
        self.copy_png_button.setMenu(image_menu)
        copy_row.addWidget(self.copy_png_button)
        copy_row.addStretch()
        result_layout.addLayout(copy_row)
        self.result_info = QLabel("识别结果与编辑内容分别保存在本机历史中")
        self.result_info.setObjectName("muted")
        result_layout.addWidget(self.result_info)
        splitter.addWidget(result_panel)
        splitter.setSizes([380, 620])
        layout.addWidget(splitter, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.setCentralWidget(central)

    def _build_history(self):
        self.history_dock = QDockWidget("本地历史", self)
        self.history_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("搜索 LaTeX…")
        self.history_search.textChanged.connect(self._refresh_history)
        layout.addWidget(self.history_search)
        self.history_list = QListWidget()
        self.history_list.setMinimumWidth(180)
        self.history_list.setWordWrap(True)
        self.history_list.itemClicked.connect(lambda item: self.restore_record(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.history_list)
        delete_button = QPushButton("删除所选历史")
        delete_button.clicked.connect(self._delete_record)
        layout.addWidget(delete_button)
        self.history_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.history_dock)

    def _build_settings(self):
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("计算设备")
        self.settings_dialog.setMinimumWidth(400)
        form = QFormLayout(self.settings_dialog)
        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU · 通用", "cpu")
        if not cpu_only():
            self.device_combo.addItem("CUDA · NVIDIA GPU", "cuda")
        self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(self._device)))
        form.addRow("计算设备", self.device_combo)
        self.device_status = QLabel("启动后自动检测；切换设备会重新加载并预热模型。")
        self.device_status.setWordWrap(True)
        form.addRow(self.device_status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_device_settings)
        buttons.rejected.connect(self.settings_dialog.reject)
        form.addRow(buttons)

    def _build_menu(self):
        files = self.menuBar().addMenu("文件")
        for action in self._input_actions:
            files.addAction(action)
        files.addSeparator()
        for title, callback in [
            ("保存 PNG…", lambda: self.save_formula("PNG")),
            ("保存 SVG…", lambda: self.save_formula("SVG")),
            ("保存可编辑 DOCX…", self.save_docx),
        ]:
            files.addAction(title, callback)
        files.addSeparator()
        files.addAction("退出", self.close)
        view = self.menuBar().addMenu("视图")
        view.addAction(self.history_dock.toggleViewAction())
        settings = self.menuBar().addMenu("设置")
        self.settings_action = settings.addAction("计算设备…", self.show_device_settings)
        self.retry_action = settings.addAction("重新初始化模型", self.retry_model)
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction("关于 Img2Tex…", self.show_about)

    def show_device_settings(self):
        if self._active_task is not None or self._loading_model:
            return
        self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(self._device)))
        self.settings_dialog.open()

    def apply_device_settings(self):
        if self._active_task is not None or self._loading_model:
            return
        device = self.device_combo.currentData()
        self._requested_device = device
        self.store.set_setting("device", device)
        self.settings_dialog.accept()
        if self._model_ready and self.engine.is_alive and device == self._device:
            return
        self._device = device
        self.load_model(force=True)

    def show_about(self):
        QMessageBox.about(self, "关于 Img2Tex", f"<h3>Img2Tex</h3>本地公式识别"
                          f"<p>版本：{__version__}<br>发行类型：{edition_label()}</p>"
                          "<p>基于 Xiaomi-OCR-0<br>支持离线识别、公式预览与导出</p>")

    def retry_model(self):
        if self._active_task is None and not self._loading_model:
            self.load_model(force=True)

    def _build_toolbar(self):
        toolbar = QToolBar("主要操作", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        self._input_actions = []
        for title, callback, shortcut in [
            ("导入图片", self.open_image, QKeySequence.StandardKey.Open),
            ("粘贴图片", self.paste_image, QKeySequence("Ctrl+V")),
        ]:
            action = QAction(title, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
                action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            toolbar.addAction(action)
            self._input_actions.append(action)
        toolbar.addSeparator()
        self.recognize_button = QPushButton("开始识别")
        self.recognize_button.setObjectName("primary")
        self.recognize_button.clicked.connect(self.start_recognition)
        toolbar.addWidget(self.recognize_button)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_recognition)
        toolbar.addWidget(self.cancel_button)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)


    def _style(self):
        self.setStyleSheet("""
            QMainWindow { background:#f4f5fa; color:#172034; }
            QWidget { font-family:'Microsoft YaHei UI','Segoe UI'; font-size:12px; }
            QToolBar { background:white; border:0; padding:10px 14px; spacing:10px; }
            QToolButton,QPushButton { border:1px solid #dce0ed; background:white;
                border-radius:6px; padding:7px 12px; color:#26324a; }
            QToolButton:hover,QPushButton:hover { background:#efedff; border-color:#a99ff5; }
            QToolButton#copyButton { color:#2580ea; border-color:#6aa7f4; border-radius:13px; }
            QToolButton#copyButton::menu-button { border-left:1px solid #d5e7fc; width:17px; }
            QPushButton#primary { background:#6d5dfc; color:white; border-color:#6d5dfc; }
            QPushButton#primary:hover { background:#5b4ae8; }
            QPushButton:disabled { background:#ebeef4; color:#99a0b1; border-color:#e2e6ef; }
            QLabel#title { font-size:24px; font-weight:600; }
            QLabel#localBadge { color:#478675; padding:6px; }
            QLabel#muted { color:#778096; font-size:11px; padding:3px 0; }
            QLabel#sectionTitle { font-weight:600; padding:6px; }
            QFrame#panel { background:white; border:1px solid #e1e5ef; border-radius:10px; }
            QLabel#imageDrop { color:#8a92a6; background:#fafbfe; border:1px dashed #d7dbea; }
            QLineEdit,QPlainTextEdit,QListWidget { background:white; color:#172034;
                border:1px solid #dce0ed; border-radius:5px; padding:6px; selection-background-color:#c8c1ff; }
            QComboBox { background:white; border:1px solid #dce0ed; border-radius:5px; padding:6px; }
            QDockWidget { font-weight:600; } QDockWidget::title { padding:9px; background:#edf0f7; }
            QDockWidget QWidget { background:#f9fafe; }
            QTabWidget::pane { border:0; } QTabBar::tab { padding:8px 12px; color:#667088; }
            QTabBar::tab:selected { color:#6d5dfc; background:white; }
            QStatusBar { color:#63708a; background:#eceff6; }
            QProgressBar { border:0; background:#e4e0ff; } QProgressBar::chunk { background:#8b7cf8; }
        """)

    def _notify(self, message):
        self.statusBar().showMessage(str(message))

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.ShortcutOverride and isinstance(watched, QWidget)
                and watched.window() is self and event.key() == Qt.Key.Key_V
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier
                and QApplication.clipboard().mimeData().hasImage()):
            # Route image pastes through the window action. Text-only clipboard
            # content keeps the focused editor's normal Ctrl+V behavior.
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def _resolve_model_directory(self):
        saved = self.store.get_setting("model_dir")
        path = resolve_model_path(saved) if saved else str(default_model_dir())
        notice = ""
        try:
            check_model_directory(path)
        except ValueError:
            bundled = default_model_dir()
            if not saved or Path(path) == bundled:
                raise
            check_model_directory(bundled)
            path = str(bundled)
            notice = "原模型路径不可用，已切换至随包模型。"
        self._model_dir = path
        self.store.set_setting("model_dir", serialize_model_path(path))
        return notice

    def load_model(self, force=False):
        if not force and (self._loading_model or (self._model_ready and self.engine.is_alive)):
            return
        self.cancel_recognition()
        self.engine.stop()
        self._model_ready = False
        self._loading_model = False
        self._initialization_failed = False
        try:
            notice = self._resolve_model_directory()
        except (ValueError, OSError) as exc:
            self.handle_event({"type": "error", "message": f"{exc} 请完整解压离线包并检查模型文件。"})
            return
        self._loading_model = True
        self.settings_action.setEnabled(False)
        self.retry_action.setEnabled(False)
        self.progress.show()
        self._device_reason = notice
        self._notify(notice + "正在准备本地模型…")
        try:
            self.engine.load(self._model_dir, self._requested_device)
        except (ValueError, RuntimeError, OSError) as exc:
            self.handle_event({"type": "error", "message": str(exc)})

    def _poll_engine(self):
        try:
            for event in self.engine.poll():
                self.handle_event(event)
            self._advance_auto_recognition()
        except (ValueError, RuntimeError, OSError, EOFError, sqlite3.Error) as exc:
            self.handle_event({"type": "error", "message": str(exc)})

    def handle_event(self, event):
        kind = event.get("type")
        task_id = event.get("task_id")
        if task_id is not None and task_id != self._active_task:
            return
        if task_id is not None and event.get("device", self._device) != self._device:
            return
        if kind == "device_info":
            self._device = event["device"]
            reason = event.get("reason", "")
            if reason:
                self._device_reason = reason
            self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(self._device)))
            available = event.get("cuda_available")
            if self.device_combo.count() > 1:
                self.device_combo.model().item(1).setEnabled(available is not False)
            self.device_status.setText(event.get("gpu") or reason or "当前使用 CPU；选择 CUDA 时会检测兼容性。")
            self.device_indicator.setText(f"{self._device.upper()} · 准备中")
        elif kind in {"loading", "warming"}:
            selected = event.get("device", self._device)
            label = "自动检测设备并加载" if selected == "auto" else selected.upper() + (" 正在预热" if kind == "warming" else " 正在加载")
            self.device_indicator.setText(label)
            self._notify(label + "本地模型…")
        elif kind == "ready":
            if not self.engine.is_alive:
                return
            self._model_ready = True
            self._loading_model = False
            self._device = event["device"]
            self._initialization_failed = False
            self.settings_action.setEnabled(True)
            self.retry_action.setEnabled(True)
            self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(self._device)))
            self.progress.hide()
            self.device_indicator.setText(f"{self._device.upper()} · 已就绪")
            reason = event.get("reason") or self._device_reason
            self._notify(f"{self._device.upper()} 模型已就绪" + (f" · {reason}" if reason else ""))
        elif kind == "result" and self._active_task is not None:
            task_image = self._task_image
            edited = self._editor_revision != self._task_editor_revision
            self._active_task = None
            self._task_image = None
            self._busy(False)
            try:
                record_id = self.store.add_result(event, task_image.original_png)
                if edited:
                    self.store.update_edited(record_id, self.editor.toPlainText())
                else:
                    self._set_editor(event["latex_normalized"])
                self.current_record_id = record_id
                self.raw_output.setPlainText(event.get("raw_output", ""))
                self._show_result_info(event)
                self._refresh_history()
                self._notify("识别完成 · 已保留您输入的编辑内容" if edited else "识别完成 · 已保存到本地历史")
            except (ValueError, OSError, sqlite3.Error) as exc:
                self._notify(f"保存识别结果失败：{exc}")
        elif kind in ("error", "cancelled"):
            self._auto_recognition_pending = False
            if task_id is None:
                self._model_ready = False
                self._loading_model = False
                self._initialization_failed = True
                self.device_indicator.setText("模型准备失败")
            self._active_task = None
            self._task_image = None
            self._busy(False)
            self.settings_action.setEnabled(True)
            self.retry_action.setEnabled(True)
            self._notify(event.get("message", "已取消识别") if kind == "error" else "已取消识别")

    def _busy(self, busy):
        self.recognize_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy or self._loading_model)
        self.settings_action.setEnabled(not busy and not self._loading_model)
        self.retry_action.setEnabled(not busy and not self._loading_model)

    def start_recognition(self):
        if self.current_image is None:
            self._notify("请先导入或粘贴一张公式图片")
            return
        if not self._model_ready:
            self._auto_recognition_pending = True
            self._auto_editor_revision = self._editor_revision
            self._busy(True)
            self._advance_auto_recognition()
            return
        if self._active_task is not None:
            return
        self.current_record_id = None
        self._active_task = uuid4().hex
        self._task_image = self.current_image
        self._task_editor_revision = self._editor_revision
        self._busy(True)
        self._notify(f"正在本机 {self._device.upper()} 识别… 可继续编辑源码")
        try:
            self.engine.recognize(self.current_image.model_png, self._active_task)
        except (ValueError, RuntimeError, OSError) as exc:
            self.handle_event({"type": "error", "task_id": self._active_task, "message": str(exc)})

    def cancel_recognition(self):
        pending = self._auto_recognition_pending
        self._auto_recognition_pending = False
        if self._active_task is not None:
            # Invalidate first: a result already in the IPC queue must never be saved.
            self._active_task = None
            self._task_image = None
            self.engine.cancel()
            self._busy(False)
            self._notify("已取消识别")
        elif pending:
            self._busy(False)
            self._notify("已取消自动识别")

    def _advance_auto_recognition(self):
        if not self._auto_recognition_pending or self._active_task is not None:
            return
        if self._loading_model:
            return
        if not self._model_ready:
            self._auto_recognition_pending = False
            if self._initialization_failed:
                self._busy(False)
                self._notify("模型准备失败，请从「设置 → 重新初始化模型」重试。")
                return
            self.load_model()
            if self._loading_model:
                self._auto_recognition_pending = True
                self.cancel_button.setEnabled(True)
            else:
                self._busy(False)
            return
        if self.engine.is_busy:
            self._notify("上一任务取消中，将自动识别最新粘贴的图片")
            return
        self._auto_recognition_pending = False
        self.start_recognition()
        if self._active_task is not None:
            # Edits made while loading/cancelling are part of this request too.
            self._task_editor_revision = self._auto_editor_revision

    def load_image_bytes(self, data):
        from img2tex.images import prepare_image
        try:
            prepared = prepare_image(data)
        except (ValueError, OSError) as exc:
            self._notify(f"无法读取图片：{exc}")
            return False
        self.cancel_recognition()
        self.current_image = prepared
        self.current_record_id = None
        self._set_editor("")
        self.raw_output.clear()
        self._show_image()
        self.result_info.setText("图片已就绪 · 点击「开始识别」")
        self._notify("图片已导入")
        return True

    def _show_image(self):
        pixmap = QPixmap()
        pixmap.loadFromData(self.current_image.original_png)
        available_width = max(180, self.image_label.width() - 20)
        available_height = max(180, self.image_label.height() - 20)
        self.image_label.setPixmap(pixmap.scaled(available_width, available_height,
                                               Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        self.image_info.setText(f"输入图片 · {self.current_image.width} × {self.current_image.height}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_image is not None:
            QTimer.singleShot(0, self._show_image)

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入公式图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;所有文件 (*)")
        if path:
            self._load_file(path)

    def _load_file(self, path):
        try:
            return self.load_image_bytes(Path(path).read_bytes())
        except OSError as exc:
            self._notify(f"无法读取文件：{exc}")
            return False

    def paste_image(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        pasted = False
        if not image.isNull():
            pasted = self.load_image_bytes(pixmap_png(QPixmap.fromImage(image)))
        elif clipboard.mimeData().hasUrls() and clipboard.mimeData().urls()[0].isLocalFile():
            pasted = self._load_file(clipboard.mimeData().urls()[0].toLocalFile())
        else:
            self._notify("剪贴板中没有图片，请先复制图片或截图")
        if pasted:
            self._auto_recognition_pending = True
            self._auto_editor_revision = self._editor_revision
            self.result_info.setText("图片已粘贴 · 自动识别")
            self._busy(True)
            self._advance_auto_recognition()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage() or (mime.hasUrls() and any(url.isLocalFile() for url in mime.urls())):
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self._load_file(url.toLocalFile())
                    event.acceptProposedAction()
                    return
        if mime.hasImage():
            self.load_image_bytes(pixmap_png(QPixmap.fromImage(QImage(mime.imageData()))))
            event.acceptProposedAction()

    def _set_editor(self, text):
        self._programmatic_edit = True
        self.editor.setPlainText(text)
        self._programmatic_edit = False
        self._render_source()

    def _editor_changed(self):
        if not self._programmatic_edit:
            self._editor_revision += 1
            if self.current_record_id is not None:
                try:
                    self.store.update_edited(self.current_record_id, self.editor.toPlainText())
                except sqlite3.Error as exc:
                    self._notify(f"保存编辑内容失败，当前源码已保留：{exc}")
            self.preview_timer.start()

    def _render_source(self):
        self.preview.set_latex(self.editor.toPlainText())

    def _preview_error(self, message):
        self.preview_status.setText(f"预览错误：{message}")
        self.preview_status.setWordWrap(True)
        self._notify("预览失败，源码已保留；可继续编辑或复制 LaTeX")

    def _refresh_history(self):
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        for record in self.store.list_history(self.history_search.text()):
            source = record["latex_edited"].replace("\n", " ")
            created = datetime.fromisoformat(record["created_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{created}  ·  {record['device'].upper()}\n{source[:88]}")
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            item.setToolTip(source)
            self.history_list.addItem(item)

    def restore_record(self, record_id):
        record = self.store.get_record(record_id)
        if record is None:
            return
        self.cancel_recognition()
        if not self.load_image_bytes(record["image_png"]):
            return
        self._set_editor(record["latex_edited"])
        self.current_record_id = record_id
        self.raw_output.setPlainText(record["raw_output"])
        self._show_result_info(record)
        self._notify("已恢复本地历史图片与编辑内容")

    def _show_result_info(self, record):
        self.result_info.setText(f"{record['device'].upper()} · {record['elapsed_seconds']:.2f} 秒 · 模型 {record['model_revision'][:12]}")

    def _delete_record(self):
        item = self.history_list.currentItem()
        if item:
            record_id = item.data(Qt.ItemDataRole.UserRole)
            self.store.delete(record_id)
            if record_id == self.current_record_id:
                self.current_record_id = None
            self._refresh_history()
            self._notify("已删除所选历史；当前源码保留")

    def _source(self):
        source = self.editor.toPlainText().strip()
        if not source:
            self._notify("请先输入或识别一条公式")
        return source

    def copy_latex(self):
        source = self._source()
        if source:
            selected = self.latex_copy_group.checkedAction().data()
            _, _, left, right = next(item for item in LATEX_COPY_FORMATS if item[0] == selected)
            QApplication.clipboard().setText(left + source + right)
            self._notify("LaTeX 已复制")

    def _select_latex_wrapper(self, format_id):
        previous = self.store.get_setting("latex_wrapper", "plain")
        try:
            self.store.set_setting("latex_wrapper", format_id)
        except sqlite3.Error as exc:
            self._latex_wrapper_actions.get(previous, self._latex_wrapper_actions["plain"]).setChecked(True)
            self._notify(f"复制格式保存失败：{exc}")
            return
        action = self._latex_wrapper_actions[format_id]
        action.setChecked(True)
        self.copy_latex_button.setToolTip("默认复制格式：" + action.text())
        self._notify("默认 LaTeX 复制格式：" + action.text())

    def copy_text_format(self, format_name):
        from img2tex import exports
        source = self._source()
        if source:
            try:
                converters = {"MathML": exports.to_mathml, "AsciiMath": exports.to_asciimath, "Typst": exports.to_typst}
                text = converters[format_name](source)
            except (ValueError, RuntimeError) as exc:
                self._notify(f"{format_name} 导出失败：{exc}")
                return
            mime = QMimeData()
            mime.setText(text)
            if format_name == "MathML":
                mime.setData("application/mathml+xml", text.encode("utf-8"))
            QApplication.clipboard().setMimeData(mime)
            self._notify(f"{format_name} 已复制")

    def copy_png(self):
        source = self._source()
        if source:
            self.preview.export_png(source, self._png_to_clipboard)

    def _png_to_clipboard(self, data, error):
        if error:
            self._notify(f"PNG 导出失败：{error}")
            return
        image = QImage.fromData(data, "PNG")
        if image.isNull():
            self._notify("PNG 导出失败：浏览器未返回有效图片")
            return
        QApplication.clipboard().setImage(image)
        self._notify("公式 PNG 已复制")

    def copy_svg(self):
        source = self._source()
        if source:
            self.preview.export_svg(source, self._svg_to_clipboard)

    def _svg_to_clipboard(self, source, error):
        if error:
            self._notify(f"SVG 导出失败：{error}")
            return
        mime = QMimeData()
        mime.setData("image/svg+xml", source.encode("utf-8"))
        mime.setText(source)
        QApplication.clipboard().setMimeData(mime)
        self._notify("公式 SVG 已复制")

    def save_formula(self, format_name):
        source = self._source()
        if not source:
            return
        suffix = format_name.lower()
        path, _ = QFileDialog.getSaveFileName(self, f"保存公式 {format_name}", f"formula.{suffix}", f"{format_name} (*.{suffix})")
        if path:
            method = self.preview.export_png if format_name == "PNG" else self.preview.export_svg
            method(source, lambda data, error: self._save_rendered(path, data, error))

    def _save_rendered(self, path, data, error):
        if error:
            self._notify(f"导出失败：{error}")
            return
        try:
            Path(path).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        except OSError as exc:
            self._notify(f"保存失败：{exc}")
        else:
            self._notify(f"已保存：{path}")

    def save_docx(self):
        from img2tex.exports import write_docx
        source = self._source()
        if not source:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存可编辑 Word 公式", "formula.docx", "Word 文档 (*.docx)")
        if path:
            try:
                write_docx(source, Path(path))
            except (ValueError, OSError, RuntimeError) as exc:
                self._notify(f"DOCX 导出失败：{exc}")
            else:
                self._notify(f"已保存可编辑 OMML 公式：{path}")

    def _system_integration(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("Img2Tex · 本地公式识别")
            menu = QMenu(self)
            menu.addAction("显示主窗口", self._show_window)
            menu.addAction("粘贴图片", self.paste_image)
            menu.addSeparator()
            menu.addAction("退出", self.close)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self._show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if not self._closed:
            self._closed = True
            self.poll_timer.stop()
            self.preview_timer.stop()
            QApplication.instance().removeEventFilter(self)
            self._active_task = None
            self.engine.stop()
            if self.tray:
                self.tray.hide()
            if self._owns_store:
                self.store.close()
        super().closeEvent(event)


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Img2Tex")
    app.setOrganizationName("Img2Tex")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    try:
        configure_runtime()
        window = MainWindow()
    except (OSError, sqlite3.Error) as exc:
        QMessageBox.critical(None, "Img2Tex 无法启动", f"无法打开应用数据，请检查目录权限或历史数据库：\n{exc}")
        return 1
    window.show()
    QTimer.singleShot(0, window.load_model)
    return app.exec()
