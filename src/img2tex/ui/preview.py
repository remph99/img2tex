"""Offline KaTeX preview, MathJax SVG and cropped browser PNG capture."""
import json
import math
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRect, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget


def pixmap_png(pixmap: QPixmap) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise ValueError("无法编码图片")
    return bytes(data)


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ("file", "qrc", "data", "about"):
            info.block(True)


class LocalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return url.scheme() in ("file", "qrc", "about", "data")


class Bridge(QObject):
    received = Signal(dict)

    @Slot(str)
    def message(self, value):
        try:
            payload = json.loads(value)
            if isinstance(payload, dict):
                self.received.emit(payload)
        except (ValueError, TypeError):
            pass


class FormulaPreview(QWidget):
    rendered = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._source = ""
        self._revision = ""
        self._rendered_revision = None
        self._render_error = None
        self._png_callbacks = {}
        self._svg_callbacks = {}
        self._capturing = False
        self.view = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)
        self.interceptor = LocalRequests(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = LocalPage(self.profile, self.view)
        self.view.setPage(self.page)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.channel = QWebChannel(self.page)
        self.bridge = Bridge(self.channel)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel)
        self.bridge.received.connect(self._message)
        self.view.loadFinished.connect(self._loaded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        asset = Path(__file__).resolve().parents[1] / "assets" / "preview.html"
        self.view.setUrl(QUrl.fromLocalFile(str(asset)))

    def _loaded(self, success):
        if not success:
            self.error.emit("本地预览资源加载失败，请检查安装目录中的 assets 文件夹")

    def set_latex(self, source):
        if source == self._source and self._revision:
            return
        self._source = source
        self._revision = uuid4().hex
        self._rendered_revision = None
        self._render_error = None
        for callback in self._png_callbacks.values():
            callback(None, "公式已变化，请重新导出")
        self._png_callbacks.clear()
        if self._ready:
            self._render()

    def _render(self):
        # JSON string literals keep arbitrary user LaTeX out of JavaScript syntax.
        self.page.runJavaScript(f"window.renderFormula({json.dumps(self._source)}, {json.dumps(self._revision)})")

    def _message(self, value):
        kind = value.get("kind")
        if kind == "ready":
            self._ready = True
            if not self._revision:
                self._revision = uuid4().hex
            self._render()
        elif kind == "render" and value.get("id") == self._revision:
            if value.get("error"):
                self._render_error = value["error"]
                self.error.emit(value["error"])
                callback = self._png_callbacks.pop(self._revision, None)
                if callback:
                    callback(None, value["error"])
            else:
                self._rendered_revision = self._revision
                self.rendered.emit()
                if self._revision in self._png_callbacks:
                    self._capture_png(self._revision)
        elif kind == "svg":
            callback = self._svg_callbacks.pop(value.get("id"), None)
            if callback:
                callback(value.get("svg"), value.get("error"))

    def export_svg(self, source, callback):
        if not self._ready:
            callback(None, "预览尚未准备好，请稍候")
            return
        request = uuid4().hex
        self._svg_callbacks[request] = callback
        self.page.runJavaScript(f"window.exportSvg({json.dumps(source)}, {json.dumps(request)})")

    def export_png(self, source, callback):
        if self._capturing or self._png_callbacks:
            callback(None, "正在生成 PNG，请稍候")
            return
        self.set_latex(source)
        if self._render_error:
            callback(None, self._render_error)
            return
        self._png_callbacks[self._revision] = callback
        if self._rendered_revision == self._revision:
            self._capture_png(self._revision)

    def _capture_png(self, revision):
        self._capturing = True
        self.page.runJavaScript("JSON.stringify(window.formulaBounds(true))",
                                lambda rect: self._size_for_capture(revision, rect))

    def _size_for_capture(self, revision, rect):
        if isinstance(rect, str):
            try:
                rect = json.loads(rect)
            except ValueError:
                rect = None
        if not isinstance(rect, dict) or revision != self._revision:
            self._finish_capture(revision, None, "公式已变化，请重新导出")
            return
        width, height = math.ceil(rect["width"]) + 2, math.ceil(rect["height"]) + 2
        if width > 16000 or height > 16000 or width * height > 32_000_000:
            self._finish_capture(revision, None, "公式尺寸过大，请使用 SVG 导出")
            return
        self._previous_size = (self.view.minimumSize(), self.view.maximumSize())
        self._capture_window = self.window()
        self._previous_window_size = self._capture_window.size()
        self.view.setFixedSize(max(width, 1), max(height, 1))
        QTimer.singleShot(120, lambda: self.page.runJavaScript(
            "JSON.stringify(window.formulaBounds(true))", lambda bounds: self._grab(revision, bounds)))

    def _grab(self, revision, bounds):
        if isinstance(bounds, str):
            try:
                bounds = json.loads(bounds)
            except ValueError:
                bounds = None
        if revision != self._revision or not isinstance(bounds, dict):
            self._finish_capture(revision, None, "公式已变化，请重新导出")
            return
        pixmap = self.view.grab()
        ratio = pixmap.devicePixelRatio()
        rect = QRect(math.floor(bounds["x"] * ratio), math.floor(bounds["y"] * ratio),
                     math.ceil(bounds["width"] * ratio), math.ceil(bounds["height"] * ratio))
        try:
            data = pixmap_png(pixmap.copy(rect))
        except ValueError as exc:
            self._finish_capture(revision, None, str(exc))
        else:
            self._finish_capture(revision, data, None)

    def _finish_capture(self, revision, data, error):
        if hasattr(self, "_previous_size"):
            minimum, maximum = self._previous_size
            self.view.setMinimumSize(minimum)
            self.view.setMaximumSize(maximum)
            del self._previous_size
            window, size = self._capture_window, self._previous_window_size
            QTimer.singleShot(0, lambda: window.resize(size))
        self.page.runJavaScript("window.formulaBounds(false)")
        self._capturing = False
        callback = self._png_callbacks.pop(revision, None)
        if callback:
            callback(data, error)
