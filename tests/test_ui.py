"""Regression checks for user data preservation across asynchronous UI work."""
import os
from io import BytesIO

# Windows' offscreen plugin has no D3D surface. Use Chromium's software path for
# genuine pixel assertions, while leaving the installed desktop app unchanged.
if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-gpu-compositing")

import pytest
from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PreviewDouble(QWidget):
    rendered = Signal()
    error = Signal(str)

    def set_latex(self, text):
        self.text = text


class EngineDouble:
    is_alive = True

    def __init__(self):
        self.events = []
        self.loads = []
        self.stops = 0

    def load(self, directory, device):
        self.loads.append((directory, device))
        self.is_alive = True

    def recognize(self, image, task_id, max_new_tokens=1024):
        self.task_id = task_id

    def cancel(self):
        pass

    def stop(self):
        self.stops += 1
        self.is_alive = False

    def poll(self):
        events, self.events = self.events, []
        return events


@pytest.fixture
def window(qtbot, tmp_path):
    from img2tex.storage import Store
    from img2tex.ui.main import MainWindow

    store = Store(tmp_path / "history.db")
    engine = EngineDouble()
    preview = PreviewDouble()
    widget = MainWindow(store=store, engine=engine, preview=preview, enable_system_integration=False)
    qtbot.addWidget(widget)
    yield widget, store, engine, preview
    widget.close()
    store.close()


def image_bytes():
    out = BytesIO()
    Image.new("RGB", (32, 20), "white").save(out, format="PNG")
    return out.getvalue()


def result(task_id, latex="x^2"):
    return {"type": "result", "task_id": task_id, "raw_output": "$$x^2$$", "latex_normalized": latex,
                "elapsed_seconds": 1.2, "device": "cpu", "model_revision": "test"}


def start(window):
    widget, store, engine, preview = window
    widget.load_image_bytes(image_bytes())
    widget.handle_event({"type": "ready", "device": "cpu"})
    widget.start_recognition()
    return widget, store, engine, preview


def test_device_change_persists_and_stops_old_worker(window):
    widget, store, engine, _ = window
    widget.model_path.setText("C:/模型")
    widget.device_combo.setCurrentIndex(1)
    assert store.get_setting("device") == "cuda"
    assert engine.stops == 1
    assert engine.loads == [("C:/模型", "cuda")]


def test_cancelled_result_cannot_write_history_or_editor(window):
    widget, store, engine, _ = start(window)
    stale = engine.task_id
    widget.cancel_recognition()
    widget.editor.setPlainText("user formula")
    widget.handle_event(result(stale))
    assert widget.editor.toPlainText() == "user formula"
    assert store.list_history() == []


def test_user_edit_during_recognition_is_not_overwritten(window):
    widget, store, engine, _ = start(window)
    widget.editor.setPlainText("a+b")
    widget.handle_event(result(engine.task_id))
    assert widget.editor.toPlainText() == "a+b"
    records = store.list_history()
    assert len(records) == 1
    assert records[0]["latex_edited"] == "a+b"
    assert store.get_record(records[0]["id"])["raw_output"] == "$$x^2$$"


def test_history_restores_image_and_edited_source(window):
    widget, store, _, _ = window
    record_id = store.add_result(result("old"), image_bytes())
    store.update_edited(record_id, r"\frac{a}{b}")
    widget.restore_record(record_id)
    assert widget.editor.toPlainText() == r"\frac{a}{b}"
    assert widget.current_image is not None
    assert not widget.image_label.pixmap().isNull()


def test_render_error_preserves_editor_and_is_visible(window):
    widget, _, _, preview = window
    widget.editor.setPlainText(r"\broken{")
    preview.error.emit("undefined command")
    assert widget.editor.toPlainText() == r"\broken{"
    assert "undefined command" in widget.preview_status.text()


def test_old_result_after_new_image_is_ignored(window):
    widget, store, engine, _ = start(window)
    stale = engine.task_id
    widget.load_image_bytes(image_bytes())
    widget.handle_event(result(stale))
    assert not store.list_history()


def test_editor_change_updates_only_edited_history(window):
    widget, store, engine, _ = start(window)
    widget.handle_event(result(engine.task_id))
    widget.editor.setPlainText("z=3")
    record = store.get_record(widget.current_record_id)
    assert record["latex_edited"] == "z=3"
    assert record["latex_normalized"] == "x^2"
    assert record["raw_output"] == "$$x^2$$"


def test_invalid_new_image_keeps_existing_image_and_source(window):
    widget, _, _, _ = window
    widget.load_image_bytes(image_bytes())
    previous = widget.current_image
    widget.editor.setPlainText("a+b")
    widget.load_image_bytes(b"this is not an image")
    assert widget.current_image == previous
    assert widget.editor.toPlainText() == "a+b"


def test_changed_model_directory_cannot_use_previously_loaded_model(window):
    widget, _, _, _ = window
    widget.handle_event({"type": "ready", "device": "cpu"})
    widget.model_path.setText("C:/another-model")
    widget.model_path.editingFinished.emit()
    widget.load_image_bytes(image_bytes())
    widget.start_recognition()
    assert widget._active_task is None
    assert "加载模型" in widget.statusBar().currentMessage()


def test_directory_change_during_load_invalidates_late_ready(window):
    widget, _, _, _ = window
    widget.model_path.setText("C:/model-a")
    widget.load_model()
    widget.model_path.setText("C:/model-b")
    widget.model_path.editingFinished.emit()
    widget.handle_event({"type": "ready", "device": "cpu"})
    widget.load_image_bytes(image_bytes())
    widget.start_recognition()
    assert widget._active_task is None


def test_local_renderer_renders_fraction_and_reports_invalid_latex(qtbot):
    from img2tex.ui.preview import FormulaPreview

    preview = FormulaPreview()
    qtbot.addWidget(preview)
    preview.resize(650, 280)
    preview.show()
    with qtbot.waitSignal(preview.rendered, timeout=15000):
        preview.set_latex(r"\frac{a}{b}")
    with qtbot.waitSignal(preview.error, timeout=10000):
        preview.set_latex(r"\frac{")


def test_local_renderer_exports_only_formula_png_and_self_contained_svg(qtbot):
    from img2tex.ui.preview import FormulaPreview

    preview = FormulaPreview()
    qtbot.addWidget(preview)
    preview.resize(650, 280)
    preview.show()
    with qtbot.waitSignal(preview.rendered, timeout=15000):
        preview.set_latex(r"\frac{a}{b}")
    png, svg = [], []
    preview.export_png(r"\frac{a}{b}", lambda data, error: png.append((data, error)))
    qtbot.waitUntil(lambda: bool(png), timeout=10000)
    assert png[0][1] is None
    image = Image.open(BytesIO(png[0][0])).convert("RGB")
    assert 20 < image.width < 200
    assert 30 < image.height < 200
    assert any(min(pixel) < 100 for pixel in image.get_flattened_data())
    preview.export_svg(r"\frac{a}{b}", lambda data, error: svg.append((data, error)))
    qtbot.waitUntil(lambda: bool(svg), timeout=15000)
    assert svg[0][1] is None
    assert "<svg" in svg[0][0] and "<path" in svg[0][0]
    assert "<use" not in svg[0][0]


def test_wide_png_export_restores_preview_window_size(qtbot):
    from PySide6.QtCore import QSize

    from img2tex.ui.preview import FormulaPreview

    preview = FormulaPreview()
    qtbot.addWidget(preview)
    preview.resize(650, 280)
    preview.show()
    formula = "+".join(["x"] * 45)
    with qtbot.waitSignal(preview.rendered, timeout=15000):
        preview.set_latex(formula)
    output = []
    preview.export_png(formula, lambda data, error: output.append((data, error)))
    qtbot.waitUntil(lambda: bool(output), timeout=10000)
    assert output[0][1] is None
    assert Image.open(BytesIO(output[0][0])).width > 650
    qtbot.waitUntil(lambda: preview.size() == QSize(650, 280), timeout=2000)


def test_svg_export_rejects_active_links(qtbot):
    from img2tex.ui.preview import FormulaPreview

    preview = FormulaPreview()
    qtbot.addWidget(preview)
    preview.show()
    with qtbot.waitSignal(preview.rendered, timeout=15000):
        preview.set_latex("x")
    output = []
    preview.export_svg(r"\href{https://example.com}{x}", lambda data, error: output.append((data, error)))
    qtbot.waitUntil(lambda: bool(output), timeout=15000)
    assert output[0][0] is None
    assert output[0][1]


def test_png_export_reports_already_visible_latex_error(qtbot):
    from img2tex.ui.preview import FormulaPreview

    preview = FormulaPreview()
    qtbot.addWidget(preview)
    preview.show()
    with qtbot.waitSignal(preview.error, timeout=15000):
        preview.set_latex(r"\frac{")
    output = []
    preview.export_png(r"\frac{", lambda data, error: output.append((data, error)))
    qtbot.waitUntil(lambda: bool(output), timeout=1200)
    assert output[0][0] is None
    assert output[0][1]


def test_downloading_model_invalidates_pending_result_and_stops_loaded_worker(window, monkeypatch):
    widget, store, engine, _ = start(window)
    stale = engine.task_id
    monkeypatch.setattr(widget.download_process, "start", lambda *args: None)
    widget.download_model()
    widget.handle_event(result(stale))
    assert engine.is_alive is False
    assert widget._active_task is None
    assert store.list_history() == []
    assert not widget.load_button.isEnabled()
    assert not widget.device_combo.isEnabled()


def test_ctrl_v_pastes_image_when_latex_editor_has_selection(window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    widget, _, _, _ = window
    widget.show()
    widget.activateWindow()
    qtbot.waitUntil(widget.isActiveWindow, timeout=1200)
    widget.editor.setPlainText("selected source")
    widget.editor.selectAll()
    widget.editor.setFocus()
    QApplication.clipboard().setImage(QImage.fromData(image_bytes()))
    qtbot.keyClick(widget.editor, Qt.Key.Key_V, modifier=Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: widget.current_image is not None, timeout=1200)
    assert (widget.current_image.width, widget.current_image.height) == (32, 20)
    assert QApplication.clipboard().mimeData().hasImage()


def test_ctrl_c_keeps_normal_copy_in_another_window(window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QPlainTextEdit

    widget, _, _, _ = window
    other = QPlainTextEdit()
    qtbot.addWidget(other)
    widget.show()
    other.show()
    other.activateWindow()
    qtbot.waitUntil(other.isActiveWindow, timeout=1200)
    other.setPlainText("other window source")
    other.selectAll()
    other.setFocus()
    qtbot.keyClick(other, Qt.Key.Key_C, modifier=Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "other window source"
    assert widget.current_image is None


def test_old_global_shortcut_settings_are_preserved_but_ignored(qtbot, tmp_path):
    from img2tex.storage import Store
    from img2tex.ui.main import MainWindow

    store = Store(tmp_path / "legacy.db")
    legacy = {"unsupported_old_schema": "unused"}
    store.set_setting("hotkeys", legacy)
    widget = None
    try:
        widget = MainWindow(store=store, engine=EngineDouble(), preview=PreviewDouble(),
                            enable_system_integration=False)
        qtbot.addWidget(widget)
        assert "Ctrl+V" in widget.image_hint.text()
        assert store.get_setting("hotkeys") == legacy
    finally:
        if widget is not None:
            widget.close()
        store.close()


def test_copy_latex_button_retains_source_copy_flow(window):
    from PySide6.QtWidgets import QApplication

    widget, _, _, _ = window
    widget.editor.setPlainText(r"\frac{a}{b}")
    widget.copy_latex()
    assert QApplication.clipboard().text() == r"\frac{a}{b}"


def test_ctrl_c_copies_selected_latex_inside_app(window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    widget, _, _, _ = window
    widget.show()
    widget.activateWindow()
    qtbot.waitUntil(widget.isActiveWindow, timeout=1200)
    widget.editor.setPlainText(r"\frac{a}{b}")
    widget.editor.selectAll()
    widget.editor.setFocus()
    QApplication.clipboard().setText("previous clipboard")
    qtbot.keyClick(widget.editor, Qt.Key.Key_C, modifier=Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == r"\frac{a}{b}"
    assert widget.current_image is None


def test_ctrl_v_keeps_normal_text_paste_in_latex_editor(window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    widget, _, _, _ = window
    widget.show()
    widget.activateWindow()
    qtbot.waitUntil(widget.isActiveWindow, timeout=1200)
    widget.editor.setPlainText("replace me")
    widget.editor.selectAll()
    widget.editor.setFocus()
    QApplication.clipboard().setText(r"\sqrt{x}")
    qtbot.keyClick(widget.editor, Qt.Key.Key_V, modifier=Qt.KeyboardModifier.ControlModifier)
    assert widget.editor.toPlainText() == r"\sqrt{x}"
    assert widget.current_image is None
