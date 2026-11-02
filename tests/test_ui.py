"""Regression checks for user data preservation across asynchronous UI work."""
import os
from io import BytesIO
from pathlib import Path

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
        self.is_busy = False
        self.recognitions = []

    def load(self, directory, device):
        self.loads.append((directory, device))
        self.is_alive = True

    def recognize(self, image, task_id, max_new_tokens=1024):
        if self.is_busy:
            raise RuntimeError("previous task is physically busy")
        self.task_id = task_id
        self.recognitions.append((image, task_id))

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


def image_bytes(color="white"):
    out = BytesIO()
    Image.new("RGB", (32, 20), color).save(out, format="PNG")
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
    assert engine.loads == [(str(Path("C:/模型")), "cuda")]


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


@pytest.mark.parametrize("format_id,left,right", [
    ("plain", "", ""), ("inline_dollars", "$", "$"), ("display_dollars", "$$", "$$"),
    ("inline_parens", r"\(", r"\)"), ("display_brackets", r"\[", r"\]"),
    ("equation", "\\begin{equation}\n", "\n\\end{equation}"),
])
def test_split_copy_menu_sets_persistent_default_without_changing_source(window, qtbot, format_id, left, right):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QToolButton

    widget, store, _, _ = window
    widget.editor.setPlainText(r"\frac{a}{b}")
    button = widget.copy_latex_button
    assert button.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
    action = next(action for action in button.menu().actions() if action.data() == format_id)
    action.trigger()
    assert action.isChecked()
    assert sum(action.isChecked() for action in button.menu().actions()) == 1
    assert store.get_setting("latex_wrapper") == format_id
    widget.show()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=button.rect().center())
    assert QApplication.clipboard().text() == left + r"\frac{a}{b}" + right
    assert widget.editor.toPlainText() == r"\frac{a}{b}"


def test_saved_copy_default_restores_and_mathml_has_direct_button(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from img2tex.storage import Store
    from img2tex.ui.main import MainWindow

    store = Store(tmp_path / "copy.db")
    store.set_setting("latex_wrapper", "display_brackets")
    widget = MainWindow(store=store, engine=EngineDouble(), preview=PreviewDouble(),
                        enable_system_integration=False)
    qtbot.addWidget(widget)
    try:
        widget.editor.setPlainText("x^2")
        widget.copy_latex()
        assert QApplication.clipboard().text() == r"\[x^2\]"
        widget.show()
        qtbot.mouseClick(widget.copy_mathml_button, Qt.MouseButton.LeftButton,
                         pos=widget.copy_mathml_button.rect().center())
        mime = QApplication.clipboard().mimeData()
        assert mime.hasFormat("application/mathml+xml")
        assert "<msup>" in mime.text()
    finally:
        widget.close()
        store.close()


def paste_fixture(widget, data=None):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setImage(QImage.fromData(data if data is not None else image_bytes()))
    widget.paste_image()


def test_paste_image_starts_recognition_without_recognize_click(window):
    widget, _, engine, _ = window
    widget.handle_event({"type": "ready", "device": "cpu"})
    paste_fixture(widget)
    assert len(engine.recognitions) == 1
    assert widget._active_task == engine.task_id


def test_first_paste_loads_model_then_recognizes_latest_image(window):
    widget, _, engine, _ = window
    paste_fixture(widget)
    paste_fixture(widget, image_bytes("blue"))
    assert len(engine.loads) == 1
    assert engine.recognitions == []
    engine.events.append({"type": "ready", "device": "cpu"})
    widget._poll_engine()
    assert len(engine.recognitions) == 1
    assert engine.recognitions[-1][0] == widget.current_image.model_png


def test_new_paste_waits_for_physical_cancellation_and_discards_late_result(window):
    widget, store, engine, _ = start(window)
    old_task = engine.task_id
    engine.is_busy = True
    paste_fixture(widget)
    paste_fixture(widget, image_bytes("blue"))
    assert len(engine.recognitions) == 1
    engine.events.append(result(old_task))
    widget._poll_engine()
    assert not store.list_history()
    assert len(engine.recognitions) == 1
    # ModelProcess may suppress the stale terminal message after clearing busy.
    engine.is_busy = False
    widget._poll_engine()
    assert len(engine.recognitions) == 2
    assert engine.task_id != old_task
    assert engine.recognitions[-1][0] == widget.current_image.model_png


def test_cancel_pending_paste_prevents_automatic_start_after_load(window):
    widget, _, engine, _ = window
    paste_fixture(widget)
    assert len(engine.loads) == 1
    widget.cancel_recognition()
    engine.events.append({"type": "ready", "device": "cpu"})
    widget._poll_engine()
    assert engine.recognitions == []


def test_restoring_history_cancels_pending_paste_without_recognizing_history(window):
    widget, store, engine, _ = window
    record_id = store.add_result(result("history"), image_bytes())
    paste_fixture(widget)
    assert len(engine.loads) == 1
    widget.restore_record(record_id)
    engine.events.append({"type": "ready", "device": "cpu"})
    widget._poll_engine()
    assert engine.recognitions == []
    assert widget.current_record_id == record_id


def test_model_load_failure_stops_auto_paste_retry_loop(window):
    widget, _, engine, _ = window
    paste_fixture(widget)
    engine.events.append({"type": "error", "message": "missing config.json", "device": "cpu"})
    widget._poll_engine()
    widget._poll_engine()
    assert len(engine.loads) == 1
    assert not engine.recognitions
    assert "missing config.json" in widget.statusBar().currentMessage()


def test_clipboard_local_image_file_also_starts_recognition(window, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtWidgets import QApplication

    widget, _, engine, _ = window
    widget.handle_event({"type": "ready", "device": "cpu"})
    image_path = tmp_path / "copied.png"
    image_path.write_bytes(image_bytes())
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image_path))])
    QApplication.clipboard().setMimeData(mime)
    widget.paste_image()
    assert len(engine.recognitions) == 1


def test_paste_during_download_waits_for_completion_before_loading(window):
    from PySide6.QtCore import QProcess

    widget, _, engine, _ = window
    widget._downloading_model = True
    paste_fixture(widget)
    assert not engine.loads
    widget._download_finished(0, QProcess.ExitStatus.NormalExit)
    widget._poll_engine()
    assert len(engine.loads) == 1


def test_failed_download_clears_queued_automatic_recognition(window):
    from PySide6.QtCore import QProcess

    widget, _, engine, _ = window
    widget._downloading_model = True
    paste_fixture(widget)
    widget._download_finished(1, QProcess.ExitStatus.NormalExit)
    widget._poll_engine()
    assert not engine.loads
    assert not widget.cancel_button.isEnabled()


def test_invalid_paste_does_not_submit_an_old_image(window, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtWidgets import QApplication

    widget, _, engine, _ = window
    widget.handle_event({"type": "ready", "device": "cpu"})
    widget.load_image_bytes(image_bytes())
    broken_path = tmp_path / "broken.png"
    broken_path.write_bytes(b"invalid")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(broken_path))])
    QApplication.clipboard().setMimeData(mime)
    widget.paste_image()
    widget._poll_engine()
    assert not engine.recognitions


def test_paste_without_model_directory_leaves_controls_usable(window):
    widget, _, engine, _ = window
    widget.model_path.clear()
    paste_fixture(widget)
    assert not engine.loads
    assert widget.recognize_button.isEnabled()
    assert not widget.cancel_button.isEnabled()
    assert not widget._auto_recognition_pending
    assert "模型目录" in widget.statusBar().currentMessage()


@pytest.mark.parametrize("waiting_for", ["loading", "cancelling"])
def test_edits_while_auto_paste_waits_are_not_overwritten(window, waiting_for):
    widget, store, engine, _ = window
    if waiting_for == "cancelling":
        widget.handle_event({"type": "ready", "device": "cpu"})
        engine.is_busy = True
    paste_fixture(widget)
    widget.editor.setPlainText("my correction")
    if waiting_for == "loading":
        engine.events.append({"type": "ready", "device": "cpu"})
    else:
        engine.is_busy = False
    widget._poll_engine()
    widget.handle_event(result(engine.task_id))
    assert widget.editor.toPlainText() == "my correction"
    assert store.list_history()[0]["latex_edited"] == "my correction"


def test_portable_history_settings_and_model_survive_folder_move(qtbot, tmp_path, monkeypatch):
    from img2tex import paths
    from img2tex.storage import Store
    from img2tex.ui.main import MainWindow

    root = tmp_path / "original portable"
    root.mkdir()
    (root / "portable.flag").touch()
    model = root / "models" / "xiaomi-ocr-0"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf8")
    monkeypatch.setattr(paths, "application_dir", lambda: root)
    store = Store(paths.app_data_dir() / "history.sqlite3")
    record_id = store.add_result(result("saved"), image_bytes())
    store.set_setting("latex_wrapper", "equation")
    widget = MainWindow(store=store, engine=EngineDouble(), preview=PreviewDouble(),
                        enable_system_integration=False)
    qtbot.addWidget(widget)
    widget._save_model_path()
    assert store.get_setting("model_dir") == "models/xiaomi-ocr-0"
    widget.close()
    store.close()
    moved = tmp_path / "移动 版本"
    root.rename(moved)
    monkeypatch.setattr(paths, "application_dir", lambda: moved)
    reopened = Store(paths.app_data_dir() / "history.sqlite3")
    restored = MainWindow(store=reopened, engine=EngineDouble(), preview=PreviewDouble(),
                          enable_system_integration=False)
    qtbot.addWidget(restored)
    try:
        assert restored.model_path.text() == str(moved / "models" / "xiaomi-ocr-0")
        restored.restore_record(record_id)
        assert restored.editor.toPlainText() == "x^2"
        assert restored.latex_copy_group.checkedAction().data() == "equation"
    finally:
        restored.close()
        reopened.close()


def test_relative_model_entry_is_resolved_before_loading(window, tmp_path, monkeypatch):
    from img2tex import paths
    widget, store, engine, _ = window
    monkeypatch.setattr(paths, "application_dir", lambda: tmp_path)
    widget.model_path.setText("models/xiaomi-ocr-0")
    widget.load_model()
    expected = str(tmp_path / "models/xiaomi-ocr-0")
    assert engine.loads[-1][0] == expected
    assert widget.model_path.text() == expected
    assert store.get_setting("model_dir") == "models/xiaomi-ocr-0"
