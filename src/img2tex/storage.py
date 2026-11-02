"""Single persistence boundary for local settings and recognition history."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recognitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                raw_output TEXT NOT NULL,
                latex_normalized TEXT NOT NULL,
                latex_edited TEXT NOT NULL,
                device TEXT NOT NULL,
                elapsed_seconds REAL NOT NULL,
                model_revision TEXT NOT NULL,
                image_png BLOB NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(recognitions)")}
        if "metadata" not in columns:
            self.connection.execute("ALTER TABLE recognitions ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        self.connection.execute("PRAGMA user_version=2")
        self.connection.commit()

    def get_setting(self, key, default=None):
        row = self.connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection:
            self.connection.execute(
                "INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def add_result(self, result: dict, image_png: bytes) -> int:
        latex = result.get("latex_normalized", "")
        if not latex.strip():
            raise ValueError("不能将空识别结果保存为成功历史。")
        metadata = {key: value for key, value in result.items() if key not in {
            "type", "task_id", "raw_output", "latex_normalized", "latex_edited",
        }}
        metadata["image_sha256"] = hashlib.sha256(image_png).hexdigest()
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO recognitions
                (created_at,raw_output,latex_normalized,latex_edited,device,elapsed_seconds,model_revision,image_png,metadata)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (datetime.now(UTC).isoformat(), result["raw_output"], latex, latex,
                 result.get("device", "cpu"), result.get("elapsed_seconds", 0),
                 result.get("model_revision", ""), image_png, json.dumps(metadata, ensure_ascii=False)),
            )
        return cursor.lastrowid

    def update_edited(self, record_id: int, latex: str):
        with self.connection:
            self.connection.execute("UPDATE recognitions SET latex_edited=? WHERE id=?", (latex, record_id))

    def list_history(self, search: str = "", limit: int = 100) -> list[dict]:
        # instr gives literal matching: a user search for '%' is not a SQL wildcard.
        rows = self.connection.execute(
            """SELECT id,created_at,raw_output,latex_normalized,latex_edited,device,
            elapsed_seconds,model_revision FROM recognitions
            WHERE instr(lower(latex_edited),lower(?))>0 ORDER BY id DESC LIMIT ?""",
            (search, max(1, min(int(limit), 1000))),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_record(self, record_id: int) -> dict | None:
        row = self.connection.execute("SELECT * FROM recognitions WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["metadata"] = json.loads(record["metadata"])
        return record

    def delete(self, record_id: int):
        with self.connection:
            self.connection.execute("DELETE FROM recognitions WHERE id=?", (record_id,))

    def close(self):
        self.connection.close()
