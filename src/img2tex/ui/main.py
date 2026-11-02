"""Chinese native desktop UI. SQLite owns settings and model output history."""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QMimeData, QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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

from img2tex.model_setup import default_model_dir

from .preview import FormulaPreview, pixmap_png

LATEX_COPY_FORMATS = (
    ("plain", "无特殊附加", "", ""),
    ("inline_dollars", "$ … $ 格式", "$", "$"),
    ("display_dollars", "$$ … $$ 格式", "$$", "$$"),
    ("inline_parens", r"\( … \) 格式", r"\(", r"\)"),
    ("display_brackets", r"\[ … \] 格式", r"\[", r"\]"),
    ("equation", r"\begin{equation} … \end{equation} 格式", "\\begin{equation}\n", "\n\\end{equation}"),
)


def app_data_dir():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "Img2Tex"


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
        self._loaded_model_dir = None
        self._closed = False
        self._download_output = ""
        self._downloading_model = False
        self.tray = None
        self.setWindowTitle("Img2Tex · 本地公式识别")
        self.setWindowIcon(app_icon())
        self.resize(1240, 840)
        self.setMinimumSize(880, 600)
        self.setAcceptDrops(True)
        self._build_ui(preview)
        self._build_history()
        self._build_settings()
        self._build_toolbar()
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
        self.download_process = QProcess(self)
        self.download_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.download_process.readyReadStandardOutput.connect(self._download_log)
        self.download_process.finished.connect(self._download_finished)
        self.download_process.errorOccurred.connect(self._download_error)
        if enable_system_integration:
            self._system_integration()
        self.statusBar().showMessage("就绪 · 导入图片后，选择设备并加载本地模型")

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
        self.settings_dock = QDockWidget("模型与设置", self)
        self.settings_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        panel = QWidget()
        form = QFormLayout(panel)
        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU · 通用 / float32", "cpu")
        self.device_combo.addItem("CUDA · NVIDIA GPU / float16", "cuda")
        self.device_combo.setCurrentIndex(1 if self.store.get_setting("device", "cpu") == "cuda" else 0)
        form.addRow("计算设备", self.device_combo)
        path_row = QHBoxLayout()
        self.model_path = QLineEdit(str(self.store.get_setting(
            "model_dir", str(default_model_dir()))))
        self.model_path.setPlaceholderText("选择已下载的 Xiaomi-OCR-0 模型目录")
        self.model_path.editingFinished.connect(self._save_model_path)
        path_row.addWidget(self.model_path, 1)
        self.browse_model_button = QPushButton("浏览…")
        self.browse_model_button.clicked.connect(self._choose_model_dir)
        path_row.addWidget(self.browse_model_button)
        self.load_button = QPushButton("加载模型")
        self.load_button.clicked.connect(self.load_model)
        path_row.addWidget(self.load_button)
        self.download_button = QPushButton("下载固定版本模型")
        self.download_button.clicked.connect(self.download_model)
        path_row.addWidget(self.download_button)
        form.addRow("模型目录", path_row)
        note = QLabel("CPU 始终可选；切换设备会停止并重新加载模型。首次下载需要网络，日常识别与导出在本机完成。")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addRow(note)
        self.download_log = QPlainTextEdit()
        self.download_log.setReadOnly(True)
        self.download_log.setMaximumHeight(90)
        self.download_log.hide()
        form.addRow(self.download_log)
        self.settings_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.settings_dock)
        self.device_combo.currentIndexChanged.connect(self._device_changed)

    def _build_toolbar(self):
        toolbar = QToolBar("主要操作", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)
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
        toolbar.addAction(self.history_dock.toggleViewAction())
        toolbar.addAction(self.settings_dock.toggleViewAction())

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

    def _save_model_path(self):
        path = self.model_path.text().strip()
        self.store.set_setting("model_dir", path)
        if (self._model_ready or self._loading_model) and path != self._loaded_model_dir:
            self.cancel_recognition()
            self.engine.stop()
            self._model_ready = False
            self._loading_model = False
            self.progress.hide()
            self.load_button.setEnabled(True)
            self._notify("模型目录已更改，请重新加载模型")

    def _choose_model_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地模型目录", self.model_path.text())
        if path:
            self.model_path.setText(path)
            self._save_model_path()

    def _device_changed(self):
        self.store.set_setting("device", self.device_combo.currentData())
        self.load_model()

    def load_model(self):
        if self._downloading_model:
            self._notify("模型正在下载，请等待完成后再加载")
            return
        path = self.model_path.text().strip()
        if not path:
            self._notify("请先选择模型目录，或下载固定版本模型")
            return
        self.cancel_recognition()
        self.engine.stop()
        self._model_ready = False
        self._loading_model = False
        self._save_model_path()
        self._loaded_model_dir = path
        self._loading_model = True
        self.load_button.setEnabled(False)
        self.progress.show()
        self._notify(f"正在加载 {self.device_combo.currentData().upper()} 模型…")
        try:
            self.engine.load(path, self.device_combo.currentData())
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
        if event.get("device") and event["device"] != self.device_combo.currentData():
            return
        if kind == "loading":
            self._notify(f"正在加载 {self.device_combo.currentData().upper()} 模型…")
        elif kind == "ready":
            if not self.engine.is_alive:
                return
            self._model_ready = True
            self._loading_model = False
            if self._loaded_model_dir is None:
                self._loaded_model_dir = self.model_path.text().strip()
            self.load_button.setEnabled(True)
            self.progress.hide()
            self._notify(f"{self.device_combo.currentData().upper()} 模型已就绪")
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
            self._active_task = None
            self._task_image = None
            self._busy(False)
            self.load_button.setEnabled(True)
            self._notify(event.get("message", "已取消识别") if kind == "error" else "已取消识别")

    def _busy(self, busy):
        self.recognize_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)

    def start_recognition(self):
        if self.current_image is None:
            self._notify("请先导入或粘贴一张公式图片")
            return
        if not self._model_ready:
            self.settings_dock.show()
            self._notify("请先选择设备并点击「加载模型」；首次使用可点击「下载固定版本模型」")
            return
        if self._active_task is not None:
            return
        self.current_record_id = None
        self._active_task = uuid4().hex
        self._task_image = self.current_image
        self._task_editor_revision = self._editor_revision
        self._busy(True)
        self._notify(f"正在本机 {self.device_combo.currentData().upper()} 识别… 可继续编辑源码")
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
        if self._loading_model or self._downloading_model:
            return
        if not self._model_ready:
            self._auto_recognition_pending = False
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
            self._save_model_path()
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

    def download_model(self):
        if self._downloading_model:
            return
        path = self.model_path.text().strip()
        if not path:
            self._notify("请先选择下载目录")
            return
        self._save_model_path()
        # Transformers may mmap weight files on Windows. Release the process and
        # logically invalidate results before the downloader replaces those files.
        self.cancel_recognition()
        self.engine.stop()
        self._model_ready = False
        self._loading_model = False
        self._downloading_model = True
        self.progress.hide()
        self._model_controls_enabled(False)
        self.download_log.clear()
        self.download_log.show()
        self._download_output = ""
        self.download_button.setEnabled(False)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONNOUSERSITE", "1")
        environment.insert("PYTHONUTF8", "1")
        self.download_process.setProcessEnvironment(environment)
        arguments = [] if getattr(sys, "frozen", False) else ["-s", "-m", "img2tex"]
        arguments.extend(["--download-model", "--model-dir", path])
        self.download_process.start(sys.executable, arguments)
        self._notify("正在下载固定版本模型，请查看模型设置中的进度")

    def _download_log(self):
        chunk = bytes(self.download_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._download_output = (self._download_output + chunk)[-16000:]
        self.download_log.setPlainText(self._download_output)
        self.download_log.verticalScrollBar().setValue(self.download_log.verticalScrollBar().maximum())

    def _download_finished(self, code, status):
        self._download_log()
        self._downloading_model = False
        self._model_controls_enabled(True)
        self.download_button.setEnabled(True)
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            self._notify("模型下载完成，点击「加载模型」即可开始识别")
        else:
            self._auto_recognition_pending = False
            self._busy(False)
            self._notify("模型下载失败，请查看下方日志；可修正网络后重试")

    def _download_error(self, error):
        self._auto_recognition_pending = False
        self._busy(False)
        self._downloading_model = False
        self._model_controls_enabled(True)
        self.download_button.setEnabled(True)
        self._notify(f"无法启动模型下载：{self.download_process.errorString()}")

    def _model_controls_enabled(self, enabled):
        for widget in (self.model_path, self.browse_model_button, self.load_button, self.device_combo):
            widget.setEnabled(enabled)

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
            if self.download_process.state() != QProcess.ProcessState.NotRunning:
                self.download_process.kill()
                self.download_process.waitForFinished(1500)
            if self._owns_store:
                self.store.close()
        super().closeEvent(event)


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Img2Tex")
    app.setOrganizationName("Img2Tex")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()
